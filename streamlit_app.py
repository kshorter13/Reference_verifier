import streamlit as st
import re
import requests
import time
import json
from typing import List, Dict, Optional
from dataclasses import dataclass
from urllib.parse import quote, urlencode
import xml.etree.ElementTree as ET

@dataclass
class Reference:
    text: str
    line_number: int
    authors: List[str] = None
    title: str = None
    year: str = None
    journal: str = None
    volume: str = None
    pages: str = None
    doi: str = None

class ReferenceParser:
    def __init__(self):
        # More flexible patterns focusing on structure rather than exact format
        self.apa_patterns = {
            'has_year_in_parentheses': r'\((\d{4}[a-z]?)\)',
            'has_title_after_year': r'\)\.\s*([^.]+)\.',
            'has_journal_info': r'([A-Za-z][^,\d]*[A-Za-z]),',
            'has_volume_pages': r'(\d+)(?:\((\d+)\))?,?\s*(\d+(?:-\d+)?)',
            'doi_pattern': r'https?://doi\.org/([^\s]+)',
            'author_pattern': r'^([^()]+?)(?:\s*\(\d{4}\))',
            'basic_structure': r'^.+\(\d{4}\)\..*\..+,.*\d+'
        }
        
        self.vancouver_patterns = {
            'starts_with_number': r'^(\d+)\.',
            'has_title_section': r'^\d+\.\s*[^.]+\.\s*([^.]+)\.',
            'has_journal_year': r'([A-Za-z][^.;]+)[\s.]*(\d{4})',
            'has_volume_pages': r';(\d+)(?:\((\d+)\))?:([^.]+)',
            'author_pattern': r'^\d+\.\s*([^.]+)\.',
            'basic_structure': r'^\d+\.\s*.+\.\s*.+\.\s*.+\d{4}'
        }

    def identify_references(self, text: str) -> List[Reference]:
        """Split text into individual references"""
        lines = text.strip().split('\n')
        references = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if line and len(line) > 30:  # Slightly longer minimum for complete references
                ref = Reference(text=line, line_number=i+1)
                references.append(ref)
        
        return references

    def check_structural_format(self, ref_text: str, format_type: str) -> Dict:
        """Check if reference has correct structural layout (lenient)"""
        result = {
            'structure_valid': False,
            'structure_issues': [],
            'extracted_elements': {}
        }
        
        if format_type == "APA":
            # Check basic APA structure
            has_year = bool(re.search(self.apa_patterns['has_year_in_parentheses'], ref_text))
            has_title = bool(re.search(self.apa_patterns['has_title_after_year'], ref_text))
            has_journal = bool(re.search(self.apa_patterns['has_journal_info'], ref_text))
            has_numbers = bool(re.search(self.apa_patterns['has_volume_pages'], ref_text))
            
            if not has_year:
                result['structure_issues'].append("Missing year in parentheses")
            if not has_title:
                result['structure_issues'].append("Missing title after year")
            if not has_journal:
                result['structure_issues'].append("Missing journal information")
            if not has_numbers:
                result['structure_issues'].append("Missing volume/page numbers")
            
            # Structure is valid if it has the basic elements (even if details might be wrong)
            result['structure_valid'] = has_year and has_title and (has_journal or has_numbers)
            
        elif format_type == "Vancouver":
            # Check basic Vancouver structure
            starts_with_number = bool(re.search(self.vancouver_patterns['starts_with_number'], ref_text))
            has_title = bool(re.search(self.vancouver_patterns['has_title_section'], ref_text))
            has_journal_year = bool(re.search(self.vancouver_patterns['has_journal_year'], ref_text))
            
            if not starts_with_number:
                result['structure_issues'].append("Should start with number and period")
            if not has_title:
                result['structure_issues'].append("Missing title section")
            if not has_journal_year:
                result['structure_issues'].append("Missing journal and year information")
            
            result['structure_valid'] = starts_with_number and has_title and has_journal_year
        
        return result

    def extract_reference_elements(self, ref_text: str, format_type: str) -> Dict:
        """Extract key elements from reference (best effort)"""
        elements = {
            'authors': None,
            'year': None,
            'title': None,
            'journal': None,
            'doi': None,
            'extraction_confidence': 'high'
        }
        
        # Extract DOI (works for both formats)
        doi_match = re.search(r'https?://doi\.org/([^\s]+)', ref_text)
        if doi_match:
            elements['doi'] = doi_match.group(1)
        
        if format_type == "APA":
            # Extract year (high confidence)
            year_match = re.search(self.apa_patterns['has_year_in_parentheses'], ref_text)
            if year_match:
                elements['year'] = year_match.group(1)
            
            # Extract title (high confidence)
            title_match = re.search(self.apa_patterns['has_title_after_year'], ref_text)
            if title_match:
                elements['title'] = title_match.group(1).strip()
            
            # Extract authors (medium confidence - before year)
            author_match = re.search(self.apa_patterns['author_pattern'], ref_text)
            if author_match:
                elements['authors'] = author_match.group(1).strip()
            
            # Extract journal (medium confidence)
            journal_match = re.search(self.apa_patterns['has_journal_info'], ref_text)
            if journal_match:
                elements['journal'] = journal_match.group(1).strip()
            
        elif format_type == "Vancouver":
            # Extract year
            year_match = re.search(r'(\d{4})', ref_text)
            if year_match:
                elements['year'] = year_match.group(1)
            
            # Extract title
            title_match = re.search(self.vancouver_patterns['has_title_section'], ref_text)
            if title_match:
                elements['title'] = title_match.group(1).strip()
            
            # Extract authors
            author_match = re.search(self.vancouver_patterns['author_pattern'], ref_text)
            if author_match:
                elements['authors'] = author_match.group(1).strip()
            
            # Extract journal
            journal_match = re.search(r'([A-Za-z][^.;\d]*[A-Za-z])[\s.]*\d{4}', ref_text)
            if journal_match:
                elements['journal'] = journal_match.group(1).strip()
        
        # Assess extraction confidence
        extracted_count = sum(1 for v in [elements['authors'], elements['year'], elements['title'], elements['journal']] if v)
        if extracted_count < 2:
            elements['extraction_confidence'] = 'low'
        elif extracted_count < 3:
            elements['extraction_confidence'] = 'medium'
        
        return elements

class DatabaseSearcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def check_doi_and_verify_content(self, doi: str, expected_title: str) -> Dict:
        """Check if DOI exists and verify title matches the actual publication"""
        if not doi:
            return {'valid': False, 'reason': 'No DOI provided'}
        
        try:
            # First check if DOI resolves
            url = f"https://doi.org/{doi}"
            response = self.session.head(url, timeout=10, allow_redirects=True)
            
            if response.status_code != 200:
                return {
                    'valid': False, 
                    'reason': f'DOI does not resolve (status: {response.status_code})',
                    'doi_url': url
                }
            
            # Get DOI metadata from Crossref API
            crossref_url = f"https://api.crossref.org/works/{doi}"
            metadata_response = self.session.get(crossref_url, timeout=15)
            
            if metadata_response.status_code != 200:
                return {
                    'valid': False,
                    'reason': 'Could not retrieve DOI metadata',
                    'doi_url': url,
                    'resolved_url': response.url
                }
            
            metadata = metadata_response.json()
            
            if 'message' not in metadata:
                return {
                    'valid': False,
                    'reason': 'Invalid DOI metadata format',
                    'doi_url': url
                }
            
            work = metadata['message']
            
            # Extract actual title from DOI metadata
            actual_title = None
            if 'title' in work and work['title']:
                actual_title = work['title'][0] if isinstance(work['title'], list) else str(work['title'])
            
            if not actual_title:
                return {
                    'valid': False,
                    'reason': 'No title found in DOI metadata',
                    'doi_url': url
                }
            
            # Compare titles
            if expected_title:
                title_similarity = self._calculate_title_similarity(expected_title.lower(), actual_title.lower())
                
                if title_similarity < 0.7:  # Strict similarity threshold
                    return {
                        'valid': False,
                        'reason': 'Title mismatch with DOI content',
                        'expected_title': expected_title,
                        'actual_title': actual_title,
                        'similarity_score': title_similarity,
                        'doi_url': url
                    }
            
            # Extract additional metadata
            authors = []
            if 'author' in work:
                for author in work['author']:
                    if 'given' in author and 'family' in author:
                        authors.append(f"{author['given']} {author['family']}")
                    elif 'family' in author:
                        authors.append(author['family'])
            
            journal = None
            if 'container-title' in work and work['container-title']:
                journal = work['container-title'][0] if isinstance(work['container-title'], list) else str(work['container-title'])
            
            published_year = None
            if 'published-print' in work and 'date-parts' in work['published-print']:
                published_year = str(work['published-print']['date-parts'][0][0])
            elif 'published-online' in work and 'date-parts' in work['published-online']:
                published_year = str(work['published-online']['date-parts'][0][0])
            
            return {
                'valid': True,
                'actual_title': actual_title,
                'actual_authors': authors,
                'actual_journal': journal,
                'actual_year': published_year,
                'title_similarity': title_similarity if expected_title else None,
                'doi_url': url,
                'resolved_url': response.url,
                'crossref_url': crossref_url
            }
            
        except Exception as e:
            return {
                'valid': False,
                'reason': f'DOI verification error: {str(e)}',
                'doi_url': f"https://doi.org/{doi}" if doi else None
            }

    def search_by_exact_title(self, title: str) -> Dict:
        """Search for exact title matches across databases with source links"""
        if not title or len(title.strip()) < 10:
            return {'found': False, 'reason': 'Title too short for reliable search'}
        
        # Search Crossref for exact title matches
        try:
            # Clean title for search
            title_clean = re.sub(r'[^\w\s]', ' ', title)
            title_words = [word for word in title_clean.split() if len(word) > 2]
            
            if len(title_words) < 3:
                return {'found': False, 'reason': 'Insufficient title words for search'}
            
            # Use title as main query
            url = "https://api.crossref.org/works"
            params = {
                'query.title': title_clean,
                'rows': 10,
                'select': 'title,author,published-print,published-online,container-title,DOI,URL'
            }
            
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if 'message' in data and 'items' in data['message']:
                items = data['message']['items']
                
                # Look for very close title matches
                for item in items:
                    if 'title' in item and item['title']:
                        item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
                        similarity = self._calculate_title_similarity(title.lower(), item_title.lower())
                        
                        if similarity > 0.8:  # High similarity threshold
                            # Get the best available source link
                            source_url = None
                            if 'DOI' in item:
                                source_url = f"https://doi.org/{item['DOI']}"
                            elif 'URL' in item:
                                source_url = item['URL']
                            
                            return {
                                'found': True,
                                'similarity': similarity,
                                'matched_title': item_title,
                                'doi': item.get('DOI', 'Not available'),
                                'source_url': source_url,
                                'crossref_url': f"https://api.crossref.org/works/{item['DOI']}" if 'DOI' in item else None
                            }
                
                return {'found': False, 'reason': f'No close title matches found ({len(items)} results checked)'}
            
            return {'found': False, 'reason': 'No results from title search'}
            
        except Exception as e:
            return {'found': False, 'reason': f'Title search error: {str(e)}'}

    def search_comprehensive(self, authors: str, title: str, year: str, journal: str) -> Dict:
        """Comprehensive search using multiple elements with source links"""
        try:
            # Build multi-part query
            query_parts = []
            
            if title:
                # Use significant words from title
                title_words = re.findall(r'\b[a-zA-Z]{4,}\b', title)[:4]
                query_parts.extend(title_words)
            
            if authors:
                # Get main author surnames
                author_parts = re.split(r'[,&]', authors)[:2]
                for author in author_parts:
                    author_clean = re.sub(r'[^\w\s]', '', author).strip()
                    if author_clean:
                        surname = author_clean.split()[-1]
                        if len(surname) > 2:
                            query_parts.append(surname)
            
            if not query_parts:
                return {'found': False, 'reason': 'Insufficient search terms'}
            
            query = " ".join(query_parts)
            
            url = "https://api.crossref.org/works"
            params = {
                'query': query,
                'rows': 15,
                'select': 'title,author,published-print,published-online,container-title,DOI,URL'
            }
            
            if year:
                params['filter'] = f'from-pub-date:{year},until-pub-date:{year}'
            
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if 'message' in data and 'items' in data['message']:
                items = data['message']['items']
                best_match = None
                best_score = 0
                
                for item in items:
                    score = self._calculate_comprehensive_match_score(item, title, authors, year, journal)
                    if score > best_score:
                        best_score = score
                        best_match = item
                
                if best_score > 0.5:  # Raised threshold for better matches
                    # Get the best available source link
                    source_url = None
                    if 'DOI' in best_match:
                        source_url = f"https://doi.org/{best_match['DOI']}"
                    elif 'URL' in best_match:
                        source_url = best_match['URL']
                    
                    return {
                        'found': True,
                        'match_score': best_score,
                        'matched_title': best_match.get('title', ['Unknown'])[0] if best_match.get('title') else 'Unknown',
                        'matched_doi': best_match.get('DOI'),
                        'source_url': source_url,
                        'crossref_url': f"https://api.crossref.org/works/{best_match['DOI']}" if best_match.get('DOI') else None,
                        'total_results': len(items)
                    }
                else:
                    return {
                        'found': False,
                        'reason': f'No good matches found (best score: {best_score:.2f})',
                        'total_results': len(items)
                    }
            
            return {'found': False, 'reason': 'No search results'}
            
        except Exception as e:
            return {'found': False, 'reason': f'Search error: {str(e)}'}

    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles"""
        words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title1.lower()))
        words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

    def _calculate_comprehensive_match_score(self, item: Dict, target_title: str, target_authors: str, target_year: str, target_journal: str) -> float:
        """Calculate comprehensive match score"""
        score = 0.0
        
        # Title matching (50% weight)
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.5
        
        # Author matching (25% weight)
        if 'author' in item and item['author'] and target_authors:
            item_authors = []
            for author in item['author']:
                if 'family' in author:
                    item_authors.append(author['family'].lower())
            
            target_surnames = []
            for author in re.split(r'[,&]', target_authors):
                author_clean = re.sub(r'[^\w\s]', '', author).strip()
                if author_clean:
                    surname = author_clean.split()[-1].lower()
                    if len(surname) > 2:
                        target_surnames.append(surname)
            
            if item_authors and target_surnames:
                common_authors = set(item_authors).intersection(set(target_surnames))
                author_score = len(common_authors) / max(len(target_surnames), 1)
                score += author_score * 0.25
        
        # Year matching (15% weight)
        if target_year:
            item_year = None
            if 'published-print' in item and 'date-parts' in item['published-print']:
                item_year = str(item['published-print']['date-parts'][0][0])
            elif 'published-online' in item and 'date-parts' in item['published-online']:
                item_year = str(item['published-online']['date-parts'][0][0])
            
            if item_year and item_year == target_year:
                score += 0.15
        
        # Journal matching (10% weight)
        if 'container-title' in item and item['container-title'] and target_journal:
            item_journal = item['container-title'][0] if isinstance(item['container-title'], list) else str(item['container-title'])
            journal_sim = self._calculate_title_similarity(target_journal, item_journal)
            score += journal_sim * 0.1
        
        return score

class ReferenceVerifier:
    def __init__(self):
        self.parser = ReferenceParser()
        self.searcher = DatabaseSearcher()

    def verify_references(self, text: str, format_type: str, progress_callback=None) -> List[Dict]:
        """Three-level verification: Structure → Content → Existence"""
        references = self.parser.identify_references(text)
        results = []
        
        total_refs = len(references)
        
        for i, ref in enumerate(references):
            if progress_callback:
                progress_callback(i + 1, total_refs, f"Verifying reference {i + 1}")
            
            result = {
                'reference': ref.text,
                'line_number': ref.line_number,
                'structure_status': 'unknown',
                'content_status': 'unknown',
                'existence_status': 'unknown',
                'overall_status': 'unknown',
                'structure_check': {},
                'content_check': {},
                'existence_check': {},
                'extracted_elements': {}
            }
            
            # LEVEL 1: Structure Check
            structure_check = self.parser.check_structural_format(ref.text, format_type)
            result['structure_check'] = structure_check
            
            if structure_check['structure_valid']:
                result['structure_status'] = 'valid'
                
                # LEVEL 2: Content Extraction
                elements = self.parser.extract_reference_elements(ref.text, format_type)
                result['extracted_elements'] = elements
                
                if elements['extraction_confidence'] in ['medium', 'high']:
                    result['content_status'] = 'extracted'
                    
                    # LEVEL 3: Existence Verification
                    existence_results = self._verify_existence(elements)
                    result['existence_check'] = existence_results
                    
                    if existence_results['any_found']:
                        result['existence_status'] = 'found'
                        result['overall_status'] = 'valid'
                    elif existence_results['doi_invalid'] or existence_results['title_not_found']:
                        result['existence_status'] = 'not_found'
                        result['overall_status'] = 'likely_fake'
                    else:
                        result['existence_status'] = 'uncertain'
                        result['overall_status'] = 'content_warning'
                else:
                    result['content_status'] = 'extraction_failed'
                    result['overall_status'] = 'content_error'
            else:
                result['structure_status'] = 'invalid'
                result['overall_status'] = 'structure_error'
            
            results.append(result)
            time.sleep(0.3)  # Rate limiting
        
        return results

    def _verify_existence(self, elements: Dict) -> Dict:
        """Verify if reference elements can be found in databases with enhanced DOI validation"""
        results = {
            'any_found': False,
            'doi_valid': False,
            'doi_invalid': False,
            'title_found': False,
            'title_not_found': False,
            'comprehensive_found': False,
            'search_details': {},
            'verification_sources': []  # Track all sources that validated this reference
        }
        
        # Enhanced DOI check with content verification
        if elements.get('doi'):
            doi_result = self.searcher.check_doi_and_verify_content(
                elements['doi'], 
                elements.get('title', '')
            )
            results['search_details']['doi'] = doi_result
            
            if doi_result['valid']:
                results['doi_valid'] = True
                results['any_found'] = True
                # Add DOI as verification source
                if doi_result.get('doi_url'):
                    results['verification_sources'].append({
                        'type': 'DOI',
                        'url': doi_result['doi_url'],
                        'description': 'DOI verified with title match'
                    })
            else:
                results['doi_invalid'] = True
        
        # Check by exact title
        if elements.get('title'):
            title_result = self.searcher.search_by_exact_title(elements['title'])
            results['search_details']['title_search'] = title_result
            
            if title_result['found']:
                results['title_found'] = True
                results['any_found'] = True
                # Add title search as verification source
                if title_result.get('source_url'):
                    results['verification_sources'].append({
                        'type': 'Title Match',
                        'url': title_result['source_url'],
                        'description': f"Exact title match (similarity: {title_result.get('similarity', 0):.1%})"
                    })
            else:
                results['title_not_found'] = True
        
        # Comprehensive search
        comprehensive_result = self.searcher.search_comprehensive(
            elements.get('authors', ''),
            elements.get('title', ''),
            elements.get('year', ''),
            elements.get('journal', '')
        )
        results['search_details']['comprehensive'] = comprehensive_result
        
        if comprehensive_result['found']:
            results['comprehensive_found'] = True
            results['any_found'] = True
            # Add comprehensive search as verification source
            if comprehensive_result.get('source_url'):
                results['verification_sources'].append({
                    'type': 'Comprehensive Search',
                    'url': comprehensive_result['source_url'],
                    'description': f"Multi-element match (confidence: {comprehensive_result.get('match_score', 0):.1%})"
                })
        
        return results

def main():
    st.set_page_config(
        page_title="Academic Reference Verifier",
        page_icon="📚",
        layout="wide"
    )
    
    st.title("📚 Academic Reference Verifier")
    st.markdown("**Three-level verification**: Structure → Content → Existence")
    
    # Sidebar for format selection
    st.sidebar.header("Settings")
    format_type = st.sidebar.selectbox(
        "Select Reference Format",
        ["APA", "Vancouver"]
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**🔍 Verification Levels:**")
    st.sidebar.markdown("1. **Structure**: Layout and format")
    st.sidebar.markdown("2. **Content**: Element extraction")
    st.sidebar.markdown("3. **Existence**: Database verification")
    
    # Main interface
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("Input References")
        reference_text = st.text_area(
            "Paste your reference list here:",
            height=400,
            placeholder="Paste your references here, one per line...\n\nExample (APA):\nSmith, J. A. (2020). Climate change impacts. Nature, 10(5), 423-431.\n\nFake Example:\nFake, A. (2023). Non-existent study. Made Up Journal, 15(3), 123-145."
        )
        
        verify_button = st.button("🔍 Verify References", type="primary", use_container_width=True)
        
        if st.button("📝 Test with Mixed Data"):
            sample_data = """Smith, J. A. (2020). Climate change impacts on marine ecosystems. Nature Climate Change, 10(5), 423-431. https://doi.org/10.1038/s41558-020-0789-5
Buchheit, M., & Mendez-Villanueva, A. (2014). Performance and physiological responses to an agility test in professional soccer players. Journal of Sports Sciences, 32(8), 675-682. https://doi.org/10.1080/02640414.2013.876411
Brown, M. (2019). Machine learning applications in healthcare. IEEE Transactions on Biomedical Engineering, 66(4), 1123-1132.
Invalid format reference without proper structure"""
            st.session_state.sample_text = sample_data
    
    with col2:
        st.header("Verification Results")
        
        # Use sample data if button was clicked
        if 'sample_text' in st.session_state:
            reference_text = st.session_state.sample_text
            del st.session_state.sample_text
            verify_button = True
        
        if verify_button and reference_text.strip():
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            def update_progress(current, total, message):
                progress = current / total
                progress_bar.progress(progress)
                status_text.text(f"{message} ({current}/{total})")
            
            with st.spinner("Initializing three-level verification..."):
                verifier = ReferenceVerifier()
                results = verifier.verify_references(reference_text, format_type, update_progress)
            
            progress_bar.empty()
            status_text.empty()
            
            if results:
                # Summary statistics
                total_refs = len(results)
                valid_refs = sum(1 for r in results if r['overall_status'] == 'valid')
                structure_errors = sum(1 for r in results if r['overall_status'] == 'structure_error')
                content_warnings = sum(1 for r in results if r['overall_status'] == 'content_warning')
                content_errors = sum(1 for r in results if r['overall_status'] == 'content_error')
                likely_fake = sum(1 for r in results if r['overall_status'] == 'likely_fake')
                
                col_a, col_b, col_c, col_d, col_e, col_f = st.columns(6)
                with col_a:
                    st.metric("Total", total_refs)
                with col_b:
                    st.metric("✅ Valid", valid_refs)
                with col_c:
                    st.metric("🔧 Structure", structure_errors)
                with col_d:
                    st.metric("⚠️ Content", content_warnings + content_errors)
                with col_e:
                    st.metric("🚨 Likely Fake", likely_fake)
                with col_f:
                    accuracy = round((valid_refs / total_refs * 100) if total_refs > 0 else 0, 1)
                    st.metric("Accuracy", f"{accuracy}%")
                
                st.markdown("---")
                
                # Display results with new categorization
                for i, result in enumerate(results):
                    ref_text = result['reference']
                    status = result['overall_status']
                    
                    if status == 'valid':
                        st.success(f"✅ **Reference {result['line_number']}**: Verified and Valid")
                        st.write(ref_text)
                        
                        # Show verification sources with clickable links
                        existence = result['existence_check']
                        verification_sources = existence.get('verification_sources', [])
                        
                        if verification_sources:
                            st.write("**✅ Verified via:**")
                            for source in verification_sources:
                                source_type = source['type']
                                source_url = source['url']
                                description = source['description']
                                
                                if source_url:
                                    st.markdown(f"• **{source_type}**: [{description}]({source_url})")
                                else:
                                    st.write(f"• **{source_type}**: {description}")
                        
                        # Show DOI content verification details if available
                        doi_details = existence.get('search_details', {}).get('doi')
                        if doi_details and doi_details.get('valid'):
                            with st.expander("📋 DOI Verification Details"):
                                st.write(f"**Actual Title:** {doi_details.get('actual_title', 'N/A')}")
                                if doi_details.get('title_similarity'):
                                    st.write(f"**Title Match Confidence:** {doi_details['title_similarity']:.1%}")
                                st.write(f"**Authors:** {', '.join(doi_details.get('actual_authors', []))}")
                                st.write(f"**Journal:** {doi_details.get('actual_journal', 'N/A')}")
                                st.write(f"**Year:** {doi_details.get('actual_year', 'N/A')}")
                                if doi_details.get('crossref_url'):
                                    st.markdown(f"**Crossref API:** [{doi_details['crossref_url']}]({doi_details['crossref_url']})")
                    
                    elif status == 'structure_error':
                        st.error(f"🔧 **Reference {result['line_number']}**: Structural Format Issues")
                        st.write(ref_text)
                        
                        issues = result['structure_check'].get('structure_issues', [])
                        if issues:
                            st.write("**Structural problems:**")
                            for issue in issues:
                                st.write(f"• {issue}")
                    
                    elif status == 'content_error':
                        st.warning(f"⚠️ **Reference {result['line_number']}**: Content Extraction Issues")
                        st.write(ref_text)
                        st.write("**Issue:** Could not extract enough elements to verify this reference.")
                    
                    elif status == 'content_warning':
                        st.warning(f"⚠️ **Reference {result['line_number']}**: Possible Content Issues")
                        st.write(ref_text)
                        st.write("**Issue:** Reference structure is correct, but some content details may be incorrect (e.g., wrong authors, journal name, etc.)")
                        
                        # Show what we found/didn't find
                        existence = result['existence_check']
                        search_details = existence.get('search_details', {})
                        
                        if 'comprehensive' in search_details:
                            comp_result = search_details['comprehensive']
                            if 'match_score' in comp_result:
                                st.write(f"**Match confidence:** {comp_result['match_score']:.1%} (below threshold)")
                    
                    elif status == 'likely_fake':
                        st.error(f"🚨 **Reference {result['line_number']}**: Likely Fake Reference")
                        st.write(ref_text)
                        
                        # Show detailed evidence with enhanced DOI analysis
                        existence = result['existence_check']
                        evidence = []
                        
                        # Enhanced DOI analysis
                        doi_details = existence.get('search_details', {}).get('doi')
                        if doi_details and not doi_details.get('valid'):
                            reason = doi_details.get('reason', 'Unknown error')
                            if 'Title mismatch' in reason:
                                evidence.append(f"DOI exists but title doesn't match (Expected: '{doi_details.get('expected_title', 'N/A')}', Actual: '{doi_details.get('actual_title', 'N/A')}')")
                            elif 'does not resolve' in reason:
                                evidence.append("DOI does not exist or is inaccessible")
                            else:
                                evidence.append(f"DOI validation failed: {reason}")
                        
                        if existence.get('title_not_found'):
                            evidence.append("Title not found in academic databases")
                        
                        search_details = existence.get('search_details', {})
                        if 'comprehensive' in search_details:
                            comp_result = search_details['comprehensive']
                            if not comp_result.get('found'):
                                evidence.append(f"No matching publications found ({comp_result.get('reason', 'unknown reason')})")
                        
                        if evidence:
                            st.write("**🚨 Evidence this reference is fake:**")
                            for item in evidence:
                                st.write(f"• {item}")
                        
                        # Show what DOI should contain if there was a title mismatch
                        if doi_details and 'actual_title' in doi_details:
                            with st.expander("🔍 What the DOI Actually Contains"):
                                st.write(f"**Actual Title:** {doi_details['actual_title']}")
                                st.write(f"**Actual Authors:** {', '.join(doi_details.get('actual_authors', []))}")
                                st.write(f"**Actual Journal:** {doi_details.get('actual_journal', 'N/A')}")
                                st.write(f"**Actual Year:** {doi_details.get('actual_year', 'N/A')}")
                                if doi_details.get('doi_url'):
                                    st.markdown(f"**Check DOI:** [{doi_details['doi_url']}]({doi_details['doi_url']})")
                        
                        st.write("**⚠️ This reference appears to be fabricated or contains significant errors.**")
                    
                    if i < len(results) - 1:
                        st.markdown("---")
            else:
                st.warning("No references found. Please check your input format.")
        
        elif verify_button:
            st.warning("Please enter some references to verify.")
    
    # Help section
    with st.expander("ℹ️ How the Three-Level Verification Works"):
        st.markdown("""
        **Level 1: Structure Check** 🔧
        - Verifies basic reference format (APA/Vancouver layout)
        - Checks for required elements (year, title, journal, etc.)
        - **Lenient** - focuses on structure, not exact formatting details
        
        **Level 2: Content Extraction** ⚠️
        - Extracts key elements (authors, title, year, journal, DOI)
        - Assesses extraction confidence
        - Identifies potential content issues
        
        **Level 3: Existence Verification** 🚨
        - DOI validation against DOI.org
        - Exact title searches in academic databases
        - Comprehensive multi-element searches
        - **Identifies likely fake references**
        
        **Result Categories:**
        - ✅ **Valid**: Passes all levels, reference verified in databases
        - 🔧 **Structure Issues**: Layout/format problems need fixing
        - ⚠️ **Content Issues**: Structure OK, but content may have errors (wrong authors, journal, etc.)
        - 🚨 **Likely Fake**: Well-formatted but doesn't exist in any database
        
        **Key Improvement:**
        This system now properly distinguishes between formatting issues and fake content!
        """)
    
    with st.expander("📊 Understanding Your Results"):
        st.markdown("""
        **What each status means:**
        
        🔧 **Structure Issues**: Your reference needs formatting fixes
        - Missing required elements (year, title, journal)
        - Incorrect punctuation or layout
        - **Action**: Fix the format according to your style guide
        
        ⚠️ **Content Issues**: Format is correct, but details might be wrong
        - Author names might be incorrect
        - Journal name might be wrong
        - Volume/issue numbers might be off
        - **Action**: Double-check all details against the original source
        
        🚨 **Likely Fake**: Reference appears to be fabricated
        - Well-formatted but doesn't exist in databases
        - Invalid DOI or title not found anywhere
        - No matching publications in academic databases
        - **Action**: Remove or replace with a real reference
        
        **Pro Tip**: A reference can look perfectly formatted but still be fake!
        """)

if __name__ == "__main__":
    main()

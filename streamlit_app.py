import streamlit as st
import re
import requests
import time
import json
from typing import List, Dict, Optional
from dataclasses import dataclass

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

class CorrectedAuthenticityParser:
    def __init__(self):
        # Fixed and improved extraction patterns
        self.flexible_patterns = {
            # Extract any year in parentheses
            'any_year': r'\((\d{4}[a-z]?)\)',
            
            # Extract DOI from anywhere in text
            'doi_pattern': r'https?://doi\.org/([^\s]+)',
            
            # Extract ISBN from anywhere
            'isbn_pattern': r'ISBN:?\s*([\d-X]+)',
            
            # Extract any URL
            'url_pattern': r'(https?://[^\s]+)',
            
            # FIXED: Better title extraction - stops at punctuation before journal
            'flexible_title': r'\)\.\s*([^.!?]+?)[\.\!?\s]*(?:[A-Z][^,\d]*[A-Za-z]\s*,|\s*$)',
            
            # FIXED: More robust journal extraction with context
            'journal_after_title': r'([A-Z][A-Za-z\s&]*(?:Journal|Review|Quarterly|Annual|Science|Research|Studies|Proceedings)[A-Za-z\s]*)\s*,\s*\d+',
            
            # Alternative journal pattern for non-standard names
            'journal_before_volume': r'([A-Z][^,\d]*[A-Za-z])\s*,\s*\d+',
            
            # FIXED: Volume and pages - search in specific context
            'volume_issue_pages': r'(\d+)\s*(?:\((\d+)\))?\s*,\s*(\d+(?:-\d+)?)',
            
            # Publisher patterns (for books)
            'publisher_keywords': r'((?:Press|Publishers?|Publications?|Books?|Academic|University|Ltd|Inc|Corp|Kluwer|Elsevier|MIT Press|Human Kinetics)[^.]*)',
            
            # Website access patterns
            'access_date': r'(?:Retrieved|Accessed)\s+([^,\n]+)',
        }
        
        # Strict APA format checking patterns
        self.apa_format_patterns = {
            'comma_before_year': r'[^.],\s*\((\d{4}[a-z]?)\)',
            'proper_year_format': r'\.\s*\((\d{4}[a-z]?)\)\.',
            'author_format': r'^([^.]+)\.\s*\(\d{4}',
            'title_journal_structure': r'\)\.\s*([^.]+?)\.\s*([A-Z][^,]+),',
        }

    def detect_reference_type(self, ref_text: str) -> str:
        """Improved reference type detection with DOI priority"""
        ref_lower = ref_text.lower()

        # HIGHEST priority: DOI = journal (very reliable)
        if re.search(self.flexible_patterns['doi_pattern'], ref_text):
            return 'journal'
        
        # HIGH priority: ISBN = book (very reliable)
        if re.search(self.flexible_patterns['isbn_pattern'], ref_text):
            return 'book'
        
        # HIGH priority: URL + access date = website
        if (re.search(self.flexible_patterns['url_pattern'], ref_text) and 
            re.search(self.flexible_patterns['access_date'], ref_text)):
            return 'website'
        
        # Content-based scoring for ambiguous cases
        journal_score = 0
        book_score = 0
        website_score = 0
        
        # Journal indicators
        if re.search(r'journal|review|proceedings|quarterly|annual|science', ref_lower):
            journal_score += 3
        if re.search(r'\d+\s*\(\d+\)\s*,\s*\d+', ref_text):  # volume(issue), pages
            journal_score += 3
        if re.search(r'vol\.|volume', ref_lower):
            journal_score += 2
            
        # Book indicators
        if re.search(self.flexible_patterns['publisher_keywords'], ref_text, re.IGNORECASE):
            book_score += 3
        if re.search(r'edition|ed\.|handbook|manual|textbook', ref_lower):
            book_score += 3
        if re.search(r'isbn|pp\.|pages', ref_lower):
            book_score += 2
            
        # Website indicators
        if re.search(r'retrieved|accessed|available from', ref_lower):
            website_score += 3
        if re.search(r'www\.|\.com|\.org|\.edu|\.gov', ref_text):
            website_score += 2
            
        # Return highest scoring type
        if book_score > journal_score and book_score > website_score:
            return 'book'
        elif website_score > journal_score and website_score > book_score:
            return 'website'
        else:
            return 'journal'  # Default assumption

    def extract_elements_safely(self, ref_text: str) -> Dict:
        """FIXED: Extract elements with proper error handling and sequencing"""
        elements = {
            'authors': None,
            'year': None,
            'title': None,
            'journal': None,
            'publisher': None,
            'url': None,
            'isbn': None,
            'doi': None,
            'volume': None,
            'issue': None,
            'pages': None,
            'reference_type': None,
            'extraction_errors': []
        }
        
        try:
            # Determine reference type first
            elements['reference_type'] = self.detect_reference_type(ref_text)
            
            # Extract year first (needed for author extraction)
            year_match = re.search(self.flexible_patterns['any_year'], ref_text)
            if year_match:
                elements['year'] = year_match.group(1)
                
                # FIXED: Extract authors (everything before year, cleaned)
                try:
                    author_section = ref_text[:year_match.start()].strip()
                    # Remove trailing comma and whitespace
                    author_section = re.sub(r'[,\s]+

    def check_apa_format_compliance(self, ref_text: str, ref_type: str) -> Dict:
        """Check APA format compliance with error handling"""
        compliance = {
            'is_compliant': True,
            'violations': [],
            'suggestions': [],
            'check_errors': []
        }
        
        try:
            # Check comma before year (major APA violation)
            if re.search(self.apa_format_patterns['comma_before_year'], ref_text):
                compliance['is_compliant'] = False
                compliance['violations'].append("Comma before year")
                compliance['suggestions'].append("Change 'Author, (2020)' to 'Author. (2020)'")
            
            # Check proper year format
            if not re.search(self.apa_format_patterns['proper_year_format'], ref_text):
                compliance['is_compliant'] = False
                compliance['violations'].append("Incorrect year format")
                compliance['suggestions'].append("Year should be formatted as '. (YYYY).' with periods")
            
            # Check author format
            if not re.search(self.apa_format_patterns['author_format'], ref_text):
                compliance['is_compliant'] = False
                compliance['violations'].append("Incorrect author format")
                compliance['suggestions'].append("Authors should end with period before year")
            
            # For journals, check title/journal structure
            if ref_type == 'journal':
                if not re.search(self.apa_format_patterns['title_journal_structure'], ref_text):
                    compliance['is_compliant'] = False
                    compliance['violations'].append("Incorrect title/journal structure")
                    compliance['suggestions'].append("Format should be: ). Title. Journal Name, Volume")
                    
        except Exception as e:
            compliance['check_errors'].append(f"Format checking error: {str(e)}")
        
        return compliance

class SafeAuthenticityChecker:
    """Improved authenticity checker with comprehensive error handling"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        # Add timeout settings
        self.timeout = 15
        self.max_retries = 2

    def check_authenticity(self, elements: Dict) -> Dict:
        """Check authenticity with comprehensive error handling"""
        result = {
            'is_authentic': False,
            'confidence': 'low',
            'sources_checked': [],
            'verification_details': [],
            'check_errors': []
        }
        
        if not elements:
            result['check_errors'].append("No elements provided for checking")
            return result
        
        ref_type = elements.get('reference_type', 'journal')
        
        # Priority 1: Check DOI (strongest indicator)
        if elements.get('doi'):
            try:
                doi_result = self._check_doi_safely(elements['doi'])
                result['sources_checked'].append('DOI Database')
                
                if doi_result['valid']:
                    result['is_authentic'] = True
                    result['confidence'] = 'high'
                    result['verification_details'].append(f"DOI {elements['doi']} verified")
                    return result
                else:
                    result['verification_details'].append(f"DOI check failed: {doi_result.get('reason', 'Invalid')}")
            except Exception as e:
                result['check_errors'].append(f"DOI check error: {str(e)}")
        
        # Priority 2: Check ISBN (for books)
        if elements.get('isbn'):
            try:
                isbn_result = self._check_isbn_safely(elements['isbn'])
                result['sources_checked'].append('ISBN Database')
                
                if isbn_result['found']:
                    result['is_authentic'] = True
                    result['confidence'] = 'high'
                    result['verification_details'].append(f"ISBN {elements['isbn']} found in database")
                    return result
                else:
                    result['verification_details'].append("ISBN not found in database")
            except Exception as e:
                result['check_errors'].append(f"ISBN check error: {str(e)}")
        
        # Priority 3: Title-based search (with length validation)
        title = elements.get('title')
        if title and len(title.strip()) > 10:
            try:
                title_result = self._search_by_title_safely(title, ref_type)
                result['sources_checked'].append('Title Search')
                
                if title_result['found']:
                    result['is_authentic'] = True
                    result['confidence'] = title_result.get('confidence', 'medium')
                    result['verification_details'].append(f"Title match found: {title_result.get('matched_title', 'Unknown')}")
                    return result
                else:
                    result['verification_details'].append("No title matches found in database")
            except Exception as e:
                result['check_errors'].append(f"Title search error: {str(e)}")
        
        # Priority 4: URL accessibility (for websites)
        if ref_type == 'website' and elements.get('url'):
            try:
                url_result = self._check_url_safely(elements['url'])
                result['sources_checked'].append('URL Check')
                
                if url_result['accessible']:
                    result['is_authentic'] = True
                    result['confidence'] = 'medium'
                    result['verification_details'].append("Website URL accessible")
                    return result
                else:
                    result['verification_details'].append(f"URL not accessible: {url_result.get('reason', 'Unknown')}")
            except Exception as e:
                result['check_errors'].append(f"URL check error: {str(e)}")
        
        # If no verification succeeded
        if not result['verification_details']:
            result['verification_details'].append("No database verification succeeded")
        
        return result

    def _check_doi_safely(self, doi: str) -> Dict:
        """Safely check DOI with retries and timeouts"""
        if not doi or not doi.strip():
            return {'valid': False, 'reason': 'Empty DOI'}
        
        for attempt in range(self.max_retries):
            try:
                url = f"https://doi.org/{doi.strip()}"
                response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
                return {
                    'valid': response.status_code == 200,
                    'reason': f"Status code: {response.status_code}" if response.status_code != 200 else "Valid"
                }
            except requests.exceptions.Timeout:
                if attempt == self.max_retries - 1:
                    return {'valid': False, 'reason': 'Request timeout'}
                time.sleep(1)  # Brief pause before retry
            except requests.exceptions.RequestException as e:
                return {'valid': False, 'reason': f"Request error: {str(e)}"}
            except Exception as e:
                return {'valid': False, 'reason': f"Unexpected error: {str(e)}"}
        
        return {'valid': False, 'reason': 'Max retries exceeded'}

    def _check_isbn_safely(self, isbn: str) -> Dict:
        """Safely check ISBN with validation"""
        if not isbn or not isbn.strip():
            return {'found': False, 'reason': 'Empty ISBN'}
        
        try:
            isbn_clean = re.sub(r'[^\d-X]', '', isbn.strip().upper())
            if not isbn_clean:
                return {'found': False, 'reason': 'Invalid ISBN format'}
            
            url = "https://openlibrary.org/api/books"
            params = {'bibkeys': f'ISBN:{isbn_clean}', 'format': 'json', 'jscmd': 'data'}
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            return {'found': bool(data), 'data': data}
        except requests.exceptions.Timeout:
            return {'found': False, 'reason': 'Request timeout'}
        except requests.exceptions.RequestException as e:
            return {'found': False, 'reason': f"Request error: {str(e)}"}
        except Exception as e:
            return {'found': False, 'reason': f"Error: {str(e)}"}

    def _search_by_title_safely(self, title: str, ref_type: str) -> Dict:
        """Safely search for title with validation"""
        if not title or len(title.strip()) < 5:
            return {'found': False, 'reason': 'Title too short for search'}
        
        try:
            if ref_type == 'journal':
                return self._search_crossref_safely(title)
            elif ref_type == 'book':
                return self._search_openlibrary_safely(title)
            else:
                return {'found': False, 'reason': 'Website titles not searchable'}
        except Exception as e:
            return {'found': False, 'reason': f"Search error: {str(e)}"}

    def _search_crossref_safely(self, title: str) -> Dict:
        """Safely search Crossref with error handling"""
        try:
            url = "https://api.crossref.org/works"
            params = {'query.title': title.strip(), 'rows': 5, 'select': 'title,DOI'}
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if 'message' in data and 'items' in data['message'] and data['message']['items']:
                for item in data['message']['items']:
                    if 'title' in item and item['title']:
                        item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
                        similarity = self._calculate_similarity_safely(title, item_title)
                        if similarity > 0.6:
                            return {
                                'found': True,
                                'confidence': 'high' if similarity > 0.8 else 'medium',
                                'matched_title': item_title,
                                'similarity': similarity
                            }
            
            return {'found': False, 'reason': 'No similar titles found in Crossref'}
        except requests.exceptions.Timeout:
            return {'found': False, 'reason': 'Crossref request timeout'}
        except requests.exceptions.RequestException as e:
            return {'found': False, 'reason': f"Crossref request error: {str(e)}"}
        except Exception as e:
            return {'found': False, 'reason': f"Crossref search error: {str(e)}"}

    def _search_openlibrary_safely(self, title: str) -> Dict:
        """Safely search Open Library"""
        try:
            # Extract meaningful words for search
            title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)[:5]
            if not title_words:
                return {'found': False, 'reason': 'No searchable words in title'}
            
            query = ' '.join(title_words)
            url = "https://openlibrary.org/search.json"
            params = {'q': query, 'limit': 5}
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if 'docs' in data and data['docs']:
                for doc in data['docs']:
                    if 'title' in doc:
                        similarity = self._calculate_similarity_safely(title, doc['title'])
                        if similarity > 0.6:
                            return {
                                'found': True,
                                'confidence': 'high' if similarity > 0.8 else 'medium',
                                'matched_title': doc['title'],
                                'similarity': similarity
                            }
            
            return {'found': False, 'reason': 'No similar book titles found'}
        except requests.exceptions.Timeout:
            return {'found': False, 'reason': 'Open Library request timeout'}
        except requests.exceptions.RequestException as e:
            return {'found': False, 'reason': f"Open Library request error: {str(e)}"}
        except Exception as e:
            return {'found': False, 'reason': f"Open Library search error: {str(e)}"}

    def _check_url_safely(self, url: str) -> Dict:
        """Safely check URL accessibility"""
        if not url or not url.strip():
            return {'accessible': False, 'reason': 'Empty URL'}
        
        try:
            clean_url = url.strip()
            if not clean_url.startswith(('http://', 'https://')):
                clean_url = 'https://' + clean_url
            
            response = self.session.head(clean_url, timeout=self.timeout, allow_redirects=True)
            return {
                'accessible': response.status_code == 200,
                'reason': f"Status: {response.status_code}" if response.status_code != 200 else "Accessible"
            }
        except requests.exceptions.Timeout:
            return {'accessible': False, 'reason': 'Request timeout'}
        except requests.exceptions.RequestException as e:
            return {'accessible': False, 'reason': f"Request error: {str(e)}"}
        except Exception as e:
            return {'accessible': False, 'reason': f"Error: {str(e)}"}

    def _calculate_similarity_safely(self, str1: str, str2: str) -> float:
        """Safely calculate similarity with error handling"""
        try:
            if not str1 or not str2:
                return 0.0
            
            words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', str1.lower()))
            words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', str2.lower()))
            
            if not words1 or not words2:
                return 0.0
            
            intersection = words1.intersection(words2)
            union = words1.union(words2)
            
            return len(intersection) / len(union) if union else 0.0
        except Exception:
            return 0.0

class CorrectedAuthenticityVerifier:
    def __init__(self):
        self.parser = CorrectedAuthenticityParser()
        self.authenticity_checker = SafeAuthenticityChecker()

    def verify_references(self, text: str, format_type: str) -> List[Dict]:
        """Verify references with comprehensive error handling"""
        if not text or not text.strip():
            return []
        
        lines = text.strip().split('\n')
        results = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or len(line) < 30:  # Skip short lines
                continue
                
            result = {
                'reference': line,
                'line_number': i + 1,
                'authenticity_status': 'unknown',
                'format_status': 'unknown',
                'overall_status': 'unknown',
                'reference_type': 'unknown',
                'extracted_elements': {},
                'authenticity_check': {},
                'format_check': {},
                'processing_errors': []
            }
            
            try:
                # Step 1: Extract elements flexibly for authenticity checking
                elements = self.parser.extract_elements_safely(line)
                result['extracted_elements'] = elements
                result['reference_type'] = elements.get('reference_type', 'unknown')
                
                if elements.get('extraction_errors'):
                    result['processing_errors'].extend(elements['extraction_errors'])
                
                # Step 2: Check authenticity FIRST
                authenticity_result = self.authenticity_checker.check_authenticity(elements)
                result['authenticity_check'] = authenticity_result
                
                if authenticity_result.get('check_errors'):
                    result['processing_errors'].extend(authenticity_result['check_errors'])
                
                if authenticity_result['is_authentic']:
                    result['authenticity_status'] = 'authentic'
                    
                    # Step 3: Only THEN check formatting (for authentic references)
                    format_check = self.parser.check_apa_format_compliance(line, elements['reference_type'])
                    result['format_check'] = format_check
                    
                    if format_check.get('check_errors'):
                        result['processing_errors'].extend(format_check['check_errors'])
                    
                    if format_check['is_compliant']:
                        result['format_status'] = 'compliant'
                        result['overall_status'] = 'valid'
                    else:
                        result['format_status'] = 'format_issues'
                        result['overall_status'] = 'authentic_but_poor_format'
                else:
                    result['authenticity_status'] = 'likely_fake'
                    result['overall_status'] = 'likely_fake'
                    # Don't check formatting for fake references
                    
            except Exception as e:
                result['processing_errors'].append(f"Critical processing error: {str(e)}")
                result['overall_status'] = 'processing_error'
            
            results.append(result)
            
            # Rate limiting to be respectful to APIs
            time.sleep(0.5)
        
        return results

def main():
    st.set_page_config(
        page_title="Corrected Authenticity-First Verifier",
        page_icon="🔧",
        layout="wide"
    )
    
    st.title("🔧 Corrected Authenticity-First Verifier")
    st.markdown("**Fixed version with comprehensive error handling and improved extraction**")
    
    st.sidebar.header("🐛 Bugs Fixed")
    st.sidebar.markdown("**✅ Volume/Pages Extraction**")
    st.sidebar.markdown("• Now searches AFTER journal name")
    st.sidebar.markdown("• No longer matches year instead of volume")
    
    st.sidebar.markdown("**✅ Title Extraction**")
    st.sidebar.markdown("• Better boundary detection")
    st.sidebar.markdown("• Stops at punctuation marks")
    
    st.sidebar.markdown("**✅ Error Handling**")
    st.sidebar.markdown("• Comprehensive try/catch blocks")
    st.sidebar.markdown("• API timeout protection")
    st.sidebar.markdown("• Input validation")
    
    st.sidebar.markdown("**✅ Author Cleaning**")
    st.sidebar.markdown("• Properly removes trailing commas")
    st.sidebar.markdown("• Better text processing")
    
    format_type = st.sidebar.selectbox("Reference Format", ["APA", "Vancouver"])
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📝 Test the Fixed Version")
        
        st.info("**Test cases**: Try both correctly formatted and problematic references to see improved extraction!")
        
        reference_text = st.text_area(
            "Paste your references here:",
            height=350,
            value="Kym Joanne Price, Brett Ashley Gordon, Stephen Richard Bird, Amanda Clare Benson, (2016). A review of guidelines for cardiac rehabilitation exercise programmes: Is there an international consensus?, European Journal of Sport, 23 (16), 1715–1733, https://doi.org/10.1177/2047487316657669",
            help="This should now correctly extract volume=23, issue=16, pages=1715-1733"
        )
        
        verify_button = st.button("🔍 Test Fixed Verifier", type="primary", use_container_width=True)
        
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("📚 Add Book Example", use_container_width=True):
                book_ref = "\n\nAmerican College of Sports Medicine. (2022). ACSM's guidelines for exercise testing and prescription (11th ed.). Wolters Kluwer."
                st.session_state.book_text = reference_text + book_ref
        
        with col_b:
            if st.button("🌐 Add Website Example", use_container_width=True):
                website_ref = "\n\nWorld Health Organization. (2021). COVID-19 pandemic response. Retrieved March 15, 2023, from https://www.who.int/emergencies/diseases/novel-coronavirus-2019"
                st.session_state.website_text = reference_text + website_ref
    
    with col2:
        st.header("📊 Detailed Analysis Results")
        
        # Handle test cases
        if 'book_text' in st.session_state:
            reference_text = st.session_state.book_text
            del st.session_state.book_text
            verify_button = True
        elif 'website_text' in st.session_state:
            reference_text = st.session_state.website_text
            del st.session_state.website_text
            verify_button = True
        
        if verify_button and reference_text.strip():
            with st.spinner("Processing with improved extraction and error handling..."):
                verifier = CorrectedAuthenticityVerifier()
                results = verifier.verify_references(reference_text, format_type)
            
            if results:
                # Summary with error tracking
                total = len(results)
                valid = sum(1 for r in results if r['overall_status'] == 'valid')
                authentic_poor_format = sum(1 for r in results if r['overall_status'] == 'authentic_but_poor_format')
                likely_fake = sum(1 for r in results if r['overall_status'] == 'likely_fake')
                processing_errors = sum(1 for r in results if r['overall_status'] == 'processing_error')
                
                col_a, col_b, col_c, col_d, col_e = st.columns(5)
                with col_a:
                    st.metric("Total", total)
                with col_b:
                    st.metric("✅ Valid", valid)
                with col_c:
                    st.metric("⚠️ Format Issues", authentic_poor_format)
                with col_d:
                    st.metric("🚨 Likely Fake", likely_fake)
                with col_e:
                    st.metric("🐛 Errors", processing_errors)
                
                st.markdown("---")
                
                # Detailed results with debugging info
                for result in results:
                    ref_type = result.get('reference_type', 'unknown')
                    # Ensure ref_type is a string and not None
                    if not ref_type or ref_type == 'unknown':
                        ref_type = 'unknown'
                    
                    type_icons = {'journal': '📄', 'book': '📚', 'website': '🌐', 'unknown': '❓'}
                    type_icon = type_icons.get(ref_type, '❓')
                    
                    # Safe title() call with fallback
                    ref_type_display = ref_type.title() if isinstance(ref_type, str) else 'Unknown'
                    
                    st.markdown(f"### {type_icon} Reference {result.get('line_number', 'N/A')} ({ref_type_display})")
                    
                    status = result.get('overall_status', 'unknown')
                    
                    if status == 'valid':
                        st.success("✅ **Authentic and Properly Formatted**")
                        
                        # Show verification details with safe access
                        auth_check = result.get('authenticity_check', {})
                        auth_details = auth_check.get('verification_details', [])
                        for detail in auth_details:
                            if detail:  # Only show non-empty details
                                st.markdown(f"  🔍 {detail}")
                    
                    elif status == 'authentic_but_poor_format':
                        st.warning("⚠️ **Authentic Reference with Format Issues**")
                        
                        # Show authenticity verification with safe access
                        st.markdown("**✅ Authenticity Verified:**")
                        auth_check = result.get('authenticity_check', {})
                        auth_details = auth_check.get('verification_details', [])
                        for detail in auth_details:
                            if detail:
                                st.markdown(f"  • {detail}")
                        
                        # Show format issues with safe access
                        st.markdown("**📝 Format Issues to Fix:**")
                        format_check = result.get('format_check', {})
                        format_violations = format_check.get('violations', [])
                        format_suggestions = format_check.get('suggestions', [])
                        
                        # Safely zip violations and suggestions
                        for i, violation in enumerate(format_violations):
                            suggestion = format_suggestions[i] if i < len(format_suggestions) else "No specific suggestion available"
                            st.markdown(f"  • **{violation}**: {suggestion}")
                    
                    elif status == 'likely_fake':
                        st.error("🚨 **Likely Fake Reference**")
                        
                        st.markdown("**❌ No database verification found:**")
                        auth_check = result.get('authenticity_check', {})
                        sources_checked = auth_check.get('sources_checked', [])
                        verification_details = auth_check.get('verification_details', [])
                        
                        if sources_checked:
                            st.markdown(f"  • **Sources checked**: {', '.join(str(s) for s in sources_checked)}")
                        for detail in verification_details:
                            if detail:
                                st.markdown(f"  • {detail}")
                    
                    elif status == 'processing_error':
                        st.error("🐛 **Processing Error**")
                        processing_errors = result.get('processing_errors', [])
                        for error in processing_errors:
                            if error:
                                st.markdown(f"  • {error}")
                    
                    else:
                        # Handle unknown status
                        st.warning(f"❓ **Unknown Status**: {status}")
                        processing_errors = result.get('processing_errors', [])
                        if processing_errors:
                            st.markdown("**Errors encountered:**")
                            for error in processing_errors:
                                if error:
                                    st.markdown(f"  • {error}")
                    
                    # Show extracted elements with debugging
                    with st.expander("🔍 Extraction Results (Debug Info)"):
                        elements = result.get('extracted_elements', {})
                        
                        st.markdown("**✅ Successfully Extracted:**")
                        extracted_something = False
                        for key, value in elements.items():
                            if value and key not in ['extraction_errors', 'reference_type']:
                                st.markdown(f"  • **{key.title()}**: `{value}`")
                                extracted_something = True
                        
                        if not extracted_something:
                            st.markdown("  • No elements successfully extracted")
                        
                        # Show extraction errors if any
                        extraction_errors = elements.get('extraction_errors', [])
                        if extraction_errors:
                            st.markdown("**⚠️ Extraction Issues:**")
                            for error in extraction_errors:
                                if error:
                                    st.markdown(f"  • {error}")
                        
                        # Show processing errors if any
                        processing_errors = result.get('processing_errors', [])
                        if processing_errors:
                            st.markdown("**🐛 Processing Errors:**")
                            for error in processing_errors:
                                if error:
                                    st.markdown(f"  • {error}")
                    
                    # Show original reference
                    with st.expander("📄 Original Reference"):
                        ref_text = result.get('reference', 'No reference text available')
                        st.code(ref_text, language="text")
                    
                    st.markdown("---")
        
        elif verify_button:
            st.warning("Please enter some references to analyze.")
    
    with st.expander("🔧 Technical Fixes Implemented"):
        st.markdown("""
        ### **🐛 Critical Bugs Fixed:**
        
        **1. Volume/Pages Extraction Error**
        ```python
        # ❌ OLD: Searched entire text, matched year "2016"
        volume_match = re.search(pattern, entire_reference)
        
        # ✅ NEW: Searches only after journal name  
        journal_pos = ref_text.find(elements['journal'])
        text_after_journal = ref_text[journal_pos:]
        volume_match = re.search(pattern, text_after_journal)
        ```
        
        **2. Title Extraction Over-capture**
        ```python
        # ❌ OLD: Captured everything until random punctuation
        'flexible_title': r'\\)\\.[\\s]*([^.]+?)(?:\\.|,[\\s]*[A-Z])'
        
        # ✅ NEW: Better boundary detection
        'flexible_title': r'\\)\\.[\\s]*([^.!?]+?)[\\.\!?\\s]*(?:[A-Z][^,\\d]*[A-Za-z]\\s*,|\\s*$)'
        ```
        
        **3. Missing Error Handling**
        ```python
        # ✅ NEW: Comprehensive try/catch blocks
        try:
            # All extraction operations
        except Exception as e:
            elements['extraction_errors'].append(f"Error: {str(e)}")
        ```
        
        **4. API Safety**
        ```python
        # ✅ NEW: Timeout protection and retries
        response = self.session.get(url, timeout=15)
        # + retry logic for failed requests
        ```
        
        **5. Input Validation**
        ```python
        # ✅ NEW: Validate all inputs before processing
        if not title or len(title.strip()) < 10:
            return {'found': False, 'reason': 'Title too short'}
        ```
        """)

if __name__ == "__main__":
    main(), '', author_section)
                    if author_section:
                        elements['authors'] = author_section
                except Exception as e:
                    elements['extraction_errors'].append(f"Author extraction error: {str(e)}")
            else:
                elements['extraction_errors'].append("No year found in parentheses")
            
            # Extract strong identifiers with error handling
            try:
                doi_match = re.search(self.flexible_patterns['doi_pattern'], ref_text)
                if doi_match:
                    elements['doi'] = doi_match.group(1)
            except Exception as e:
                elements['extraction_errors'].append(f"DOI extraction error: {str(e)}")
            
            try:
                isbn_match = re.search(self.flexible_patterns['isbn_pattern'], ref_text)
                if isbn_match:
                    elements['isbn'] = isbn_match.group(1)
            except Exception as e:
                elements['extraction_errors'].append(f"ISBN extraction error: {str(e)}")
            
            # Extract URL for websites
            if elements.get('reference_type') == 'website':
                try:
                    url_match = re.search(self.flexible_patterns['url_pattern'], ref_text)
                    if url_match:
                        elements['url'] = url_match.group(1)
                except Exception as e:
                    elements['extraction_errors'].append(f"URL extraction error: {str(e)}")
            
            # FIXED: Extract title and journal with proper sequencing
            if year_match:
                try:
                    text_after_year = ref_text[year_match.end():]
                    
                    # Extract title
                    title_match = re.search(self.flexible_patterns['flexible_title'], text_after_year)
                    if title_match:
                        elements['title'] = title_match.group(1).strip()
                    else:
                        # Fallback: simple extraction
                        simple_title = re.search(r'\)\.\s*([^.!?]+)', text_after_year)
                        if simple_title:
                            elements['title'] = simple_title.group(1).strip()
                        else:
                            elements['extraction_errors'].append("Could not extract title")
                except Exception as e:
                    elements['extraction_errors'].append(f"Title extraction error: {str(e)}")
                
                # Extract journal (for journal articles)
                if elements.get('reference_type') == 'journal':
                    try:
                        text_after_year = ref_text[year_match.end():]
                        # Try specific journal pattern first
                        journal_match = re.search(self.flexible_patterns['journal_after_title'], text_after_year)
                        if not journal_match:
                            # Try general pattern
                            journal_match = re.search(self.flexible_patterns['journal_before_volume'], text_after_year)
                        
                        if journal_match:
                            elements['journal'] = journal_match.group(1).strip()
                        else:
                            elements['extraction_errors'].append("Could not extract journal name")
                    except Exception as e:
                        elements['extraction_errors'].append(f"Journal extraction error: {str(e)}")
                
                # Extract publisher (for books)
                elif elements.get('reference_type') == 'book':
                    try:
                        publisher_match = re.search(self.flexible_patterns['publisher_keywords'], ref_text, re.IGNORECASE)
                        if publisher_match:
                            elements['publisher'] = publisher_match.group(1).strip()
                        else:
                            elements['extraction_errors'].append("Could not extract publisher")
                    except Exception as e:
                        elements['extraction_errors'].append(f"Publisher extraction error: {str(e)}")
            
            # FIXED: Extract volume/issue/pages from the RIGHT context
            if elements.get('journal'):
                try:
                    # Search for volume/pages AFTER the journal name
                    journal_name = elements['journal']
                    journal_pos = ref_text.find(journal_name)
                    if journal_pos != -1:
                        text_after_journal = ref_text[journal_pos + len(journal_name):]
                        volume_match = re.search(self.flexible_patterns['volume_issue_pages'], text_after_journal)
                        if volume_match:
                            elements['volume'] = volume_match.group(1)
                            if volume_match.group(2):  # Issue number
                                elements['issue'] = volume_match.group(2)
                            if volume_match.group(3):  # Page numbers
                                elements['pages'] = volume_match.group(3)
                        else:
                            elements['extraction_errors'].append("Could not extract volume/issue/pages")
                    else:
                        elements['extraction_errors'].append("Could not find journal name in text for volume extraction")
                except Exception as e:
                    elements['extraction_errors'].append(f"Volume/pages extraction error: {str(e)}")
            
        except Exception as e:
            elements['extraction_errors'].append(f"Critical extraction error: {str(e)}")
        
        return elements

    def check_apa_format_compliance(self, ref_text: str, ref_type: str) -> Dict:
        """Check APA format compliance with error handling"""
        compliance = {
            'is_compliant': True,
            'violations': [],
            'suggestions': [],
            'check_errors': []
        }
        
        try:
            # Check comma before year (major APA violation)
            if re.search(self.apa_format_patterns['comma_before_year'], ref_text):
                compliance['is_compliant'] = False
                compliance['violations'].append("Comma before year")
                compliance['suggestions'].append("Change 'Author, (2020)' to 'Author. (2020)'")
            
            # Check proper year format
            if not re.search(self.apa_format_patterns['proper_year_format'], ref_text):
                compliance['is_compliant'] = False
                compliance['violations'].append("Incorrect year format")
                compliance['suggestions'].append("Year should be formatted as '. (YYYY).' with periods")
            
            # Check author format
            if not re.search(self.apa_format_patterns['author_format'], ref_text):
                compliance['is_compliant'] = False
                compliance['violations'].append("Incorrect author format")
                compliance['suggestions'].append("Authors should end with period before year")
            
            # For journals, check title/journal structure
            if ref_type == 'journal':
                if not re.search(self.apa_format_patterns['title_journal_structure'], ref_text):
                    compliance['is_compliant'] = False
                    compliance['violations'].append("Incorrect title/journal structure")
                    compliance['suggestions'].append("Format should be: ). Title. Journal Name, Volume")
                    
        except Exception as e:
            compliance['check_errors'].append(f"Format checking error: {str(e)}")
        
        return compliance

class SafeAuthenticityChecker:
    """Improved authenticity checker with comprehensive error handling"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        # Add timeout settings
        self.timeout = 15
        self.max_retries = 2

    def check_authenticity(self, elements: Dict) -> Dict:
        """Check authenticity with comprehensive error handling"""
        result = {
            'is_authentic': False,
            'confidence': 'low',
            'sources_checked': [],
            'verification_details': [],
            'check_errors': []
        }
        
        if not elements:
            result['check_errors'].append("No elements provided for checking")
            return result
        
        ref_type = elements.get('reference_type', 'journal')
        
        # Priority 1: Check DOI (strongest indicator)
        if elements.get('doi'):
            try:
                doi_result = self._check_doi_safely(elements['doi'])
                result['sources_checked'].append('DOI Database')
                
                if doi_result['valid']:
                    result['is_authentic'] = True
                    result['confidence'] = 'high'
                    result['verification_details'].append(f"DOI {elements['doi']} verified")
                    return result
                else:
                    result['verification_details'].append(f"DOI check failed: {doi_result.get('reason', 'Invalid')}")
            except Exception as e:
                result['check_errors'].append(f"DOI check error: {str(e)}")
        
        # Priority 2: Check ISBN (for books)
        if elements.get('isbn'):
            try:
                isbn_result = self._check_isbn_safely(elements['isbn'])
                result['sources_checked'].append('ISBN Database')
                
                if isbn_result['found']:
                    result['is_authentic'] = True
                    result['confidence'] = 'high'
                    result['verification_details'].append(f"ISBN {elements['isbn']} found in database")
                    return result
                else:
                    result['verification_details'].append("ISBN not found in database")
            except Exception as e:
                result['check_errors'].append(f"ISBN check error: {str(e)}")
        
        # Priority 3: Title-based search (with length validation)
        title = elements.get('title')
        if title and len(title.strip()) > 10:
            try:
                title_result = self._search_by_title_safely(title, ref_type)
                result['sources_checked'].append('Title Search')
                
                if title_result['found']:
                    result['is_authentic'] = True
                    result['confidence'] = title_result.get('confidence', 'medium')
                    result['verification_details'].append(f"Title match found: {title_result.get('matched_title', 'Unknown')}")
                    return result
                else:
                    result['verification_details'].append("No title matches found in database")
            except Exception as e:
                result['check_errors'].append(f"Title search error: {str(e)}")
        
        # Priority 4: URL accessibility (for websites)
        if ref_type == 'website' and elements.get('url'):
            try:
                url_result = self._check_url_safely(elements['url'])
                result['sources_checked'].append('URL Check')
                
                if url_result['accessible']:
                    result['is_authentic'] = True
                    result['confidence'] = 'medium'
                    result['verification_details'].append("Website URL accessible")
                    return result
                else:
                    result['verification_details'].append(f"URL not accessible: {url_result.get('reason', 'Unknown')}")
            except Exception as e:
                result['check_errors'].append(f"URL check error: {str(e)}")
        
        # If no verification succeeded
        if not result['verification_details']:
            result['verification_details'].append("No database verification succeeded")
        
        return result

    def _check_doi_safely(self, doi: str) -> Dict:
        """Safely check DOI with retries and timeouts"""
        if not doi or not doi.strip():
            return {'valid': False, 'reason': 'Empty DOI'}
        
        for attempt in range(self.max_retries):
            try:
                url = f"https://doi.org/{doi.strip()}"
                response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
                return {
                    'valid': response.status_code == 200,
                    'reason': f"Status code: {response.status_code}" if response.status_code != 200 else "Valid"
                }
            except requests.exceptions.Timeout:
                if attempt == self.max_retries - 1:
                    return {'valid': False, 'reason': 'Request timeout'}
                time.sleep(1)  # Brief pause before retry
            except requests.exceptions.RequestException as e:
                return {'valid': False, 'reason': f"Request error: {str(e)}"}
            except Exception as e:
                return {'valid': False, 'reason': f"Unexpected error: {str(e)}"}
        
        return {'valid': False, 'reason': 'Max retries exceeded'}

    def _check_isbn_safely(self, isbn: str) -> Dict:
        """Safely check ISBN with validation"""
        if not isbn or not isbn.strip():
            return {'found': False, 'reason': 'Empty ISBN'}
        
        try:
            isbn_clean = re.sub(r'[^\d-X]', '', isbn.strip().upper())
            if not isbn_clean:
                return {'found': False, 'reason': 'Invalid ISBN format'}
            
            url = "https://openlibrary.org/api/books"
            params = {'bibkeys': f'ISBN:{isbn_clean}', 'format': 'json', 'jscmd': 'data'}
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            return {'found': bool(data), 'data': data}
        except requests.exceptions.Timeout:
            return {'found': False, 'reason': 'Request timeout'}
        except requests.exceptions.RequestException as e:
            return {'found': False, 'reason': f"Request error: {str(e)}"}
        except Exception as e:
            return {'found': False, 'reason': f"Error: {str(e)}"}

    def _search_by_title_safely(self, title: str, ref_type: str) -> Dict:
        """Safely search for title with validation"""
        if not title or len(title.strip()) < 5:
            return {'found': False, 'reason': 'Title too short for search'}
        
        try:
            if ref_type == 'journal':
                return self._search_crossref_safely(title)
            elif ref_type == 'book':
                return self._search_openlibrary_safely(title)
            else:
                return {'found': False, 'reason': 'Website titles not searchable'}
        except Exception as e:
            return {'found': False, 'reason': f"Search error: {str(e)}"}

    def _search_crossref_safely(self, title: str) -> Dict:
        """Safely search Crossref with error handling"""
        try:
            url = "https://api.crossref.org/works"
            params = {'query.title': title.strip(), 'rows': 5, 'select': 'title,DOI'}
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if 'message' in data and 'items' in data['message'] and data['message']['items']:
                for item in data['message']['items']:
                    if 'title' in item and item['title']:
                        item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
                        similarity = self._calculate_similarity_safely(title, item_title)
                        if similarity > 0.6:
                            return {
                                'found': True,
                                'confidence': 'high' if similarity > 0.8 else 'medium',
                                'matched_title': item_title,
                                'similarity': similarity
                            }
            
            return {'found': False, 'reason': 'No similar titles found in Crossref'}
        except requests.exceptions.Timeout:
            return {'found': False, 'reason': 'Crossref request timeout'}
        except requests.exceptions.RequestException as e:
            return {'found': False, 'reason': f"Crossref request error: {str(e)}"}
        except Exception as e:
            return {'found': False, 'reason': f"Crossref search error: {str(e)}"}

    def _search_openlibrary_safely(self, title: str) -> Dict:
        """Safely search Open Library"""
        try:
            # Extract meaningful words for search
            title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)[:5]
            if not title_words:
                return {'found': False, 'reason': 'No searchable words in title'}
            
            query = ' '.join(title_words)
            url = "https://openlibrary.org/search.json"
            params = {'q': query, 'limit': 5}
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if 'docs' in data and data['docs']:
                for doc in data['docs']:
                    if 'title' in doc:
                        similarity = self._calculate_similarity_safely(title, doc['title'])
                        if similarity > 0.6:
                            return {
                                'found': True,
                                'confidence': 'high' if similarity > 0.8 else 'medium',
                                'matched_title': doc['title'],
                                'similarity': similarity
                            }
            
            return {'found': False, 'reason': 'No similar book titles found'}
        except requests.exceptions.Timeout:
            return {'found': False, 'reason': 'Open Library request timeout'}
        except requests.exceptions.RequestException as e:
            return {'found': False, 'reason': f"Open Library request error: {str(e)}"}
        except Exception as e:
            return {'found': False, 'reason': f"Open Library search error: {str(e)}"}

    def _check_url_safely(self, url: str) -> Dict:
        """Safely check URL accessibility"""
        if not url or not url.strip():
            return {'accessible': False, 'reason': 'Empty URL'}
        
        try:
            clean_url = url.strip()
            if not clean_url.startswith(('http://', 'https://')):
                clean_url = 'https://' + clean_url
            
            response = self.session.head(clean_url, timeout=self.timeout, allow_redirects=True)
            return {
                'accessible': response.status_code == 200,
                'reason': f"Status: {response.status_code}" if response.status_code != 200 else "Accessible"
            }
        except requests.exceptions.Timeout:
            return {'accessible': False, 'reason': 'Request timeout'}
        except requests.exceptions.RequestException as e:
            return {'accessible': False, 'reason': f"Request error: {str(e)}"}
        except Exception as e:
            return {'accessible': False, 'reason': f"Error: {str(e)}"}

    def _calculate_similarity_safely(self, str1: str, str2: str) -> float:
        """Safely calculate similarity with error handling"""
        try:
            if not str1 or not str2:
                return 0.0
            
            words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', str1.lower()))
            words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', str2.lower()))
            
            if not words1 or not words2:
                return 0.0
            
            intersection = words1.intersection(words2)
            union = words1.union(words2)
            
            return len(intersection) / len(union) if union else 0.0
        except Exception:
            return 0.0

class CorrectedAuthenticityVerifier:
    def __init__(self):
        self.parser = CorrectedAuthenticityParser()
        self.authenticity_checker = SafeAuthenticityChecker()

    def verify_references(self, text: str, format_type: str) -> List[Dict]:
        """Verify references with comprehensive error handling"""
        if not text or not text.strip():
            return []
        
        lines = text.strip().split('\n')
        results = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or len(line) < 30:  # Skip short lines
                continue
                
            result = {
                'reference': line,
                'line_number': i + 1,
                'authenticity_status': 'unknown',
                'format_status': 'unknown',
                'overall_status': 'unknown',
                'reference_type': 'unknown',
                'extracted_elements': {},
                'authenticity_check': {},
                'format_check': {},
                'processing_errors': []
            }
            
            try:
                # Step 1: Extract elements flexibly for authenticity checking
                elements = self.parser.extract_elements_safely(line)
                result['extracted_elements'] = elements
                result['reference_type'] = elements.get('reference_type', 'unknown')
                
                if elements.get('extraction_errors'):
                    result['processing_errors'].extend(elements['extraction_errors'])
                
                # Step 2: Check authenticity FIRST
                authenticity_result = self.authenticity_checker.check_authenticity(elements)
                result['authenticity_check'] = authenticity_result
                
                if authenticity_result.get('check_errors'):
                    result['processing_errors'].extend(authenticity_result['check_errors'])
                
                if authenticity_result['is_authentic']:
                    result['authenticity_status'] = 'authentic'
                    
                    # Step 3: Only THEN check formatting (for authentic references)
                    format_check = self.parser.check_apa_format_compliance(line, elements['reference_type'])
                    result['format_check'] = format_check
                    
                    if format_check.get('check_errors'):
                        result['processing_errors'].extend(format_check['check_errors'])
                    
                    if format_check['is_compliant']:
                        result['format_status'] = 'compliant'
                        result['overall_status'] = 'valid'
                    else:
                        result['format_status'] = 'format_issues'
                        result['overall_status'] = 'authentic_but_poor_format'
                else:
                    result['authenticity_status'] = 'likely_fake'
                    result['overall_status'] = 'likely_fake'
                    # Don't check formatting for fake references
                    
            except Exception as e:
                result['processing_errors'].append(f"Critical processing error: {str(e)}")
                result['overall_status'] = 'processing_error'
            
            results.append(result)
            
            # Rate limiting to be respectful to APIs
            time.sleep(0.5)
        
        return results

def main():
    st.set_page_config(
        page_title="Corrected Authenticity-First Verifier",
        page_icon="🔧",
        layout="wide"
    )
    
    st.title("🔧 Corrected Authenticity-First Verifier")
    st.markdown("**Fixed version with comprehensive error handling and improved extraction**")
    
    st.sidebar.header("🐛 Bugs Fixed")
    st.sidebar.markdown("**✅ Volume/Pages Extraction**")
    st.sidebar.markdown("• Now searches AFTER journal name")
    st.sidebar.markdown("• No longer matches year instead of volume")
    
    st.sidebar.markdown("**✅ Title Extraction**")
    st.sidebar.markdown("• Better boundary detection")
    st.sidebar.markdown("• Stops at punctuation marks")
    
    st.sidebar.markdown("**✅ Error Handling**")
    st.sidebar.markdown("• Comprehensive try/catch blocks")
    st.sidebar.markdown("• API timeout protection")
    st.sidebar.markdown("• Input validation")
    
    st.sidebar.markdown("**✅ Author Cleaning**")
    st.sidebar.markdown("• Properly removes trailing commas")
    st.sidebar.markdown("• Better text processing")
    
    format_type = st.sidebar.selectbox("Reference Format", ["APA", "Vancouver"])
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📝 Test the Fixed Version")
        
        st.info("**Test cases**: Try both correctly formatted and problematic references to see improved extraction!")
        
        reference_text = st.text_area(
            "Paste your references here:",
            height=350,
            value="Kym Joanne Price, Brett Ashley Gordon, Stephen Richard Bird, Amanda Clare Benson, (2016). A review of guidelines for cardiac rehabilitation exercise programmes: Is there an international consensus?, European Journal of Sport, 23 (16), 1715–1733, https://doi.org/10.1177/2047487316657669",
            help="This should now correctly extract volume=23, issue=16, pages=1715-1733"
        )
        
        verify_button = st.button("🔍 Test Fixed Verifier", type="primary", use_container_width=True)
        
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("📚 Add Book Example", use_container_width=True):
                book_ref = "\n\nAmerican College of Sports Medicine. (2022). ACSM's guidelines for exercise testing and prescription (11th ed.). Wolters Kluwer."
                st.session_state.book_text = reference_text + book_ref
        
        with col_b:
            if st.button("🌐 Add Website Example", use_container_width=True):
                website_ref = "\n\nWorld Health Organization. (2021). COVID-19 pandemic response. Retrieved March 15, 2023, from https://www.who.int/emergencies/diseases/novel-coronavirus-2019"
                st.session_state.website_text = reference_text + website_ref
    
    with col2:
        st.header("📊 Detailed Analysis Results")
        
        # Handle test cases
        if 'book_text' in st.session_state:
            reference_text = st.session_state.book_text
            del st.session_state.book_text
            verify_button = True
        elif 'website_text' in st.session_state:
            reference_text = st.session_state.website_text
            del st.session_state.website_text
            verify_button = True
        
        if verify_button and reference_text.strip():
            with st.spinner("Processing with improved extraction and error handling..."):
                verifier = CorrectedAuthenticityVerifier()
                results = verifier.verify_references(reference_text, format_type)
            
            if results:
                # Summary with error tracking
                total = len(results)
                valid = sum(1 for r in results if r['overall_status'] == 'valid')
                authentic_poor_format = sum(1 for r in results if r['overall_status'] == 'authentic_but_poor_format')
                likely_fake = sum(1 for r in results if r['overall_status'] == 'likely_fake')
                processing_errors = sum(1 for r in results if r['overall_status'] == 'processing_error')
                
                col_a, col_b, col_c, col_d, col_e = st.columns(5)
                with col_a:
                    st.metric("Total", total)
                with col_b:
                    st.metric("✅ Valid", valid)
                with col_c:
                    st.metric("⚠️ Format Issues", authentic_poor_format)
                with col_d:
                    st.metric("🚨 Likely Fake", likely_fake)
                with col_e:
                    st.metric("🐛 Errors", processing_errors)
                
                st.markdown("---")
                
                # Detailed results with debugging info
                for result in results:
                    ref_type = result.get('reference_type', 'unknown')
                    # Ensure ref_type is a string and not None
                    if not ref_type or ref_type == 'unknown':
                        ref_type = 'unknown'
                    
                    type_icons = {'journal': '📄', 'book': '📚', 'website': '🌐', 'unknown': '❓'}
                    type_icon = type_icons.get(ref_type, '❓')
                    
                    # Safe title() call with fallback
                    ref_type_display = ref_type.title() if isinstance(ref_type, str) else 'Unknown'
                    
                    st.markdown(f"### {type_icon} Reference {result.get('line_number', 'N/A')} ({ref_type_display})")
                    
                    status = result.get('overall_status', 'unknown')
                    
                    if status == 'valid':
                        st.success("✅ **Authentic and Properly Formatted**")
                        
                        # Show verification details with safe access
                        auth_check = result.get('authenticity_check', {})
                        auth_details = auth_check.get('verification_details', [])
                        for detail in auth_details:
                            if detail:  # Only show non-empty details
                                st.markdown(f"  🔍 {detail}")
                    
                    elif status == 'authentic_but_poor_format':
                        st.warning("⚠️ **Authentic Reference with Format Issues**")
                        
                        # Show authenticity verification with safe access
                        st.markdown("**✅ Authenticity Verified:**")
                        auth_check = result.get('authenticity_check', {})
                        auth_details = auth_check.get('verification_details', [])
                        for detail in auth_details:
                            if detail:
                                st.markdown(f"  • {detail}")
                        
                        # Show format issues with safe access
                        st.markdown("**📝 Format Issues to Fix:**")
                        format_check = result.get('format_check', {})
                        format_violations = format_check.get('violations', [])
                        format_suggestions = format_check.get('suggestions', [])
                        
                        # Safely zip violations and suggestions
                        for i, violation in enumerate(format_violations):
                            suggestion = format_suggestions[i] if i < len(format_suggestions) else "No specific suggestion available"
                            st.markdown(f"  • **{violation}**: {suggestion}")
                    
                    elif status == 'likely_fake':
                        st.error("🚨 **Likely Fake Reference**")
                        
                        st.markdown("**❌ No database verification found:**")
                        auth_check = result.get('authenticity_check', {})
                        sources_checked = auth_check.get('sources_checked', [])
                        verification_details = auth_check.get('verification_details', [])
                        
                        if sources_checked:
                            st.markdown(f"  • **Sources checked**: {', '.join(str(s) for s in sources_checked)}")
                        for detail in verification_details:
                            if detail:
                                st.markdown(f"  • {detail}")
                    
                    elif status == 'processing_error':
                        st.error("🐛 **Processing Error**")
                        processing_errors = result.get('processing_errors', [])
                        for error in processing_errors:
                            if error:
                                st.markdown(f"  • {error}")
                    
                    else:
                        # Handle unknown status
                        st.warning(f"❓ **Unknown Status**: {status}")
                        processing_errors = result.get('processing_errors', [])
                        if processing_errors:
                            st.markdown("**Errors encountered:**")
                            for error in processing_errors:
                                if error:
                                    st.markdown(f"  • {error}")
                    
                    # Show extracted elements with debugging
                    with st.expander("🔍 Extraction Results (Debug Info)"):
                        elements = result.get('extracted_elements', {})
                        
                        st.markdown("**✅ Successfully Extracted:**")
                        extracted_something = False
                        for key, value in elements.items():
                            if value and key not in ['extraction_errors', 'reference_type']:
                                st.markdown(f"  • **{key.title()}**: `{value}`")
                                extracted_something = True
                        
                        if not extracted_something:
                            st.markdown("  • No elements successfully extracted")
                        
                        # Show extraction errors if any
                        extraction_errors = elements.get('extraction_errors', [])
                        if extraction_errors:
                            st.markdown("**⚠️ Extraction Issues:**")
                            for error in extraction_errors:
                                if error:
                                    st.markdown(f"  • {error}")
                        
                        # Show processing errors if any
                        processing_errors = result.get('processing_errors', [])
                        if processing_errors:
                            st.markdown("**🐛 Processing Errors:**")
                            for error in processing_errors:
                                if error:
                                    st.markdown(f"  • {error}")
                    
                    # Show original reference
                    with st.expander("📄 Original Reference"):
                        ref_text = result.get('reference', 'No reference text available')
                        st.code(ref_text, language="text")
                    
                    st.markdown("---")
        
        elif verify_button:
            st.warning("Please enter some references to analyze.")
    
    with st.expander("🔧 Technical Fixes Implemented"):
        st.markdown("""
        ### **🐛 Critical Bugs Fixed:**
        
        **1. Volume/Pages Extraction Error**
        ```python
        # ❌ OLD: Searched entire text, matched year "2016"
        volume_match = re.search(pattern, entire_reference)
        
        # ✅ NEW: Searches only after journal name  
        journal_pos = ref_text.find(elements['journal'])
        text_after_journal = ref_text[journal_pos:]
        volume_match = re.search(pattern, text_after_journal)
        ```
        
        **2. Title Extraction Over-capture**
        ```python
        # ❌ OLD: Captured everything until random punctuation
        'flexible_title': r'\\)\\.[\\s]*([^.]+?)(?:\\.|,[\\s]*[A-Z])'
        
        # ✅ NEW: Better boundary detection
        'flexible_title': r'\\)\\.[\\s]*([^.!?]+?)[\\.\!?\\s]*(?:[A-Z][^,\\d]*[A-Za-z]\\s*,|\\s*$)'
        ```
        
        **3. Missing Error Handling**
        ```python
        # ✅ NEW: Comprehensive try/catch blocks
        try:
            # All extraction operations
        except Exception as e:
            elements['extraction_errors'].append(f"Error: {str(e)}")
        ```
        
        **4. API Safety**
        ```python
        # ✅ NEW: Timeout protection and retries
        response = self.session.get(url, timeout=15)
        # + retry logic for failed requests
        ```
        
        **5. Input Validation**
        ```python
        # ✅ NEW: Validate all inputs before processing
        if not title or len(title.strip()) < 10:
            return {'found': False, 'reason': 'Title too short'}
        ```
        """)

if __name__ == "__main__":
    main()

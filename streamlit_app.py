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

class AuthenticityFirstParser:
    def __init__(self):
        # Flexible extraction patterns - focus on getting content, not perfect format
        self.flexible_patterns = {
            # Extract any year in parentheses
            'any_year': r'\((\d{4}[a-z]?)\)',
            
            # Extract DOI from anywhere in text
            'doi_pattern': r'https?://doi\.org/([^\s]+)',
            
            # Extract ISBN from anywhere
            'isbn_pattern': r'ISBN:?\s*([\d-X]+)',
            
            # Extract any URL
            'url_pattern': r'(https?://[^\s]+)',
            
            # Flexible title extraction (after year, before likely journal/publisher)
            'flexible_title': r'\)\.\s*([^.]+?)(?:\.|,\s*[A-Z])',
            
            # Flexible journal extraction (capitalized words followed by comma and numbers)
            'flexible_journal': r'([A-Z][^,\d]*(?:\s+[A-Z][^,\d]*)*)\s*,\s*\d+',
            
            # Volume and pages
            'volume_pages': r'(\d+)\s*(?:\((\d+)\))?,?\s*(\d+(?:-\d+)?)',
            
            # Publisher patterns (for books)
            'publisher_keywords': r'((?:Press|Publishers?|Publications?|Books?|Academic|University|Ltd|Inc|Corp|Kluwer|Elsevier|MIT Press|Human Kinetics)[^.]*)',
            
            # Website access patterns
            'access_date': r'(?:Retrieved|Accessed)\s+([^,\n]+)',
        }
        
        # Strict APA format checking patterns (used AFTER authenticity check)
        self.apa_format_patterns = {
            'comma_before_year': r'[^.],\s*\((\d{4}[a-z]?)\)',
            'proper_year_format': r'\.\s*\((\d{4}[a-z]?)\)\.',
            'author_format': r'^([^.]+)\.\s*\(\d{4}',
            'title_journal_structure': r'\)\.\s*([^.]+?)\.\s*([A-Z][^,]+),',
        }

    def detect_reference_type(self, ref_text: str) -> str:
        """Detect reference type based on content indicators"""
        ref_lower = ref_text.lower()

        # Strong indicators
        if re.search(self.flexible_patterns['doi_pattern'], ref_text):
            return 'journal'
        if re.search(self.flexible_patterns['isbn_pattern'], ref_text):
            return 'book'
        if re.search(self.flexible_patterns['url_pattern'], ref_text) and \
           re.search(self.flexible_patterns['access_date'], ref_text):
            return 'website'
        
        # Content-based scoring
        journal_score = 0
        book_score = 0
        website_score = 0
        
        # Journal indicators
        if re.search(r'journal|review|proceedings|quarterly|annual', ref_lower):
            journal_score += 2
        if re.search(r'\d+\s*\(\d+\)\s*,\s*\d+', ref_text):  # volume(issue), pages
            journal_score += 2
        if re.search(r'vol\.|volume', ref_lower):
            journal_score += 1
            
        # Book indicators
        if re.search(self.flexible_patterns['publisher_keywords'], ref_text):
            book_score += 2
        if re.search(r'edition|ed\.|handbook|manual|textbook', ref_lower):
            book_score += 2
        if re.search(r'isbn|pp\.|pages', ref_lower):
            book_score += 1
            
        # Website indicators
        if re.search(r'retrieved|accessed|available from', ref_lower):
            website_score += 2
        if re.search(r'www\.|http|\.com|\.org|\.edu', ref_text):
            website_score += 1
            
        if book_score > journal_score and book_score > website_score:
            return 'book'
        elif website_score > journal_score and website_score > book_score:
            return 'website'
        else:
            return 'journal'  # Default assumption

    def extract_elements_flexibly(self, ref_text: str) -> Dict:
        """Extract elements flexibly for authenticity checking"""
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
            'reference_type': self.detect_reference_type(ref_text),
            'extraction_method': 'flexible'
        }
        
        # Extract year
        year_match = re.search(self.flexible_patterns['any_year'], ref_text)
        if year_match:
            elements['year'] = year_match.group(1)
            
            # Extract authors (everything before year, cleaned up)
            author_section = ref_text[:year_match.start()].strip()
            author_section = re.sub(r'[,\s]+$', '', author_section)  # Remove trailing commas/spaces
            elements['authors'] = author_section if author_section else None
        
        # Extract DOI
        doi_match = re.search(self.flexible_patterns['doi_pattern'], ref_text)
        if doi_match:
            elements['doi'] = doi_match.group(1)
        
        # Extract ISBN
        isbn_match = re.search(self.flexible_patterns['isbn_pattern'], ref_text)
        if isbn_match:
            elements['isbn'] = isbn_match.group(1)
        
        # Extract URL (for websites)
        if elements['reference_type'] == 'website':
            url_match = re.search(self.flexible_patterns['url_pattern'], ref_text)
            if url_match:
                elements['url'] = url_match.group(1)
        
        # Extract title (flexible approach)
        if year_match:
            # Look for title after year
            text_after_year = ref_text[year_match.end():]
            title_match = re.search(self.flexible_patterns['flexible_title'], text_after_year)
            if title_match:
                elements['title'] = title_match.group(1).strip()
        
        # Extract journal (for journal articles)
        if elements['reference_type'] == 'journal':
            journal_match = re.search(self.flexible_patterns['flexible_journal'], ref_text)
            if journal_match:
                elements['journal'] = journal_match.group(1).strip()
        
        # Extract publisher (for books)
        elif elements['reference_type'] == 'book':
            publisher_match = re.search(self.flexible_patterns['publisher_keywords'], ref_text)
            if publisher_match:
                elements['publisher'] = publisher_match.group(1).strip()
        
        # Extract volume/pages
        volume_match = re.search(self.flexible_patterns['volume_pages'], ref_text)
        if volume_match:
            elements['volume'] = volume_match.group(1)
            if volume_match.group(2):
                elements['issue'] = volume_match.group(2)
            if volume_match.group(3):
                elements['pages'] = volume_match.group(3)
        
        return elements

    def check_apa_format_compliance(self, ref_text: str, ref_type: str) -> Dict:
        """Check APA format compliance AFTER authenticity is verified"""
        compliance = {
            'is_compliant': True,
            'violations': [],
            'suggestions': []
        }
        
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
        
        return compliance

class SimpleAuthenticityChecker:
    """Simplified authenticity checker for demo purposes"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def check_authenticity(self, elements: Dict) -> Dict:
        """Check if reference exists in databases"""
        result = {
            'is_authentic': False,
            'confidence': 'low',
            'sources_checked': [],
            'verification_details': []
        }
        
        ref_type = elements.get('reference_type', 'journal')
        
        # Priority 1: Check DOI (strongest indicator)
        if elements.get('doi'):
            doi_result = self._check_doi(elements['doi'])
            result['sources_checked'].append('DOI Database')
            
            if doi_result['valid']:
                result['is_authentic'] = True
                result['confidence'] = 'high'
                result['verification_details'].append(f"DOI {elements['doi']} verified")
                return result
            else:
                result['verification_details'].append(f"DOI check failed: {doi_result.get('reason', 'Invalid')}")
        
        # Priority 2: Check ISBN (for books)
        if elements.get('isbn'):
            isbn_result = self._check_isbn(elements['isbn'])
            result['sources_checked'].append('ISBN Database')
            
            if isbn_result['found']:
                result['is_authentic'] = True
                result['confidence'] = 'high'
                result['verification_details'].append(f"ISBN {elements['isbn']} found in database")
                return result
            else:
                result['verification_details'].append(f"ISBN not found in database")
        
        # Priority 3: Title-based search
        if elements.get('title') and len(elements['title']) > 10:
            title_result = self._search_by_title(elements['title'], ref_type)
            result['sources_checked'].append('Title Search')
            
            if title_result['found']:
                result['is_authentic'] = True
                result['confidence'] = title_result.get('confidence', 'medium')
                result['verification_details'].append(f"Title match found: {title_result.get('matched_title', 'Unknown')}")
                return result
            else:
                result['verification_details'].append("No title matches found in database")
        
        # Priority 4: URL accessibility (for websites)
        if ref_type == 'website' and elements.get('url'):
            url_result = self._check_url_accessibility(elements['url'])
            result['sources_checked'].append('URL Check')
            
            if url_result['accessible']:
                result['is_authentic'] = True
                result['confidence'] = 'medium'
                result['verification_details'].append("Website URL accessible")
                return result
            else:
                result['verification_details'].append(f"URL not accessible: {url_result.get('reason', 'Unknown')}")
        
        # If we get here, no verification succeeded
        result['verification_details'].append("No database verification succeeded")
        return result

    def _check_doi(self, doi: str) -> Dict:
        """Check if DOI resolves"""
        try:
            url = f"https://doi.org/{doi}"
            response = self.session.head(url, timeout=10, allow_redirects=True)
            return {
                'valid': response.status_code == 200,
                'reason': f"Status code: {response.status_code}" if response.status_code != 200 else "Valid"
            }
        except Exception as e:
            return {'valid': False, 'reason': f"Error: {str(e)}"}

    def _check_isbn(self, isbn: str) -> Dict:
        """Check ISBN in Open Library"""
        try:
            isbn_clean = re.sub(r'[^\d-X]', '', isbn)
            url = f"https://openlibrary.org/api/books"
            params = {'bibkeys': f'ISBN:{isbn_clean}', 'format': 'json', 'jscmd': 'data'}
            
            response = self.session.get(url, params=params, timeout=15)
            data = response.json()
            
            return {'found': bool(data), 'data': data}
        except Exception as e:
            return {'found': False, 'reason': f"Error: {str(e)}"}

    def _search_by_title(self, title: str, ref_type: str) -> Dict:
        """Search for title in appropriate database"""
        try:
            if ref_type == 'journal':
                return self._search_crossref_title(title)
            elif ref_type == 'book':
                return self._search_openlibrary_title(title)
            else:
                return {'found': False, 'reason': 'Website titles not searchable'}
        except Exception as e:
            return {'found': False, 'reason': f"Search error: {str(e)}"}

    def _search_crossref_title(self, title: str) -> Dict:
        """Search Crossref for journal articles"""
        try:
            url = "https://api.crossref.org/works"
            params = {'query.title': title, 'rows': 3, 'select': 'title,DOI'}
            
            response = self.session.get(url, params=params, timeout=15)
            data = response.json()
            
            if 'message' in data and 'items' in data['message'] and data['message']['items']:
                # Simple title matching
                for item in data['message']['items']:
                    if 'title' in item and item['title']:
                        item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
                        similarity = self._calculate_similarity(title.lower(), item_title.lower())
                        if similarity > 0.6:
                            return {
                                'found': True,
                                'confidence': 'high' if similarity > 0.8 else 'medium',
                                'matched_title': item_title,
                                'similarity': similarity
                            }
            
            return {'found': False, 'reason': 'No similar titles found'}
        except Exception as e:
            return {'found': False, 'reason': f"Crossref error: {str(e)}"}

    def _search_openlibrary_title(self, title: str) -> Dict:
        """Search Open Library for books"""
        try:
            title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)[:5]
            query = ' '.join(title_words)
            
            url = "https://openlibrary.org/search.json"
            params = {'q': query, 'limit': 5}
            
            response = self.session.get(url, params=params, timeout=15)
            data = response.json()
            
            if 'docs' in data and data['docs']:
                for doc in data['docs']:
                    if 'title' in doc:
                        similarity = self._calculate_similarity(title.lower(), doc['title'].lower())
                        if similarity > 0.6:
                            return {
                                'found': True,
                                'confidence': 'high' if similarity > 0.8 else 'medium',
                                'matched_title': doc['title'],
                                'similarity': similarity
                            }
            
            return {'found': False, 'reason': 'No similar book titles found'}
        except Exception as e:
            return {'found': False, 'reason': f"Open Library error: {str(e)}"}

    def _check_url_accessibility(self, url: str) -> Dict:
        """Check if URL is accessible"""
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            response = self.session.head(url, timeout=10, allow_redirects=True)
            return {
                'accessible': response.status_code == 200,
                'reason': f"Status: {response.status_code}" if response.status_code != 200 else "Accessible"
            }
        except Exception as e:
            return {'accessible': False, 'reason': f"Error: {str(e)}"}

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Simple word-based similarity calculation"""
        words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', str1.lower()))
        words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', str2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

class AuthenticityFirstVerifier:
    def __init__(self):
        self.parser = AuthenticityFirstParser()
        self.authenticity_checker = SimpleAuthenticityChecker()

    def verify_references(self, text: str, format_type: str) -> List[Dict]:
        """Verify references: Authenticity FIRST, then formatting"""
        lines = text.strip().split('\n')
        results = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or len(line) < 30:
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
                'format_check': {}
            }
            
            # Step 1: Extract elements flexibly for authenticity checking
            elements = self.parser.extract_elements_flexibly(line)
            result['extracted_elements'] = elements
            result['reference_type'] = elements['reference_type']
            
            # Step 2: Check authenticity FIRST
            authenticity_result = self.authenticity_checker.check_authenticity(elements)
            result['authenticity_check'] = authenticity_result
            
            if authenticity_result['is_authentic']:
                result['authenticity_status'] = 'authentic'
                
                # Step 3: Only THEN check formatting (for authentic references)
                format_check = self.parser.check_apa_format_compliance(line, elements['reference_type'])
                result['format_check'] = format_check
                
                if format_check['is_compliant']:
                    result['format_status'] = 'compliant'
                    result['overall_status'] = 'valid'
                else:
                    result['format_status'] = 'format_issues'
                    result['overall_status'] = 'authentic_but_poor_format'
            else:
                result['authenticity_status'] = 'likely_fake'
                result['overall_status'] = 'likely_fake'
                # Don't waste time on format checking for fake references
            
            results.append(result)
            time.sleep(0.5)  # Rate limiting
        
        return results

def main():
    st.set_page_config(
        page_title="Authenticity-First Reference Verifier",
        page_icon="🔍",
        layout="wide"
    )
    
    st.title("🔍 Authenticity-First Reference Verifier")
    st.markdown("**Step 1**: Check if reference exists → **Step 2**: Check formatting")
    
    st.sidebar.header("Verification Order")
    st.sidebar.markdown("**🔍 New Approach:**")
    st.sidebar.markdown("1. **Authenticity Check** (Is it real?)")
    st.sidebar.markdown("   - DOI verification")
    st.sidebar.markdown("   - Database searches")
    st.sidebar.markdown("   - ISBN lookups")
    st.sidebar.markdown("2. **Format Check** (Is it properly formatted?)")
    st.sidebar.markdown("   - APA compliance")
    st.sidebar.markdown("   - Style violations")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**📊 Result Categories:**")
    st.sidebar.markdown("✅ **Valid**: Authentic + properly formatted")
    st.sidebar.markdown("⚠️ **Authentic but poor format**: Real paper, style issues")
    st.sidebar.markdown("🚨 **Likely fake**: Doesn't exist in databases")
    
    format_type = st.sidebar.selectbox("Reference Format", ["APA", "Vancouver"])
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📝 Input References")
        
        st.info("**Test the new approach**: Even with format errors, authentic references will be properly identified!")
        
        reference_text = st.text_area(
            "Paste your references here:",
            height=350,
            value="Kym Joanne Price, Brett Ashley Gordon, Stephen Richard Bird, Amanda Clare Benson, (2016). A review of guidelines for cardiac rehabilitation exercise programmes: Is there an international consensus?, European Journal of Sport, 23 (16), 1715–1733, https://doi.org/10.1177/2047487316657669",
            help="This reference has format issues but should be identified as authentic due to valid DOI"
        )
        
        verify_button = st.button("🔍 Verify References", type="primary", use_container_width=True)
        
        if st.button("📝 Add Fake Reference Test", use_container_width=True):
            fake_ref = "\n\nSmith, J. A. (2023). Completely made up research on fictional topics. Journal of Fake Studies, 99(1), 123-456. https://doi.org/10.1000/fakearticle"
            st.session_state.test_text = reference_text + fake_ref
    
    with col2:
        st.header("📊 Verification Results")
        
        if 'test_text' in st.session_state:
            reference_text = st.session_state.test_text
            del st.session_state.test_text
            verify_button = True
        
        if verify_button and reference_text.strip():
            with st.spinner("Checking authenticity first, then formatting..."):
                verifier = AuthenticityFirstVerifier()
                results = verifier.verify_references(reference_text, format_type)
            
            if results:
                # Summary statistics
                total = len(results)
                authentic = sum(1 for r in results if r['authenticity_status'] == 'authentic')
                valid = sum(1 for r in results if r['overall_status'] == 'valid')
                format_issues = sum(1 for r in results if r['overall_status'] == 'authentic_but_poor_format')
                likely_fake = sum(1 for r in results if r['overall_status'] == 'likely_fake')
                
                col_a, col_b, col_c, col_d = st.columns(4)
                with col_a:
                    st.metric("✅ Valid", valid)
                with col_b:
                    st.metric("⚠️ Format Issues", format_issues)
                with col_c:
                    st.metric("🔍 Authentic", authentic)
                with col_d:
                    st.metric("🚨 Likely Fake", likely_fake)
                
                st.markdown("---")
                
                # Detailed results
                for result in results:
                    ref_type = result['reference_type']
                    type_icons = {'journal': '📄', 'book': '📚', 'website': '🌐'}
                    type_icon = type_icons.get(ref_type, '📄')
                    
                    st.markdown(f"### {type_icon} Reference {result['line_number']} ({ref_type.title()})")
                    
                    status = result['overall_status']
                    
                    if status == 'valid':
                        st.success("✅ **Authentic and Properly Formatted**")
                        
                        auth_details = result['authenticity_check']['verification_details']
                        for detail in auth_details:
                            st.markdown(f"  🔍 {detail}")
                    
                    elif status == 'authentic_but_poor_format':
                        st.warning("⚠️ **Authentic Reference with Format Issues**")
                        
                        # Show authenticity verification
                        st.markdown("**✅ Authenticity Verified:**")
                        auth_details = result['authenticity_check']['verification_details']
                        for detail in auth_details:
                            st.markdown(f"  • {detail}")
                        
                        # Show format issues
                        st.markdown("**📝 Format Issues to Fix:**")
                        format_violations = result['format_check']['violations']
                        format_suggestions = result['format_check']['suggestions']
                        
                        for violation, suggestion in zip(format_violations, format_suggestions):
                            st.markdown(f"  • **{violation}**: {suggestion}")
                    
                    elif status == 'likely_fake':
                        st.error("🚨 **Likely Fake Reference**")
                        
                        st.markdown("**❌ No database verification found:**")
                        sources_checked = result['authenticity_check']['sources_checked']
                        verification_details = result['authenticity_check']['verification_details']
                        
                        st.markdown(f"  • **Sources checked**: {', '.join(sources_checked)}")
                        for detail in verification_details:
                            st.markdown(f"  • {detail}")
                    
                    # Show extracted elements
                    with st.expander("🔍 Extracted Elements"):
                        elements = result['extracted_elements']
                        for key, value in elements.items():
                            if value and key != 'extraction_method':
                                st.markdown(f"**{key.title()}**: {value}")
                    
                    # Show original reference
                    with st.expander("📄 Original Reference"):
                        st.code(result['reference'], language="text")
                    
                    st.markdown("---")
        
        elif verify_button:
            st.warning("Please enter some references to verify.")
    
    with st.expander("🆕 Why Authenticity-First is Better"):
        st.markdown("""
        **🔄 Old Approach (Format → Authenticity):**
        1. Check formatting first
        2. If format fails → "Invalid reference" 
        3. Never check if it's actually real
        
        **❌ Problem**: Real papers with minor format errors labeled as "invalid"
        
        ---
        
        **✅ New Approach (Authenticity → Format):**
        1. **Extract flexibly** (ignore format issues)
        2. **Check databases** (DOI, title search, ISBN)
        3. **If authentic** → then check formatting
        4. **If fake** → don't waste time on formatting
        
        **✅ Benefits**: 
        - Real papers identified even with format errors
        - Clear distinction between "fake" vs "poorly formatted"
        - Better user guidance on what to fix
        """)

if __name__ == "__main__":
    main()

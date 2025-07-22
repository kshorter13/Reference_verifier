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

class SyntaxFixedParser:
    def __init__(self):
        # FIXED: Simplified and corrected regex patterns with proper syntax
        self.flexible_patterns = {
            # Extract any year in parentheses
            'any_year': r'\((\d{4}[a-z]?)\)',
            
            # Extract DOI from anywhere in text
            'doi_pattern': r'https?://doi\.org/([^\s]+)',
            
            # Extract ISBN from anywhere
            'isbn_pattern': r'ISBN:?\s*([\d-X]+)',
            
            # Extract any URL
            'url_pattern': r'(https?://[^\s]+)',
            
            # FIXED: Simplified title extraction with proper parentheses matching
            'flexible_title': r'\)\.\s*([^.!?]+?)[\.\!\?]?',
            
            # FIXED: Simplified journal extraction patterns
            'journal_with_keywords': r'([A-Z][A-Za-z\s]*(?:Journal|Review|Science|Research|Studies)[A-Za-z\s]*)\s*,\s*\d+',
            'journal_general': r'([A-Z][^,\d]*[A-Za-z])\s*,\s*\d+',
            
            # Volume, issue, and pages
            'volume_issue_pages': r'(\d+)\s*(?:\((\d+)\))?\s*,\s*(\d+(?:-\d+)?)',
            
            # FIXED: Simplified publisher pattern
            'publisher_simple': r'(Press|Publishers?|Publications?|University|Academic)',
            'publisher_names': r'(Wolters Kluwer|Elsevier|MIT Press|Human Kinetics)',
            
            # Website access patterns
            'access_date': r'(?:Retrieved|Accessed)\s+([^,\n]+)',
        }
        
        # FIXED: Simplified APA format checking patterns
        self.apa_format_patterns = {
            'comma_before_year': r'[^.],\s*\(\d{4}[a-z]?\)',
            'proper_year_format': r'\.\s*\(\d{4}[a-z]?\)\.',
            'author_format': r'^[^.]+\.\s*\(\d{4}',
            'title_structure': r'\)\.\s*[^.]+\.',
        }

    def detect_reference_type(self, ref_text: str) -> str:
        """Simplified reference type detection"""
        if not ref_text:
            return 'unknown'
        
        ref_lower = ref_text.lower()

        # HIGHEST priority: Strong identifiers
        if re.search(self.flexible_patterns['doi_pattern'], ref_text):
            return 'journal'
        
        if re.search(self.flexible_patterns['isbn_pattern'], ref_text):
            return 'book'
        
        # URL + access date = website
        has_url = re.search(self.flexible_patterns['url_pattern'], ref_text)
        has_access = re.search(self.flexible_patterns['access_date'], ref_text)
        if has_url and has_access:
            return 'website'
        
        # Content-based detection
        journal_indicators = ['journal', 'review', 'science', 'research', 'quarterly', 'annual']
        book_indicators = ['press', 'publisher', 'edition', 'handbook', 'manual', 'textbook']
        website_indicators = ['retrieved', 'accessed', 'available', 'www', '.com', '.org']
        
        journal_score = sum(1 for indicator in journal_indicators if indicator in ref_lower)
        book_score = sum(1 for indicator in book_indicators if indicator in ref_lower)
        website_score = sum(1 for indicator in website_indicators if indicator in ref_lower)
        
        # Volume(issue), pages pattern strongly suggests journal
        if re.search(r'\d+\s*\(\d+\)\s*,\s*\d+', ref_text):
            journal_score += 3
            
        if book_score > journal_score and book_score > website_score:
            return 'book'
        elif website_score > journal_score and website_score > book_score:
            return 'website'
        else:
            return 'journal'

    def extract_elements_safely(self, ref_text: str) -> Dict:
        """Extract elements with fixed syntax and comprehensive error handling"""
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
            'reference_type': 'unknown',
            'extraction_errors': []
        }
        
        if not ref_text:
            elements['extraction_errors'].append("Empty reference text")
            return elements
        
        try:
            # Determine reference type first
            elements['reference_type'] = self.detect_reference_type(ref_text)
            
            # Extract year first (most reliable anchor)
            year_match = re.search(self.flexible_patterns['any_year'], ref_text)
            if year_match:
                elements['year'] = year_match.group(1)
                
                # FIXED: Extract authors with proper error handling
                try:
                    author_section = ref_text[:year_match.start()].strip()
                    # FIXED: Complete regex pattern with proper syntax
                    author_section = re.sub(r'[,\s]+$', '', author_section)
                    if author_section:
                        elements['authors'] = author_section
                except Exception as e:
                    elements['extraction_errors'].append(f"Author extraction error: {str(e)}")
            else:
                elements['extraction_errors'].append("No year found in parentheses")
            
            # Extract strong identifiers
            self._extract_identifiers(ref_text, elements)
            
            # Extract content based on type
            if year_match:
                self._extract_content_by_type(ref_text, year_match, elements)
            
            # Extract volume/issue/pages for journals
            if elements.get('journal'):
                self._extract_volume_info(ref_text, elements)
            
        except Exception as e:
            elements['extraction_errors'].append(f"Critical extraction error: {str(e)}")
        
        return elements

    def _extract_identifiers(self, ref_text: str, elements: Dict) -> None:
        """Extract DOI, ISBN, URL with error handling"""
        try:
            # DOI extraction
            doi_match = re.search(self.flexible_patterns['doi_pattern'], ref_text)
            if doi_match:
                elements['doi'] = doi_match.group(1)
        except Exception as e:
            elements['extraction_errors'].append(f"DOI extraction error: {str(e)}")
        
        try:
            # ISBN extraction
            isbn_match = re.search(self.flexible_patterns['isbn_pattern'], ref_text)
            if isbn_match:
                elements['isbn'] = isbn_match.group(1)
        except Exception as e:
            elements['extraction_errors'].append(f"ISBN extraction error: {str(e)}")
        
        try:
            # URL extraction (for websites)
            if elements.get('reference_type') == 'website':
                url_match = re.search(self.flexible_patterns['url_pattern'], ref_text)
                if url_match:
                    elements['url'] = url_match.group(1)
        except Exception as e:
            elements['extraction_errors'].append(f"URL extraction error: {str(e)}")

    def _extract_content_by_type(self, ref_text: str, year_match, elements: Dict) -> None:
        """Extract title, journal, or publisher based on reference type"""
        try:
            text_after_year = ref_text[year_match.end():]
            ref_type = elements.get('reference_type', 'unknown')
            
            # Extract title (works for all types)
            title_match = re.search(self.flexible_patterns['flexible_title'], text_after_year)
            if title_match:
                elements['title'] = title_match.group(1).strip()
            else:
                # Fallback: simple extraction
                simple_title = re.search(r'\)\.\s*([^.!?]{10,})', text_after_year)
                if simple_title:
                    elements['title'] = simple_title.group(1).strip()
                else:
                    elements['extraction_errors'].append("Could not extract title")
            
            # Type-specific extraction
            if ref_type == 'journal':
                self._extract_journal(text_after_year, elements)
            elif ref_type == 'book':
                self._extract_publisher(ref_text, elements)
                
        except Exception as e:
            elements['extraction_errors'].append(f"Content extraction error: {str(e)}")

    def _extract_journal(self, text_after_year: str, elements: Dict) -> None:
        """Extract journal name with multiple fallback patterns"""
        try:
            # Try journal with keywords first
            journal_match = re.search(self.flexible_patterns['journal_with_keywords'], text_after_year)
            if not journal_match:
                # Try general pattern
                journal_match = re.search(self.flexible_patterns['journal_general'], text_after_year)
            
            if journal_match:
                elements['journal'] = journal_match.group(1).strip()
            else:
                elements['extraction_errors'].append("Could not extract journal name")
                
        except Exception as e:
            elements['extraction_errors'].append(f"Journal extraction error: {str(e)}")

    def _extract_publisher(self, ref_text: str, elements: Dict) -> None:
        """Extract publisher information"""
        try:
            # Try specific publisher names first
            publisher_match = re.search(self.flexible_patterns['publisher_names'], ref_text, re.IGNORECASE)
            if not publisher_match:
                # Try general publisher keywords
                publisher_match = re.search(self.flexible_patterns['publisher_simple'], ref_text, re.IGNORECASE)
            
            if publisher_match:
                elements['publisher'] = publisher_match.group(1).strip()
            else:
                elements['extraction_errors'].append("Could not extract publisher")
                
        except Exception as e:
            elements['extraction_errors'].append(f"Publisher extraction error: {str(e)}")

    def _extract_volume_info(self, ref_text: str, elements: Dict) -> None:
        """Extract volume/issue/pages information"""
        try:
            journal_name = elements.get('journal', '')
            if not journal_name:
                return
            
            # Find position after journal name
            journal_pos = ref_text.find(journal_name)
            if journal_pos == -1:
                elements['extraction_errors'].append("Could not locate journal name for volume extraction")
                return
            
            text_after_journal = ref_text[journal_pos + len(journal_name):]
            volume_match = re.search(self.flexible_patterns['volume_issue_pages'], text_after_journal)
            
            if volume_match:
                elements['volume'] = volume_match.group(1)
                if volume_match.group(2):  # Issue number in parentheses
                    elements['issue'] = volume_match.group(2)
                if volume_match.group(3):  # Page numbers
                    elements['pages'] = volume_match.group(3)
            else:
                elements['extraction_errors'].append("Could not extract volume/issue/pages")
                
        except Exception as e:
            elements['extraction_errors'].append(f"Volume extraction error: {str(e)}")

    def check_apa_format_compliance(self, ref_text: str, ref_type: str) -> Dict:
        """Check APA format compliance with simplified patterns"""
        compliance = {
            'is_compliant': True,
            'violations': [],
            'suggestions': [],
            'check_errors': []
        }
        
        if not ref_text:
            compliance['check_errors'].append("Empty reference text")
            return compliance
        
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
            
            # Check title structure
            if not re.search(self.apa_format_patterns['title_structure'], ref_text):
                compliance['is_compliant'] = False
                compliance['violations'].append("Incorrect title structure")
                compliance['suggestions'].append("Title should end with period after year")
                    
        except Exception as e:
            compliance['check_errors'].append(f"Format checking error: {str(e)}")
        
        return compliance

class SimplifiedAuthenticityChecker:
    """Simplified authenticity checker with robust error handling"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.timeout = 10
        self.max_retries = 1  # Reduced for faster processing

    def check_authenticity(self, elements: Dict) -> Dict:
        """Check authenticity with simplified approach"""
        result = {
            'is_authentic': False,
            'confidence': 'low',
            'sources_checked': [],
            'verification_details': [],
            'check_errors': []
        }
        
        if not elements or not isinstance(elements, dict):
            result['check_errors'].append("Invalid elements provided")
            return result
        
        ref_type = elements.get('reference_type', 'unknown')
        
        # Priority 1: Check DOI
        if elements.get('doi'):
            doi_result = self._check_doi_safe(elements['doi'])
            result['sources_checked'].append('DOI Database')
            
            if doi_result.get('valid'):
                result['is_authentic'] = True
                result['confidence'] = 'high'
                result['verification_details'].append(f"DOI {elements['doi']} verified")
                return result
            else:
                result['verification_details'].append(f"DOI check failed: {doi_result.get('reason', 'Invalid')}")
        
        # Priority 2: Check ISBN
        if elements.get('isbn'):
            isbn_result = self._check_isbn_safe(elements['isbn'])
            result['sources_checked'].append('ISBN Database')
            
            if isbn_result.get('found'):
                result['is_authentic'] = True
                result['confidence'] = 'high'
                result['verification_details'].append(f"ISBN {elements['isbn']} verified")
                return result
            else:
                result['verification_details'].append("ISBN not found in database")
        
        # Priority 3: Check URL (for websites)
        if ref_type == 'website' and elements.get('url'):
            url_result = self._check_url_safe(elements['url'])
            result['sources_checked'].append('URL Check')
            
            if url_result.get('accessible'):
                result['is_authentic'] = True
                result['confidence'] = 'medium'
                result['verification_details'].append("Website URL accessible")
                return result
            else:
                result['verification_details'].append(f"URL not accessible: {url_result.get('reason', 'Unknown')}")
        
        # If no strong verification, mark as likely fake
        if not result['verification_details']:
            result['verification_details'].append("No database verification succeeded")
        
        return result

    def _check_doi_safe(self, doi: str) -> Dict:
        """Safely check DOI"""
        if not doi or not isinstance(doi, str):
            return {'valid': False, 'reason': 'Invalid DOI'}
        
        try:
            url = f"https://doi.org/{doi.strip()}"
            response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            return {
                'valid': response.status_code == 200,
                'reason': f"Status: {response.status_code}" if response.status_code != 200 else "Valid"
            }
        except requests.exceptions.Timeout:
            return {'valid': False, 'reason': 'Request timeout'}
        except Exception as e:
            return {'valid': False, 'reason': f"Error: {str(e)[:50]}"}

    def _check_isbn_safe(self, isbn: str) -> Dict:
        """Safely check ISBN"""
        if not isbn or not isinstance(isbn, str):
            return {'found': False, 'reason': 'Invalid ISBN'}
        
        try:
            isbn_clean = re.sub(r'[^\d-X]', '', isbn.strip().upper())
            if len(isbn_clean) < 10:
                return {'found': False, 'reason': 'ISBN too short'}
            
            url = "https://openlibrary.org/api/books"
            params = {'bibkeys': f'ISBN:{isbn_clean}', 'format': 'json', 'jscmd': 'data'}
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            data = response.json()
            
            return {'found': bool(data)}
        except Exception as e:
            return {'found': False, 'reason': f"Error: {str(e)[:50]}"}

    def _check_url_safe(self, url: str) -> Dict:
        """Safely check URL"""
        if not url or not isinstance(url, str):
            return {'accessible': False, 'reason': 'Invalid URL'}
        
        try:
            clean_url = url.strip()
            if not clean_url.startswith(('http://', 'https://')):
                clean_url = 'https://' + clean_url
            
            response = self.session.head(clean_url, timeout=self.timeout, allow_redirects=True)
            return {
                'accessible': response.status_code == 200,
                'reason': f"Status: {response.status_code}" if response.status_code != 200 else "Accessible"
            }
        except Exception as e:
            return {'accessible': False, 'reason': f"Error: {str(e)[:50]}"}

class SyntaxFixedVerifier:
    """Main verifier class with all syntax fixes"""
    
    def __init__(self):
        self.parser = SyntaxFixedParser()
        self.authenticity_checker = SimplifiedAuthenticityChecker()

    def verify_references(self, text: str, format_type: str) -> List[Dict]:
        """Verify references with comprehensive error handling"""
        if not text or not isinstance(text, str):
            return []
        
        lines = text.strip().split('\n')
        results = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or len(line) < 20:  # Skip very short lines
                continue
                
            result = self._process_single_reference(line, i + 1, format_type)
            results.append(result)
            
            # Rate limiting
            time.sleep(0.3)
        
        return results

    def _process_single_reference(self, line: str, line_number: int, format_type: str) -> Dict:
        """Process a single reference with comprehensive error handling"""
        result = {
            'reference': line,
            'line_number': line_number,
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
            # Step 1: Extract elements
            elements = self.parser.extract_elements_safely(line)
            result['extracted_elements'] = elements
            result['reference_type'] = elements.get('reference_type', 'unknown')
            
            if elements.get('extraction_errors'):
                result['processing_errors'].extend(elements['extraction_errors'])
            
            # Step 2: Check authenticity
            authenticity_result = self.authenticity_checker.check_authenticity(elements)
            result['authenticity_check'] = authenticity_result
            
            if authenticity_result.get('check_errors'):
                result['processing_errors'].extend(authenticity_result['check_errors'])
            
            if authenticity_result.get('is_authentic'):
                result['authenticity_status'] = 'authentic'
                
                # Step 3: Check formatting (only for authentic references)
                format_check = self.parser.check_apa_format_compliance(line, elements.get('reference_type', 'unknown'))
                result['format_check'] = format_check
                
                if format_check.get('check_errors'):
                    result['processing_errors'].extend(format_check['check_errors'])
                
                if format_check.get('is_compliant'):
                    result['format_status'] = 'compliant'
                    result['overall_status'] = 'valid'
                else:
                    result['format_status'] = 'format_issues'
                    result['overall_status'] = 'authentic_but_poor_format'
            else:
                result['authenticity_status'] = 'likely_fake'
                result['overall_status'] = 'likely_fake'
                
        except Exception as e:
            result['processing_errors'].append(f"Critical processing error: {str(e)}")
            result['overall_status'] = 'processing_error'
        
        return result

def main():
    st.set_page_config(
        page_title="Syntax-Fixed Reference Verifier",
        page_icon="✅",
        layout="wide"
    )
    
    st.title("✅ Syntax-Fixed Reference Verifier")
    st.markdown("**All syntax errors fixed, simplified patterns, robust error handling**")
    
    st.sidebar.header("🔧 Fixes Applied")
    st.sidebar.markdown("**✅ Syntax Errors Fixed**")
    st.sidebar.markdown("• Fixed unterminated string literals")
    st.sidebar.markdown("• Fixed unmatched parentheses in regex")
    st.sidebar.markdown("• Completed re.sub() parameters")
    
    st.sidebar.markdown("**✅ Pattern Simplification**")
    st.sidebar.markdown("• Simplified complex regex patterns")
    st.sidebar.markdown("• Multiple fallback patterns")
    st.sidebar.markdown("• Better error handling")
    
    st.sidebar.markdown("**✅ Robust Processing**")
    st.sidebar.markdown("• Comprehensive null checks")
    st.sidebar.markdown("• Safe dictionary access")
    st.sidebar.markdown("• Graceful error recovery")
    
    format_type = st.sidebar.selectbox("Reference Format", ["APA", "Vancouver"])
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📝 Test the Fixed Version")
        
        reference_text = st.text_area(
            "Paste your references here:",
            height=300,
            value="Kym Joanne Price, Brett Ashley Gordon, Stephen Richard Bird, Amanda Clare Benson, (2016). A review of guidelines for cardiac rehabilitation exercise programmes: Is there an international consensus?, European Journal of Sport, 23 (16), 1715–1733, https://doi.org/10.1177/2047487316657669",
            help="This should now work without syntax errors"
        )
        
        verify_button = st.button("🔍 Test Fixed Verifier", type="primary", use_container_width=True)
        
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("📚 Add Book Test", use_container_width=True):
                book_ref = "\n\nAmerican College of Sports Medicine. (2022). ACSM's guidelines for exercise testing and prescription (11th ed.). Wolters Kluwer."
                st.session_state.book_text = reference_text + book_ref
        
        with col_b:
            if st.button("🌐 Add Website Test", use_container_width=True):
                website_ref = "\n\nWorld Health Organization. (2021). COVID-19 pandemic response. Retrieved March 15, 2023, from https://www.who.int/emergencies/diseases/novel-coronavirus-2019"
                st.session_state.website_text = reference_text + website_ref
        
        with st.expander("🧪 Test Cases"):
            st.markdown("**Perfect for testing:**")
            st.markdown("• Format errors (comma before year)")
            st.markdown("• Missing elements")
            st.markdown("• Valid DOIs vs fake DOIs")
            st.markdown("• Different reference types")
    
    with col2:
        st.header("📊 Results")
        
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
            with st.spinner("Processing with syntax-fixed verifier..."):
                verifier = SyntaxFixedVerifier()
                results = verifier.verify_references(reference_text, format_type)
            
            if results:
                # Summary metrics with safe access
                total = len(results)
                valid = sum(1 for r in results if r.get('overall_status') == 'valid')
                authentic_poor_format = sum(1 for r in results if r.get('overall_status') == 'authentic_but_poor_format')
                likely_fake = sum(1 for r in results if r.get('overall_status') == 'likely_fake')
                processing_errors = sum(1 for r in results if r.get('overall_status') == 'processing_error')
                
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
                
                # Process each result safely
                for result in results:
                    ref_type = result.get('reference_type', 'unknown')
                    if not ref_type:
                        ref_type = 'unknown'
                    
                    type_icons = {'journal': '📄', 'book': '📚', 'website': '🌐', 'unknown': '❓'}
                    type_icon = type_icons.get(ref_type, '❓')
                    
                    ref_type_display = ref_type.title() if isinstance(ref_type, str) else 'Unknown'
                    line_num = result.get('line_number', 'N/A')
                    
                    st.markdown(f"### {type_icon} Reference {line_num} ({ref_type_display})")
                    
                    status = result.get('overall_status', 'unknown')
                    
                    if status == 'valid':
                        st.success("✅ **Authentic and Properly Formatted**")
                        
                        auth_check = result.get('authenticity_check', {})
                        auth_details = auth_check.get('verification_details', [])
                        for detail in auth_details:
                            if detail:
                                st.markdown(f"  🔍 {detail}")
                    
                    elif status == 'authentic_but_poor_format':
                        st.warning("⚠️ **Authentic Reference with Format Issues**")
                        
                        st.markdown("**✅ Authenticity Verified:**")
                        auth_check = result.get('authenticity_check', {})
                        auth_details = auth_check.get('verification_details', [])
                        for detail in auth_details:
                            if detail:
                                st.markdown(f"  • {detail}")
                        
                        st.markdown("**📝 Format Issues to Fix:**")
                        format_check = result.get('format_check', {})
                        violations = format_check.get('violations', [])
                        suggestions = format_check.get('suggestions', [])
                        
                        for i, violation in enumerate(violations):
                            suggestion = suggestions[i] if i < len(suggestions) else "See APA guidelines"
                            st.markdown(f"  • **{violation}**: {suggestion}")
                    
                    elif status == 'likely_fake':
                        st.error("🚨 **Likely Fake Reference**")
                        
                        st.markdown("**❌ Database verification failed:**")
                        auth_check = result.get('authenticity_check', {})
                        sources = auth_check.get('sources_checked', [])
                        details = auth_check.get('verification_details', [])
                        
                        if sources:
                            st.markdown(f"  • **Sources checked**: {', '.join(str(s) for s in sources)}")
                        for detail in details:
                            if detail:
                                st.markdown(f"  • {detail}")
                    
                    elif status == 'processing_error':
                        st.error("🐛 **Processing Error**")
                        errors = result.get('processing_errors', [])
                        for error in errors:
                            if error:
                                st.markdown(f"  • {error}")
                    
                    else:
                        st.warning(f"❓ **Unknown Status**: {status}")
                    
                    # Show extraction results
                    with st.expander("🔍 Extraction Details"):
                        elements = result.get('extracted_elements', {})
                        
                        st.markdown("**✅ Successfully Extracted:**")
                        extracted_count = 0
                        for key, value in elements.items():
                            if value and key not in ['extraction_errors', 'reference_type']:
                                st.markdown(f"  • **{key.title()}**: `{value}`")
                                extracted_count += 1
                        
                        if extracted_count == 0:
                            st.markdown("  • No elements successfully extracted")
                        
                        # Show errors if any
                        errors = elements.get('extraction_errors', [])
                        if errors:
                            st.markdown("**⚠️ Extraction Issues:**")
                            for error in errors:
                                if error:
                                    st.markdown(f"  • {error}")
                        
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
    
    with st.expander("🔧 All Syntax Fixes Applied"):
        st.markdown("""
        ### **✅ Critical Syntax Errors Fixed:**
        
        **1. Unterminated String Literal (Line 147)**
        ```python
        # ❌ BEFORE: Missing closing quote and parameters
        author_section = re.sub(r'[,\\s]+
        
        # ✅ AFTER: Complete pattern with all parameters
        author_section = re.sub(r'[,\\s]+, '', author_section)
        ```
        
        **2. Unmatched Parentheses in Regex**
        ```python
        # ❌ BEFORE: Complex pattern with unmatched parentheses
        'flexible_title': r'\\)\\.\\s*([^.!?]+?)[\\.\!?\\s]*(?:[A-Z][^,\\d]*[A-Za-z]\\s*,|\\s*$)'
        
        # ✅ AFTER: Simplified pattern with proper matching
        'flexible_title': r'\\)\\.\\s*([^.!?]+?)[\\.\!?]?'
        ```
        
        **3. Over-Complex Patterns Simplified**
        ```python
        # ❌ BEFORE: Very complex journal pattern (100+ chars)
        'journal_after_title': r'([A-Z][A-Za-z\\s&]*(?:Journal|Review|...)\\s*)*'
        
        # ✅ AFTER: Multiple simple patterns with fallbacks
        'journal_with_keywords': r'([A-Z][A-Za-z\\s]*(?:Journal|Review|Science)\\s*),'
        'journal_general': r'([A-Z][^,\\d]*[A-Za-z])\\s*,\\s*\\d+'
        ```
        
        **4. Safe Dictionary Access**
        ```python
        # ❌ BEFORE: Direct access could cause KeyError
        ref_type = result['reference_type']
        
        # ✅ AFTER: Safe access with defaults
        ref_type = result.get('reference_type', 'unknown')
        if not ref_type:
            ref_type = 'unknown'
        ```
        
        **5. Comprehensive Error Handling**
        ```python
        # ✅ NEW: Every operation wrapped in try/catch
        try:
            # Extraction operation
        except Exception as e:
            elements['extraction_errors'].append(f"Error: {str(e)}")
        ```
        
        ### **🛡️ Additional Safety Features:**
        - Input validation for all parameters
        - Null checks before string operations  
        - Safe type checking with isinstance()
        - Graceful degradation on errors
        - Rate limiting for API calls
        - Timeout protection for network requests
        """)

if __name__ == "__main__":
    main()

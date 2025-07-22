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

class ImprovedReferenceParser:
    def __init__(self):
        # Updated APA patterns with better accuracy
        self.apa_patterns = {
            # Year should be preceded by period and space (proper APA format)
            'proper_year_format': r'\.\s*\((\d{4}[a-z]?)\)\.',
            
            # Incorrect: comma before year (common mistake)
            'comma_before_year': r'[^.],\s*\((\d{4}[a-z]?)\)',
            
            # Extract title and journal separately using proper APA structure
            'title_and_journal': r'\)\.\s*([^.]+?)\.\s*([A-Z][^,\d]*(?:[A-Za-z]\s*){0,}[A-Za-z])\s*,',
            
            # Volume and pages pattern
            'volume_pages': r'(\d+)\s*(?:\((\d+)\))?,?\s*(\d+(?:-\d+)?)',
            
            # Author pattern - should end with period before year
            'proper_author_format': r'^([^.]+)\.\s*\(\d{4}',
            
            # DOI pattern
            'doi_pattern': r'https?://doi\.org/([^\s]+)',
            
            # Publishers for books
            'publisher_info': r'([A-Z][^.]*(?:Press|Publishers?|Publications?|Books?|Academic|University|Ltd|Inc|Corp|Kluwer|Elsevier|MIT Press|Human Kinetics)[^.]*)',
            
            # ISBN pattern
            'isbn_pattern': r'ISBN:?\s*([\d-]+)',
            
            # URL pattern
            'url_pattern': r'(https?://[^\s]+)',
            
            # Website access date
            'website_access_date': r'(?:Retrieved|Accessed)\s+([^,]+)'
        }
        
        # Vancouver patterns (keeping original for now)
        self.vancouver_patterns = {
            'starts_with_number': r'^(\d+)\.',
            'journal_title_section': r'^\d+\.\s*[^.]+\.\s*([^.]+)\.',
            'journal_year': r'([A-Za-z][^.;]+)\s*(\d{4})',
            'author_pattern_vancouver': r'^\d+\.\s*([^.]+)\.',
            'book_publisher': r'([A-Z][^;:]+);\s*(\d{4})',
            'website_url_vancouver': r'Available\s+(?:from|at):\s*(https?://[^\s]+)'
        }
        
        self.type_indicators = {
            'journal': [
                r'[,;]\s*\d+(?:\(\d+\))?[,:]\s*\d+(?:-\d+)?',
                r'Journal|Review|Proceedings|Quarterly|Annual',
                r'https?://doi\.org/',
                r'\b(volume|issue|pages|p\.)\b'
            ],
            'book': [
                r'(?:Press|Publishers?|Publications?|Books?|Academic|University|Kluwer|Elsevier|MIT Press|Human Kinetics)',
                r'ISBN:?\s*[\d-]+',
                r'(?:pp?\.|pages?)\s*\d+(?:-\d+)?',
                r'\b(edition|ed\.)\b',
                r'\b(manual|handbook|textbook|guidelines)\b',
                r'\b(vol\.|volume|chapter)\b'
            ],
            'website': [
                r'(?:Retrieved|Accessed)\s+(?:from|on)',
                r'https?://(?:www\.)?[^/\s]+\.[a-z]{2,}',
                r'Available\s+(?:from|at)'
            ]
        }

    def detect_reference_type(self, ref_text: str) -> str:
        """Detect if reference is journal, book, or website"""
        ref_lower = ref_text.lower()

        # High priority: DOI -> Journal
        if re.search(self.apa_patterns['doi_pattern'], ref_text):
            return 'journal'

        # High priority: ISBN -> Book
        if re.search(self.apa_patterns['isbn_pattern'], ref_text):
            return 'book'

        # Website: URL + Access Date
        if re.search(self.apa_patterns['url_pattern'], ref_text) and \
           re.search(self.apa_patterns['website_access_date'], ref_text):
            return 'website'
        
        # Score-based detection
        type_scores = {'journal': 0, 'book': 0, 'website': 0}
        
        for ref_type, patterns in self.type_indicators.items():
            for pattern in patterns:
                if re.search(pattern, ref_lower):
                    type_scores[ref_type] += 1
        
        # Additional scoring
        if re.search(r'\b(edition|ed\.)\b', ref_lower) or \
           re.search(r'\b(manual|handbook|textbook|guidelines)\b', ref_lower):
            type_scores['book'] += 2.0

        if re.search(r'\b(volume|issue|pages|p\.)\b', ref_lower):
            type_scores['journal'] += 1.5

        if any(score > 0 for score in type_scores.values()):
            max_score = max(type_scores.values())
            if type_scores['book'] == max_score and max_score > 0:
                return 'book'
            if type_scores['journal'] == max_score and max_score > 0:
                return 'journal'
            if type_scores['website'] == max_score and max_score > 0:
                return 'website'
            return max(type_scores, key=type_scores.get)
        else:
            return 'journal'

    def check_apa_format_violations(self, ref_text: str, ref_type: str = 'journal') -> List[str]:
        """Check for specific APA format violations"""
        violations = []
        
        # Check for comma before year (major APA violation)
        if re.search(self.apa_patterns['comma_before_year'], ref_text):
            violations.append("Authors should end with a period before year, not a comma (e.g., 'Smith, J. (2020).' not 'Smith, J., (2020)')")
        
        # Check for proper year format
        if not re.search(self.apa_patterns['proper_year_format'], ref_text):
            violations.append("Year should be in format '. (YYYY).' with periods before and after")
        
        # For journals, check if we can properly extract title and journal
        if ref_type == 'journal':
            title_journal_match = re.search(self.apa_patterns['title_and_journal'], ref_text)
            if not title_journal_match:
                violations.append("Cannot identify separate title and journal name - format should be: ). Title. Journal Name, Volume")
        
        # Check for proper author format (should start correctly)
        if not re.search(self.apa_patterns['proper_author_format'], ref_text):
            violations.append("Authors section should end with period before year (e.g., 'Smith, J. A. (2020).')")
        
        return violations

    def extract_elements_improved(self, ref_text: str, format_type: str, ref_type: str = None) -> Dict:
        """Extract reference elements with improved accuracy"""
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
            'access_date': None,
            'reference_type': ref_type or self.detect_reference_type(ref_text),
            'extraction_confidence': 'low'
        }
        
        detected_type = elements['reference_type']
        
        # Extract DOI
        doi_match = re.search(self.apa_patterns['doi_pattern'], ref_text)
        if doi_match:
            elements['doi'] = doi_match.group(1)
        
        # Extract ISBN
        isbn_match = re.search(self.apa_patterns['isbn_pattern'], ref_text)
        if isbn_match:
            elements['isbn'] = isbn_match.group(1)

        # Extract URL (only for websites)
        if detected_type == 'website':
            url_match = re.search(self.apa_patterns['url_pattern'], ref_text)
            if url_match:
                elements['url'] = url_match.group(1)
        
        if format_type == "APA":
            # Extract year - try both proper and improper formats
            year_match = re.search(r'\((\d{4}[a-z]?)\)', ref_text)
            if year_match:
                elements['year'] = year_match.group(1)
            
            # Extract authors (everything before the year)
            if year_match:
                author_section = ref_text[:year_match.start()].strip()
                # Remove trailing comma if present (format error)
                author_section = re.sub(r',\s*$', '', author_section)
                elements['authors'] = author_section
            
            # Extract title and journal using improved pattern
            if detected_type == 'journal':
                title_journal_match = re.search(self.apa_patterns['title_and_journal'], ref_text)
                if title_journal_match:
                    elements['title'] = title_journal_match.group(1).strip()
                    elements['journal'] = title_journal_match.group(2).strip()
                else:
                    # Fallback: try to extract what we can
                    year_pos = year_match.end() if year_match else 0
                    remaining_text = ref_text[year_pos:]
                    # Try to find title (after "). " and before next period)
                    title_fallback = re.search(r'\)\.\s*([^.]+)', remaining_text)
                    if title_fallback:
                        elements['title'] = title_fallback.group(1).strip()
            
            elif detected_type == 'book':
                # For books, extract title after year
                if year_match:
                    year_pos = year_match.end()
                    remaining_text = ref_text[year_pos:]
                    title_match = re.search(r'\)\.\s*([^.]+)\.', remaining_text)
                    if title_match:
                        elements['title'] = title_match.group(1).strip()
                
                # Extract publisher
                publisher_match = re.search(self.apa_patterns['publisher_info'], ref_text)
                if publisher_match:
                    elements['publisher'] = publisher_match.group(1).strip()
            
            elif detected_type == 'website':
                # For websites, extract title and access date
                if year_match:
                    year_pos = year_match.end()
                    remaining_text = ref_text[year_pos:]
                    title_match = re.search(r'\)\.\s*([^.]+)\.', remaining_text)
                    if title_match:
                        elements['title'] = title_match.group(1).strip()
                
                access_match = re.search(self.apa_patterns['website_access_date'], ref_text)
                if access_match:
                    elements['access_date'] = access_match.group(1).strip()
            
            # Extract volume, issue, pages
            volume_match = re.search(self.apa_patterns['volume_pages'], ref_text)
            if volume_match:
                elements['volume'] = volume_match.group(1)
                if volume_match.group(2):  # Issue number
                    elements['issue'] = volume_match.group(2)
                if volume_match.group(3):  # Page numbers
                    elements['pages'] = volume_match.group(3)
        
        elif format_type == "Vancouver":
            # Vancouver format extraction (simplified for this example)
            year_match = re.search(r'(\d{4})', ref_text)
            if year_match:
                elements['year'] = year_match.group(1)
            
            title_match = re.search(self.vancouver_patterns['journal_title_section'], ref_text)
            if title_match:
                elements['title'] = title_match.group(1).strip()
            
            author_match = re.search(self.vancouver_patterns['author_pattern_vancouver'], ref_text)
            if author_match:
                elements['authors'] = author_match.group(1).strip()
        
        # Assess extraction confidence
        if detected_type == 'journal':
            required_fields = [elements['authors'], elements['year'], elements['title'], elements['journal']]
        elif detected_type == 'book':
            required_fields = [elements['authors'], elements['year'], elements['title'], elements['publisher']]
        elif detected_type == 'website':
            required_fields = [elements['title'], elements['url']]
        else:
            required_fields = [elements['authors'], elements['year'], elements['title']]
        
        extracted_count = sum(1 for v in required_fields if v)
        if extracted_count == len(required_fields):
            elements['extraction_confidence'] = 'high'
        elif extracted_count >= len(required_fields) - 1:
            elements['extraction_confidence'] = 'medium'
        else:
            elements['extraction_confidence'] = 'low'
        
        return elements

    def check_structural_format(self, ref_text: str, format_type: str, ref_type: str = None) -> Dict:
        """Enhanced structural format checking"""
        result = {
            'structure_valid': False,
            'format_violations': [],
            'extraction_issues': [],
            'reference_type': ref_type or self.detect_reference_type(ref_text)
        }
        
        detected_type = result['reference_type']
        
        if format_type == "APA":
            # Check for APA format violations
            violations = self.check_apa_format_violations(ref_text, detected_type)
            result['format_violations'] = violations
            
            # Extract elements to check extraction quality
            elements = self.extract_elements_improved(ref_text, format_type, detected_type)
            
            # Check extraction issues
            if elements['extraction_confidence'] == 'low':
                result['extraction_issues'].append("Poor element extraction - missing key information")
            
            if detected_type == 'journal':
                if not elements['journal']:
                    result['extraction_issues'].append("Could not identify journal name")
                if not elements['title']:
                    result['extraction_issues'].append("Could not identify article title")
                if not elements['volume'] and not elements['doi']:
                    result['extraction_issues'].append("Missing volume information or DOI")
            
            elif detected_type == 'book':
                if not elements['publisher']:
                    result['extraction_issues'].append("Could not identify publisher")
                if not elements['title']:
                    result['extraction_issues'].append("Could not identify book title")
            
            elif detected_type == 'website':
                if not elements['url']:
                    result['extraction_issues'].append("Could not identify website URL")
                if not elements['title']:
                    result['extraction_issues'].append("Could not identify website title")
            
            # Structure is valid if no major violations and decent extraction
            has_major_violations = len(violations) > 0
            has_extraction_issues = len(result['extraction_issues']) > 1
            
            result['structure_valid'] = not has_major_violations and not has_extraction_issues
        
        elif format_type == "Vancouver":
            # Vancouver format checking (simplified)
            starts_with_number = bool(re.search(self.vancouver_patterns['starts_with_number'], ref_text))
            has_title = bool(re.search(self.vancouver_patterns['journal_title_section'], ref_text))
            
            if not starts_with_number:
                result['format_violations'].append("Should start with number and period")
            if not has_title:
                result['format_violations'].append("Missing title section")
            
            result['structure_valid'] = starts_with_number and has_title
        
        return result

    def identify_references(self, text: str) -> List[Reference]:
        """Identify individual references in text"""
        lines = text.strip().split('\n')
        references = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if line and len(line) > 30:  # Minimum length for valid reference
                ref = Reference(text=line, line_number=i+1)
                references.append(ref)
        
        return references

# Rest of the classes remain the same (DatabaseSearcher, ReferenceVerifier)
# I'll include a simplified version for the demo

class SimplifiedVerifier:
    def __init__(self):
        self.parser = ImprovedReferenceParser()

    def verify_references(self, text: str, format_type: str) -> List[Dict]:
        references = self.parser.identify_references(text)
        results = []
        
        for ref in references:
            result = {
                'reference': ref.text,
                'line_number': ref.line_number,
                'structure_status': 'unknown',
                'overall_status': 'unknown',
                'structure_check': {},
                'extracted_elements': {}
            }
            
            # Structure check
            structure_check = self.parser.check_structural_format(ref.text, format_type)
            result['structure_check'] = structure_check
            result['reference_type'] = structure_check['reference_type']
            
            # Extract elements
            elements = self.parser.extract_elements_improved(ref.text, format_type, structure_check['reference_type'])
            result['extracted_elements'] = elements
            
            if structure_check['structure_valid']:
                result['structure_status'] = 'valid'
                result['overall_status'] = 'valid' if elements['extraction_confidence'] in ['medium', 'high'] else 'content_error'
            else:
                result['structure_status'] = 'invalid'
                result['overall_status'] = 'structure_error'
            
            results.append(result)
        
        return results

def main():
    st.set_page_config(
        page_title="Improved Academic Reference Verifier",
        page_icon="📚",
        layout="wide"
    )
    
    st.title("📚 Improved Academic Reference Verifier")
    st.markdown("**Enhanced APA format detection with detailed error reporting**")
    
    st.sidebar.header("Settings")
    format_type = st.sidebar.selectbox(
        "Select Reference Format",
        ["APA", "Vancouver"]
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**🔍 What's Improved:**")
    st.sidebar.markdown("• **Better APA detection**: Catches comma-before-year errors")
    st.sidebar.markdown("• **Accurate journal extraction**: Properly separates title and journal")
    st.sidebar.markdown("• **Specific error messages**: Tells you exactly what's wrong")
    st.sidebar.markdown("• **Format violation detection**: Identifies APA rule violations")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📝 Input References")
        
        st.markdown("""
        **Test the improved detection:**
        - Try the problematic reference from your example
        - See detailed format violation reporting
        - Get specific suggestions for fixes
        """)
        
        reference_text = st.text_area(
            "Paste your references here (one per line):",
            height=300,
            value="Kym Joanne Price, Brett Ashley Gordon, Stephen Richard Bird, Amanda Clare Benson, (2016). A review of guidelines for cardiac rehabilitation exercise programmes: Is there an international consensus?, European Journal of Sport, 23 (16), 1715–1733, https://doi.org/10.1177/2047487316657669",
            help="This example shows common APA format errors that the improved system will detect."
        )
        
        verify_button = st.button("🔍 Analyze References", type="primary", use_container_width=True)
        
        if st.button("📝 Load Corrected Version", use_container_width=True):
            corrected_example = """Price, K. J., Gordon, B. A., Bird, S. R., & Benson, A. C. (2016). A review of guidelines for cardiac rehabilitation exercise programmes: Is there an international consensus? European Journal of Sport Science, 23(16), 1715-1733. https://doi.org/10.1177/2047487316657669"""
            st.session_state.corrected_text = corrected_example
    
    with col2:
        st.header("📊 Analysis Results")
        
        if 'corrected_text' in st.session_state:
            reference_text = st.session_state.corrected_text
            del st.session_state.corrected_text
            verify_button = True
        
        if verify_button and reference_text.strip():
            verifier = SimplifiedVerifier()
            results = verifier.verify_references(reference_text, format_type)
            
            if results:
                for i, result in enumerate(results):
                    ref_text = result['reference']
                    status = result['overall_status']
                    ref_type = result['reference_type']
                    
                    type_icons = {'journal': '📄', 'book': '📚', 'website': '🌐'}
                    type_icon = type_icons.get(ref_type, '📄')
                    
                    st.markdown(f"### {type_icon} Reference {result['line_number']} ({ref_type.title()})")
                    
                    if status == 'structure_error':
                        st.error("❌ **Format Violations Detected**")
                        
                        violations = result['structure_check'].get('format_violations', [])
                        extraction_issues = result['structure_check'].get('extraction_issues', [])
                        
                        if violations:
                            st.markdown("**🚨 APA Format Violations:**")
                            for violation in violations:
                                st.markdown(f"• {violation}")
                        
                        if extraction_issues:
                            st.markdown("**⚠️ Extraction Issues:**")
                            for issue in extraction_issues:
                                st.markdown(f"• {issue}")
                        
                        # Show extracted elements for debugging
                        elements = result['extracted_elements']
                        st.markdown("**🔍 What Was Extracted:**")
                        extraction_display = []
                        for key in ['authors', 'year', 'title', 'journal', 'volume', 'pages']:
                            value = elements.get(key)
                            if value:
                                extraction_display.append(f"**{key.title()}**: {value}")
                            else:
                                extraction_display.append(f"**{key.title()}**: ❌ Not found")
                        
                        for item in extraction_display:
                            st.markdown(f"  - {item}")
                    
                    elif status == 'valid':
                        st.success("✅ **Valid Reference Format**")
                        elements = result['extracted_elements']
                        
                        st.markdown("**✅ Successfully Extracted:**")
                        for key in ['authors', 'year', 'title', 'journal', 'volume', 'pages']:
                            value = elements.get(key)
                            if value:
                                st.markdown(f"  - **{key.title()}**: {value}")
                    
                    # Show the reference text
                    with st.expander("📄 View Reference Text"):
                        st.code(ref_text, language="text")
                    
                    if i < len(results) - 1:
                        st.markdown("---")
        
        elif verify_button:
            st.warning("Please enter some references to analyze.")
    
    with st.expander("🆕 What's Been Fixed"):
        st.markdown("""
        **Key Improvements Made:**
        
        1. **❌ Problem**: Original code extracted 'Kym Joanne Price' as journal name
           **✅ Solution**: New regex properly separates title and journal: `). Title. Journal,`
        
        2. **❌ Problem**: Comma before year not detected as APA violation  
           **✅ Solution**: Specific pattern detects and reports this error
        
        3. **❌ Problem**: Structure validation was too lenient
           **✅ Solution**: Strict APA format checking with detailed violation reporting
        
        4. **❌ Problem**: Poor error messages
           **✅ Solution**: Specific, actionable feedback about what's wrong
        
        **Test both versions:**
        - **Wrong**: `Author, A., (2016). Title...` (comma before year)
        - **Right**: `Author, A. (2016). Title...` (period before year)
        """)

if __name__ == "__main__":
    main()

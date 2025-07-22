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

class ReferenceParser:
    def __init__(self):
        self.apa_patterns = {
            'journal_year_in_parentheses': r'\((\d{4}[a-z]?)\)',
            'journal_title_after_year': r'\)\.\s*([^.]+)\.', # This is for a specific title format
            'volume_pages': r'(\d+)(?:\((\d+)\))?,?\s*(?:p\.?\s*)?(\d+(?:-\d+)?)\.?', # Added optional 'p.'
            'publisher_info': r'([A-Z][^.]*(?:Press|Publishers?|Publications?|Books?|Academic|University|Ltd|Inc|Corp|Kluwer|Elsevier|MIT Press|Human Kinetics)[^.]*)',
            'doi_pattern': r'https?://doi\.org/([^\s]+)',
            'author_pattern': r'^([^()]+?)(?:\s*\(\d{4}\))', # Corrected backslashes
            'isbn_pattern': r'ISBN:?\s*([\d-]+)',
            'url_pattern': r'(https?://[^\s]+)',
            'website_access_date': r'(?:Retrieved|Accessed)\\s+([^,]+)'
        }
        
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
        ref_lower = ref_text.lower()

        if re.search(self.apa_patterns['doi_pattern'], ref_text):
            return 'journal'

        if re.search(self.apa_patterns['isbn_pattern'], ref_text):
            return 'book'

        if re.search(self.apa_patterns['url_pattern'], ref_text) and \
           re.search(self.apa_patterns['website_access_date'], ref_text):
            return 'website'
        
        type_scores = {'journal': 0, 'book': 0, 'website': 0}
        
        for ref_type, patterns in self.type_indicators.items():
            for pattern in patterns:
                if re.search(pattern, ref_lower):
                    type_scores[ref_type] += 1
        
        if re.search(r'\b(edition|ed\.)\b', ref_lower) or \
           re.search(r'\b(manual|handbook|textbook|guidelines)\b', ref_lower) or \
           re.search(r'\b(vol\.|volume|chapter)\b', ref_lower):
            type_scores['book'] += 2.0

        if re.search(r'\b(volume|issue|pages|p\.)\b', ref_lower):
            type_scores['journal'] += 1.5

        if not (type_scores['journal'] >= 1.5 or type_scores['website'] >= 1.5):
            if re.search(r'\b(wolters kluwer|elsevier|mit press|university press|human kinetics)\b', ref_lower):
                type_scores['book'] += 1.0

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

    def identify_references(self, text: str) -> List[Reference]:
        lines = text.strip().split('\n')
        references = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if line and len(line) > 30:
                ref = Reference(text=line, line_number=i+1)
                references.append(ref)
        
        return references

    def check_structural_format(self, ref_text: str, format_type: str, ref_type: str = None) -> Dict:
        result = {
            'structure_valid': False,
            'structure_issues': [],
            'reference_type': ref_type or self.detect_reference_type(ref_text)
        }
        
        detected_type = result['reference_type']
        
        if format_type == "APA":
            has_year = bool(re.search(self.apa_patterns['journal_year_in_parentheses'], ref_text))
            has_title = bool(re.search(self.apa_patterns['journal_title_after_year'], ref_text))
            
            if detected_type == 'journal':
                # More flexible check for journal presence
                has_journal_like_text = bool(re.search(r'[A-Z][a-zA-Z\s&]+,?\s*\d+\(', ref_text)) or \
                                        bool(re.search(r'[A-Z][a-zA-Z\s&]+,\s*\d+-\d+\.', ref_text))
                has_numbers = bool(re.search(self.apa_patterns['volume_pages'], ref_text))
                has_doi_in_text = bool(re.search(self.apa_patterns['doi_pattern'], ref_text))
                
                if not has_year:
                    result['structure_issues'].append("Missing year in parentheses")
                if not has_title:
                    result['structure_issues'].append("Missing article title after year")
                if not has_journal_like_text: # Use the more flexible check
                    result['structure_issues'].append("Missing or malformed journal information")
                if not has_numbers:
                    result['structure_issues'].append("Missing volume/page numbers")
                if not has_doi_in_text:
                    result['structure_issues'].append("Missing DOI")
                
                result['structure_valid'] = has_year and has_title and has_journal_like_text and has_numbers and has_doi_in_text
            
            elif detected_type == 'book':
                has_publisher = bool(re.search(self.apa_patterns['publisher_info'], ref_text))
                
                if not has_year:
                    result['structure_issues'].append("Missing year in parentheses")
                if not has_title:
                    result['structure_issues'].append("Missing book title")
                if not has_publisher:
                    result['structure_issues'].append("Missing publisher information")
                
                result['structure_valid'] = has_year and has_title and has_publisher
            
            elif detected_type == 'website':
                has_url = bool(re.search(self.apa_patterns['url_pattern'], ref_text))
                has_access_info = bool(re.search(self.apa_patterns['website_access_date'], ref_text))
                
                if not has_title:
                    result['structure_issues'].append("Missing website title")
                if not has_url:
                    result['structure_issues'].append("Missing URL")
                if not has_access_info:
                    result['structure_issues'].append("Missing access date information")
                
                result['structure_valid'] = has_title and has_url
        
        elif format_type == "Vancouver":
            starts_with_number = bool(re.search(self.vancouver_patterns['starts_with_number'], ref_text))
            has_title = bool(re.search(self.vancouver_patterns['journal_title_section'], ref_text))
            
            if not starts_with_number:
                result['structure_issues'].append("Should start with number and period")
            if not has_title:
                result['structure_issues'].append("Missing title section")
            
            if detected_type == 'journal':
                has_journal_year = bool(re.search(self.vancouver_patterns['journal_year'], ref_text))
                if not has_journal_year:
                    result['structure_issues'].append("Missing journal and year information")
                result['structure_valid'] = starts_with_number and has_title and has_journal_year
            
            elif detected_type == 'book':
                has_publisher = bool(re.search(self.vancouver_patterns['book_publisher'], ref_text))
                if not has_publisher:
                    result['structure_issues'].append("Missing publisher and year information")
                result['structure_valid'] = starts_with_number and has_title and has_publisher
            
            elif detected_type == 'website':
                has_url = bool(re.search(self.vancouver_patterns['website_url_vancouver'], ref_text))
                if not has_url:
                    result['structure_issues'].append("Missing 'Available from:' URL")
                result['structure_valid'] = starts_with_number and has_title and has_url
        
        return result

    def _extract_author_parts(self, author_string: str) -> Optional[Dict]:
        """
        Extracts surname and initials from an author string.
        Handles "Lastname, F. M." and "F. M. Lastname" patterns.
        Returns {'surname': '...', 'initials': '...'} or None.
        """
        author_string = author_string.strip()
        if not author_string:
            return None

        # Try "Lastname, F. M." pattern
        match_comma = re.match(r'([^,]+),\s*(.*)', author_string)
        if match_comma:
            surname = match_comma.group(1).strip()
            initials_part = match_comma.group(2).strip()
            initials = ''.join(re.findall(r'[A-Za-z]', initials_part)).lower()
            return {'surname': surname.lower(), 'initials': initials}

        # Try "F. M. Lastname" pattern (or just "Lastname")
        parts = author_string.split()
        if parts:
            surname = parts[-1].strip()
            initials = ''.join(re.findall(r'[A-Za-z]', ' '.join(parts[:-1]))).lower()
            return {'surname': surname.lower(), 'initials': initials}
        
        return None

    def extract_reference_elements(self, ref_text: str, format_type: str, ref_type: str = None) -> Dict:
        elements = {
            'authors': None, 'year': None, 'title': None, 'journal': None,
            'publisher': None, 'url': None, 'isbn': None, 'doi': None,
            'access_date': None, 'reference_type': ref_type or self.detect_reference_type(ref_text),
            'extraction_confidence': 'high'
        }
        
        original_ref_text = ref_text # Keep original for parsing specific parts later
        detected_type = elements['reference_type'] # Get detected type early

        # 0. Extract DOI, ISBN, URL first and remove from working text
        doi_match = re.search(self.apa_patterns['doi_pattern'], ref_text)
        if doi_match:
            elements['doi'] = doi_match.group(1)
            ref_text = ref_text[:doi_match.start()] + ref_text[doi_match.end():]
        
        isbn_match = re.search(self.apa_patterns['isbn_pattern'], ref_text)
        if isbn_match:
            elements['isbn'] = isbn_match.group(1)
            ref_text = ref_text[:isbn_match.start()] + ref_text[isbn_match.end():]

        # Only extract generic URL if it's a website type, otherwise it might be part of a DOI or other text
        if detected_type == 'website':
            url_match = re.search(self.apa_patterns['url_pattern'], ref_text)
            if url_match:
                elements['url'] = url_match.group(1)
                ref_text = ref_text[:url_match.start()] + ref_text[url_match.end():]
        
        # Normalize spaces and remove redundant periods
        ref_text = re.sub(r'\s+', ' ', ref_text).strip()
        ref_text = re.sub(r'\.\s*\.', '.', ref_text) # Replace multiple periods with one

        if format_type == "APA":
            # 1. Extract Year
            year_match = re.search(self.apa_patterns['journal_year_in_parentheses'], ref_text)
            if year_match:
                elements['year'] = year_match.group(1)
                year_start_idx = year_match.start()
                year_end_idx = year_match.end()
                
                # 2. Extract Authors (everything before the year)
                elements['authors'] = ref_text[:year_start_idx].strip().rstrip('.').strip()

                # 3. Process text after year for Title, Journal, Volume, Pages
                remaining_after_year = ref_text[year_end_idx:].strip()
                if remaining_after_year.startswith('.'):
                    remaining_after_year = remaining_after_year[1:].strip() # Remove the period after year

                if detected_type == 'journal':
                    # Look for volume/pages pattern first, as it's very specific
                    volume_pages_match = re.search(self.apa_patterns['volume_pages'], remaining_after_year)
                    
                    if volume_pages_match:
                        elements['volume'] = volume_pages_match.group(1)
                        elements['pages'] = volume_pages_match.group(3)
                        
                        # The text before volume/pages is Title and Journal
                        text_before_vol_pages = remaining_after_year[:volume_pages_match.start()].strip()
                        
                        # Split Title and Journal: Journal is typically after the last period before volume/pages
                        last_period_idx = text_before_vol_pages.rfind('.')
                        if last_period_idx != -1:
                            elements['title'] = text_before_vol_pages[:last_period_idx].strip()
                            elements['journal'] = text_before_vol_pages[last_period_idx+1:].strip().rstrip(',').strip()
                        else: # Fallback if no clear period separator, try to split by common journal words
                            # This is a heuristic for cases like "Title JournalName, 43(5), 54-64"
                            # Try to find a common journal keyword to split
                            journal_keywords_for_split = ['Journal', 'Review', 'Quarterly', 'Annual', 'Strength & Conditioning Journal', 'Strength and Conditioning Journal'] # Added full name
                            split_found = False
                            for kw in journal_keywords_for_split:
                                # Look for the keyword followed by numbers (volume/issue)
                                pattern = r'(.*?)(\s*' + re.escape(kw) + r'\s*(?:\d+.*|$))' # Make volume/issue optional after journal keyword
                                match_split = re.match(pattern, text_before_vol_pages, re.IGNORECASE)
                                if match_split:
                                    elements['title'] = match_split.group(1).strip()
                                    elements['journal'] = match_split.group(2).strip().rstrip(',').strip()
                                    split_found = True
                                    break
                            if not split_found:
                                elements['title'] = text_before_vol_pages # Assign all to title as fallback
                                elements['journal'] = None # Cannot reliably extract
                        
                        # Clean up 'p' from pages
                        if elements['pages']:
                            elements['pages'] = re.sub(r'p\.?\s*', '', elements['pages'], flags=re.IGNORECASE).strip()

                    else: # No standard volume/pages found (e.g., Handford, Matthew J. ... October 2021.)
                        # Assume remaining_after_year contains Title, Journal, and possibly other info
                        # Try to extract the title by looking for the first major period after the year
                        title_match_simple = re.match(r'([^.]+)\.\s*(.*)', remaining_after_year)
                        if title_match_simple:
                            elements['title'] = title_match_simple.group(1).strip()
                            # The rest is potentially journal and other info
                            rest_of_journal_info = title_match_simple.group(2).strip()
                            # Try to extract journal from the rest
                            journal_candidate_match = re.match(r'([A-Z][^,]+?)(?:,.*|$)', rest_of_journal_info)
                            if journal_candidate_match:
                                elements['journal'] = journal_candidate_match.group(1).strip()
                                # Try to get volume/pages from the rest of journal info
                                vol_pages_in_rest = re.search(self.apa_patterns['volume_pages'], rest_of_journal_info)
                                if vol_pages_in_rest:
                                    elements['volume'] = vol_pages_in_rest.group(1)
                                    elements['pages'] = vol_pages_in_rest.group(3)
                                    if elements['pages']:
                                        elements['pages'] = re.sub(r'p\.?\s*', '', elements['pages'], flags=re.IGNORECASE).strip()
                            else:
                                elements['journal'] = rest_of_journal_info # Assign rest to journal if no clear split
                        else: # Very unstructured, assign all to title
                            elements['title'] = remaining_after_year.strip()
                            elements['journal'] = None

                elif detected_type == 'book':
                    publisher_match = re.search(self.apa_patterns['publisher_info'], remaining_after_year)
                    if publisher_match:
                        elements['publisher'] = publisher_match.group(1).strip()
                        elements['title'] = remaining_after_year[:publisher_match.start()].strip().rstrip('.').strip()
                    else:
                        elements['title'] = remaining_after_year.strip().rstrip('.').strip()
                        elements['publisher'] = None

                elif detected_type == 'website':
                    access_match = re.search(self.apa_patterns['website_access_date'], original_ref_text)
                    if access_match:
                        elements['access_date'] = access_match.group(1).strip()
                        title_end_for_website = original_ref_text.find("Retrieved")
                        if title_end_for_website != -1:
                            elements['title'] = original_ref_text[year_end_idx:title_end_for_website].strip().rstrip('.').strip()
                        else:
                            elements['title'] = remaining_after_year.strip().rstrip('.').strip()
                    else:
                        elements['title'] = remaining_after_year.strip().rstrip('.').strip()
                        elements['access_date'] = None


        elif format_type == "Vancouver":
            starts_with_number = re.match(self.vancouver_patterns['starts_with_number'], ref_text)
            if starts_with_number:
                ref_text_after_number = ref_text[starts_with_number.end():].strip()
                
                title_start_match = re.search(r'\.\s*([A-Z])', ref_text_after_number) # Period followed by capital letter
                if title_start_match:
                    elements['authors'] = ref_text_after_number[:title_start_match.start()].strip().rstrip('.').strip()
                    ref_text_after_authors = ref_text_after_number[title_start_match.start():].strip()
                    if ref_text_after_authors.startswith('.'):
                        ref_text_after_authors = ref_text_after_authors[1:].strip()

                    if detected_type == 'journal':
                        journal_year_match = re.search(self.vancouver_patterns['journal_year'], ref_text_after_authors)
                        if journal_year_match:
                            elements['journal'] = journal_year_match.group(1).strip()
                            elements['year'] = journal_year_match.group(2).strip()
                            elements['title'] = ref_text_after_authors[:journal_year_match.start()].strip().rstrip('.').strip()
                            
                            volume_pages_match = re.search(self.apa_patterns['volume_pages'], ref_text_after_authors[journal_year_match.end():])
                            if volume_pages_match:
                                elements['volume'] = volume_pages_match.group(1)
                                elements['pages'] = volume_pages_match.group(3)
                                if elements['pages']:
                                    elements['pages'] = re.sub(r'p\.?\s*', '', elements['pages'], flags=re.IGNORECASE).strip()
                        else: # Fallback if journal/year not found in expected place
                            elements['title'] = ref_text_after_authors.strip().rstrip('.').strip()
                            elements['journal'] = None
                            elements['year'] = None

                    elif detected_type == 'book':
                        publisher_match = re.search(self.vancouver_patterns['book_publisher'], ref_text_after_authors)
                        if publisher_match:
                            elements['publisher'] = publisher_match.group(1).strip()
                            elements['year'] = publisher_match.group(2).strip()
                            elements['title'] = ref_text_after_authors[:publisher_match.start()].strip().rstrip('.').strip()
                        else:
                            elements['title'] = ref_text_after_authors.strip().rstrip('.').strip()
                            elements['publisher'] = None
                            elements['year'] = None
                    
                    elif detected_type == 'website':
                        url_match = re.search(self.vancouver_patterns['website_url_vancouver'], ref_text_after_authors)
                        if url_match:
                            elements['url'] = url_match.group(1)
                            elements['title'] = ref_text_after_authors[:url_match.start()].strip().rstrip('.').strip()
                            year_match_in_website = re.search(r'(\d{4})', elements['title'])
                            if year_match_in_website:
                                elements['year'] = year_match_in_website.group(1)
                                elements['title'] = re.sub(r'\s*\(\d{4}\)\s*', '', elements['title']).strip()
                        else:
                            elements['title'] = ref_text_after_authors.strip().rstrip('.').strip()
                            elements['url'] = None

        # Assess extraction confidence
        required_fields_count = 0
        if detected_type == 'journal':
            if elements['authors']: required_fields_count += 1
            if elements['year']: required_fields_count += 1
            if elements['title']: required_fields_count += 1
            if elements['journal']: required_fields_count += 1
            
            if required_fields_count < 3:
                elements['extraction_confidence'] = 'low'
            elif required_fields_count < 4:
                elements['extraction_confidence'] = 'medium'
            else:
                elements['extraction_confidence'] = 'high'

        elif detected_type == 'book':
            if elements['authors']: required_fields_count += 1
            if elements['year']: required_fields_count += 1
            if elements['title']: required_fields_count += 1
            if elements['publisher']: required_fields_count += 1

            if required_fields_count < 3:
                elements['extraction_confidence'] = 'low'
            elif required_fields_count < 4:
                elements['extraction_confidence'] = 'medium'
            else:
                elements['extraction_confidence'] = 'high'

        elif detected_type == 'website':
            if elements['title']: required_fields_count += 1
            if elements['url']: required_fields_count += 1
            if elements['access_date']: required_fields_count += 1

            if required_fields_count < 2 or not elements['url']:
                elements['extraction_confidence'] = 'low'
            elif required_fields_count < 3:
                elements['extraction_confidence'] = 'medium'
            else:
                elements['extraction_confidence'] = 'high'
        
        return elements

class DatabaseSearcher:
    def __init__(self, similarity_threshold: float = 0.90):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.similarity_threshold = similarity_threshold
        self.max_retries = 3
        self.timeout = 30 # Increased timeout to 30 seconds

    def _make_request_with_retries(self, method: str, url: str, **kwargs) -> requests.Response:
        for attempt in range(self.max_retries):
            try:
                if method == 'get':
                    response = self.session.get(url, timeout=self.timeout, **kwargs)
                elif method == 'head':
                    response = self.session.head(url, timeout=self.timeout, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                if response.status_code >= 500 or response.status_code == 408:
                    st.warning(f"Attempt {attempt + 1}/{self.max_retries}: Server error or timeout ({response.status_code}) for {url}. Retrying...")
                    time.sleep(2 ** attempt)
                    continue
                return response
            except requests.exceptions.Timeout as e:
                st.warning(f"Attempt {attempt + 1}/{self.max_retries}: Request timed out for {url}: {e}. Retrying...")
                time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise e
                st.warning(f"Attempt {attempt + 1}/{self.max_retries}: Network error for {url}: {e}. Retrying...")
                time.sleep(2 ** attempt)
        raise requests.exceptions.RequestException(f"Failed after {self.max_retries} attempts for {url}")


    def check_doi_and_verify_content(self, doi: str, expected_title: str, expected_authors: str, expected_journal: str, expected_year: str) -> Dict:
        if not doi:
            return {'valid': False, 'reason': 'No DOI provided'}
        
        try:
            doi_url = f"https://doi.org/{doi}"
            response = self._make_request_with_retries('head', doi_url, allow_redirects=True)
            
            if response.status_code != 200:
                return {
                    'valid': False, 
                    'reason': f'DOI does not resolve (HTTP {response.status_code})',
                    'doi_url': doi_url
                }
            
            crossref_url = f"https://api.crossref.org/works/{doi}"
            metadata_response = self._make_request_with_retries('get', crossref_url)
            
            if metadata_response.status_code != 200:
                return {
                    'valid': False,
                    'reason': f'DOI found but no metadata in Crossref (HTTP {metadata_response.status_code})',
                    'doi_url': doi_url
                }
            
            try:
                metadata = metadata_response.json()
            except json.JSONDecodeError:
                return {
                    'valid': False,
                    'reason': 'Invalid response from Crossref API for DOI metadata',
                    'doi_url': doi_url
                }
            
            if 'message' not in metadata:
                return {
                    'valid': False,
                    'reason': 'DOI metadata not found in Crossref message',
                    'doi_url': doi_url
                }
            
            work = metadata['message']
            
            actual_title = work.get('title', [''])[0] if work.get('title') else ''
            actual_authors_list = [author.get('family', '') for author in work.get('author', []) if 'family' in author]
            actual_journal = work.get('container-title', [''])[0] if work.get('container-title') else ''
            actual_year = str(work.get('published-print', {}).get('date-parts', [[None]])[0][0]) if work.get('published-print') else \
                          str(work.get('published-online', {}).get('date-parts', [[None]])[0][0]) if work.get('published-online') else ''

            validation_errors = []
            composite_score = 0.0

            title_similarity = 0.0
            if expected_title and actual_title:
                title_similarity = self._calculate_title_similarity(expected_title.lower(), actual_title.lower())
                if title_similarity < self.similarity_threshold:
                    validation_errors.append(f"Title mismatch (expected: '{expected_title}', actual: '{actual_title}', similarity: {title_similarity:.1%})")
                composite_score += title_similarity * 0.5 # New weight: 0.5 (50%)

            # --- Author Match (15% weight) ---
            parsed_expected_authors = []
            raw_expected_author_parts = re.split(r',\s*|&\s*|and\s*', expected_authors)
            for raw_part in raw_expected_author_parts:
                cleaned_part = raw_part.strip()
                if cleaned_part:
                    parsed_author = ReferenceParser()._extract_author_parts(cleaned_part)
                    if parsed_author:
                        parsed_expected_authors.append(parsed_author)

            parsed_actual_authors = []
            for author_data in work.get('author', []):
                surname = author_data.get('family', '').lower()
                given_name = author_data.get('given', '')
                initials = ''.join(re.findall(r'[A-Za-z]', given_name)).lower()
                if surname:
                    parsed_actual_authors.append({'surname': surname, 'initials': initials})

            author_score = self._calculate_author_match_score(parsed_expected_authors, parsed_actual_authors)

            if author_score < self.similarity_threshold:
                 validation_errors.append(f"Author mismatch (expected: {expected_authors}, actual: {actual_authors_list}, score: {author_score:.1%})")
            composite_score += author_score * 0.15 # New weight: 0.15 (15%)


            journal_sim = 0.0
            if expected_journal and actual_journal:
                journal_sim = self._calculate_title_similarity(expected_journal.lower(), actual_journal.lower())
                if journal_sim < self.similarity_threshold:
                    validation_errors.append(f"Journal mismatch (expected: '{expected_journal}', actual: '{actual_journal}', similarity: {journal_sim:.1%})")
                composite_score += journal_sim * 0.25 # New weight: 0.25 (25%)
            
            year_match_score = 0.0
            if expected_year and actual_year:
                if expected_year == actual_year:
                    year_match_score = 1.0
                elif abs(int(expected_year) - int(actual_year)) <= 2:
                    year_match_score = 0.5
                if year_match_score < 1.0 and expected_year != actual_year:
                     validation_errors.append(f"Year mismatch (expected: {expected_year}, actual: {actual_year})")
                composite_score += year_match_score * 0.1 # Weight: 0.1 (10%)

            if validation_errors:
                return {
                    'valid': False,
                    'reason': 'Content mismatch with DOI metadata',
                    'validation_errors': validation_errors,
                    'doi_url': doi_url,
                    'crossref_url': crossref_url,
                    'actual_title': actual_title,
                    'actual_authors': actual_authors_list,
                    'actual_journal': actual_journal,
                    'actual_year': actual_year,
                    'match_score': composite_score
                }
            
            return {
                'valid': True,
                'match_score': composite_score,
                'actual_title': actual_title,
                'actual_authors': actual_authors_list,
                'actual_journal': actual_journal,
                'actual_year': actual_year,
                'doi_url': doi_url,
                'resolved_url': response.url,
                'crossref_url': crossref_url
            }
            
        except requests.exceptions.RequestException as e:
            return {
                'valid': False,
                'reason': f'Network error during DOI verification: {str(e)}',
                'doi_url': f"https://doi.org/{doi}" if doi else None
            }
        except Exception as e:
            return {
                'valid': False,
                'reason': f'DOI verification error: {str(e)}',
                'doi_url': f"https://doi.org/{doi}" if doi else None
            }

    def search_by_exact_title(self, title: str) -> Dict:
        if not title or len(title.strip()) < 10:
            return {'found': False, 'reason': 'Title too short for reliable search'}
        
        try:
            url = "https://api.crossref.org/works"
            params = {
                'query.title': title,
                'rows': 5,
                'select': 'title,author,DOI,URL'
            }
            
            response = self._make_request_with_retries('get', url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if 'message' in data and 'items' in data['message']:
                items = data['message']['items']
                
                for item in items:
                    if 'title' in item and item['title']:
                        item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
                        similarity = self._calculate_title_similarity(title.lower(), item_title.lower())
                        
                        if similarity > self.similarity_threshold:
                            source_url = None
                            if 'DOI' in item:
                                source_url = f"https://doi.org/{item['DOI']}"
                            elif 'URL' in item:
                                source_url = item['URL']
                            
                            return {
                                'found': True,
                                'similarity': similarity,
                                'matched_title': item_title,
                                'source_url': source_url
                            }
                
                return {'found': False, 'reason': 'No close title matches found'}
            
            return {'found': False, 'reason': 'No results from title search'}
            
        except Exception as e:
            return {'found': False, 'reason': f'Title search error: {str(e)}'}

    def search_comprehensive(self, authors: str, title: str, year: str, journal: str) -> Dict:
        # Initialize parsed_expected_authors here
        parsed_expected_authors = []
        raw_expected_author_parts = re.split(r',\s*|&\s*|and\s*', authors)
        for raw_part in raw_expected_author_parts:
            cleaned_part = raw_part.strip()
            if cleaned_part:
                parsed_author = ReferenceParser()._extract_author_parts(cleaned_part)
                if parsed_author:
                    parsed_expected_authors.append(parsed_author)

        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{4,}\b', title)[:4]
                query_parts.extend(title_words)
            
            # Use parsed authors for query parts
            parsed_authors_for_query = []
            raw_query_author_parts = re.split(r',\s*|&\s*|and\s*', authors)
            for raw_part in raw_query_author_parts:
                cleaned_part = raw_part.strip()
                if cleaned_part:
                    parsed_author = ReferenceParser()._extract_author_parts(cleaned_part)
                    if parsed_author and parsed_author['surname'] and len(parsed_author['surname']) > 2:
                        parsed_authors_for_query.append(parsed_author['surname'])
            if parsed_authors_for_query:
                query_parts.extend(parsed_authors_for_query[:2]) # Add up to 2 surnames to query

            if not query_parts:
                return {'found': False, 'reason': 'Insufficient search terms'}
            
            query = " ".join(query_parts)
            
            url = "https://api.crossref.org/works"
            params = {
                'query': query,
                'rows': 10,
                'select': 'title,author,DOI,URL,published-print,published-online,container-title'
            }
            
            if year:
                params['filter'] = f'from-pub-date:{int(year)-2},until-pub-date:{int(year)+2}'
            
            response = self._make_request_with_retries('get', url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if 'message' in data and 'items' in data['message']:
                items = data['message']['items']
                best_match = None
                best_score = 0.0
                
                for item in items:
                    # Pass parsed_expected_authors to _calculate_comprehensive_match_score
                    score = self._calculate_comprehensive_match_score(item, title, authors, year, journal, parsed_expected_authors)
                    if score > best_score:
                        best_score = score
                        best_match = item
                
                if best_score > self.similarity_threshold:
                    source_url = None
                    if 'DOI' in best_match:
                        source_url = f"https://doi.org/{best_match['DOI']}"
                    elif 'URL' in best_match:
                        source_url = best_match['URL']
                    
                    return {
                        'found': True,
                        'match_score': best_score,
                        'matched_title': best_match.get('title', ['Unknown'])[0] if best_match.get('title') else 'Unknown',
                        'source_url': source_url,
                        'total_results': len(items)
                    }
                else:
                    return {
                        'found': False,
                        'reason': f'No strong matches found (best score: {best_score:.2f})',
                        'total_results': len(items)
                    }
            
            return {'found': False, 'reason': 'No search results'}
            
        except Exception as e:
            return {'found': False, 'reason': f'Search error: {str(e)}'}

    def search_pubmed(self, title: str, authors: str, year: str) -> Dict:
        """
        Searches PubMed using NCBI E-utilities.
        Note: PubMed API usage limits apply. No API key required for basic use.
        """
        if not title and not authors:
            return {'found': False, 'reason': 'Insufficient search terms for PubMed'}

        try:
            # Constructing the search query for PubMed
            query_parts = []
            if title:
                query_parts.append(f"{title}[Title]")
            
            parsed_authors_for_query = []
            raw_query_author_parts = re.split(r',\s*|&\s*|and\s*', authors)
            for raw_part in raw_query_author_parts:
                cleaned_part = raw_part.strip()
                if cleaned_part:
                    parsed_author = ReferenceParser()._extract_author_parts(cleaned_part)
                    if parsed_author and parsed_author['surname']:
                        parsed_authors_for_query.append(parsed_author['surname'])
            if parsed_authors_for_query:
                query_parts.append(f"{' '.join(parsed_authors_for_query)}[Author]")

            if year:
                query_parts.append(f"{year}[pdat]") # Publication date

            search_query = " AND ".join(query_parts)
            
            # Step 1: Search for IDs
            esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            esearch_params = {
                'db': 'pubmed',
                'term': search_query,
                'retmax': 5, # Retrieve up to 5 results
                'retmode': 'json'
            }
            esearch_response = self._make_request_with_retries('get', esearch_url, params=esearch_params)
            esearch_response.raise_for_status()
            esearch_data = esearch_response.json()

            if 'esearchresult' not in esearch_data or not esearch_data['esearchresult'].get('idlist'):
                return {'found': False, 'reason': 'No matching articles found in PubMed.'}

            id_list = esearch_data['esearchresult']['idlist']
            if not id_list:
                return {'found': False, 'reason': 'No matching articles found in PubMed.'}

            # Step 2: Fetch details for the found IDs
            efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            efetch_params = {
                'db': 'pubmed',
                'id': ",".join(id_list),
                'retmode': 'xml', # Request XML to parse details
                'rettype': 'abstract'
            }
            efetch_response = self._make_request_with_retries('get', efetch_url, params=efetch_params)
            efetch_response.raise_for_status()
            
            xml_text = efetch_response.text
            
            best_match = None
            best_score = 0.0
            
            articles = re.findall(r'<PubmedArticle>(.*?)</PubmedArticle>', xml_text, re.DOTALL)
            
            for article_xml in articles:
                item_title = re.search(r'<ArticleTitle>(.*?)</ArticleTitle>', article_xml, re.DOTALL)
                item_title = item_title.group(1).strip() if item_title else ''

                # Parse authors from PubMed XML into surname/initials dicts
                parsed_item_authors = []
                author_list_match = re.search(r'<AuthorList.*?>(.*?)</AuthorList>', article_xml, re.DOTALL)
                if author_list_match:
                    author_tags = re.findall(r'<Author.*?>(.*?)</Author>', author_list_match.group(1), re.DOTALL)
                    for author_tag in author_tags:
                        surname = re.search(r'<LastName>(.*?)</LastName>', author_tag)
                        surname = surname.group(1).strip() if surname else ''
                        fore_name = re.search(r'<ForeName>(.*?)</ForeName>', author_tag)
                        fore_name = fore_name.group(1).strip() if fore_name else ''
                        initials_tag = re.search(r'<Initials>(.*?)</Initials>', author_tag)
                        initials_val = initials_tag.group(1).strip() if initials_tag else ''

                        if surname:
                            initials_for_author = initials_val if initials_val else ''.join(re.findall(r'[A-Za-z]', fore_name)).lower()
                            parsed_item_authors.append({'surname': surname.lower(), 'initials': initials_for_author})

                item_journal = re.search(r'<Journal><Title>(.*?)</Title>', article_xml, re.DOTALL)
                item_journal = item_journal.group(1).strip() if item_journal else ''

                item_year = re.search(r'<PubDate><Year>(\d{4})</Year>', article_xml)
                item_year = item_year.group(1) if item_year else ''

                item_doi = re.search(r'<ArticleId IdType="doi">(.*?)</ArticleId>', article_xml)
                item_doi = item_doi.group(1) if item_doi else ''
                
                # Prepare parsed_expected_authors for scoring
                parsed_expected_authors = []
                raw_expected_author_parts = re.split(r',\s*|&\s*|and\s*', authors)
                for raw_part in raw_expected_author_parts:
                    cleaned_part = raw_part.strip()
                    if cleaned_part:
                        parsed_author = ReferenceParser()._extract_author_parts(cleaned_part)
                        if parsed_author:
                            parsed_expected_authors.append(parsed_author)

                score = self._calculate_pubmed_match_score(
                    item_title, parsed_item_authors, item_journal, item_year, # Pass parsed_item_authors
                    title, authors, year, parsed_expected_authors
                )

                if score > best_score:
                    best_score = score
                    best_match = {
                        'title': item_title,
                        'authors': [a['surname'] for a in parsed_item_authors], # Store just surnames for display
                        'journal': item_journal,
                        'year': item_year,
                        'doi': item_doi,
                        'pubmed_id': re.search(r'<PMID Version="\d+">(\d+)</PMID>', article_xml).group(1) if re.search(r'<PMID Version="\d+">(\d+)</PMID>', article_xml) else None
                    }
            
            if best_match and best_score >= self.similarity_threshold:
                source_url = f"https://pubmed.ncbi.nlm.nih.gov/{best_match['pubmed_id']}/" if best_match.get('pubmed_id') else None
                return {
                    'found': True,
                    'match_score': best_score,
                    'matched_title': best_match['title'],
                    'matched_authors': best_match['authors'],
                    'matched_journal': best_match['journal'],
                    'matched_year': best_match['year'],
                    'source_url': source_url,
                    'total_results': len(articles)
                }
            
            return {'found': False, 'reason': f'No strong PubMed match (best score: {best_score:.2f})'}

        except requests.exceptions.RequestException as e:
            return {'found': False, 'reason': f'PubMed network error: {str(e)}'}
        except Exception as e:
            return {'found': False, 'reason': f'PubMed search error: {str(e)}'}

    def search_semantic_scholar(self, title: str, authors: str, year: str) -> Dict:
        """
        Searches Semantic Scholar API.
        Note: Semantic Scholar has rate limits. An API key is recommended for higher usage.
        """
        if not title and not authors:
            return {'found': False, 'reason': 'Insufficient search terms for Semantic Scholar'}

        try:
            query_parts = []
            if title:
                query_parts.append(title)
            
            parsed_authors_for_query = []
            raw_query_author_parts = re.split(r',\s*|&\s*|and\s*', authors)
            for raw_part in raw_query_author_parts:
                cleaned_part = raw_part.strip()
                if cleaned_part:
                    parsed_author = ReferenceParser()._extract_author_parts(cleaned_part)
                    if parsed_author and parsed_author['surname']:
                        parsed_authors_for_query.append(parsed_author['surname'])
            if parsed_authors_for_query:
                query_parts.append(" ".join(parsed_authors_for_query))

            query = " ".join(query_parts)
            
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            params = {
                'query': query,
                'fields': 'title,authors,venue,year,externalIds', # Request relevant fields
                'limit': 5 # Retrieve up to 5 results
            }
            # Add API key if available (e.g., if user provides it via Streamlit secrets)
            # headers = {'x-api-key': 'YOUR_SEMANTIC_SCHOLAR_API_KEY'} 
            # response = self._make_request_with_retries('get', url, params=params, headers=headers)
            response = self._make_request_with_retries('get', url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if 'data' not in data or not data['data']:
                return {'found': False, 'reason': 'No matching articles found in Semantic Scholar.'}

            best_match = None
            best_score = 0.0
            
            for item in data['data']:
                item_title = item.get('title', '')
                
                # Parse Semantic Scholar authors into surname/initials format
                parsed_item_authors = []
                for author_data_ss in item.get('authors', []):
                    full_name_ss = author_data_ss.get('name', '')
                    parsed_author_ss = ReferenceParser()._extract_author_parts(full_name_ss)
                    if parsed_author_ss:
                        parsed_item_authors.append(parsed_author_ss)

                item_venue = item.get('venue', '') # Journal/conference name
                item_year = str(item.get('year', ''))
                item_doi = item.get('externalIds', {}).get('DOI', '')
                
                # Prepare parsed_expected_authors for scoring
                parsed_expected_authors = []
                raw_expected_author_parts = re.split(r',\s*|&\s*|and\s*', authors)
                for raw_part in raw_expected_author_parts:
                    cleaned_part = raw_part.strip()
                    if cleaned_part:
                        parsed_author = ReferenceParser()._extract_author_parts(cleaned_part)
                        if parsed_author:
                            parsed_expected_authors.append(parsed_author)

                score = self._calculate_semantic_scholar_match_score(
                    item_title, parsed_item_authors, item_venue, item_year, # Pass parsed_item_authors
                    title, authors, year, parsed_expected_authors
                )

                if score > best_score:
                    best_score = score
                    best_match = {
                        'title': item_title,
                        'authors': [a.get('name', '') for a in item.get('authors', [])], # Store original full names for display
                        'journal': item_venue,
                        'year': item_year,
                        'doi': item_doi,
                        's2id': item.get('paperId')
                    }
            
            if best_match and best_score >= self.similarity_threshold:
                source_url = f"https://www.semanticscholar.org/paper/{best_match['s2id']}" if best_match.get('s2id') else None
                return {
                    'found': True,
                    'match_score': best_score,
                    'matched_title': best_match['title'],
                    'matched_authors': best_match['authors'],
                    'matched_journal': best_match['journal'],
                    'matched_year': best_match['year'],
                    'source_url': source_url,
                    'total_results': len(data['data'])
                }
            
            return {'found': False, 'reason': f'No strong Semantic Scholar match (best score: {best_score:.2f})'}

        except requests.exceptions.RequestException as e:
            return {'found': False, 'reason': f'Semantic Scholar network error: {str(e)}'}
        except Exception as e:
            return {'found': False, 'reason': f'Semantic Scholar search error: {str(e)}'}


    def search_books_isbn(self, isbn: str) -> Dict:
        if not isbn:
            return {'found': False, 'reason': 'No ISBN provided'}
        
        try:
            isbn_clean = re.sub(r'[^\d-]', '', isbn)
            
            url = f"https://openlibrary.org/api/books"
            params = {
                'bibkeys': f'ISBN:{isbn_clean}',
                'format': 'json',
                'jscmd': 'data'
            }
            
            response = self._make_request_with_retries('get', url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data:
                isbn_key = f'ISBN:{isbn_clean}'
                if isbn_key in data:
                    book_data = data[isbn_key]
                    return {
                        'found': True,
                        'title': book_data.get('title', 'Unknown'),
                        'authors': [author.get('name', 'Unknown') for author in book_data.get('authors', [])],
                        'source_url': f"https://openlibrary.org/isbn/{isbn_clean}",
                        'isbn': isbn_clean
                    }
            
            return {'found': False, 'reason': 'ISBN not found in Open Library'}
            
        except Exception as e:
            return {'found': False, 'reason': f'ISBN search error: {str(e)}'}

    def search_books_comprehensive(self, title: str, authors: str, year: str, publisher: str) -> Dict:
        # Initialize parsed_expected_authors here
        parsed_expected_authors = []
        raw_expected_author_parts = re.split(r',\s*|&\s*|and\s*', authors)
        for raw_part in raw_expected_author_parts:
            cleaned_part = raw_part.strip()
            if cleaned_part:
                parsed_author = ReferenceParser()._extract_author_parts(cleaned_part)
                if parsed_author:
                    parsed_expected_authors.append(parsed_author)

        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)[:5]
                query_parts.extend(title_words)
            
            parsed_authors_for_query = []
            raw_query_author_parts = re.split(r',\s*|&\s*|and\s*', authors)
            for raw_part in raw_query_author_parts:
                cleaned_part = raw_part.strip()
                if cleaned_part:
                    parsed_author = ReferenceParser()._extract_author_parts(cleaned_part)
                    if parsed_author and parsed_author['surname'] and len(parsed_author['surname']) > 2:
                        parsed_authors_for_query.append(parsed_author['surname'])
            if parsed_authors_for_query:
                query_parts.extend(parsed_authors_for_query[:2])

            if not query_parts:
                return {'found': False, 'reason': 'Insufficient search terms for Open Library book search'}
            
            url = "https://openlibrary.org/search.json"
            params = {
                'q': ' '.join(query_parts),
                'limit': 10
            }
            
            response = self._make_request_with_retries('get', url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if 'docs' in data and data['docs']:
                best_match = None
                best_score = 0.0
                
                for doc in data['docs']:
                    # Pass parsed_expected_authors to _calculate_book_match_score
                    score = self._calculate_book_match_score(doc, title, authors, year, publisher, parsed_expected_authors)
                    if score > best_score:
                        best_score = score
                        best_match = doc
                
                if best_score > self.similarity_threshold:
                    return {
                        'found': True,
                        'match_score': best_score,
                        'matched_title': best_match.get('title', 'Unknown'),
                        'matched_authors': best_match.get('author_name', ['Unknown']),
                        'matched_year': best_match.get('first_publish_year'),
                        'source_url': f"https://openlibrary.org{best_match['key']}" if 'key' in best_match else None,
                        'total_results': len(data['docs'])
                    }
            
            return {'found': False, 'reason': f'No good Open Library search results (best score: {best_score:.2f})'}
            
        except Exception as e:
            return {'found': False, 'reason': f'Open Library book search error: {str(e)}'}

    def search_books_google_books(self, title: str, authors: str, year: str, publisher: str) -> Dict:
        # Initialize parsed_expected_authors here
        parsed_expected_authors = []
        raw_expected_author_parts = re.split(r',\s*|&\s*|and\s*', authors)
        for raw_part in raw_expected_author_parts:
            cleaned_part = raw_part.strip()
            if cleaned_part:
                parsed_author = ReferenceParser()._extract_author_parts(cleaned_part)
                if parsed_author:
                    parsed_expected_authors.append(parsed_author)

        try:
            query_parts = []
            if title:
                query_parts.append(f"intitle:{title}")
            
            parsed_authors_for_query = []
            raw_query_author_parts = re.split(r',\s*|&\s*|and\s*', authors)
            for raw_part in raw_query_author_parts:
                cleaned_part = raw_part.strip()
                if cleaned_part:
                    parsed_author = ReferenceParser()._extract_author_parts(cleaned_part)
                    if parsed_author and parsed_author['surname'] and len(parsed_author['surname']) > 2:
                        parsed_authors_for_query.append(parsed_author['surname'])
            if parsed_authors_for_query:
                query_parts.append(f"inauthor:{' '.join(parsed_authors_for_query)}")

            if publisher:
                query_parts.append(f"inpublisher:{publisher}")
            if year:
                query_parts.append(f"inpublicdate:{year}")

            if not query_parts:
                return {'found': False, 'reason': 'Insufficient search terms for Google Books search'}

            q = ' '.join(query_parts)
            url = "https://www.googleapis.com/books/v1/volumes"
            params = {
                'q': q,
                'maxResults': 10
            }

            response = self._make_request_with_retries('get', url, params=params)
            response.raise_for_status()

            data = response.json()

            if 'items' in data:
                best_match = None
                best_score = 0.0

                for item in data['items']:
                    volume_info = item.get('volumeInfo', {})
                    
                    item_title = volume_info.get('title', '')
                    item_authors = volume_info.get('authors', [])
                    item_published_date = volume_info.get('publishedDate', '')
                    item_publisher = volume_info.get('publisher', '')

                    # Pass parsed_expected_authors to _calculate_google_book_match_score
                    score = self._calculate_google_book_match_score(
                        item_title, item_authors, item_published_date, item_publisher,
                        title, authors, year, publisher, parsed_expected_authors
                    )

                    if score > best_score:
                        best_score = score
                        best_match = item

                if best_score > self.similarity_threshold:
                    return {
                        'found': True,
                        'match_score': best_score,
                        'matched_title': best_match.get('volumeInfo', {}).get('title', 'Unknown'),
                        'matched_authors': best_match.get('volumeInfo', {}).get('authors', ['Unknown']),
                        'matched_year': best_match.get('volumeInfo', {}).get('publishedDate', '')[:4],
                        'source_url': best_match.get('volumeInfo', {}).get('infoLink'),
                        'total_results': data.get('totalItems', 0)
                    }
            
            return {'found': False, 'reason': f'No good Google Books search results (best score: {best_score:.2f})'}

        except Exception as e:
            return {'found': False, 'reason': f'Google Books search error: {str(e)}'}


    def check_website_accessibility(self, url: str) -> Dict:
        if not url:
            return {'accessible': False, 'reason': 'No URL provided'}
        
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            response = self._make_request_with_retries('get', url)
            
            if response.status_code == 200:
                page_title_match = re.search(r'<title>(.*?)</title>', response.text, re.IGNORECASE | re.DOTALL)
                page_title = page_title_match.group(1).strip() if page_title_match else 'Title not found'
                
                return {
                    'accessible': True,
                    'status_code': response.status_code,
                    'final_url': response.url,
                    'page_title': page_title
                }
            else:
                return {
                    'accessible': False,
                    'reason': f'Website not accessible (status: {response.status_code})',
                    'status_code': response.status_code
                }
                
        except Exception as e:
            return {
                'accessible': False,
                'reason': f'Website check error: {str(e)}'
            }

    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        # Normalize by replacing '&' with 'and', then removing other non-alphanumeric characters and converting to lowercase
        normalized_title1 = re.sub(r'&', 'and', title1)
        normalized_title1 = re.sub(r'[^a-zA-Z0-9\s]', '', normalized_title1).lower()
        
        normalized_title2 = re.sub(r'&', 'and', title2)
        normalized_title2 = re.sub(r'[^a-zA-Z0-9\s]', '', normalized_title2).lower()

        words1 = set(normalized_title1.split())
        words2 = set(normalized_title2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

    def _calculate_author_match_score(self, parsed_expected_authors: List[Dict], actual_authors_data: List[Dict]) -> float:
        """
        Calculates a match score between expected and actual parsed author lists.
        parsed_expected_authors: List of {'surname': '...', 'initials': '...'} for expected authors.
        actual_authors_data: List of {'surname': '...', 'initials': '...'} for actual authors.
        """
        if not parsed_expected_authors or not actual_authors_data:
            return 0.0

        matched_surnames = 0
        initial_bonus = 0.0

        actual_surnames_set = {a['surname'] for a in actual_authors_data}
        actual_initials_map = {a['surname']: a['initials'] for a in actual_authors_data if a['initials']}

        for exp_author in parsed_expected_authors:
            exp_surname = exp_author['surname']
            exp_initials = exp_author['initials']

            if exp_surname in actual_surnames_set:
                matched_surnames += 1
                if exp_initials and exp_surname in actual_initials_map and exp_initials == actual_initials_map[exp_surname]:
                    initial_bonus += 0.5

        author_score = matched_surnames / len(parsed_expected_authors)
        author_score += (initial_bonus / len(parsed_expected_authors)) * 0.1 # Small bonus for initials
        return min(author_score, 1.0) # Cap score at 1.0

    def _calculate_comprehensive_match_score(self, item: Dict, target_title: str, target_authors_str: str, target_year: str, target_journal: str, parsed_expected_authors: List[Dict]) -> float:
        score = 0.0
        
        title_sim = 0.0
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.5 # New weight: 0.5 (50%)
        
        # --- Author Matching (15% weight) ---
        parsed_item_authors = []
        if 'author' in item and item['author']:
            for author_data in item['author']:
                surname = author_data.get('family', '').lower()
                given_name = author_data.get('given', '')
                initials = ''.join(re.findall(r'[A-Za-z]', given_name)).lower()
                if surname:
                    parsed_item_authors.append({'surname': surname, 'initials': initials})

        author_score = self._calculate_author_match_score(parsed_expected_authors, parsed_item_authors)
        score += author_score * 0.15 # New weight: 0.15 (15%)
        
        year_match_score = 0.0
        if target_year:
            item_year = None
            if 'published-print' in item and 'date-parts' in item['published-print']:
                item_year = str(item['published-print']['date-parts'][0][0])
            elif 'published-online' in item and 'date-parts' in item['published-online']:
                item_year = str(item['published-online']['date-parts'][0][0])
            
            if item_year and item_year == target_year:
                year_match_score = 1.0
            elif item_year and abs(int(item_year) - int(target_year)) <= 2:
                year_match_score = 0.5
            score += year_match_score * 0.1 # Weight: 0.1 (10%)
            
        journal_match_score = 0.0
        if target_journal and 'container-title' in item and item['container-title']:
            item_journal_titles = [t.lower() for t in (item['container-title'] if isinstance(item['container-title'], list) else [item['container-title']])]
            target_journal_lower = target_journal.lower()
            
            max_journal_sim = 0.0
            for ij in item_journal_titles:
                max_journal_sim = max(max_journal_sim, self._calculate_title_similarity(target_journal_lower, ij))
            
            journal_match_score = max_journal_sim * 0.25 # New weight: 0.25 (25%)
            score += journal_match_score
            
        return score

    def _calculate_pubmed_match_score(self, item_title: str, parsed_item_authors: List[Dict], item_journal: str, item_year: str,
                                      target_title: str, target_authors_str: str, target_year: str, parsed_expected_authors: List[Dict]) -> float:
        score = 0.0

        title_sim = 0.0
        if item_title and target_title:
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.5 # New weight: 0.5 (50%)

        # --- Author Matching (15% weight) ---
        author_score = self._calculate_author_match_score(parsed_expected_authors, parsed_item_authors)
        score += author_score * 0.15 # New weight: 0.15 (15%)

        year_match_score = 0.0
        if target_year and item_year:
            if item_year == target_year:
                year_match_score = 1.0
            elif abs(int(item_year) - int(target_year)) <= 2:
                year_match_score = 0.5
            score += year_match_score * 0.1 # Weight: 0.1 (10%)

        journal_match_score = 0.0
        if target_journal and item_journal:
            journal_match_score = self._calculate_title_similarity(target_journal, item_journal)
            score += journal_match_score * 0.25 # New weight: 0.25 (25%)
        
        return score

    def _calculate_semantic_scholar_match_score(self, item_title: str, parsed_item_authors: List[Dict], item_venue: str, item_year: str,
                                                target_title: str, target_authors_str: str, target_year: str, parsed_expected_authors: List[Dict]) -> float:
        score = 0.0

        title_sim = 0.0
        if item_title and target_title:
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.5 # New weight: 0.5 (50%)

        # --- Author Matching (15% weight) ---
        author_score = self._calculate_author_match_score(parsed_expected_authors, parsed_item_authors)
        score += author_score * 0.15 # New weight: 0.15 (15%)

        year_match_score = 0.0
        if target_year and item_year:
            if item_year == target_year:
                year_match_score = 1.0
            elif abs(int(item_year) - int(target_year)) <= 2:
                year_match_score = 0.5
            score += year_match_score * 0.1 # Weight: 0.1 (10%)

        journal_match_score = 0.0
        if target_journal and item_venue: # Corrected: target_journal instead of target_venue
            journal_match_score = self._calculate_title_similarity(target_journal, item_venue)
            score += journal_match_score * 0.25 # New weight: 0.25 (25%)
        
        return score

    def _calculate_book_match_score(self, item: Dict, target_title: str, target_authors: str, target_year: str, target_publisher: str, parsed_expected_authors: List[Dict]) -> float:
        score = 0.0
        
        title_sim = 0.0
        if 'title' in item and target_title:
            item_title = item['title']
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.5
        
        # --- Author Matching (30% weight) ---
        parsed_item_authors = []
        if 'author_name' in item and item['author_name']:
            for author_name_str in item['author_name']: # item['author_name'] is a list of strings
                parsed_author = ReferenceParser()._extract_author_parts(author_name_str)
                if parsed_author:
                    parsed_item_authors.append(parsed_author)

        author_match_score = self._calculate_author_match_score(parsed_expected_authors, parsed_item_authors)
        score += author_match_score * 0.3

        year_match_score = 0.0
        if target_year and 'first_publish_year' in item:
            item_year = str(item['first_publish_year'])
            if item_year == target_year:
                year_match_score = 0.15
            elif abs(int(item_year) - int(target_year)) <= 2:
                year_match_score = 0.075
            score += year_match_score

        publisher_match_score = 0.0
        if target_publisher and 'publisher' in item and item['publisher']:
            item_publishers_lower = [p.lower() for p in (item['publisher'] if isinstance(item['publisher'], list) else [item['publisher']])]
            target_publisher_lower = target_publisher.lower()
            
            max_publisher_sim = 0.0
            for ip in item_publishers_lower:
                max_publisher_sim = max(max_publisher_sim, self._calculate_title_similarity(target_publisher_lower, ip))
            
            publisher_match_score = max_publisher_sim * 0.05
            score += publisher_match_score
        
        return score

    def _calculate_google_book_match_score(self, item_title: str, item_authors: List[str], item_published_date: str, item_publisher: str,
                                          target_title: str, target_authors: str, target_year: str, target_publisher: str, parsed_expected_authors: List[Dict]) -> float:
        score = 0.0

        title_sim = 0.0
        if item_title and target_title:
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.5

        # --- Author Matching (30% weight) ---
        parsed_item_authors = []
        if item_authors: # item_authors from Google Books API is already a list of strings
            for author_name_str in item_authors:
                parsed_author = ReferenceParser()._extract_author_parts(author_name_str)
                if parsed_author:
                    parsed_item_authors.append(parsed_author)

        author_match_score = self._calculate_author_match_score(parsed_expected_authors, parsed_item_authors)
        score += author_match_score * 0.3
        
        year_match_score = 0.0
        if target_year and item_published_date:
            item_year = item_published_date[:4]
            if item_year == target_year:
                year_match_score = 0.15
            elif abs(int(item_year) - int(target_year)) <= 2:
                year_match_score = 0.075
            score += year_match_score

        publisher_match_score = 0.0
        if target_publisher and item_publisher:
            pub_sim = self._calculate_title_similarity(target_publisher, item_publisher)
            publisher_match_score = pub_sim * 0.05
            score += publisher_match_score
        
        return score


class ReferenceVerifier:
    def __init__(self, similarity_threshold: float = 0.90):
        self.parser = ReferenceParser()
        self.searcher = DatabaseSearcher(similarity_threshold)

    def verify_references(self, text: str, format_type: str, progress_callback=None) -> List[Dict]:
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
                'existence_check': {},
                'extracted_elements': {}
            }
            
            ref_type = self.parser.detect_reference_type(ref.text)
            
            elements = self.parser.extract_reference_elements(ref.text, format_type, ref_type)
            result['extracted_elements'] = elements
            result['reference_type'] = ref_type

            if elements['extraction_confidence'] == 'low':
                result['content_status'] = 'extraction_failed'
                result['overall_status'] = 'content_error'
            else:
                existence_results = self._verify_existence(elements)
                result['existence_check'] = existence_results

                if existence_results['any_found']:
                    result['existence_status'] = 'found'
                    
                    structure_check_result = self.parser.check_structural_format(ref.text, format_type, ref_type)
                    result['structure_check'] = structure_check_result
                    result['format_valid'] = structure_check_result['structure_valid']
                    result['errors'] = structure_check_result['structure_issues']

                    if structure_check_result['structure_valid']:
                        result['structure_status'] = 'valid'
                        result['overall_status'] = 'valid'
                    else:
                        result['structure_status'] = 'invalid'
                        result['overall_status'] = 'authentic_but_structure_error'
                else:
                    result['existence_status'] = 'not_found'
                    result['overall_status'] = 'likely_fake'
            
            results.append(result)
            time.sleep(0.3)
        
        return results

    def _verify_existence(self, elements: Dict) -> Dict:
        results = {
            'any_found': False,
            'doi_valid': False,
            'title_found': False,
            'comprehensive_journal_found_crossref': False,
            'comprehensive_journal_found_pubmed': False, # New field
            'comprehensive_journal_found_semanticscholar': False, # New field
            'isbn_found': False,
            'comprehensive_book_found_openlibrary': False,
            'comprehensive_book_found_googlebooks': False,
            'website_accessible': False,
            'search_details': {},
            'verification_sources': []
        }
        
        ref_type = elements.get('reference_type', 'journal')
        
        # Try DOI first (most definitive for journals)
        if elements.get('doi'):
            doi_result = self.searcher.check_doi_and_verify_content(
                elements.get('doi', ''), 
                elements.get('title', ''),
                elements.get('authors', ''),
                elements.get('journal', ''),
                elements.get('year', '')
            )
            results['search_details']['doi'] = doi_result
            
            if doi_result['valid'] and doi_result.get('match_score', 0) >= self.searcher.similarity_threshold:
                results['doi_valid'] = True
                results['any_found'] = True
                if doi_result.get('doi_url'):
                    results['verification_sources'].append({
                        'type': 'DOI (Comprehensive Match)',
                        'url': doi_result['doi_url'],
                        'description': f"DOI verified with {doi_result.get('match_score', 0):.1%} content match"
                    })

        # If it's a journal and DOI didn't work or wasn't present, try other journal databases
        if ref_type == 'journal' and not results['any_found']:
            # Try Semantic Scholar
            semantic_scholar_result = self.searcher.search_semantic_scholar(
                elements.get('title', ''),
                elements.get('authors', ''),
                elements.get('year', '')
            )
            results['search_details']['comprehensive_journal_semanticscholar'] = semantic_scholar_result
            if semantic_scholar_result['found']:
                results['comprehensive_journal_found_semanticscholar'] = True
                results['any_found'] = True
                if semantic_scholar_result.get('source_url'):
                    results['verification_sources'].append({
                        'type': 'Journal Comprehensive Search (Semantic Scholar)',
                        'url': semantic_scholar_result['source_url'],
                        'description': f"Multi-element match (confidence: {semantic_scholar_result.get('match_score', 0):.1%})"
                    })

            # If still not found, try PubMed
            if not results['any_found']:
                pubmed_result = self.searcher.search_pubmed(
                    elements.get('title', ''),
                    elements.get('authors', ''),
                    elements.get('year', '')
                )
                results['search_details']['comprehensive_journal_pubmed'] = pubmed_result
                if pubmed_result['found']:
                    results['comprehensive_journal_found_pubmed'] = True
                    results['any_found'] = True
                    if pubmed_result.get('source_url'):
                        results['verification_sources'].append({
                            'type': 'Journal Comprehensive Search (PubMed)',
                            'url': pubmed_result['source_url'],
                            'description': f"Multi-element match (confidence: {pubmed_result.get('match_score', 0):.1%})"
                        })

            # Finally, try comprehensive Crossref search if others failed
            if not results['any_found']:
                comprehensive_crossref_result = self.searcher.search_comprehensive(
                    elements.get('authors', ''),
                    elements.get('title', ''),
                    elements.get('year', ''),
                    elements.get('journal', '')
                )
                results['search_details']['comprehensive_journal_crossref'] = comprehensive_crossref_result
                if comprehensive_crossref_result['found']:
                    results['comprehensive_journal_found_crossref'] = True
                    results['any_found'] = True
                    if comprehensive_crossref_result.get('source_url'):
                        results['verification_sources'].append({
                            'type': 'Journal Comprehensive Search (Crossref)',
                            'url': comprehensive_crossref_result['source_url'],
                            'description': f"Multi-element match (confidence: {comprehensive_crossref_result.get('match_score', 0):.1%})"
                        })
        
        # Book-specific searches
        elif ref_type == 'book':
            if elements.get('isbn'):
                isbn_result = self.searcher.search_books_isbn(elements['isbn'])
                results['search_details']['isbn_search'] = isbn_result
                
                if isbn_result['found']:
                    results['isbn_found'] = True
                    results['any_found'] = True
                    if isbn_result.get('source_url'):
                        results['verification_sources'].append({
                            'type': 'ISBN Verification (Open Library)',
                            'url': isbn_result['source_url'],
                            'description': f"ISBN {isbn_result['isbn']} found in Open Library"
                        })

            if not results['any_found']: # Only search comprehensive if ISBN or previous attempts failed
                book_result_ol = self.searcher.search_books_comprehensive(
                    elements.get('title', ''),
                    elements.get('authors', ''),
                    elements.get('year', ''),
                    elements.get('publisher', '')
                )
                results['search_details']['comprehensive_book_openlibrary'] = book_result_ol
                
                if book_result_ol['found']:
                    results['comprehensive_book_found_openlibrary'] = True
                    results['any_found'] = True
                    if book_result_ol.get('source_url'):
                        results['verification_sources'].append({
                            'type': 'Book Comprehensive Search (Open Library)',
                            'url': book_result_ol['source_url'],
                            'description': f"Book match (confidence: {book_result_ol.get('match_score', 0):.1%})"
                        })
            
            if not results['any_found'] and (elements.get('title') or elements.get('authors')):
                book_result_gb = self.searcher.search_books_google_books(
                    elements.get('title', ''),
                    elements.get('authors', ''),
                    elements.get('year', ''),
                    elements.get('publisher', '')
                )
                results['search_details']['comprehensive_book_googlebooks'] = book_result_gb

                if book_result_gb['found']:
                    results['comprehensive_book_found_googlebooks'] = True
                    results['any_found'] = True
                    if book_result_gb.get('source_url'):
                        results['verification_sources'].append({
                            'type': 'Book Comprehensive Search (Google Books)',
                            'url': book_result_gb['source_url'],
                            'description': f"Book match (confidence: {book_result_gb.get('match_score', 0):.1%})"
                        })

        # Website-specific search
        if elements.get('url') and (ref_type == 'website' or not results['any_found']):
            website_result = self.searcher.check_website_accessibility(elements['url'])
            results['search_details']['website_check'] = website_result
            
            if website_result['accessible']:
                results['website_accessible'] = True
                if ref_type == 'website' or not results['any_found']:
                    results['any_found'] = True
                results['verification_sources'].append({
                    'type': 'Website Accessibility',
                    'url': website_result.get('final_url', elements['url']),
                    'description': f"Website accessible - {website_result.get('page_title', 'No title')}"
                })
        
        return results

def main():
    st.set_page_config(
        page_title="Academic Reference Verifier",
        page_icon="📚",
        layout="wide"
    )
    
    st.title("📚 Academic Reference Verifier")
    st.markdown("**Three-level verification**: Authenticity → Structure → Content")
    st.markdown("Supports **journals** 📄, **books** 📚, and **websites** 🌐")
    
    st.sidebar.header("Settings")
    format_type = st.sidebar.selectbox(
        "Select Reference Format",
        ["APA", "Vancouver"]
    )

    similarity_percentage = st.sidebar.slider(
        "Set Authenticity Similarity Threshold (%)",
        min_value=70,
        max_value=100,
        value=90,
        step=5,
        help="Adjust the strictness of authenticity matching. Higher values require closer matches in external databases."
    )
    similarity_threshold = similarity_percentage / 100.0
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**🔍 Verification Process (New Order):**")
    st.sidebar.markdown("• **Authenticity**: Database verification (Authors, Title, Journal/Publisher Match)")
    st.sidebar.markdown("• **Structure**: Layout validation")
    st.sidebar.markdown("• **Content**: Element extraction")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**📋 Supported Types:**")
    st.sidebar.markdown("📄 **Journals**: DOI, Crossref, PubMed, Semantic Scholar") # Updated
    st.sidebar.markdown("📚 **Books**: ISBN, Open Library, Google Books")
    st.sidebar.markdown("🌐 **Websites**: URL accessibility")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📝 Input References")
        
        st.markdown("""
        **Instructions:**
        1. Paste your reference list below (one reference per line)
        2. Select your citation format (APA or Vancouver)
        3. Click "Verify References" to check validity
        
        **Supported reference types:**
        - 📄 Journal articles (with DOI verification)
        - 📚 Books (with ISBN lookup)  
        - 🌐 Websites (with URL checking)
        """)
        
        reference_text = st.text_area(
            "Paste your references here (one per line):",
            height=350,
            placeholder="""Example references:

📄 Journal (APA):
Smith, J. A. (2020). Climate change impacts on marine ecosystems. Nature Climate Change, 10(5), 423-431. https://doi.org/10.1038/s41558-020-0789-5

📚 Book (APA):
Brown, M. (2019). Machine learning in healthcare. MIT Press.

🌐 Website (APA):
World Health Organization. (2021). COVID-19 pandemic response. Retrieved March 15, 2023, from https://www.who.int/emergencies/diseases/novel-coronavirus-2019""",
            help="Each reference should be on a separate line. The system will automatically detect whether each reference is a journal article, book, or website."
        )
        
        col_a, col_b = st.columns(2)
        with col_a:
            verify_button = st.button("🔍 Verify References", type="primary", use_container_width=True)
        
        with col_b:
            if st.button("📝 Load Sample Data", use_container_width=True):
                sample_data = """American College of Sports Medicine. (2022). ACSM’s guidelines for exercise testing and prescription (11th ed.). Wolters Kluwer.
American Heart Association. (2024). Understanding blood pressure readings. American Heart Association. https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings
Australian Government Department of Health and Aged Care. (2021, July 29). Body Mass Index (BMI) and Waist Measurement. Department of Health and Aged Care. https://www.health.gov.au/topics/overweight-and-obesity/bmi-and-waist
Coombes, J., & Skinner, T. (2014). ESSA’s student manual for health, exercise and sport assessment. Elsevier.
Health Direct. (2019). Resting heart rate. Healthdirect.gov.au; Healthdirect Australia. https://www.healthdirect.gov.au/resting-heart-rate
Kumar, K. (2022, January 12). What Is a Good Resting Heart Rate by Age? MedicineNet. https://www.medicinet.com/what_is_a_good_resting_heart_rate_by_age/article.htm
Haff, G. G., & Triplett, N. T. (2016). Essentials of strength training and conditioning (4th ed.). Human Kinetics.
Powden, C. J., Hoch, J. M., & Hoch, M. C. (2015b). Reliability and Minimal detectable Change of the weight-bearing Lunge test: a Systematic Review. Manual Therapy, 20(4), 524–532. https://doi.org/10.1016/j.math.2015.01.004
Ryan, C., Uthoff, A., McKenzie, C., & Cronin, J. (2022). Traditional and modified 5-0-5 change of direction test: Normative and reliability analysis. Strength & Conditioning Journal, 44(4), 22–37. https://doi.org/10.1519/SSC.0000000000000635
Shrestha, M. (2022). Sit and Reach Test. Physiopedia. https://www.physio-pedia.com/Sit_and_Reach_Test
Watson, S., & Nall, R. (2023, February 2). What Is the Waist-to-Hip Ratio? Healthline; Healthline Media. https://www.healthline.com/health/waist-to-hip-ratio
Wood, R. (2008). Push Up Test: Home fitness tests. Topendsports.com. https://www.topendsports.com/testing/tests/home-pushup.htm"""
                st.session_state.sample_text = sample_data
        
        with st.expander("💡 Quick Tips"):
            st.markdown("""
            **For best results:**
            - Include DOIs for journal articles when available
            - Include ISBNs for books when available  
            - Include complete URLs for websites
            - Use consistent formatting throughout your list
            
            **Common issues:**
            - Missing punctuation (periods, commas)
            - Inconsistent author name formatting
            - Missing publication years
            - Incomplete journal/publisher information
            """)
    
    with col2:
        st.header("📊 Verification Results")
        
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
            
            with st.spinner("Initializing verification..."):
                verifier = ReferenceVerifier(similarity_threshold)
                results = verifier.verify_references(reference_text, format_type, update_progress)
            
            progress_bar.empty()
            status_text.empty()
            
            if results:
                total_refs = len(results)
                valid_refs = sum(1 for r in results if r['overall_status'] == 'valid')
                authentic_structure_errors = sum(1 for r in results if r['overall_status'] == 'authentic_but_structure_error')
                content_errors = sum(1 for r in results if r['overall_status'] == 'content_error')
                likely_fake = sum(1 for r in results if r['overall_status'] == 'likely_fake')
                
                type_counts = {}
                for result in results:
                    ref_type = result.get('reference_type', 'journal')
                    type_counts[ref_type] = type_counts.get(ref_type, 0) + 1
                
                col_a, col_b, col_c, col_d, col_e = st.columns(5)
                with col_a:
                    st.metric("Total", total_refs)
                with col_b:
                    st.metric("✅ Valid", valid_refs)
                with col_c:
                    st.metric("⚠️ Authentic, Fix Format", authentic_structure_errors)
                with col_d:
                    st.metric("⚠️ Content", content_errors)
                with col_e:
                    st.metric("🚨 Likely Fake", likely_fake)
                
                if type_counts:
                    st.markdown("**Reference Types Detected:**")
                    type_display = []
                    type_icons = {'journal': '📄', 'book': '📚', 'website': '🌐'}
                    for ref_type, count in type_counts.items():
                        icon = type_icons.get(ref_type, '📄')
                        type_display.append(f"{icon} {ref_type.title()}: {count}")
                    st.write(" • ".join(type_display))
                
                st.markdown("---")
                
                for i, result in enumerate(results):
                    ref_text = result['reference']
                    status = result['overall_status']
                    
                    type_icons = {'journal': '📄', 'book': '📚', 'website': '🌐'}
                    type_icon = type_icons.get(result.get('reference_type', 'journal'), '📄')
                    
                    if status == 'valid':
                        st.success(f"✅ {type_icon} **Reference {result['line_number']}**: Verified and Valid")
                        st.write(ref_text)
                        
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
                    
                    elif status == 'authentic_but_structure_error':
                        st.warning(f"⚠️ {type_icon} **Reference {result['line_number']}**: Authentic but Structural Format Issues")
                        st.write(ref_text)
                        
                        st.write("**This reference was found in external databases and is likely authentic, but its formatting needs correction.**")
                        issues = result['structure_check'].get('structure_issues', [])
                        if issues:
                            st.write(f"**Structural problems:**")
                            for issue in issues:
                                st.write(f"• {issue}")
                        
                        existence = result['existence_check']
                        verification_sources = existence.get('verification_sources', [])
                        if verification_sources:
                            st.write("**✅ Authenticity verified via:**")
                            for source in verification_sources:
                                source_type = source['type']
                                source_url = source['url']
                                description = source['description']
                                if source_url:
                                    st.markdown(f"• **{source_type}**: [{description}]({source_url})")
                                else:
                                    st.write(f"• **{source_type}**: {description}")
                        st.write("---")
                        st.write("**Suggestion:** Correct the formatting issues listed above to make this reference fully compliant.")

                    elif status == 'content_error':
                        st.warning(f"⚠️ {type_icon} **Reference {result['line_number']}**: Content Extraction Issues")
                        st.write(ref_text)
                        st.write(f"**Issue:** Could not extract enough key elements (like authors, title, year) to perform a reliable authenticity check. Please ensure the reference text is clear and complete.")
                    
                    elif status == 'likely_fake':
                        st.error(f"🚨 {type_icon} **Reference {result['line_number']}**: Likely Fake Reference")
                        st.write(ref_text)
                        
                        existence = result['existence_check']
                        search_details = existence.get('search_details', {})
                        extracted_elements = result['extracted_elements']
                        
                        st.write(f"**⚠️ This reference could not be verified in external databases and appears to be fabricated or contains significant errors.**")
                        st.write("**Details of failed authenticity checks:**")
                        
                        current_ref_type = result.get('reference_type', 'journal')

                        if current_ref_type == 'journal':
                            if 'doi' in search_details:
                                st.write(f"• DOI check: {search_details['doi'].get('reason', 'N/A')}")
                                if 'validation_errors' in search_details['doi'] and search_details['doi']['validation_errors']:
                                    for err in search_details['doi']['validation_errors']:
                                        st.markdown(f"  - _{err}_")
                            if 'comprehensive_journal_semanticscholar' in search_details:
                                st.write(f"• Semantic Scholar search: {search_details['comprehensive_journal_semanticscholar'].get('reason', 'N/A')}")
                            if 'comprehensive_journal_pubmed' in search_details:
                                st.write(f"• PubMed search: {search_details['comprehensive_journal_pubmed'].get('reason', 'N/A')}")
                            if 'comprehensive_journal_crossref' in search_details:
                                st.write(f"• Crossref search: {search_details['comprehensive_journal_crossref'].get('reason', 'N/A')}")

                        elif current_ref_type == 'book':
                            if 'isbn_search' in search_details:
                                st.write(f"• ISBN check: {search_details['isbn_search'].get('reason', 'N/A')}")
                            if 'comprehensive_book_openlibrary' in search_details:
                                st.write(f"• Book database search (Open Library): {search_details['comprehensive_book_openlibrary'].get('reason', 'N/A')}")
                            if 'comprehensive_book_googlebooks' in search_details:
                                st.write(f"• Book database search (Google Books): {search_details['comprehensive_book_googlebooks'].get('reason', 'N/A')}")
                        elif current_ref_type == 'website':
                            if 'website_check' in search_details:
                                st.write(f"• Website accessibility: {search_details['website_check'].get('reason', 'N/A')}")
                        
                        st.write("• No credible external database verification was successful for this reference based on the extracted information.")
                        st.write("---")
                        st.write("**Suggestions:**")
                        st.write("- Double-check the authors, title, year, and journal/publisher/URL for typos.")
                        st.write("- Ensure the reference is genuinely published and not a draft or unindexed work.")
                        st.write("- If it's a book, try searching by ISBN directly if available.")
                    
                    if i < len(results) - 1:
                        st.markdown("---")
            else:
                st.warning("No references found. Please enter some references to verify.")
        
        elif verify_button:
            st.warning("Please enter some references to verify.")
    
    with st.expander("ℹ️ How the Three-Level Verification Works"):
        st.markdown("""
        The verification process now prioritizes **Authenticity** first, then checks **Structure**, and relies on **Content Extraction** to feed the other two levels.
        
        **Level 2: Content Extraction** ⚠️ (Happens First)
        - Extracts key elements (authors, title, year, journal/publisher, DOI/ISBN/URL) from the raw text.
        - Assesses how confidently these elements could be extracted. If extraction fails significantly, the reference cannot be verified further.
        
        **Level 3: Existence Verification (Authenticity)** 🚨 (Happens Second)
        - **This is the primary authenticity check.**
        - **Journals**: DOI validation (now with comprehensive content matching), Crossref searches (matching authors, title, journal, year), **PubMed**, and **Semantic Scholar**.
        - **Books**: ISBN lookup via Open Library, comprehensive book search via Open Library and Google Books (matching authors, title, publisher, year).
        - **Websites**: URL accessibility checking.
        - **Identifies likely fake references**: If no strong matches are found across multiple key data points in reputable databases.
        
        **Level 1: Structure Check** 🔧 (Happens Third, if Authentic)
        - If a reference is confirmed as authentic by Level 3, this level then verifies its basic formatting (APA/Vancouver layout).
        - Checks for required elements based on its detected type (journal/book/website).
        - **Lenient** - focuses on structure, not exact formatting details.
        
        **Result Categories:**
        - ✅ **Valid**: Passes authenticity and has correct formatting.
        - ⚠️ **Authentic but Structural Format Issues**: Verified as authentic in databases, but has formatting problems that need fixing.
        - ⚠️ **Content Issues**: Key information could not be reliably extracted from the reference text, preventing authenticity checks.
        - 🚨 **Likely Fake**: Well-formatted but could not be found or verified in any external database, suggesting it might be fabricated.
        """)

if __name__ == "__main__":
    main()

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
        self.timeout = 20

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
                composite_score += title_similarity * 0.4

            # --- Author Match (30% weight) ---
            parsed_expected_authors = []
            for a in re.split(r'[,&]', expected_authors):
                parsed_author = ReferenceParser()._extract_author_parts(a) # Use ReferenceParser's method
                if parsed_author:
                    parsed_expected_authors.append(parsed_author)

            parsed_actual_authors = []
            for author_data in work.get('author', []):
                surname = author_data.get('family', '').lower()
                given_name = author_data.get('given', '')
                initials = ''.join(re.findall(r'[A-Za-z]', given_name)).lower()
                if surname:
                    parsed_actual_authors.append({'surname': surname, 'initials': initials})

            author_score = 0.0
            if parsed_expected_authors and parsed_actual_authors:
                matched_surnames = 0
                matched_initials_bonus_score = 0.0
                
                actual_surnames_set = {a['surname'] for a in parsed_actual_authors}
                actual_initials_map = {a['surname']: a['initials'] for a in parsed_actual_authors if a['initials']}

                for exp_author in parsed_expected_authors:
                    exp_surname = exp_author['surname']
                    exp_initials = exp_author['initials']

                    if exp_surname in actual_surnames_set:
                        matched_surnames += 1
                        if exp_initials and exp_surname in actual_initials_map and exp_initials == actual_initials_map[exp_surname]:
                            matched_initials_bonus_score += 0.5 # Each initial match adds 0.5 to a potential bonus

                if parsed_expected_authors:
                    author_score = matched_surnames / len(parsed_expected_authors)
                
                # Add a small, capped bonus for initials match
                author_score += (matched_initials_bonus_score / len(parsed_expected_authors)) * 0.1 # Max 0.05 bonus
                author_score = min(author_score, 1.0) # Cap score at 1.0

                if author_score < self.similarity_threshold: # Check overall author score against threshold
                     validation_errors.append(f"Author mismatch (expected: {expected_authors}, actual: {actual_authors_list}, score: {author_score:.1%})")
            composite_score += author_score * 0.3


            journal_sim = 0.0
            if expected_journal and actual_journal:
                journal_sim = self._calculate_title_similarity(expected_journal.lower(), actual_journal.lower())
                if journal_sim < self.similarity_threshold:
                    validation_errors.append(f"Journal mismatch (expected: '{expected_journal}', actual: '{actual_journal}', similarity: {journal_sim:.1%})")
                composite_score += journal_sim * 0.2
            
            year_match_score = 0.0
            if expected_year and actual_year:
                if expected_year == actual_year:
                    year_match_score = 1.0
                elif abs(int(expected_year) - int(actual_year)) <= 2:
                    year_match_score = 0.5
                if year_match_score < 1.0 and expected_year != actual_year:
                     validation_errors.append(f"Year mismatch (expected: {expected_year}, actual: {actual_year})")
                composite_score += year_match_score * 0.1

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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{4,}\b', title)[:4]
                query_parts.extend(title_words)
            
            # Use parsed authors for query parts
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_comprehensive_match_score(item, title, authors, year, journal)
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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)[:5]
                query_parts.extend(title_words)
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_book_match_score(doc, title, authors, year, publisher)
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
        try:
            query_parts = []
            if title:
                query_parts.append(f"intitle:{title}")
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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

                    score = self._calculate_google_book_match_score(
                        item_title, item_authors, item_published_date, item_publisher,
                        title, authors, year, publisher
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
        words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title1.lower()))
        words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

    def _calculate_comprehensive_match_score(self, item: Dict, target_title: str, target_authors: str, target_year: str, target_journal: str) -> float:
        score = 0.0
        
        title_sim = 0.0
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.4 # Title weight 40%
        
        # --- Author Matching (30% weight) ---
        parsed_target_authors = []
        for a in re.split(r'and|&|,', target_authors):
            parsed_author = ReferenceParser()._extract_author_parts(a)
            if parsed_author:
                parsed_target_authors.append(parsed_author)

        parsed_item_authors = []
        if 'author' in item and item['author']:
            for author_data in item['author']:
                surname = author_data.get('family', '').lower()
                given_name = author_data.get('given', '')
                initials = ''.join(re.findall(r'[A-Za-z]', given_name)).lower()
                if surname:
                    parsed_item_authors.append({'surname': surname, 'initials': initials})

        author_score = 0.0
        if parsed_target_authors and parsed_item_authors:
            matched_surnames = 0
            initial_bonus = 0.0 # Total bonus from initials

            item_surnames_set = {a['surname'] for a in parsed_item_authors}
            item_initials_map = {a['surname']: a['initials'] for a in parsed_item_authors if a['initials']}

            for target_author_part in parsed_target_authors:
                target_surname = target_author_part['surname']
                target_initials = target_author_part['initials']

                if target_surname in item_surnames_set:
                    matched_surnames += 1
                    # Add bonus for matching initials if surname is already matched
                    if target_initials and target_surname in item_initials_map and target_initials == item_initials_map[target_surname]:
                        initial_bonus += 0.5 # Each initial match adds 0.5 to a potential bonus

            if parsed_target_authors:
                # Base score on proportion of matched surnames
                author_score = matched_surnames / len(parsed_target_authors)
                # Add capped bonus from initials
                author_score += (initial_bonus / len(parsed_target_authors)) * 0.1 # Max 0.05 bonus
                author_score = min(author_score, 1.0) # Cap score at 1.0
        
        score += author_score * 0.3 # Author weight 30%
        
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
            if year_match_score < 1.0 and expected_year != actual_year:
                     validation_errors.append(f"Year mismatch (expected: {expected_year}, actual: {actual_year})")
                composite_score += year_match_score * 0.1

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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{4,}\b', title)[:4]
                query_parts.extend(title_words)
            
            # Use parsed authors for query parts
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_comprehensive_match_score(item, title, authors, year, journal)
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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)[:5]
                query_parts.extend(title_words)
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_book_match_score(doc, title, authors, year, publisher)
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
        try:
            query_parts = []
            if title:
                query_parts.append(f"intitle:{title}")
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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

                    score = self._calculate_google_book_match_score(
                        item_title, item_authors, item_published_date, item_publisher,
                        title, authors, year, publisher
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
        words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title1.lower()))
        words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

    def _calculate_comprehensive_match_score(self, item: Dict, target_title: str, target_authors: str, target_year: str, target_journal: str) -> float:
        score = 0.0
        
        title_sim = 0.0
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.4 # Title weight 40%
        
        # --- Author Matching (30% weight) ---
        parsed_target_authors = []
        for a in re.split(r'and|&|,', target_authors):
            parsed_author = ReferenceParser()._extract_author_parts(a)
            if parsed_author:
                parsed_target_authors.append(parsed_author)

        parsed_item_authors = []
        if 'author' in item and item['author']:
            for author_data in item['author']:
                surname = author_data.get('family', '').lower()
                given_name = author_data.get('given', '')
                initials = ''.join(re.findall(r'[A-Za-z]', given_name)).lower()
                if surname:
                    parsed_item_authors.append({'surname': surname, 'initials': initials})

        author_score = 0.0
        if parsed_target_authors and parsed_item_authors:
            matched_surnames = 0
            initial_bonus = 0.0 # Total bonus from initials

            item_surnames_set = {a['surname'] for a in parsed_item_authors}
            item_initials_map = {a['surname']: a['initials'] for a in parsed_item_authors if a['initials']}

            for target_author_part in parsed_target_authors:
                target_surname = target_author_part['surname']
                target_initials = target_author_part['initials']

                if target_surname in item_surnames_set:
                    matched_surnames += 1
                    # Add bonus for matching initials if surname is already matched
                    if target_initials and target_surname in item_initials_map and target_initials == item_initials_map[target_surname]:
                        initial_bonus += 0.5 # Each initial match adds 0.5 to a potential bonus

            if parsed_target_authors:
                # Base score on proportion of matched surnames
                author_score = matched_surnames / len(parsed_target_authors)
                # Add capped bonus from initials
                author_score += (initial_bonus / len(parsed_target_authors)) * 0.1 # Max 0.05 bonus
                author_score = min(author_score, 1.0) # Cap score at 1.0
        
        score += author_score * 0.3 # Author weight 30%
        
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
            if year_match_score < 1.0 and expected_year != actual_year:
                     validation_errors.append(f"Year mismatch (expected: {expected_year}, actual: {actual_year})")
                composite_score += year_match_score * 0.1

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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{4,}\b', title)[:4]
                query_parts.extend(title_words)
            
            # Use parsed authors for query parts
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_comprehensive_match_score(item, title, authors, year, journal)
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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)[:5]
                query_parts.extend(title_words)
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_book_match_score(doc, title, authors, year, publisher)
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
        try:
            query_parts = []
            if title:
                query_parts.append(f"intitle:{title}")
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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

                    score = self._calculate_google_book_match_score(
                        item_title, item_authors, item_published_date, item_publisher,
                        title, authors, year, publisher
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
        words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title1.lower()))
        words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

    def _calculate_comprehensive_match_score(self, item: Dict, target_title: str, target_authors: str, target_year: str, target_journal: str) -> float:
        score = 0.0
        
        title_sim = 0.0
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.4 # Title weight 40%
        
        # --- Author Matching (30% weight) ---
        parsed_target_authors = []
        for a in re.split(r'and|&|,', target_authors):
            parsed_author = ReferenceParser()._extract_author_parts(a)
            if parsed_author:
                parsed_target_authors.append(parsed_author)

        parsed_item_authors = []
        if 'author' in item and item['author']:
            for author_data in item['author']:
                surname = author_data.get('family', '').lower()
                given_name = author_data.get('given', '')
                initials = ''.join(re.findall(r'[A-Za-z]', given_name)).lower()
                if surname:
                    parsed_item_authors.append({'surname': surname, 'initials': initials})

        author_score = 0.0
        if parsed_target_authors and parsed_item_authors:
            matched_surnames = 0
            initial_bonus = 0.0 # Total bonus from initials

            item_surnames_set = {a['surname'] for a in parsed_item_authors}
            item_initials_map = {a['surname']: a['initials'] for a in parsed_item_authors if a['initials']}

            for target_author_part in parsed_target_authors:
                target_surname = target_author_part['surname']
                target_initials = target_author_part['initials']

                if target_surname in item_surnames_set:
                    matched_surnames += 1
                    # Add bonus for matching initials if surname is already matched
                    if target_initials and target_surname in item_initials_map and target_initials == item_initials_map[target_surname]:
                        initial_bonus += 0.5 # Each initial match adds 0.5 to a potential bonus

            if parsed_target_authors:
                # Base score on proportion of matched surnames
                author_score = matched_surnames / len(parsed_target_authors)
                # Add capped bonus from initials
                author_score += (initial_bonus / len(parsed_target_authors)) * 0.1 # Max 0.05 bonus
                author_score = min(author_score, 1.0) # Cap score at 1.0
        
        score += author_score * 0.3 # Author weight 30%
        
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
            if year_match_score < 1.0 and expected_year != actual_year:
                     validation_errors.append(f"Year mismatch (expected: {expected_year}, actual: {actual_year})")
                composite_score += year_match_score * 0.1

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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{4,}\b', title)[:4]
                query_parts.extend(title_words)
            
            # Use parsed authors for query parts
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_comprehensive_match_score(item, title, authors, year, journal)
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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)[:5]
                query_parts.extend(title_words)
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_book_match_score(doc, title, authors, year, publisher)
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
        try:
            query_parts = []
            if title:
                query_parts.append(f"intitle:{title}")
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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

                    score = self._calculate_google_book_match_score(
                        item_title, item_authors, item_published_date, item_publisher,
                        title, authors, year, publisher
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
        words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title1.lower()))
        words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

    def _calculate_comprehensive_match_score(self, item: Dict, target_title: str, target_authors: str, target_year: str, target_journal: str) -> float:
        score = 0.0
        
        title_sim = 0.0
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.4 # Title weight 40%
        
        # --- Author Matching (30% weight) ---
        parsed_target_authors = []
        for a in re.split(r'and|&|,', target_authors):
            parsed_author = ReferenceParser()._extract_author_parts(a)
            if parsed_author:
                parsed_target_authors.append(parsed_author)

        parsed_item_authors = []
        if 'author' in item and item['author']:
            for author_data in item['author']:
                surname = author_data.get('family', '').lower()
                given_name = author_data.get('given', '')
                initials = ''.join(re.findall(r'[A-Za-z]', given_name)).lower()
                if surname:
                    parsed_item_authors.append({'surname': surname, 'initials': initials})

        author_score = 0.0
        if parsed_target_authors and parsed_item_authors:
            matched_surnames = 0
            initial_bonus = 0.0 # Total bonus from initials

            item_surnames_set = {a['surname'] for a in parsed_item_authors}
            item_initials_map = {a['surname']: a['initials'] for a in parsed_item_authors if a['initials']}

            for target_author_part in parsed_target_authors:
                target_surname = target_author_part['surname']
                target_initials = target_author_part['initials']

                if target_surname in item_surnames_set:
                    matched_surnames += 1
                    # Add bonus for matching initials if surname is already matched
                    if target_initials and target_surname in item_initials_map and target_initials == item_initials_map[target_surname]:
                        initial_bonus += 0.5 # Each initial match adds 0.5 to a potential bonus

            if parsed_target_authors:
                # Base score on proportion of matched surnames
                author_score = matched_surnames / len(parsed_target_authors)
                # Add capped bonus from initials
                author_score += (initial_bonus / len(parsed_target_authors)) * 0.1 # Max 0.05 bonus
                author_score = min(author_score, 1.0) # Cap score at 1.0
        
        score += author_score * 0.3 # Author weight 30%
        
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
            if year_match_score < 1.0 and expected_year != actual_year:
                     validation_errors.append(f"Year mismatch (expected: {expected_year}, actual: {actual_year})")
                composite_score += year_match_score * 0.1

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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{4,}\b', title)[:4]
                query_parts.extend(title_words)
            
            # Use parsed authors for query parts
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_comprehensive_match_score(item, title, authors, year, journal)
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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)[:5]
                query_parts.extend(title_words)
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_book_match_score(doc, title, authors, year, publisher)
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
        try:
            query_parts = []
            if title:
                query_parts.append(f"intitle:{title}")
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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

                    score = self._calculate_google_book_match_score(
                        item_title, item_authors, item_published_date, item_publisher,
                        title, authors, year, publisher
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
        words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title1.lower()))
        words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

    def _calculate_comprehensive_match_score(self, item: Dict, target_title: str, target_authors: str, target_year: str, target_journal: str) -> float:
        score = 0.0
        
        title_sim = 0.0
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.4 # Title weight 40%
        
        # --- Author Matching (30% weight) ---
        parsed_target_authors = []
        for a in re.split(r'and|&|,', target_authors):
            parsed_author = ReferenceParser()._extract_author_parts(a)
            if parsed_author:
                parsed_target_authors.append(parsed_author)

        parsed_item_authors = []
        if 'author' in item and item['author']:
            for author_data in item['author']:
                surname = author_data.get('family', '').lower()
                given_name = author_data.get('given', '')
                initials = ''.join(re.findall(r'[A-Za-z]', given_name)).lower()
                if surname:
                    parsed_item_authors.append({'surname': surname, 'initials': initials})

        author_score = 0.0
        if parsed_target_authors and parsed_item_authors:
            matched_surnames = 0
            initial_bonus = 0.0 # Total bonus from initials

            item_surnames_set = {a['surname'] for a in parsed_item_authors}
            item_initials_map = {a['surname']: a['initials'] for a in parsed_item_authors if a['initials']}

            for target_author_part in parsed_target_authors:
                target_surname = target_author_part['surname']
                target_initials = target_author_part['initials']

                if target_surname in item_surnames_set:
                    matched_surnames += 1
                    # Add bonus for matching initials if surname is already matched
                    if target_initials and target_surname in item_initials_map and target_initials == item_initials_map[target_surname]:
                        initial_bonus += 0.5 # Each initial match adds 0.5 to a potential bonus

            if parsed_target_authors:
                # Base score on proportion of matched surnames
                author_score = matched_surnames / len(parsed_target_authors)
                # Add capped bonus from initials
                author_score += (initial_bonus / len(parsed_target_authors)) * 0.1 # Max 0.05 bonus
                author_score = min(author_score, 1.0) # Cap score at 1.0
        
        score += author_score * 0.3 # Author weight 30%
        
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
            if year_match_score < 1.0 and expected_year != actual_year:
                     validation_errors.append(f"Year mismatch (expected: {expected_year}, actual: {actual_year})")
                composite_score += year_match_score * 0.1

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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{4,}\b', title)[:4]
                query_parts.extend(title_words)
            
            # Use parsed authors for query parts
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_comprehensive_match_score(item, title, authors, year, journal)
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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)[:5]
                query_parts.extend(title_words)
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_book_match_score(doc, title, authors, year, publisher)
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
        try:
            query_parts = []
            if title:
                query_parts.append(f"intitle:{title}")
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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

                    score = self._calculate_google_book_match_score(
                        item_title, item_authors, item_published_date, item_publisher,
                        title, authors, year, publisher
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
        words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title1.lower()))
        words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

    def _calculate_comprehensive_match_score(self, item: Dict, target_title: str, target_authors: str, target_year: str, target_journal: str) -> float:
        score = 0.0
        
        title_sim = 0.0
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.4 # Title weight 40%
        
        # --- Author Matching (30% weight) ---
        parsed_target_authors = []
        for a in re.split(r'and|&|,', target_authors):
            parsed_author = ReferenceParser()._extract_author_parts(a)
            if parsed_author:
                parsed_target_authors.append(parsed_author)

        parsed_item_authors = []
        if 'author' in item and item['author']:
            for author_data in item['author']:
                surname = author_data.get('family', '').lower()
                given_name = author_data.get('given', '')
                initials = ''.join(re.findall(r'[A-Za-z]', given_name)).lower()
                if surname:
                    parsed_item_authors.append({'surname': surname, 'initials': initials})

        author_score = 0.0
        if parsed_target_authors and parsed_item_authors:
            matched_surnames = 0
            initial_bonus = 0.0 # Total bonus from initials

            item_surnames_set = {a['surname'] for a in parsed_item_authors}
            item_initials_map = {a['surname']: a['initials'] for a in parsed_item_authors if a['initials']}

            for target_author_part in parsed_target_authors:
                target_surname = target_author_part['surname']
                target_initials = target_author_part['initials']

                if target_surname in item_surnames_set:
                    matched_surnames += 1
                    # Add bonus for matching initials if surname is already matched
                    if target_initials and target_surname in item_initials_map and target_initials == item_initials_map[target_surname]:
                        initial_bonus += 0.5 # Each initial match adds 0.5 to a potential bonus

            if parsed_target_authors:
                # Base score on proportion of matched surnames
                author_score = matched_surnames / len(parsed_target_authors)
                # Add capped bonus from initials
                author_score += (initial_bonus / len(parsed_target_authors)) * 0.1 # Max 0.05 bonus
                author_score = min(author_score, 1.0) # Cap score at 1.0
        
        score += author_score * 0.3 # Author weight 30%
        
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
            if year_match_score < 1.0 and expected_year != actual_year:
                     validation_errors.append(f"Year mismatch (expected: {expected_year}, actual: {actual_year})")
                composite_score += year_match_score * 0.1

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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{4,}\b', title)[:4]
                query_parts.extend(title_words)
            
            # Use parsed authors for query parts
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_comprehensive_match_score(item, title, authors, year, journal)
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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)[:5]
                query_parts.extend(title_words)
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_book_match_score(doc, title, authors, year, publisher)
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
        try:
            query_parts = []
            if title:
                query_parts.append(f"intitle:{title}")
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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

                    score = self._calculate_google_book_match_score(
                        item_title, item_authors, item_published_date, item_publisher,
                        title, authors, year, publisher
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
        words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title1.lower()))
        words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

    def _calculate_comprehensive_match_score(self, item: Dict, target_title: str, target_authors: str, target_year: str, target_journal: str) -> float:
        score = 0.0
        
        title_sim = 0.0
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.4 # Title weight 40%
        
        # --- Author Matching (30% weight) ---
        parsed_target_authors = []
        for a in re.split(r'and|&|,', target_authors):
            parsed_author = ReferenceParser()._extract_author_parts(a)
            if parsed_author:
                parsed_target_authors.append(parsed_author)

        parsed_item_authors = []
        if 'author' in item and item['author']:
            for author_data in item['author']:
                surname = author_data.get('family', '').lower()
                given_name = author_data.get('given', '')
                initials = ''.join(re.findall(r'[A-Za-z]', given_name)).lower()
                if surname:
                    parsed_item_authors.append({'surname': surname, 'initials': initials})

        author_score = 0.0
        if parsed_target_authors and parsed_item_authors:
            matched_surnames = 0
            initial_bonus = 0.0 # Total bonus from initials

            item_surnames_set = {a['surname'] for a in parsed_item_authors}
            item_initials_map = {a['surname']: a['initials'] for a in parsed_item_authors if a['initials']}

            for target_author_part in parsed_target_authors:
                target_surname = target_author_part['surname']
                target_initials = target_author_part['initials']

                if target_surname in item_surnames_set:
                    matched_surnames += 1
                    # Add bonus for matching initials if surname is already matched
                    if target_initials and target_surname in item_initials_map and target_initials == item_initials_map[target_surname]:
                        initial_bonus += 0.5 # Each initial match adds 0.5 to a potential bonus

            if parsed_target_authors:
                # Base score on proportion of matched surnames
                author_score = matched_surnames / len(parsed_target_authors)
                # Add capped bonus from initials
                author_score += (initial_bonus / len(parsed_target_authors)) * 0.1 # Max 0.05 bonus
                author_score = min(author_score, 1.0) # Cap score at 1.0
        
        score += author_score * 0.3 # Author weight 30%
        
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
            if year_match_score < 1.0 and expected_year != actual_year:
                     validation_errors.append(f"Year mismatch (expected: {expected_year}, actual: {actual_year})")
                composite_score += year_match_score * 0.1

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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{4,}\b', title)[:4]
                query_parts.extend(title_words)
            
            # Use parsed authors for query parts
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_comprehensive_match_score(item, title, authors, year, journal)
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
        try:
            query_parts = []
            
            if title:
                title_words = re.findall(r'\b[a-zA-Z]{3,}\b', title)[:5]
                query_parts.extend(title_words)
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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
                    score = self._calculate_book_match_score(doc, title, authors, year, publisher)
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
        try:
            query_parts = []
            if title:
                query_parts.append(f"intitle:{title}")
            
            parsed_authors_for_query = []
            for a in re.split(r'[,&]', authors):
                parsed_author = ReferenceParser()._extract_author_parts(a)
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

                    score = self._calculate_google_book_match_score(
                        item_title, item_authors, item_published_date, item_publisher,
                        title, authors, year, publisher
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
        words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title1.lower()))
        words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', title2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

    def _calculate_comprehensive_match_score(self, item: Dict, target_title: str, target_authors: str, target_year: str, target_journal: str) -> float:
        score = 0.0
        
        title_sim = 0.0
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.4 # Title weight 40%
        
        # --- Author Matching (30% weight) ---
        parsed_target_authors = []
        for a in re.split(r'and|&|,', target_authors):
            parsed_author = ReferenceParser()._extract_author_parts(a)
            if parsed_author:
                parsed_target_authors.append(parsed_author)

        parsed_item_authors = []
        if 'author' in item and item['author']:
            for author_data in item['author']:
                surname = author_data.get('family', '').lower()
                given_name = author_data.get('given', '')
                initials = ''.join(re.findall(r'[A-Za-z]', given_name)).lower()
                if surname:
                    parsed_item_authors.append({'surname': surname, 'initials': initials})

        author_score = 0.0
        if parsed_target_authors and parsed_item_authors:
            matched_surnames = 0
            initial_bonus = 0.0 # Total bonus from initials

            item_surnames_set = {a['surname'] for a in parsed_item_authors}
            item_initials_map = {a['surname']: a['initials'] for a in parsed_item_authors if a['initials']}

            for target_author_part in parsed_target_authors:
                target_surname = target_author_part['surname']
                target_initials = target_author_part['initials']

                if target_surname in item_surnames_set:
                    matched_surnames += 1
                    # Add bonus for matching initials if surname is already matched
                    if target_initials and target_surname in item_initials_map and target_initials == item_initials_map[target_surname]:
                        initial_bonus += 0.5 # Each initial match adds 0.5 to a potential bonus

            if parsed_target_authors:
                # Base score on proportion of matched surnames
                author_score = matched_surnames / len(parsed_target_authors)
                # Add capped bonus from initials
                author_score += (initial_bonus / len(parsed_target_authors)) * 0.1 # Max 0.05 bonus
                author_score = min(author_score, 1.0) # Cap score at 1.0
        
        score += author_score * 0.3 # Author weight 30%
        
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
            if year_match_score < 1.0 and expected_year != actual_year:
                     validation_errors.append(f"Year mismatch (expected: {expected_year}, actual: {actual_year})")
                composite_score += year_match_score * 0.1

            if validation_errors:
                return {
                    'vali

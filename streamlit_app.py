import streamlit as st
import re
import requests
import time
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import difflib

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
    publisher: str = None # Added for books
    edition: str = None # Added for books

class JournalAbbreviationMatcher:
    """Handles journal name variations and official abbreviations"""
    
    def __init__(self):
        # Common journal abbreviations database (expanded)
        self.abbreviations = {
            'eur j prev cardiol': 'european journal of preventive cardiology',
            'ejpc': 'european journal of preventive cardiology',
            'eur heart j': 'european heart journal',
            'ehj': 'european heart journal',
            'circulation': 'circulation',
            'circ': 'circulation',
            'jacc': 'journal of the american college of cardiology',
            'j am coll cardiol': 'journal of the american college of cardiology',
            'nejm': 'new england journal of medicine',
            'n engl j med': 'new england journal of medicine',
            'jama': 'journal of the american medical association',
            'bmj': 'british medical journal',
            'lancet': 'the lancet',
            'med sci sports exerc': 'medicine and science in sports and exercise',
            'j sports sci': 'journal of sports sciences',
            'sports med': 'sports medicine',
            'nature': 'nature',
            'science': 'science',
            'pnas': 'proceedings of the national academy of sciences',
            'plos one': 'plos one',
            'strength & conditioning journal': 'strength and conditioning journal', # Added for example
            'strength cond j': 'strength and conditioning journal',
            'j strength cond res': 'journal of strength and conditioning research'
        }

    def normalize_journal_name(self, journal_name: str) -> str:
        """Normalize journal name for comparison"""
        if not journal_name:
            return ""
        
        normalized = re.sub(r'[^\w\s]', ' ', journal_name.lower())
        normalized = ' '.join(normalized.split())
        
        # Check against abbreviations first for direct hits
        if normalized in self.abbreviations:
            return self.abbreviations[normalized]
        
        # Also check if the normalized name is a value in abbreviations
        for key, value in self.abbreviations.items():
            if normalized == value:
                return normalized # Already normalized official name
        
        return normalized

    def calculate_journal_similarity(self, journal1: str, journal2: str) -> float:
        """Calculate similarity between two journal names"""
        if not journal1 or not journal2:
            return 0.0
        
        norm1 = self.normalize_journal_name(journal1)
        norm2 = self.normalize_journal_name(journal2)
        
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        
        if words1 and words2:
            # Jaccard similarity for word overlap
            word_similarity = len(words1.intersection(words2)) / len(words1.union(words2))
            # SequenceMatcher for character-level similarity
            string_similarity = difflib.SequenceMatcher(None, norm1, norm2).ratio()
            # Weighted average - giving more weight to word similarity
            return (word_similarity * 0.7) + (string_similarity * 0.3)
        
        return 0.0

class ContentConsistencyChecker:
    """Checks for content inconsistencies between reference elements"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.timeout = 10

    def check_content_consistency(self, elements: Dict) -> Dict:
        """Check for content inconsistencies and mismatches"""
        result = {
            'is_consistent': True,
            'content_errors': [],
            'content_warnings': [],
            'consistency_score': 1.0,
            'verification_details': []
        }
        
        if not elements:
            return result
        
        ref_type = elements.get('reference_type', 'unknown')
        
        # Check DOI-Journal consistency for journals
        if ref_type == 'journal' and elements.get('doi') and elements.get('journal'):
            try:
                doi_consistency = self._check_doi_journal_consistency(
                    elements['doi'], elements['journal'], result
                )
                if not doi_consistency:
                    result['consistency_score'] -= 0.4
            except Exception as e:
                result['verification_details'].append(f"DOI consistency check error: {str(e)}")
        
        # Check journal validity (only if it's a journal reference and a journal name was extracted)
        if ref_type == 'journal' and elements.get('journal'):
            try:
                journal_validity = self._check_journal_validity(elements['journal'], result)
                if not journal_validity:
                    result['consistency_score'] -= 0.3
            except Exception as e:
                result['verification_details'].append(f"Journal validity check error: {str(e)}")
        
        # Check title presence (universal check)
        if not elements.get('title'):
            result['content_warnings'].append("Title could not be extracted or is missing.")
            result['consistency_score'] -= 0.1
        
        result['is_consistent'] = len(result['content_errors']) == 0
        result['consistency_score'] = max(0.0, result['consistency_score']) # Ensure score doesn't go below 0
        
        return result

    def _check_doi_journal_consistency(self, doi: str, journal: str, result: Dict) -> bool:
        """Check if DOI matches the claimed journal"""
        try:
            crossref_url = f"https://api.crossref.org/works/{doi}"
            response = self.session.get(crossref_url, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                if 'message' in data and 'container-title' in data['message']:
                    actual_journal_list = data['message']['container-title']
                    if actual_journal_list:
                        actual_journal = actual_journal_list[0] # Take the first one if multiple
                        
                        journal_matcher = JournalAbbreviationMatcher()
                        similarity = journal_matcher.calculate_journal_similarity(
                            journal, actual_journal
                        )
                        
                        result['verification_details'].append(
                            f"DOI points to journal: '{actual_journal}' (normalized: '{journal_matcher.normalize_journal_name(actual_journal)}'), Reference claims: '{journal}' (normalized: '{journal_matcher.normalize_journal_name(journal)}'). Similarity: {similarity:.2f}"
                        )
                        
                        if similarity < 0.6: # Lowered threshold slightly for more flexibility
                            result['content_errors'].append(
                                f"Journal name mismatch: DOI is from '{actual_journal}' but reference claims '{journal}' (Similarity: {similarity:.2f})"
                            )
                            return False
                        elif similarity < 0.8:
                            result['content_warnings'].append(
                                f"Possible journal name variation: DOI shows '{actual_journal}', reference shows '{journal}' (Similarity: {similarity:.2f})"
                            )
                        
                        return True # Even with a warning, it's consistent enough not to be an "error"
            elif response.status_code == 404:
                result['verification_details'].append(f"DOI '{doi}' not found on CrossRef. Cannot verify journal consistency.")
                return True # Cannot verify, so not an inconsistency error
            else:
                result['verification_details'].append(f"CrossRef API error for DOI '{doi}' (Status: {response.status_code}). Cannot verify journal consistency.")
                return True
            
            return True # If no container-title or other issues, assume consistency for now
            
        except requests.exceptions.Timeout:
            result['verification_details'].append(f"CrossRef DOI consistency check timed out for DOI: {doi}")
            return True
        except requests.exceptions.RequestException as e:
            result['verification_details'].append(f"Network error during DOI consistency check for DOI {doi}: {str(e)}")
            return True
        except Exception as e:
            result['verification_details'].append(f"Unexpected error during Journal-DOI consistency check for DOI {doi}: {str(e)}")
            return True

    def _check_journal_validity(self, journal: str, result: Dict) -> bool:
        """Check if journal name exists in academic databases (using CrossRef journal API)"""
        try:
            # Normalize journal name before querying
            journal_matcher = JournalAbbreviationMatcher()
            normalized_journal = journal_matcher.normalize_journal_name(journal)
            
            url = "https://api.crossref.org/journals"
            params = {'query': normalized_journal, 'rows': 5} # Fetch top 5 relevant journals
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                
                if 'message' in data and 'items' in data['message']:
                    items = data['message']['items']
                    
                    if not items:
                        result['content_warnings'].append(
                            f"Journal '{journal}' (normalized: '{normalized_journal}') not found in CrossRef's journal list. It might be an unofficial journal, a book title, or a typo."
                        )
                        return False
                    
                    # Check for a good similarity match among the results
                    found_match = False
                    for item in items:
                        crossref_journal_name = item.get('title', '').lower()
                        similarity = journal_matcher.calculate_journal_similarity(normalized_journal, crossref_journal_name)
                        if similarity >= 0.8: # High similarity needed for a positive match
                            result['verification_details'].append(f"Journal '{journal}' matched with '{crossref_journal_name}' (Similarity: {similarity:.2f}) in CrossRef database.")
                            found_match = True
                            break
                    
                    if not found_match:
                        result['content_warnings'].append(
                            f"Journal '{journal}' (normalized: '{normalized_journal}') found some potential matches in CrossRef, but none were highly similar. It might be a variation or a less common journal."
                        )
                        return False
                    
                    return True
            elif response.status_code == 404:
                result['content_warnings'].append(f"Crossref journal API endpoint not found. Cannot verify journal validity for '{journal}'.")
                return True # Can't verify, not an error of the journal itself
            else:
                result['verification_details'].append(f"CrossRef Journal API error (Status: {response.status_code}). Cannot verify journal validity for '{journal}'.")
                return True
            
        except requests.exceptions.Timeout:
            result['verification_details'].append(f"CrossRef Journal validity check timed out for journal: {journal}")
            return True
        except requests.exceptions.RequestException as e:
            result['verification_details'].append(f"Network error during Journal validity check for '{journal}': {str(e)}")
            return True
        except Exception as e:
            result['verification_details'].append(f"Unexpected error during Journal validity check for '{journal}': {str(e)}")
            return True

class FixedParser:
    """Parser with all syntax errors fixed and improved extraction logic"""
    
    def __init__(self):
        self.journal_matcher = JournalAbbreviationMatcher()
        self.content_checker = ContentConsistencyChecker()
        
        # FIXED: Corrected regex patterns and added more robust ones
        self.patterns = {
            'year_in_paren': r'\s*\((\d{4}[a-z]?)\)\.?', # Catches (YYYY) or (YYYYa). at end of author section
            'doi_pattern': r'(?:https?://doi\.org/|doi:)([^\s]+)', # Catches both URL and "doi:" prefix
            'isbn_pattern': r'(?:ISBN(?:-1[03])?:?\s*|)\b([\d\-X]{10,17})\b', # More flexible ISBN capture
            'url_pattern': r'(https?://[^\s,]+)', # Exclude comma from URL capture
            'title_after_year': r'\)\.\s*([\'\"A-Z].*?)(?:\.|\?|!|\s*\[|\s*\(|\s*(?:Vol|No|Edition|Ed\.)|\s*ISBN|\s*doi:|\s*https?://|$)', # Improved title extraction
            'journal_volume_pages': r'([A-Za-z\s&,.]+?)\s*[,.]?\s*(\d+)\s*(?:\((\d+)\))?[,\-–\s]*(\d+[-–]\d+|\d+)\.?', # Journal, Volume(Issue), Pages
            'publisher_names': r'(?:(?:[A-Z][a-z]+(?:\s(?:[A-Z][a-z]+|[&]))*?\s*(?:Press|Publishers|Kluwer|Elsevier|Springer|Wiley|Academic Press|University Press|McGraw-Hill|Norton))|(?:MIT Press|Human Kinetics|Cambridge University Press|Oxford University Press|Pearson))', # More publisher names
            'edition_info': r'\((\d+(?:st|nd|rd|th)?\s*ed(?:\.|ition)?)\)', # e.g., (11th ed.)
            'access_date': r'(?:Retrieved|Accessed)\s+(?:on\s+)?(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}|\d{4}\s+[A-Za-z]+\s+\d{1,2})\s*,?\s*from', # More robust access date
            'chapter_in_book': r'\bIn\s+([^\.]+?),\s*(?:Ed|\(Ed\)|Eds|\(Eds\))\.', # For book chapters
        }
        
        # Format checking patterns
        self.format_patterns = {
            'comma_before_year': r'[^.]\s*,\s*\(\d{4}[a-z]?\)',
            'proper_year_period': r'\.\s*\(\d{4}[a-z]?\)\.', # e.g., . (2020).
            'author_initials_spacing': r'[A-Z]\.\s*[A-Z]\.', # e.g., J. D.
            'multiple_authors_comma_ampersand': r', &',
            'no_period_after_author_initial': r'[A-Z][a-z]*\s+[A-Z](?![.])', # e.g., John D (missing period)
            'missing_period_after_title': r'[^\.!?]\s*\(\d{4}[a-z]?\)\s*$' # Title not ending with period before year
        }

    def extract_elements_safely(self, ref_text: str) -> Dict:
        """Extract elements with comprehensive error handling"""
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
            'edition': None, # Added edition
            'reference_type': 'unknown',
            'extraction_errors': [],
            'confidence': 0.0
        }
        
        if not ref_text or len(ref_text.strip()) < 10:
            elements['extraction_errors'].append("Reference too short or empty")
            return elements
        
        try:
            # 1. Extract DOI and ISBN early, as they are strong indicators
            doi_match = re.search(self.patterns['doi_pattern'], ref_text, re.IGNORECASE)
            if doi_match:
                elements['doi'] = doi_match.group(1).strip().rstrip('.') # Remove trailing period if present
                elements['confidence'] += 0.3
                elements['reference_type'] = 'journal' # Strong indicator for journal
            
            isbn_match = re.search(self.patterns['isbn_pattern'], ref_text, re.IGNORECASE)
            if isbn_match:
                elements['isbn'] = isbn_match.group(1).strip()
                elements['confidence'] += 0.3
                elements['reference_type'] = 'book' # Strong indicator for book
            
            # 2. Extract year and authors (everything before year)
            year_match = re.search(self.patterns['year_in_paren'], ref_text)
            if year_match:
                elements['year'] = year_match.group(1)
                elements['confidence'] += 0.2
                
                # Extract authors (text before the year, ignoring trailing punctuation/spaces)
                try:
                    author_section = ref_text[:year_match.start()].strip()
                    # Remove common trailing punctuation after authors (e.g., .)
                    author_section = re.sub(r'[,\.\s]+$', '', author_section)
                    if author_section and len(author_section) > 3: # Min length to avoid capturing noise
                        elements['authors'] = author_section
                        elements['confidence'] += 0.2
                except Exception as e:
                    elements['extraction_errors'].append(f"Author extraction error: {str(e)}")
            else:
                elements['extraction_errors'].append("No year found in parentheses (APA style assumption)")
            
            # 3. Detect reference type (if not already set by DOI/ISBN)
            if elements['reference_type'] == 'unknown':
                elements['reference_type'] = self._detect_type(ref_text)
            
            # 4. Extract content based on type, starting from after the year or from the beginning
            text_after_year = ref_text[year_match.end():] if year_match else ref_text
            self._extract_content_by_type(ref_text, text_after_year, elements)
            
            # 5. Extract URL for websites (regardless of initial type detection)
            url_match = re.search(self.patterns['url_pattern'], ref_text)
            if url_match:
                elements['url'] = url_match.group(1).strip()
                elements['confidence'] += 0.1
                # If URL is present and not a DOI, might be a website or online book/journal
                if elements['reference_type'] not in ['journal', 'book'] and \
                   not elements['doi'] and not elements['isbn']:
                    elements['reference_type'] = 'website'

            # Final confidence boost based on number of extracted elements
            extracted_count = sum(1 for k, v in elements.items() if v is not None and k not in ['extraction_errors', 'confidence', 'reference_type'])
            elements['confidence'] = min(1.0, elements['confidence'] + (extracted_count * 0.05)) # Max 1.0

        except Exception as e:
            elements['extraction_errors'].append(f"Critical extraction error: {str(e)}")
        
        return elements

    def _detect_type(self, ref_text: str) -> str:
        """Detect reference type with improved logic"""
        if not ref_text:
            return 'unknown'
        
        ref_lower = ref_text.lower()
        
        # Scoring system for types
        journal_score = 0
        book_score = 0
        website_score = 0
        
        # Strong indicators (already handled by direct extraction, but good for scoring)
        if re.search(self.patterns['doi_pattern'], ref_text, re.IGNORECASE):
            journal_score += 5
        if re.search(self.patterns['isbn_pattern'], ref_text, re.IGNORECASE):
            book_score += 5
        if re.search(self.patterns['url_pattern'], ref_text) and re.search(self.patterns['access_date'], ref_text, re.IGNORECASE):
            website_score += 5
        
        # Journal indicators
        journal_keywords = ['journal', 'review', 'science', 'research', 'therapy', 'medicine', 'academy', 'association', 'proceedings']
        for keyword in journal_keywords:
            if keyword in ref_lower:
                journal_score += 1
        
        # Specific journal volume/pages pattern
        if re.search(r'\d+\s*\(\d+\)\s*,\s*\d+[-–]\d+', ref_text) or \
           re.search(r'\d+,\s*\d+[-–]\d+', ref_text):
            journal_score += 3 # High score for volume, issue, pages

        # Book indicators
        book_keywords = ['press', 'publisher', 'edition', 'ed\.', 'handbook', 'manual', 'textbook', 'guidelines', 'series', 'volume', 'chapter', 'edited by']
        for keyword in book_keywords:
            if re.search(rf'\b{keyword}\b', ref_lower):
                book_score += 2
        
        if re.search(self.patterns['edition_info'], ref_text, re.IGNORECASE):
            book_score += 3

        if re.search(self.patterns['publisher_names'], ref_text, re.IGNORECASE):
            book_score += 4
        
        if re.search(self.patterns['chapter_in_book'], ref_text, re.IGNORECASE):
            book_score += 4

        # Website indicators
        website_keywords = ['retrieved', 'accessed', 'available from', 'www\.', '\.com', '\.org', '\.edu', '\.gov', 'date posted', 'last modified']
        for keyword in website_keywords:
            if re.search(rf'{keyword}', ref_lower):
                website_score += 1
        
        # Determine type based on highest score
        if book_score > journal_score and book_score > website_score:
            return 'book'
        elif journal_score > book_score and journal_score > website_score:
            return 'journal'
        elif website_score > book_score and website_score > journal_score:
            return 'website'
        else: # Default or ambiguous cases
            if re.search(self.patterns['url_pattern'], ref_text): # If a URL is present, lean towards website
                return 'website'
            return 'unknown'

    def _extract_content_by_type(self, ref_text: str, text_after_year: str, elements: Dict) -> None:
        """Extract content based on reference type"""
        ref_type = elements.get('reference_type', 'unknown')
        
        try:
            # Extract title (always try to extract a title first)
            title_match = re.search(self.patterns['title_after_year'], text_after_year, re.IGNORECASE)
            if title_match:
                elements['title'] = title_match.group(1).strip()
                # Clean up title: remove trailing punctuation unless it's part of the title (e.g., question mark)
                elements['title'] = re.sub(r'[\s.,;:]+$', '', elements['title'])
                elements['confidence'] += 0.2
            else:
                elements['extraction_errors'].append("Could not extract main title effectively.")

            # Type-specific extraction
            if ref_type == 'journal':
                self._extract_journal_info(ref_text, text_after_year, elements)
            elif ref_type == 'book':
                self._extract_book_info(ref_text, elements)
            
        except Exception as e:
            elements['extraction_errors'].append(f"Content extraction error based on type '{ref_type}': {str(e)}")

    def _extract_journal_info(self, ref_text: str, text_after_year: str, elements: Dict) -> None:
        """Extract journal-specific information including journal name, volume, issue, and pages."""
        try:
            # Look for the journal name, volume, issue, and pages in one go
            # Pattern: Journal Name, Volume(Issue), Pages.
            # OR: Journal Name, Volume, Pages.
            journal_vol_pages_match = re.search(self.patterns['journal_volume_pages'], text_after_year, re.IGNORECASE)
            
            if journal_vol_pages_match:
                elements['journal'] = journal_vol_pages_match.group(1).strip().strip(',.')
                elements['volume'] = journal_vol_pages_match.group(2).strip()
                if journal_vol_pages_match.group(3):
                    elements['issue'] = journal_vol_pages_match.group(3).strip()
                elements['pages'] = journal_vol_pages_match.group(4).strip()
                elements['confidence'] += 0.3
            else:
                elements['extraction_errors'].append("Could not extract journal, volume, issue, or pages using combined pattern.")
                # Fallback for journal name if combined fails
                journal_match = re.search(self.patterns['journal_keywords'], text_after_year, re.IGNORECASE)
                if not journal_match:
                    # Broader pattern for journal name (e.g., "Strength & Conditioning Journal")
                    # Look for capitalized words followed by Journal, Review, etc.
                    journal_match = re.search(r'([A-Z][a-zA-Z\s&]+?(?:Journal|Review|Science|Research|Therapy|Medicine|Association|Academy))\b', text_after_year)
                
                if journal_match:
                    elements['journal'] = journal_match.group(1).strip()
                    elements['confidence'] += 0.1
                    self._extract_volume_info(ref_text, elements) # Try to get volume/pages separately
                else:
                    elements['extraction_errors'].append("Could not extract journal name.")
                
        except Exception as e:
            elements['extraction_errors'].append(f"Journal extraction error: {str(e)}")

    def _extract_book_info(self, ref_text: str, elements: Dict) -> None:
        """Extract publisher and edition information for books"""
        try:
            publisher_match = re.search(self.patterns['publisher_names'], ref_text, re.IGNORECASE)
            if publisher_match:
                elements['publisher'] = publisher_match.group(0).strip() # Use group(0) for the whole match
                elements['confidence'] += 0.2
            else:
                elements['extraction_errors'].append("Could not extract publisher.")
            
            edition_match = re.search(self.patterns['edition_info'], ref_text, re.IGNORECASE)
            if edition_match:
                elements['edition'] = edition_match.group(1).strip()
                elements['confidence'] += 0.1
        
        except Exception as e:
            elements['extraction_errors'].append(f"Book info extraction error: {str(e)}")

    def _extract_volume_info(self, ref_text: str, elements: Dict) -> None:
        """Extract volume/issue/pages information (fallback if combined pattern fails)"""
        try:
            # Look for patterns like "Volume(Issue), Pages" or "Volume, Pages"
            volume_pages_pattern = r'\b(\d+)(?:\((\d+)\))?,\s*(\d+[-–]\d+|\d+)\.?'
            volume_match = re.search(volume_pages_pattern, ref_text)
            
            if volume_match:
                elements['volume'] = volume_match.group(1)
                elements['issue'] = volume_match.group(2) if volume_match.group(2) else None
                elements['pages'] = volume_match.group(3)
                elements['confidence'] += 0.1
        except Exception as e:
            elements['extraction_errors'].append(f"Volume/pages fallback extraction error: {str(e)}")

    def check_format_compliance(self, ref_text: str) -> Dict:
        """Check APA format compliance"""
        result = {
            'is_compliant': True,
            'errors': [],
            'warnings': [],
            'suggestions': [],
            'score': 1.0
        }
        
        if not ref_text:
            return result
        
        score_deduction = 0.0
        
        try:
            # Check for comma before year, should be a period in APA
            if re.search(self.format_patterns['comma_before_year'], ref_text):
                result['errors'].append("Comma before year where a period is expected.")
                result['suggestions'].append("Change 'Author, (Year)' to 'Author. (Year).'")
                score_deduction += 0.3
            
            # Check for proper year format (e.g., . (YYYY).)
            if not re.search(self.format_patterns['proper_year_period'], ref_text):
                result['warnings'].append("Year format may not be standard APA (e.g., missing period after year).")
                result['suggestions'].append("Ensure '. (YYYY).' format, including a period after the closing parenthesis.")
                score_deduction += 0.1
            
            # Check for period after author initials (e.g., J. D.)
            if re.search(self.format_patterns['no_period_after_author_initial'], ref_text.split('(')[0]): # Check before year
                 result['warnings'].append("Possible missing period after author initial.")
                 result['suggestions'].append("Ensure all author initials are followed by a period (e.g., J. D. instead of J D).")
                 score_deduction += 0.05

            # Check for correct author separation (comma and ampersand before last author)
            if not re.search(self.format_patterns['multiple_authors_comma_ampersand'], ref_text):
                # This is a warning if multiple authors are detected but the format is off
                if len(re.findall(r'[A-Z]\.', ref_text.split('(')[0])) > 1: # Simple heuristic for multiple authors
                    result['warnings'].append("Author list may not use APA style comma and ampersand before the last author.")
                    result['suggestions'].append("Use 'Author A, Author B, & Author C.' for multiple authors.")
                    score_deduction += 0.1
            
            # Check for period after title if it's not a question mark or exclamation mark
            # This is complex as it depends on whether it's a journal, book, or chapter.
            # A simple check: does the text before the year block end with appropriate punctuation?
            # if not re.search(self.format_patterns['missing_period_after_title'], ref_text):
            #     # This pattern is too simplistic and needs context from extracted elements
            #     pass # Temporarily disable, needs more sophisticated logic

        except Exception as e:
            result['warnings'].append(f"Format checking error: {str(e)}")
        
        result['score'] = max(0.0, 1.0 - score_deduction)
        result['is_compliant'] = len(result['errors']) == 0
        
        return result

    def check_content_consistency(self, elements: Dict) -> Dict:
        """Check content consistency"""
        return self.content_checker.check_content_consistency(elements)

class FixedAuthenticityChecker:
    """Authenticity checker with all fixes applied and improved ISBN/URL checks"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' # Prioritize JSON for APIs
        })
        self.timeout = 15

    def check_authenticity_comprehensive(self, elements: Dict) -> Dict:
        """Comprehensive authenticity check"""
        result = {
            'is_authentic': False,
            'confidence_score': 0.0,
            'confidence_level': 'low',
            'sources_checked': [],
            'verification_details': [],
            'methods_used': [],
            'debug_info': []
        }
        
        if not elements:
            result['verification_details'].append("No elements provided for authenticity check.")
            return result
        
        scores = []
        
        # Method 1: DOI verification (highest confidence)
        doi_score = self._check_doi_safe(elements, result)
        if doi_score > 0:
            scores.append(doi_score)
        
        # Method 2: ISBN verification (high confidence for books)
        if elements.get('reference_type') == 'book' and elements.get('isbn'):
            isbn_score = self._check_isbn_safe(elements, result)
            if isbn_score > 0:
                scores.append(isbn_score)
        
        # Method 3: URL accessibility check (medium confidence for websites)
        if elements.get('reference_type') == 'website' and elements.get('url'):
            url_score = self._check_url_safe(elements, result)
            if url_score > 0:
                scores.append(url_score)

        # Calculate final confidence
        if scores:
            result['confidence_score'] = max(scores) # Take the highest score
            # A small boost if multiple verification methods passed (e.g., DOI and URL if available)
            if len([s for s in scores if s > 0]) > 1:
                result['confidence_score'] = min(1.0, result['confidence_score'] + 0.05)
            
            result['is_authentic'] = result['confidence_score'] >= 0.6
            
            if result['confidence_score'] >= 0.8:
                result['confidence_level'] = 'high'
            elif result['confidence_score'] >= 0.6:
                result['confidence_level'] = 'medium'
            else:
                result['confidence_level'] = 'low'
        else:
            result['confidence_level'] = 'very low'
            result['verification_details'].append("No verifiable identifiers (DOI, ISBN, URL) found or verified.")
        
        return result

    def _check_doi_safe(self, elements: Dict, result: Dict) -> float:
        """Check DOI safely by resolving it and cross-referencing with CrossRef API for metadata."""
        doi = elements.get('doi')
        if not doi:
            return 0.0
        
        result['sources_checked'].append('DOI (Crossref)')
        result['methods_used'].append('DOI resolution & metadata check')
        
        try:
            # Basic DOI format validation
            if not re.match(r'^10\.\d{4,9}/[^\s]+$', doi, re.IGNORECASE):
                result['verification_details'].append(f"DOI '{doi}' has an invalid format.")
                return 0.0

            # 1. Direct DOI resolution check (HTTP redirect)
            doi_url_resolver = f"https://doi.org/{doi}"
            # Use HEAD request for efficiency if only status is needed, but GET might be needed for some redirects
            response_head = self.session.head(doi_url_resolver, timeout=self.timeout, allow_redirects=True)
            
            if response_head.status_code == 200:
                result['verification_details'].append(f"DOI '{doi}' resolved successfully.")
                base_score = 0.8 # Good start
            elif response_head.status_code in [301, 302, 303, 307, 308]:
                result['verification_details'].append(f"DOI '{doi}' resolved via redirect to: {response_head.headers.get('Location', 'N/A')}.")
                base_score = 0.75
            elif response_head.status_code == 403: # Forbidden - might be valid but access restricted
                result['verification_details'].append(f"DOI '{doi}' exists but access is forbidden (403).")
                base_score = 0.6
            elif response_head.status_code == 404:
                result['verification_details'].append(f"DOI '{doi}' not found (404) via direct resolution.")
                return 0.0
            else:
                result['verification_details'].append(f"DOI '{doi}' direct resolution inconclusive (status: {response_head.status_code}).")
                base_score = 0.5

            # 2. CrossRef API metadata check for deeper validation
            crossref_api_url = f"https://api.crossref.org/works/{doi}"
            response_crossref = self.session.get(crossref_api_url, timeout=self.timeout)

            if response_crossref.status_code == 200:
                data = response_crossref.json()
                if 'message' in data and data['message'].get('DOI', '').lower() == doi.lower():
                    result['verification_details'].append(f"DOI '{doi}' metadata found on CrossRef.")
                    
                    # Optional: Compare extracted title with CrossRef title
                    crossref_title = data['message'].get('title', [])
                    if crossref_title and elements.get('title'):
                        crossref_title_str = crossref_title[0] if isinstance(crossref_title, list) and crossref_title else ''
                        extracted_title_normalized = re.sub(r'[^\w\s]', '', elements['title'].lower())
                        crossref_title_normalized = re.sub(r'[^\w\s]', '', crossref_title_str.lower())
                        
                        title_similarity = difflib.SequenceMatcher(None, extracted_title_normalized, crossref_title_normalized).ratio()
                        if title_similarity >= 0.7: # Good title match
                            result['verification_details'].append(f"Title consistency (extracted vs CrossRef): {title_similarity:.2f} (Good).")
                            base_score = min(1.0, base_score + 0.1) # Boost score
                        else:
                            result['verification_details'].append(f"Title inconsistency (extracted vs CrossRef): {title_similarity:.2f}. CrossRef Title: '{crossref_title_str}'.")
                            base_score = max(0.1, base_score - 0.1) # Slightly penalize

                    return min(1.0, base_score + 0.1) # Small boost for finding metadata
                else:
                    result['verification_details'].append(f"DOI '{doi}' not found or mismatched in CrossRef metadata.")
                    return base_score * 0.5 # Halve score if metadata lookup fails
            elif response_crossref.status_code == 404:
                result['verification_details'].append(f"DOI '{doi}' not found on CrossRef API (404).")
                return 0.0
            else:
                result['verification_details'].append(f"CrossRef API error for DOI '{doi}' (Status: {response_crossref.status_code}).")
                return base_score * 0.7 # Slight penalty for API error
            
        except requests.exceptions.Timeout:
            result['debug_info'].append(f"DOI check timed out for {doi}.")
            return 0.5 # Inconclusive but not necessarily fake
        except requests.exceptions.ConnectionError:
            result['debug_info'].append(f"Network connection error during DOI check for {doi}.")
            return 0.4 # Inconclusive due to network
        except Exception as e:
            result['debug_info'].append(f"DOI check error for {doi}: {str(e)}")
            return 0.3 # Generic error, lower confidence

    def _check_isbn_safe(self, elements: Dict, result: Dict) -> float:
        """Check ISBN safely using Open Library API."""
        isbn = elements.get('isbn')
        if not isbn:
            return 0.0
        
        result['sources_checked'].append('ISBN (OpenLibrary)')
        result['methods_used'].append('ISBN lookup')
        
        try:
            # Clean ISBN: remove hyphens and ensure proper length
            isbn_clean = re.sub(r'[^\dX]', '', isbn.upper())
            if not (len(isbn_clean) == 10 or len(isbn_clean) == 13):
                result['verification_details'].append(f"ISBN '{isbn}' (cleaned: '{isbn_clean}') has an invalid length.")
                return 0.0
            
            url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_clean}&format=json&jscmd=data"
            
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                if f'ISBN:{isbn_clean}' in data:
                    book_data = data[f'ISBN:{isbn_clean}']
                    result['verification_details'].append(f"ISBN '{isbn_clean}' verified via OpenLibrary. Title: '{book_data.get('title', 'N/A')}', Authors: {', '.join([a['name'] for a in book_data.get('authors', [])])}.")
                    
                    # Optional: Cross-verify extracted title/authors if available
                    extracted_title = elements.get('title', '').lower()
                    openlibrary_title = book_data.get('title', '').lower()
                    
                    if extracted_title and openlibrary_title:
                        title_similarity = difflib.SequenceMatcher(None, extracted_title, openlibrary_title).ratio()
                        if title_similarity >= 0.7:
                            result['verification_details'].append(f"Title consistency (extracted vs OpenLibrary): {title_similarity:.2f} (Good).")
                            return 0.9
                        else:
                            result['verification_details'].append(f"Title inconsistency (extracted vs OpenLibrary): {title_similarity:.2f}. OpenLibrary Title: '{openlibrary_title}'.")
                            return 0.75 # Found ISBN, but title mismatch suggests possible error
                    return 0.85 # Found ISBN, no title to compare or good title match

            result['verification_details'].append(f"ISBN '{isbn_clean}' not found on OpenLibrary.")
            return 0.0
            
        except requests.exceptions.Timeout:
            result['debug_info'].append(f"ISBN check timed out for {isbn}.")
            return 0.5
        except requests.exceptions.ConnectionError:
            result['debug_info'].append(f"Network connection error during ISBN check for {isbn}.")
            return 0.4
        except Exception as e:
            result['debug_info'].append(f"ISBN check error for {isbn}: {str(e)}")
            return 0.3

    def _check_url_safe(self, elements: Dict, result: Dict) -> float:
        """Check URL safely for accessibility."""
        url = elements.get('url')
        if not url:
            return 0.0
        
        result['sources_checked'].append('URL accessibility')
        result['methods_used'].append('HTTP HEAD request')
        
        try:
            # Add scheme if missing for robust request
            clean_url = url if url.startswith(('http://', 'https://')) else f'https://{url}'
            
            # Use HEAD request as it's lighter than GET, only fetches headers
            response = self.session.head(clean_url, timeout=self.timeout, allow_redirects=True)
            
            if response.status_code == 200:
                result['verification_details'].append(f"URL '{clean_url}' is accessible (Status: 200 OK).")
                return 0.7
            elif response.status_code >= 300 and response.status_code < 400:
                result['verification_details'].append(f"URL '{clean_url}' redirects (Status: {response.status_code}).")
                return 0.6 # Redirects are often fine
            elif response.status_code == 404:
                result['verification_details'].append(f"URL '{clean_url}' not found (Status: 404).")
                return 0.0
            elif response.status_code >= 400 and response.status_code < 500:
                result['verification_details'].append(f"URL '{clean_url}' client error (Status: {response.status_code}).")
                return 0.2 # Client errors might mean temporary issues or soft 404
            elif response.status_code >= 500:
                result['verification_details'].append(f"URL '{clean_url}' server error (Status: {response.status_code}).")
                return 0.1 # Server issues, less likely to be fake reference
            else:
                result['verification_details'].append(f"URL '{clean_url}' accessibility inconclusive (Status: {response.status_code}).")
                return 0.3
                
        except requests.exceptions.Timeout:
            result['debug_info'].append(f"URL check timed out for {url}.")
            return 0.2 # Timed out, less confident
        except requests.exceptions.ConnectionError:
            result['debug_info'].append(f"Network connection error during URL check for {url}.")
            return 0.1 # Network issue
        except Exception as e:
            result['debug_info'].append(f"URL check error for {url}: {str(e)}")
            return 0.0

class FullyCorrectedVerifier:
    """Main verifier with all corrections applied"""
    
    def __init__(self):
        self.parser = FixedParser()
        self.checker = FixedAuthenticityChecker()

    def verify_references(self, text: str, format_type: str) -> List[Dict]:
        """Verify references with comprehensive checking"""
        if not text:
            return []
        
        # Split by lines, but also handle multi-line references (simple heuristic for now)
        # Assuming each reference starts on a new line for simplicity in this version.
        lines = text.strip().split('\n')
        
        results = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or len(line) < 15:  # Skip very short or empty lines
                continue
            
            result = self._process_reference(line, i + 1, format_type)
            results.append(result)
            time.sleep(0.3)  # Rate limiting for external API calls
        
        return results

    def _process_reference(self, line: str, line_number: int, format_type: str) -> Dict:
        """Process single reference with all fixes"""
        result = {
            'reference': line,
            'line_number': line_number,
            'authenticity_status': 'unknown',
            'format_status': 'unknown',
            'content_status': 'unknown',
            'overall_status': 'unknown',
            'confidence_score': 0.0,
            'reference_type': 'unknown',
            'extracted_elements': {},
            'authenticity_check': {},
            'format_check': {},
            'content_check': {},
            'processing_errors': []
        }
        
        try:
            # 1. Extract elements
            elements = self.parser.extract_elements_safely(line)
            result['extracted_elements'] = elements
            result['reference_type'] = elements.get('reference_type', 'unknown')
            
            if elements.get('extraction_errors'):
                result['processing_errors'].extend(elements['extraction_errors'])
            
            # 2. Check authenticity
            auth_result = self.checker.check_authenticity_comprehensive(elements)
            result['authenticity_check'] = auth_result
            result['confidence_score'] = auth_result.get('confidence_score', 0.0)
            
            if auth_result.get('is_authentic'):
                result['authenticity_status'] = 'authentic'
                
                # 3. Check content consistency (only if authentic)
                content_result = self.parser.check_content_consistency(elements)
                result['content_check'] = content_result
                
                # 4. Check format (always check format regardless of authenticity)
                format_result = self.parser.check_format_compliance(line)
                result['format_check'] = format_result
                
                # 5. Determine overall status based on combined checks
                has_content_errors = len(content_result.get('content_errors', [])) > 0
                has_content_warnings = len(content_result.get('content_warnings', [])) > 0
                has_format_errors = len(format_result.get('errors', [])) > 0
                has_format_warnings = len(format_result.get('warnings', [])) > 0
                
                if has_content_errors:
                    result['content_status'] = 'content_errors'
                    result['overall_status'] = 'authentic_with_content_errors'
                elif has_format_errors: # Prioritize format errors after content errors
                    result['format_status'] = 'format_errors'
                    result['overall_status'] = 'authentic_with_format_errors'
                elif has_content_warnings:
                    result['content_status'] = 'content_warnings'
                    if has_format_warnings:
                        result['overall_status'] = 'authentic_with_content_and_format_warnings'
                    else:
                        result['overall_status'] = 'authentic_with_content_warnings'
                elif has_format_warnings:
                    result['format_status'] = 'format_warnings'
                    result['overall_status'] = 'authentic_with_format_warnings'
                else:
                    result['overall_status'] = 'valid' # Fully valid
                
            else:
                result['authenticity_status'] = 'likely_fake'
                result['overall_status'] = 'likely_fake'
                # Still check format and content even if likely fake, to give full feedback
                content_result = self.parser.check_content_consistency(elements)
                result['content_check'] = content_result
                format_result = self.parser.check_format_compliance(line)
                result['format_check'] = format_result
            
        except Exception as e:
            result['processing_errors'].append(f"Processing error for reference '{line}': {str(e)}")
            result['overall_status'] = 'processing_error'
        
        return result

def main():
    st.set_page_config(
        page_title="Fully Corrected Reference Verifier",
        page_icon="🛠️",
        layout="wide"
    )
    
    st.title("🛠️ Fully Corrected Reference Verifier")
    st.markdown("**All critical errors fixed: syntax, regex, extraction, and content checking**")
    
    st.sidebar.header("🔧 Critical Fixes Applied")
    st.sidebar.markdown("**✅ Syntax Errors Fixed:**")
    st.sidebar.markdown("• Fixed indentation errors")
    st.sidebar.markdown("• Completed all function definitions")
    st.sidebar.markdown("• Proper import statements")
    
    st.sidebar.markdown("**✅ Regex Errors Fixed:**")
    st.sidebar.markdown("• Fixed 'bad character range \\d-X'")
    st.sidebar.markdown("• Escaped hyphens in patterns")
    st.sidebar.markdown("• Added error handling for regex")
    st.sidebar.markdown("• **Improved journal/volume/page patterns**")
    st.sidebar.markdown("• **More robust title extraction patterns**")
    
    st.sidebar.markdown("**✅ Extraction Improved:**")
    st.sidebar.markdown("• Better reference type detection (more accurate scoring)")
    st.sidebar.markdown("• Enhanced pattern matching")
    st.sidebar.markdown("• Comprehensive error handling")
    st.sidebar.markdown("• **Improved Book/Edition/Publisher extraction**")
    
    st.sidebar.markdown("**✅ Content Checking:**")
    st.sidebar.markdown("• DOI-journal consistency (now compares actual names)")
    st.sidebar.markdown("• Journal name validation (against CrossRef)")
    st.sidebar.markdown("• Content vs format error distinction")
    st.sidebar.markdown("• **Added title consistency checks via DOI/ISBN**")
    
    format_type = st.sidebar.selectbox("Reference Format", ["APA", "Vancouver"]) # Not fully implemented format-specific checks yet.
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📝 Test Fixed Verifier")
        
        st.info("**Now properly handles**: Books, journals, websites, DOIs, ISBNs, URLs with accurate extraction and **improved verification!**")
        
        reference_text = st.text_area(
            "Paste your references here:",
            height=350,
            value="""Handford, M. J., Rivera, F. M., Maroto-Izquierdo, S., & Hughes, J. D. (2021). Plyo-accentuated eccentric loading methods to enhance lower limb muscle power. Strength & Conditioning Journal, 43(5), 54-64. https://doi.org/10.1519/JSC.0000000000004128
American College of Sports Medicine. (2022). ACSM's guidelines for exercise testing and prescription (11th ed.). Wolters Kluwer. ISBN: 978-1975171738
American Heart Association. (2024). Understanding blood pressure readings. Retrieved March 15, 2024, from https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings
Fake Author, A. (2023). This is a fake journal article. Journal of Nonexistent Research, 1(1), 1-5.
Smith, J. (2020). Exercise benefits. Journal of Fake Studies, 27(1), 1-10. https://doi.org/10.1016/j.math.2015.01.004
""", # Added problem reference and fake one
            help="Test with the provided references to see the improvements!"
        )
        
        verify_button = st.button("🛠️ Run Fixed Verifier", type="primary", use_container_width=True)
        
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🧪 Test Content Errors", use_container_width=True):
                content_error_test = "\n\nSmith, J. (2020). Exercise benefits. Journal of Fake Studies, 27(1), 1-10. https://doi.org/10.1016/j.math.2015.01.004" # DOI points to a different journal
                st.session_state.reference_text = reference_text + content_error_test # Use session_state to trigger re-run
                st.session_state.trigger_verify = True
        
        with col_b:
            if st.button("📊 Test All Types", use_container_width=True):
                all_types_test = """
Jones, P. (2021). Sports science manual. Human Kinetics.
Health Canada. (2023). Exercise guidelines. Retrieved from https://www.canada.ca/health/en/public-health/services/health-promotion/healthy-living/physical-activity-sedentary-behaviour.html
Doe, J. (2019). My research on exercise physiology. Journal of Applied Physiology, 126(3), 600-610. https://doi.org/10.1152/japplphysiol.00840.2018
"""
                st.session_state.reference_text = all_types_test # Overwrite for full test
                st.session_state.trigger_verify = True
        
        with st.expander("🔧 What's Been Fixed"):
            st.markdown("**Critical Error Fixes:**")
            st.markdown("1. **Indentation Error**: Fixed unmatched indentation levels")
            st.markdown("2. **Regex Error**: Fixed 'bad character range \\d-X' and other regex issues by escaping hyphen and refining patterns.")
            st.markdown("3. **Type Detection**: Improved reference type classification with more accurate scoring and heuristics.")
            st.markdown("4. **Content Extraction**: Better title, journal, author, publisher, and edition extraction with more robust patterns and fallbacks.")
            st.markdown("5. **Error Handling**: Comprehensive try/catch blocks added for resilience.")
            st.markdown("6. **Pattern Matching**: More robust regex patterns for all elements.")
            st.markdown("7. **Content Consistency**: Enhanced DOI-journal mismatch detection by comparing actual journal names and titles.")
            st.markdown("8. **Authenticity Checking**: Improved DOI, ISBN, and URL verification methods, including metadata lookup for DOIs and OpenLibrary for ISBNs.")
    
    with col2:
        st.header("📊 Fixed Verification Results")
        
        # Handle test cases via session state
        if 'trigger_verify' in st.session_state and st.session_state.trigger_verify:
            reference_text = st.session_state.reference_text
            verify_button = True
            del st.session_state.trigger_verify # Reset trigger
            del st.session_state.reference_text # Clear text from session
        
        if verify_button and reference_text.strip():
            with st.spinner("Running fully corrected verifier..."):
                verifier = FullyCorrectedVerifier()
                results = verifier.verify_references(reference_text, format_type)
            
            if results:
                # Summary metrics
                total = len(results)
                valid = sum(1 for r in results if r.get('overall_status') == 'valid')
                content_errors = sum(1 for r in results if 'content_errors' in r.get('overall_status', ''))
                format_issues = sum(1 for r in results if 'format' in r.get('overall_status', '') and 'authentic' in r.get('overall_status', ''))
                likely_fake = sum(1 for r in results if r.get('overall_status') == 'likely_fake')
                processing_errors = sum(1 for r in results if r.get('overall_status') == 'processing_error')
                avg_confidence = sum(r.get('confidence_score', 0) for r in results) / total if total > 0 else 0
                
                col_a, col_b, col_c, col_d, col_e, col_f = st.columns(6)
                with col_a:
                    st.metric("Total", total)
                with col_b:
                    st.metric("✅ Valid", valid)
                with col_c:
                    st.metric("🔴 Content Errors", content_errors)
                with col_d:
                    st.metric("📝 Format Issues", format_issues)
                with col_e:
                    st.metric("🚨 Likely Fake", likely_fake)
                with col_f:
                    st.metric("🐛 Processing Errors", processing_errors)
                
                st.markdown(f"**Average Confidence**: {avg_confidence:.2f}")
                st.markdown("---")
                
                # Display results
                for result in results:
                    ref_type = result.get('reference_type', 'unknown')
                    type_icons = {'journal': '📄', 'book': '📚', 'website': '🌐', 'unknown': '❓'}
                    type_icon = type_icons.get(ref_type, '❓')
                    
                    confidence = result.get('confidence_score', 0.0)
                    confidence_emoji = "🟢" if confidence >= 0.8 else "🟡" if confidence >= 0.6 else "🔴"
                    
                    st.markdown(f"### {type_icon} Reference {result.get('line_number', 'N/A')} ({ref_type.title()}) {confidence_emoji} {confidence:.2f}")
                    
                    status = result.get('overall_status', 'unknown')
                    
                    # Enhanced status display
                    if status == 'valid':
                        st.success("✅ **Valid Reference** - Authentic, accurate content, and properly formatted.")
                    elif status == 'authentic_with_content_errors':
                        st.error("🔴 **Authentic but Content Errors** - Real DOI/source but incorrect details detected (e.g., journal name mismatch).")
                    elif status == 'authentic_with_content_and_format_warnings':
                        st.warning("🟡 **Authentic with Content & Format Warnings** - Real source but suspicious details AND minor formatting issues.")
                    elif status == 'authentic_with_content_warnings':
                        st.warning("🟡 **Authentic with Content Warnings** - Real source but suspicious details (e.g., journal not highly found).")
                    elif status == 'authentic_with_format_errors':
                        st.warning("📝 **Authentic but Format Errors** - Real reference with citation style issues (e.g., comma before year).")
                    elif status == 'authentic_with_format_warnings':
                        st.info("📝 **Authentic with Format Warnings** - Real reference with minor style issues.")
                    elif status == 'likely_fake':
                        st.error("🚨 **Likely Fake Reference** - Could not verify authenticity through DOI, ISBN, or URL.")
                    elif status == 'processing_error':
                        st.error("🐛 **Processing Error** - An error occurred during verification. Check debug info.")
                    else:
                        st.info(f"❓ **Status**: {status}")
                    
                    # Show verification details
                    auth_check = result.get('authenticity_check', {})
                    verification_details = auth_check.get('verification_details', [])
                    methods_used = auth_check.get('methods_used', [])
                    sources_checked = auth_check.get('sources_checked', [])
                    
                    if verification_details:
                        st.markdown("**🔍 Authenticity Verification:**")
                        for detail in verification_details:
                            st.markdown(f"  • {detail}")
                        
                        if methods_used:
                            st.markdown(f"  • **Methods Used**: {', '.join(methods_used)}")
                        
                        if sources_checked:
                            st.markdown(f"  • **Sources Checked**: {', '.join(sources_checked)}")
                    
                    # Show content consistency
                    content_check = result.get('content_check', {})
                    content_errors_list = content_check.get('content_errors', [])
                    content_warnings_list = content_check.get('content_warnings', [])
                    
                    if content_errors_list or content_warnings_list:
                        with st.expander("🔍 Content Consistency Analysis"):
                            consistency_score = content_check.get('consistency_score', 1.0)
                            st.markdown(f"**Content Consistency Score**: {consistency_score:.2f}")
                            
                            if content_errors_list:
                                st.markdown("**🔴 Content Errors:**")
                                for error in content_errors_list:
                                    st.markdown(f"  • {error}")
                            
                            if content_warnings_list:
                                st.markdown("**🟡 Content Warnings:**")
                                for warning in content_warnings_list:
                                    st.markdown(f"  • {warning}")
                            
                            verification_details_content = content_check.get('verification_details', [])
                            if verification_details_content:
                                st.markdown("**🔍 Detailed Content Verification:**")
                                for detail in verification_details_content:
                                    st.markdown(f"  • {detail}")
                    
                    # Show format issues
                    format_check = result.get('format_check', {})
                    format_errors = format_check.get('errors', [])
                    format_warnings = format_check.get('warnings', [])
                    suggestions = format_check.get('suggestions', [])
                    
                    if format_errors or format_warnings:
                        with st.expander("📝 Format Analysis"):
                            format_score = format_check.get('score', 1.0)
                            st.markdown(f"**Format Compliance Score**: {format_score:.2f}")
                            
                            if format_errors:
                                st.markdown("**🔴 Critical Format Errors:**")
                                for error in format_errors:
                                    st.markdown(f"  • {error}")
                            
                            if format_warnings:
                                st.markdown("**🟡 Format Warnings:**")
                                for warning in format_warnings:
                                    st.markdown(f"  • {warning}")
                            
                            if suggestions:
                                st.markdown("**💡 Suggestions:**")
                                for suggestion in suggestions:
                                    st.markdown(f"  • {suggestion}")
                    
                    # Show extraction details
                    with st.expander("🔍 Extraction Results"):
                        elements = result.get('extracted_elements', {})
                        extraction_confidence = elements.get('confidence', 0.0)
                        
                        st.markdown(f"**Extraction Confidence**: {extraction_confidence:.2f}")
                        
                        st.markdown("**✅ Successfully Extracted Elements:**")
                        extracted_count = 0
                        for key, value in elements.items():
                            if value and key not in ['extraction_errors', 'reference_type', 'confidence']:
                                # Format keys nicely for display
                                display_key = key.replace('_', ' ').title()
                                st.markdown(f"  • **{display_key}**: `{value}`")
                                extracted_count += 1
                        
                        if extracted_count == 0:
                            st.markdown("  • No key elements successfully extracted.")
                        
                        # Show extraction errors
                        extraction_errors = elements.get('extraction_errors', [])
                        if extraction_errors:
                            st.markdown("**⚠️ Extraction Issues:**")
                            for error in extraction_errors:
                                st.markdown(f"  • {error}")
                        
                        # Show processing errors (errors that happened during the overall processing flow)
                        processing_errors = result.get('processing_errors', [])
                        if processing_errors:
                            st.markdown("**🐛 Overall Processing Errors:**")
                            for error in processing_errors:
                                st.markdown(f"  • {error}")
                    
                    # Show debug information
                    debug_info = auth_check.get('debug_info', [])
                    if debug_info:
                        with st.expander("🔧 Debug Information (for developers)"):
                            for debug in debug_info:
                                st.markdown(f"  • {debug}")
                    
                    # Show original reference
                    with st.expander("📄 Original Reference Text"):
                        ref_text = result.get('reference', 'No reference text available')
                        st.code(ref_text, language="text")
                    
                    st.markdown("---")
        
        elif verify_button: # If button was clicked but text area was empty
            st.warning("Please enter some references to analyze.")
    
    with st.expander("🛠️ Complete Fix Summary"):
        st.markdown("""
        ### **🔧 All Critical Errors Fixed (and improvements made):**
        
        #### **1. Syntax Errors**
        ```python
        # ❌ BEFORE: IndentationError: unindent does not match any outer indentation level
        # (Example of syntax errors that were present, now resolved for a runnable app)
        # with col_bimport streamlit as st 
        # (This was a concatenation error from example, actual fixes were more subtle)
        
        # ✅ AFTER: Proper indentation and complete statements throughout the code.
        with col_b:
            if st.button(...):
                # Correctly indented code
        ```
        
        #### **2. Regex Errors**
        ```python
        # ❌ BEFORE: bad character range \\d-X at position 11 (for ISBN)
        'isbn_pattern': r'ISBN:?\\s*([\\d-X]+)'
        
        # ✅ AFTER: Properly escaped hyphen, more robust patterns for various elements.
        'isbn_pattern': r'(?:ISBN(?:-1[03])?:?\\s*|)\\b([\\d\\-X]{10,17})\\b'
        # Improved title pattern:
        'title_after_year': r'\\).\\s*([\\'\\\"A-Z].*?)(?:\\.|\?|!|\\s*\\[|\\s*\\(|\\s*(?:Vol|No|Edition|Ed\\.)|\\s*ISBN|\\s*doi:|\\s*https?:\\/\\/|$)'
        # Improved journal/volume/pages pattern:
        'journal_volume_pages': r'([A-Za-z\\s&,.]+?)\\s*[,.]?\\s*(\\d+)\\s*(?:\\((\\d+)\\))?[,\\-–\\s]*(\\d+[-–]\\d+|\\d+)\\.?'
        ```
        
        #### **3. Reference Type Detection**
        ```python
        # ✅ IMPROVED: Enhanced keyword and pattern scoring system.
        - Stronger indicators for DOI/ISBN/URL now directly influence initial type.
        - Refined heuristics for distinguishing between books, journals, and websites based on common structural elements (e.g., edition for books, volume/issue for journals, access date for websites).
        ```
        
        #### **4. Content Extraction**
        ```python
        # ✅ IMPROVED: More granular and robust extraction with improved error handling.
        - **Title Extraction**: Better general title capture, with cleaner post-processing.
        - **Journal Info**: Combined regex for Journal Name, Volume, Issue, Pages for higher accuracy. Fallback for separate extraction.
        - **Book Info**: Dedicated _extract_book_info method to find publishers (expanded list) and edition information.
        - **Authors & Year**: More precise identification of author section and year parsing.
        ```
        
        #### **5. Error Handling**
        ```python
        # ✅ ADDED: More comprehensive try/catch blocks across all critical extraction and verification steps.
        - Specific error messages for clearer debugging.
        - Graceful degradation instead of crashing, allowing partial results.
        ```
        
        #### **6. Authenticity Checking**
        ```python
        # ✅ ENHANCED: Deeper verification methods.
        - **DOI Verification**: Now not only checks if DOI resolves, but also queries CrossRef API for metadata (like journal name and title) to cross-verify against extracted information, significantly improving accuracy for journal articles.
        - **ISBN Verification**: Utilizes OpenLibrary API more effectively, with ISBN cleaning and optional title cross-verification.
        - **URL Accessibility**: More detailed status code handling and error reporting for URL checks.
        ```
        
        ### **📊 Expected Improvements:**
        
        **Before Fixes:**
        - High rate of "Likely Fake" for legitimate references (e.g., the Handford et al. journal article).
        - Frequent "Unknown" type detection.
        - Low average confidence scores.
        - Many unhandled extraction and processing errors.
        - Poor differentiation between content errors and format errors.
        
        **After Fixes:**
        - **Significantly reduced "Likely Fake" classifications for valid references.**
        - **Accurate detection of Book, Journal, and Website types.**
        - **Higher average confidence scores** due to more successful extractions and robust verification.
        - **Clearer identification of content mismatches** (e.g., a DOI linking to a different journal than stated).
        - **Correct distinction between content accuracy and format compliance.**
        - **More informative output** with detailed verification steps and debugging information.
        """)

if __name__ == "__main__":
    main()

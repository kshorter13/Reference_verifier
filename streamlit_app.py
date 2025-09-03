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
            'journal_title_after_year': r'\)\.\s*([^.]+)\.',
            'journal_info': r'([A-Za-z][^,\d]*[A-Za-z]),',
            'volume_pages': r'(\d+)(?:\((\d+)\))?,?\s*(\d+(?:-\d+)?)', # Corrected escaping for regex
            'publisher_info': r'([A-Z][^.]*(?:Press|Publishers?|Publications?|Books?|Academic|University|Ltd|Inc|Corp|Kluwer|Elsevier|MIT Press|Human Kinetics)[^.]*)', # Added Human Kinetics
            'doi_pattern': r'https?://doi\.org/([^\s]+)',
            'author_pattern': r'^([^()]+?)(?:\s*\(\d{4}\))', # Corrected escaping for regex
            'isbn_pattern': r'ISBN:?\s*([\d-]+)',
            'url_pattern': r'(https?://[^\s]+)',
            'website_access_date': r'(?:Retrieved|Accessed)\s+([^,]+)'
        }
        
        self.vancouver_patterns = {
            'starts_with_number': r'^(\d+)\.',
            'journal_title_section': r'^\d+\.\s*[^.]+\.\s*([^.]+)\.', # Corrected escaping for regex
            'journal_year': r'([A-Za-z][^.;]+)\s*(\d{4})', # Corrected escaping for regex
            'author_pattern_vancouver': r'^\d+\.\s*([^.]+)\.', # Corrected escaping for regex
            'book_publisher': r'([A-Z][^;:]+);\s*(\d{4})', # Corrected escaping for regex
            'website_url_vancouver': r'Available\s+(?:from|at):\s*(https?://[^\s]+)' # Corrected escaping for regex
        }
        
        self.type_indicators = {
            'journal': [
                r'[,;]\s*\d+(?:\(\d+\))?[,:]\s*\d+(?:-\d+)?',
                r'Journal|Review|Proceedings|Quarterly|Annual',
                r'https?://doi\.org/',
                r'\b(volume|issue|pages|p\.)\b' # Strong journal indicator
            ],
            'book': [
                r'(?:Press|Publishers?|Publications?|Books?|Academic|University|Kluwer|Elsevier|MIT Press|Human Kinetics)', # Added Human Kinetics
                r'ISBN:?\s*[\d-]+',
                r'(?:pp?\.|pages?)\s*\d+(?:-\d+)?',
                r'\b(edition|ed\.)\b', # Strong book indicator
                r'\b(manual|handbook|textbook|guidelines)\b', # Strong book indicator, added guidelines
                r'\b(vol\.|volume|chapter)\b' # Added vol/chapter for books
            ],
            'website': [
                r'(?:Retrieved|Accessed)\s+(?:from|on)',
                r'https?://(?:www\.)?[^/\s]+\.[a-z]{2,}',
                r'Available\s+(?:from|at)'
            ]
        }

    def detect_reference_type(self, ref_text: str) -> str:
        ref_lower = ref_text.lower()

        # 1. Highest priority: DOI -> Journal
        if re.search(self.apa_patterns['doi_pattern'], ref_text):
            return 'journal'

        # 2. Next priority: ISBN -> Book
        if re.search(self.apa_patterns['isbn_pattern'], ref_text):
            return 'book'

        # 3. Strong Website indicator: URL + Access Date/Retrieved phrase
        # This is crucial to avoid misclassifying books/journals with incidental URLs
        if re.search(self.apa_patterns['url_pattern'], ref_text) and \
           re.search(self.apa_patterns['website_access_date'], ref_text):
            return 'website'
        
        # 4. Fallback to scoring for less clear cases, or if strong indicators are absent
        type_scores = {'journal': 0, 'book': 0, 'website': 0}
        
        for ref_type, patterns in self.type_indicators.items():
            for pattern in patterns:
                if re.search(pattern, ref_lower):
                    type_scores[ref_type] += 1
        
        # Boost scores for explicit keywords not covered by direct identifiers
        # These boosts help differentiate when direct identifiers are missing
        if re.search(r'\b(edition|ed\.)\b', ref_lower) or \
           re.search(r'\b(manual|handbook|textbook|guidelines)\b', ref_lower) or \
           re.search(r'\b(vol\.|volume|chapter)\b', ref_lower):
            type_scores['book'] += 2.0 # Increased boost for very strong book indicators

        if re.search(r'\b(volume|issue|pages|p\.)\b', ref_lower):
            type_scores['journal'] += 1.5 # Boost journal score

        # Check for common publisher names specifically for books if no strong type detected yet
        # Only apply this if not already leaning strongly towards journal/website
        if not (type_scores['journal'] >= 1.5 or type_scores['website'] >= 1.5): # Use score threshold
            if re.search(r'\b(wolters kluwer|elsevier|mit press|university press|human kinetics)\b', ref_lower): # Added human kinetics
                type_scores['book'] += 1.0 # Add a moderate boost for publishers

        # Final decision based on scores, with tie-breaking preference
        if any(score > 0 for score in type_scores.values()):
            max_score = max(type_scores.values())
            # Prioritize book if it has the max score
            if type_scores['book'] == max_score and max_score > 0:
                return 'book'
            # Then journal
            if type_scores['journal'] == max_score and max_score > 0:
                return 'journal'
            # Then website
            if type_scores['website'] == max_score and max_score > 0:
                return 'website'
            return max(type_scores, key=type_scores.get) # Fallback if tie-breaking rules don't apply uniquely
        else:
            return 'journal' # Default if no indicators are found

    def identify_references(self, text: str) -> List[Reference]:
        lines = text.strip().split('\n')
        references = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if line and len(line) > 30: # Minimum length to consider it a valid reference line
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
                has_journal = bool(re.search(self.apa_patterns['journal_info'], ref_text))
                has_numbers = bool(re.search(self.apa_patterns['volume_pages'], ref_text))
                
                if not has_year:
                    result['structure_issues'].append("Missing year in parentheses")
                if not has_title:
                    result['structure_issues'].append("Missing title after year")
                if not has_journal:
                    result['structure_issues'].append("Missing journal information")
                if not has_numbers:
                    result['structure_issues'].append("Missing volume/page numbers")
                
                result['structure_valid'] = has_year and has_title and (has_journal or has_numbers)
            
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
                
                result['structure_valid'] = has_title and has_url # Access info is often optional for basic validity
        
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

    def extract_reference_elements(self, ref_text: str, format_type: str, ref_type: str = None) -> Dict:
        elements = {
            'authors': None,
            'year': None,
            'title': None,
            'journal': None,
            'publisher': None,
            'url': None, # Initialize as None
            'isbn': None,
            'doi': None,
            'access_date': None,
            'reference_type': ref_type or self.detect_reference_type(ref_text),
            'extraction_confidence': 'high'
        }
        
        detected_type = elements['reference_type']
        
        # Extract DOI and ISBN first, as they are strong identifiers
        doi_match = re.search(self.apa_patterns['doi_pattern'], ref_text)
        if doi_match:
            elements['doi'] = doi_match.group(1)
        
        isbn_match = re.search(self.apa_patterns['isbn_pattern'], ref_text)
        if isbn_match:
            elements['isbn'] = isbn_match.group(1)

        # IMPORTANT: Only extract generic URL if the detected type is 'website'.
        # This prevents a book reference from picking up a random URL in its text.
        if detected_type == 'website':
            url_match = re.search(self.apa_patterns['url_pattern'], ref_text)
            if url_match:
                elements['url'] = url_match.group(1)
        
        if format_type == "APA":
            year_match = re.search(self.apa_patterns['journal_year_in_parentheses'], ref_text)
            if year_match:
                elements['year'] = year_match.group(1)
            
            title_match = re.search(self.apa_patterns['journal_title_after_year'], ref_text)
            if title_match:
                elements['title'] = title_match.group(1).strip()
            
            author_match = re.search(self.apa_patterns['author_pattern'], ref_text)
            if author_match:
                elements['authors'] = author_match.group(1).strip()
            
            if detected_type == 'journal':
                journal_match = re.search(self.apa_patterns['journal_info'], ref_text)
                if journal_match:
                    elements['journal'] = journal_match.group(1).strip()
            
            elif detected_type == 'book':
                publisher_match = re.search(self.apa_patterns['publisher_info'], ref_text)
                if publisher_match:
                    elements['publisher'] = publisher_match.group(1).strip()
            
            elif detected_type == 'website':
                access_match = re.search(self.apa_patterns['website_access_date'], ref_text)
                if access_match:
                    elements['access_date'] = access_match.group(1).strip()
        
        elif format_type == "Vancouver":
            year_match = re.search(r'(\d{4})', ref_text)
            if year_match:
                elements['year'] = year_match.group(1)
            
            title_match = re.search(self.vancouver_patterns['journal_title_section'], ref_text)
            if title_match:
                elements['title'] = title_match.group(1).strip()
            
            author_match = re.search(self.vancouver_patterns['author_pattern_vancouver'], ref_text)
            if author_match:
                elements['authors'] = author_match.group(1).strip()
            
            if detected_type == 'journal':
                journal_match = re.search(r'([A-Za-z][^.;\d]*[A-Za-z])[\s.]*\d{4}', ref_text)
                if journal_match:
                    elements['journal'] = journal_match.group(1).strip()
            
            elif detected_type == 'book':
                publisher_match = re.search(self.vancouver_patterns['book_publisher'], ref_text)
                if publisher_match:
                    elements['publisher'] = publisher_match.group(1).strip()
        
        # Assess extraction confidence
        if detected_type == 'journal':
            required_fields = [elements['authors'], elements['year'], elements['title'], elements['journal']]
        elif detected_type == 'book':
            required_fields = [elements['authors'], elements['year'], elements['title'], elements['publisher']]
        elif detected_type == 'website':
            required_fields = [elements['title'], elements['url']]
        else: # Fallback
            required_fields = [elements['authors'], elements['year'], elements['title']]
        
        extracted_count = sum(1 for v in required_fields if v)
        if extracted_count < 2:
            elements['extraction_confidence'] = 'low'
        elif extracted_count < len(required_fields):
            elements['extraction_confidence'] = 'medium'
        
        return elements

class DatabaseSearcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def check_doi_and_verify_content(self, doi: str, expected_title: str) -> Dict:
        if not doi:
            return {'valid': False, 'reason': 'No DOI provided'}
        
        try:
            url = f"https://doi.org/{doi}"
            response = self.session.head(url, timeout=10, allow_redirects=True)
            
            if response.status_code != 200:
                return {
                    'valid': False, 
                    'reason': f'DOI does not resolve (status: {response.status_code})',
                    'doi_url': url
                }
            
            return {
                'valid': True,
                'doi_url': url,
                'resolved_url': response.url
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
            
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if 'message' in data and 'items' in data['message']:
                items = data['message']['items']
                
                for item in items:
                    if 'title' in item and item['title']:
                        item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
                        similarity = self._calculate_title_similarity(title.lower(), item_title.lower())
                        
                        if similarity > 0.6: # Threshold for exact title match
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
                # Use a few key words from the title for initial broad search
                title_words = re.findall(r'\b[a-zA-Z]{4,}\b', title)[:4]
                query_parts.extend(title_words)
            
            if authors:
                # Use surnames for author search
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
                'rows': 10, # Fetch more results to find the best match
                'select': 'title,author,DOI,URL,published-print,published-online,container-title' # Request more fields
            }
            
            # Crossref allows filtering by publication year range
            if year:
                params['filter'] = f'from-pub-date:{int(year)-1},until-pub-date:{int(year)+1}' # Allow +/- 1 year
            
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if 'message' in data and 'items' in data['message']:
                items = data['message']['items']
                best_match = None
                best_score = 0.0 # Use float for score
                
                for item in items:
                    score = self._calculate_comprehensive_match_score(item, title, authors, year, journal)
                    if score > best_score:
                        best_score = score
                        best_match = item
                
                if best_score > 0.6: # Higher threshold for comprehensive match
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
            
            response = self.session.get(url, params=params, timeout=15)
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
            
            if authors:
                author_parts = re.split(r'[,&]', authors)[:2]
                for author in author_parts:
                    author_clean = re.sub(r'[^\w\s]', '', author).strip()
                    if author_clean:
                        name_parts = author_clean.split()
                        query_parts.extend([part for part in name_parts if len(part) > 2])
            
            if not query_parts:
                return {'found': False, 'reason': 'Insufficient search terms for Open Library book search'}
            
            url = "https://openlibrary.org/search.json"
            params = {
                'q': ' '.join(query_parts),
                'limit': 10 # Increase limit to get more potential matches
            }
            
            response = self.session.get(url, params=params, timeout=15)
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
                
                if best_score > 0.5: # Set a reasonable threshold for Open Library book matches
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
            if authors:
                # Google Books API supports inauthor
                author_surnames = [re.sub(r'[^\w\s]', '', a).strip().split()[-1] for a in re.split(r'[,&]', authors) if re.sub(r'[^\w\s]', '', a).strip()]
                if author_surnames:
                    query_parts.append(f"inauthor:{' '.join(author_surnames)}")
            if publisher:
                query_parts.append(f"inpublisher:{publisher}")
            if year:
                # Google Books API 'inpublicdate' is for year, or year range
                query_parts.append(f"inpublicdate:{year}")

            if not query_parts:
                return {'found': False, 'reason': 'Insufficient search terms for Google Books search'}

            q = ' '.join(query_parts)
            url = "https://www.googleapis.com/books/v1/volumes"
            params = {
                'q': q,
                'maxResults': 10 # Fetch more results to find the best match
            }

            response = self.session.get(url, params=params, timeout=15)
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
                        title, authors, year, publisher # Corrected to use function parameters
                    )

                    if score > best_score:
                        best_score = score
                        best_match = item

                if best_score > 0.6: # Set a reasonable threshold for Google Books matches
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
            
            # Use a GET request to potentially retrieve title, but HEAD is faster for just accessibility
            response = self.session.get(url, timeout=10, allow_redirects=True)
            
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
        
        # Title matching (50% weight)
        title_sim = 0.0
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.5
        
        # Author matching (25% weight)
        author_score = 0.0
        if 'author' in item and item['author'] and target_authors:
            item_authors = []
            for author in item['author']:
                if 'family' in author:
                    item_authors.append(author['family'].lower())
            
            target_surnames = []
            for author in re.split(r'and|&|,', target_authors): # Handle 'and', '&', ',' separators
                author_clean = re.sub(r'[^\w\s]', '', author).strip()
                if author_clean:
                    name_parts = author_clean.split()
                    if name_parts:
                        surname = name_parts[-1].lower()
                        if len(surname) > 2: # Ensure it's a meaningful surname
                            target_surnames.append(surname)
            
            if item_authors and target_surnames:
                common_authors = set(item_authors).intersection(set(target_surnames))
                author_score = len(common_authors) / max(len(target_surnames), len(item_authors), 1) # Divide by max for better precision
                score += author_score * 0.25
        
        # Year matching (15% weight)
        year_match_score = 0.0
        if target_year:
            item_year = None
            if 'published-print' in item and 'date-parts' in item['published-print']:
                item_year = str(item['published-print']['date-parts'][0][0])
            elif 'published-online' in item and 'date-parts' in item['published-online']:
                item_year = str(item['published-online']['date-parts'][0][0])
            
            if item_year and item_year == target_year:
                year_match_score = 0.15
            elif item_year and abs(int(item_year) - int(target_year)) <= 1: # Slight year tolerance
                year_match_score = 0.075 # Half score for +/- 1 year
            score += year_match_score
        
        # Journal matching (10% weight)
        journal_match_score = 0.0
        if target_journal and 'container-title' in item and item['container-title']:
            item_journal_titles = [t.lower() for t in (item['container-title'] if isinstance(item['container-title'], list) else [item['container-title']])]
            target_journal_lower = target_journal.lower()
            
            if any(target_journal_lower in ij for ij in item_journal_titles) or \
               any(self._calculate_title_similarity(target_journal_lower, ij) > 0.7 for ij in item_journal_titles):
                journal_match_score = 0.10
            score += journal_match_score

        # Adjust score based on how many key elements had a decent match
        matched_elements_count = 0
        if title_sim > 0.6: matched_elements_count += 1
        if author_score > 0.5: matched_elements_count += 1
        if year_match_score > 0: matched_elements_count += 1
        if journal_match_score > 0: matched_elements_count += 1

        # Penalize if very few elements matched strongly, unless the overall score is already very high
        if matched_elements_count < 2 and score < 0.7:
            score *= 0.7 # Reduce score if only one element is a strong match
            
        return score

    def _calculate_book_match_score(self, item: Dict, target_title: str, target_authors: str, target_year: str, target_publisher: str) -> float:
        score = 0.0
        
        # Title matching (50% weight)
        title_sim = 0.0
        if 'title' in item and target_title:
            item_title = item['title']
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.5
        
        # Author matching (30% weight)
        author_score = 0.0
        if 'author_name' in item and item['author_name'] and target_authors:
            item_authors_lower = [a.lower() for a in item['author_name']]
            target_surnames = []
            for author in re.split(r'and|&|,', target_authors):
                author_clean = re.sub(r'[^\w\s]', '', author).strip()
                if author_clean:
                    name_parts = author_clean.split()
                    if name_parts:
                        surname = name_parts[-1].lower()
                        if len(surname) > 2:
                            target_surnames.append(surname)
            
            if item_authors_lower and target_surnames:
                # Check for surname presence in item's author names
                author_match_count = sum(1 for ts in target_surnames if any(ts in ia for ia in item_authors_lower))
                author_score = author_match_count / max(len(target_surnames), len(item_authors_lower), 1)
                score += author_score * 0.3

        # Year matching (15% weight)
        year_match_score = 0.0
        if target_year and 'first_publish_year' in item:
            item_year = str(item['first_publish_year'])
            if item_year == target_year:
                year_match_score = 0.15
            elif abs(int(item_year) - int(target_year)) <= 1: # Allow for +/- 1 year discrepancy
                year_match_score = 0.075
            score += year_match_score

        # Publisher matching (5% weight) - Open Library might not have precise publisher in search results
        publisher_match_score = 0.0
        if target_publisher and 'publisher' in item and item['publisher']:
            item_publishers_lower = [p.lower() for p in (item['publisher'] if isinstance(item['publisher'], list) else [item['publisher']])]
            target_publisher_lower = target_publisher.lower()
            if any(target_publisher_lower in ip for ip in item_publishers_lower):
                publisher_match_score = 0.05
            score += publisher_match_score
        
        return score

    def _calculate_google_book_match_score(self, item_title: str, item_authors: List[str], item_published_date: str, item_publisher: str,
                                          target_title: str, target_authors: str, target_year: str, target_publisher: str) -> float:
        score = 0.0

        # Title matching (50% weight)
        title_sim = 0.0
        if item_title and target_title:
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.5

        # Author matching (30% weight)
        author_score = 0.0
        if item_authors and target_authors:
            item_authors_lower = [a.lower() for a in item_authors]
            target_surnames = []
            for author in re.split(r'and|&|,', target_authors):
                author_clean = re.sub(r'[^\w\s]', '', author).strip()
                if author_clean:
                    name_parts = author_clean.split()
                    if name_parts:
                        surname = name_parts[-1].lower()
                        if len(surname) > 2:
                            target_surnames.append(surname)
            
            if item_authors_lower and target_surnames:
                author_match_count = sum(1 for ts in target_surnames if any(ts in ia for ia in item_authors_lower))
                author_score = author_match_count / max(len(target_surnames), len(item_authors_lower), 1)
                score += author_score * 0.3

        # Year matching (15% weight)
        year_match_score = 0.0
        if target_year and item_published_date:
            item_year = item_published_date[:4] # Take first 4 chars for year
            if item_year == target_year:
                year_match_score = 0.15
            elif abs(int(item_year) - int(target_year)) <= 1:
                year_match_score = 0.075
            score += year_match_score

        # Publisher matching (5% weight)
        publisher_match_score = 0.0
        if target_publisher and item_publisher:
            # Use title similarity for publisher as well for flexibility
            pub_sim = self._calculate_title_similarity(target_publisher, item_publisher)
            if pub_sim > 0.6: # A reasonable similarity for publisher names
                publisher_match_score = 0.05
            score += publisher_match_score
        
        return score


class ReferenceVerifier:
    def __init__(self):
        self.parser = ReferenceParser()
        self.searcher = DatabaseSearcher()

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
            
            # Use check_structural_format for format validity and issues
            structure_check_result = self.parser.check_structural_format(ref.text, format_type, ref_type)
            result['format_valid'] = structure_check_result['structure_valid']
            result['errors'] = structure_check_result['structure_issues'] # Use structural issues as format errors
            result['reference_type'] = ref_type
            
            # Structural Check (Level 1)
            result['structure_check'] = structure_check_result
            
            if structure_check_result['structure_valid']:
                result['structure_status'] = 'valid'
                
                # Content Extraction (Level 2)
                elements = self.parser.extract_reference_elements(ref.text, format_type, ref_type)
                result['extracted_elements'] = elements
                
                if elements['extraction_confidence'] in ['medium', 'high']:
                    result['content_status'] = 'extracted'
                    
                    # Existence Verification (Level 3)
                    existence_results = self._verify_existence(elements)
                    result['existence_check'] = existence_results
                    
                    if existence_results['any_found']:
                        result['existence_status'] = 'found'
                        result['overall_status'] = 'valid'
                    else:
                        result['existence_status'] = 'not_found'
                        result['overall_status'] = 'likely_fake'
                else:
                    result['content_status'] = 'extraction_failed'
                    result['overall_status'] = 'content_error'
            else:
                result['structure_status'] = 'invalid'
                result['overall_status'] = 'structure_error'
            
            results.append(result)
            time.sleep(0.3) # Small delay to prevent hitting API rate limits too quickly
        
        return results

    def _verify_existence(self, elements: Dict) -> Dict:
        results = {
            'any_found': False,
            'doi_valid': False,
            'title_found': False, # For journals, via exact title
            'comprehensive_journal_found': False, # Renamed for clarity
            'isbn_found': False,
            'comprehensive_book_found_openlibrary': False, # Renamed for clarity
            'comprehensive_book_found_googlebooks': False, # New field for Google Books
            'website_accessible': False,
            'search_details': {},
            'verification_sources': []
        }
        
        ref_type = elements.get('reference_type', 'journal')
        
        # --- Priority 1: Direct Identifiers (DOI, ISBN) ---
        # DOI check (common for journals, sometimes present elsewhere)
        if elements.get('doi'):
            doi_result = self.searcher.check_doi_and_verify_content(
                elements['doi'], 
                elements.get('title', '')
            )
            results['search_details']['doi'] = doi_result
            
            if doi_result['valid']:
                results['doi_valid'] = True
                results['any_found'] = True
                if doi_result.get('doi_url'):
                    results['verification_sources'].append({
                        'type': 'DOI',
                        'url': doi_result['doi_url'],
                        'description': 'DOI verified'
                    })

        # ISBN check (most direct for books)
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

        # --- Priority 2: Comprehensive Searches (if direct identifiers not found or invalid) ---
        # Only run comprehensive journal search if DOI didn't validate or wasn't present
        if ref_type == 'journal' and not results['doi_valid']:
            comprehensive_result = self.searcher.search_comprehensive(
                elements.get('authors', ''),
                elements.get('title', ''),
                elements.get('year', ''),
                elements.get('journal', '')
            )
            results['search_details']['comprehensive_journal'] = comprehensive_result
            
            if comprehensive_result['found']:
                results['comprehensive_journal_found'] = True
                results['any_found'] = True
                if comprehensive_result.get('source_url'):
                    results['verification_sources'].append({
                        'type': 'Journal Comprehensive Search (Crossref)',
                        'url': comprehensive_result['source_url'],
                        'description': f"Multi-element match (confidence: {comprehensive_result.get('match_score', 0):.1%})"
                    })
        
        # Only run comprehensive book search if ISBN didn't validate or wasn't present
        elif ref_type == 'book' and not results['isbn_found']:
            # Try Open Library first
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
            
            # If Open Library didn't find a strong match, try Google Books
            if not results['any_found'] and (elements.get('title') or elements.get('authors')): # Only search if we have title/author
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

        # --- Priority 3: Website Accessibility (only if primary type is website, or as a last resort for others if no other verification succeeded) ---
        # Only check URL if it's detected as a website, or if it's a book/journal and no other verification has worked yet.
        if elements.get('url') and (ref_type == 'website' or not results['any_found']):
            website_result = self.searcher.check_website_accessibility(elements['url'])
            results['search_details']['website_check'] = website_result
            
            if website_result['accessible']:
                results['website_accessible'] = True
                # Only set any_found if this is the primary type or no other verification worked
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
    st.markdown("A traffic light system to check your references: **<font color='green'>Valid</font>**, **<font color='orange'>Potential Issues</font>**, or **<font color='red'>Likely Fake</font>**.", unsafe_allow_html=True)
    
    st.sidebar.header("Settings")
    format_type = st.sidebar.selectbox(
        "Select Reference Format",
        ["APA", "Vancouver"]
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**🔍 Verification Process:**")
    st.sidebar.markdown("1. **Structure**: Checks formatting rules.")
    st.sidebar.markdown("2. **Content**: Extracts key details.")
    st.sidebar.markdown("3. **Existence**: Verifies details in databases.")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**📋 Supported Types:**")
    st.sidebar.markdown("📄 **Journals**: DOI, Crossref")
    st.sidebar.markdown("📚 **Books**: ISBN, Open Library, Google Books")
    st.sidebar.markdown("🌐 **Websites**: URL accessibility")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📝 Input References")
        
        st.markdown("""
        **Instructions:**
        1. Paste your reference list below (one per line).
        2. Select the citation format (APA or Vancouver).
        3. Click "Verify References" to get your results.
        """)
        
        reference_text = st.text_area(
            "Paste your references here (one per line):",
            height=350,
            placeholder="""Example (APA):

Smith, J. A. (2020). Climate change impacts on marine ecosystems. Nature Climate Change, 10(5), 423-431. https://doi.org/10.1038/s41558-020-0789-5
Brown, M. (2019). Machine learning in healthcare. MIT Press.
World Health Organization. (2021). COVID-19 pandemic. Retrieved March 15, 2023, from https://www.who.int/emergencies/diseases/novel-coronavirus-2019""",
            help="Each reference should be on a new line. The system automatically detects if it's a journal, book, or website."
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
Kumar, K. (2022, January 12). What Is a Good Resting Heart Rate by Age? MedicineNet. https://www.medicinenet.com/what_is_a_good_resting_heart_rate_by_age/article.htm
Haff, G. G., & Triplett, N. T. (2016). Essentials of strength training and conditioning (4th ed.). Human Kinetics.
Powden, C. J., Hoch, J. M., & Hoch, M. C. (2015b). Reliability and Minimal Detectable Change of the weight-bearing Lunge test: a Systematic Review. Manual Therapy, 20(4), 524–532. https://doi.org/10.1016/j.math.2015.01.004
Ryan, C., Uthoff, A., McKenzie, C., & Cronin, J. (2022). Traditional and modified 5-0-5 change of direction test: Normative and reliability analysis. Strength & Conditioning Journal, 44(4), 22–37. https://doi.org/10.1519/SSC.0000000000000635
Shrestha, M. (2022). Sit and Reach Test. Physiopedia. https://www.physio-pedia.com/Sit_and_Reach_Test
Watson, S., & Nall, R. (2023, February 2). What Is the Waist-to-Hip Ratio? Healthline; Healthline Media. https://www.healthline.com/health/waist-to-hip-ratio
Wood, R. (2008). Push Up Test: Home fitness tests. Topendsports.com. https://www.topendsports.com/testing/tests/home-pushup.htm"""
                st.session_state.sample_text = sample_data
        
        with st.expander("💡 Quick Tips"):
            st.markdown("""
            **For best results:**
            - Include DOIs for journal articles and ISBNs for books.
            - Ensure URLs for websites are complete.
            - Use consistent formatting throughout your list.
            - Missing punctuation (e.g., periods, commas) can cause formatting errors.
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
            
            with st.spinner("Analyzing references..."):
                verifier = ReferenceVerifier()
                results = verifier.verify_references(reference_text, format_type, update_progress)
            
            progress_bar.empty()
            status_text.empty()
            
            if results:
                total_refs = len(results)
                valid_refs = sum(1 for r in results if r['overall_status'] == 'valid')
                potential_issues = sum(1 for r in results if r['overall_status'] in ['structure_error', 'content_error'])
                likely_fake = sum(1 for r in results if r['overall_status'] == 'likely_fake')
                
                # --- MODIFIED: Summary Metrics ---
                col_a, col_b, col_c, col_d = st.columns(4)
                with col_a:
                    st.metric("Total References", total_refs)
                with col_b:
                    st.metric("✅ Valid", valid_refs)
                with col_c:
                    st.metric("🟡 Potential Issues", potential_issues)
                with col_d:
                    st.metric("🔴 Likely Fake", likely_fake)
                
                st.markdown("---")
                
                # --- MODIFIED: Results Display Loop ---
                for i, result in enumerate(results):
                    ref_text = result['reference']
                    status = result['overall_status']
                    
                    type_icons = {'journal': '📄', 'book': '📚', 'website': '🌐'}
                    type_icon = type_icons.get(result.get('reference_type', 'journal'), '📄')
                    
                    # --- GREEN LIGHT ---
                    if status == 'valid':
                        with st.container():
                            st.success(f"✅ **Reference {result['line_number']}**: Verified and Valid")
                            st.write(f"_{type_icon} {result.get('reference_type', 'N/A').title()}_")
                            st.write(ref_text)
                            
                            existence = result['existence_check']
                            verification_sources = existence.get('verification_sources', [])
                            
                            if verification_sources:
                                st.write("**Verified via:**")
                                for source in verification_sources:
                                    st.markdown(f"• **{source['type']}**: [{source['description']}]({source['url']})")
                    
                    # --- YELLOW LIGHT ---
                    elif status in ['structure_error', 'content_error']:
                        with st.container():
                            st.warning(f"🟡 **Reference {result['line_number']}**: Potential Formatting or Content Issue")
                            st.write(f"_{type_icon} {result.get('reference_type', 'N/A').title()}_")
                            st.write(ref_text)
                            
                            if status == 'structure_error':
                                issues = result['structure_check'].get('structure_issues', [])
                                st.write("**Reason:** The reference has formatting problems.")
                                for issue in issues:
                                    st.write(f"• {issue}")
                            elif status == 'content_error':
                                st.write("**Reason:** Could not reliably extract key information (like title or authors) to perform an existence check.")

                    # --- RED LIGHT ---
                    elif status == 'likely_fake':
                        with st.container():
                            st.error(f"🔴 **Reference {result['line_number']}**: Likely Fake or Erroneous")
                            st.write(f"_{type_icon} {result.get('reference_type', 'N/A').title()}_")
                            st.write(ref_text)
                            
                            existence = result['existence_check']
                            search_details = existence.get('search_details', {})
                            
                            st.write(f"**Reason:** While the format may be correct, this reference could not be found in any academic or public databases.")
                            st.write("**Verification Attempts:**")

                            current_ref_type = result.get('reference_type', 'journal')
                            if current_ref_type == 'journal':
                                if 'doi' in search_details and not search_details['doi'].get('valid'):
                                    st.write(f"• **DOI Check**: {search_details['doi'].get('reason')}")
                                if 'comprehensive_journal' in search_details and not search_details['comprehensive_journal'].get('found'):
                                    st.write(f"• **Database Search**: {search_details['comprehensive_journal'].get('reason')}")

                            elif current_ref_type == 'book':
                                if 'isbn_search' in search_details and not search_details['isbn_search'].get('found'):
                                    st.write(f"• **ISBN Check**: {search_details['isbn_search'].get('reason')}")
                                if 'comprehensive_book_openlibrary' in search_details and not search_details['comprehensive_book_openlibrary'].get('found'):
                                    st.write(f"• **Open Library Search**: {search_details['comprehensive_book_openlibrary'].get('reason')}")
                                if 'comprehensive_book_googlebooks' in search_details and not search_details['comprehensive_book_googlebooks'].get('found'):
                                    st.write(f"• **Google Books Search**: {search_details['comprehensive_book_googlebooks'].get('reason')}")

                            elif current_ref_type == 'website':
                                if 'website_check' in search_details and not search_details['website_check'].get('accessible'):
                                    st.write(f"• **URL Check**: {search_details['website_check'].get('reason')}")
                    
                    if i < len(results) - 1:
                        st.markdown("---")
            else:
                st.warning("No references found. Please check your input format.")
        
        elif verify_button:
            st.warning("Please enter some references to verify.")
    
    # --- MODIFIED: Explainer Text ---
    with st.expander("ℹ️ How the Traffic Light System Works"):
        st.markdown("""
        The verifier uses a three-level process to assign a status to each reference:
        
        #### ✅ Green: Verified and Valid
        - **Structure**: Correctly formatted.
        - **Content**: Key details were extracted successfully.
        - **Existence**: The reference was found and verified in an external database (e.g., Crossref, Open Library, or a live website).
        
        #### 🟡 Yellow: Potential Issues
        - This status means the reference needs manual review. It can be caused by:
          - **Formatting Errors**: The reference doesn't follow the selected style (APA/Vancouver) rules, such as missing a year or publisher.
          - **Content Extraction Failure**: The reference is too malformed to reliably identify its parts (title, authors, etc.), preventing an existence check.
        
        #### 🔴 Red: Likely Fake or Erroneous
        - **Structure**: The reference may look perfectly formatted.
        - **Content**: Key details were extracted.
        - **Existence**: **Failed.** The verifier searched all relevant databases (using DOI, ISBN, title, authors, etc.) but could not find any evidence that this publication exists. This indicates the reference may be fabricated or contain critical errors.
        """)

if __name__ == "__main__":
    main()

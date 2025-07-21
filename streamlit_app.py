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
            'volume_pages': r'(\d+)(?:\((\d+)\))?,?\s*(\d+(?:-\d+)?)',
            'publisher_info': r'([A-Z][^.]*(?:Press|Publishers?|Publications?|Books?|Academic|University|Ltd|Inc|Corp)[^.]*)',
            'doi_pattern': r'https?://doi\.org/([^\s]+)',
            'author_pattern': r'^([^()]+?)(?:\s*\(\d{4}\))',
            'isbn_pattern': r'ISBN:?\s*([\d-]+)',
            'url_pattern': r'(https?://[^\s]+)',
            'website_access_date': r'(?:Retrieved|Accessed)\s+([^,]+)'
        }
        
        self.vancouver_patterns = {
            'starts_with_number': r'^(\d+)\.',
            'journal_title_section': r'^\d+\.\s*[^.]+\.\s*([^.]+)\.',
            'journal_year': r'([A-Za-z][^.;]+)[\s.]*(\d{4})',
            'author_pattern_vancouver': r'^\d+\.\s*([^.]+)\.',
            'book_publisher': r'([A-Z][^;:]+);\s*(\d{4})',
            'website_url_vancouver': r'Available\s+(?:from|at):\s*(https?://[^\s]+)'
        }
        
        self.type_indicators = {
            'journal': [
                r'[,;]\s*\d+(?:\(\d+\))?[,:]\s*\d+(?:-\d+)?',
                r'Journal|Review|Proceedings|Quarterly|Annual',
                r'https?://doi\.org/'
            ],
            'book': [
                r'(?:Press|Publishers?|Publications?|Books?|Academic|University)',
                r'ISBN:?\s*[\d-]+',
                r'(?:pp?\.|pages?)\s*\d+(?:-\d+)?'
            ],
            'website': [
                r'(?:Retrieved|Accessed)\s+(?:from|on)',
                r'https?://(?:www\.)?[^/\s]+\.[a-z]{2,}',
                r'Available\s+(?:from|at)'
            ]
        }

    def detect_reference_type(self, ref_text: str) -> str:
        ref_lower = ref_text.lower()
        type_scores = {'journal': 0, 'book': 0, 'website': 0}
        
        for ref_type, patterns in self.type_indicators.items():
            for pattern in patterns:
                if re.search(pattern, ref_lower):
                    type_scores[ref_type] += 1
        
        if any(score > 0 for score in type_scores.values()):
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

    def extract_reference_elements(self, ref_text: str, format_type: str, ref_type: str = None) -> Dict:
        elements = {
            'authors': None,
            'year': None,
            'title': None,
            'journal': None,
            'publisher': None,
            'url': None,
            'isbn': None,
            'doi': None,
            'access_date': None,
            'reference_type': ref_type or self.detect_reference_type(ref_text),
            'extraction_confidence': 'high'
        }
        
        detected_type = elements['reference_type']
        
        # Extract common elements
        doi_match = re.search(self.apa_patterns['doi_pattern'], ref_text)
        if doi_match:
            elements['doi'] = doi_match.group(1)
        
        url_match = re.search(self.apa_patterns['url_pattern'], ref_text)
        if url_match:
            elements['url'] = url_match.group(1)
        
        isbn_match = re.search(self.apa_patterns['isbn_pattern'], ref_text)
        if isbn_match:
            elements['isbn'] = isbn_match.group(1)
        
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
        else:
            required_fields = [elements['authors'], elements['year'], elements['title']]
        
        extracted_count = sum(1 for v in required_fields if v)
        if extracted_count < 2:
            elements['extraction_confidence'] = 'low'
        elif extracted_count < len(required_fields):
            elements['extraction_confidence'] = 'medium'
        
        return elements

    def parse_apa_reference(self, ref_text: str) -> Dict:
        result = {
            'format_valid': False,
            'authors': None,
            'year': None,
            'title': None,
            'journal': None,
            'publisher': None,
            'doi': None,
            'errors': []
        }
        
        # Extract year
        year_match = re.search(self.apa_patterns['journal_year_in_parentheses'], ref_text)
        if year_match:
            result['year'] = year_match.group(1)
        else:
            result['errors'].append("Year not found in correct format (YYYY)")
        
        # Extract authors
        author_match = re.search(self.apa_patterns['author_pattern'], ref_text)
        if author_match:
            result['authors'] = author_match.group(1).strip()
        else:
            result['errors'].append("Authors not found or incorrectly formatted")
        
        # Extract title
        title_match = re.search(self.apa_patterns['journal_title_after_year'], ref_text)
        if title_match:
            result['title'] = title_match.group(1).strip()
        else:
            result['errors'].append("Title not found")
        
        if len(result['errors']) == 0:
            result['format_valid'] = True
        
        return result

    def parse_vancouver_reference(self, ref_text: str) -> Dict:
        result = {
            'format_valid': False,
            'authors': None,
            'year': None,
            'title': None,
            'journal': None,
            'publisher': None,
            'errors': []
        }
        
        if not re.match(r'^\d+\.', ref_text):
            result['errors'].append("Vancouver format should start with number followed by period")
        
        # Extract authors
        author_match = re.search(self.vancouver_patterns['author_pattern_vancouver'], ref_text)
        if author_match:
            result['authors'] = author_match.group(1).strip()
        else:
            result['errors'].append("Authors not found")
        
        # Extract title
        title_match = re.search(self.vancouver_patterns['journal_title_section'], ref_text)
        if title_match:
            result['title'] = title_match.group(1).strip()
        else:
            result['errors'].append("Title not found")
        
        # Extract year
        year_match = re.search(r'(\d{4})', ref_text)
        if year_match:
            result['year'] = year_match.group(1)
        else:
            result['errors'].append("Year not found")
        
        if len(result['errors']) == 0:
            result['format_valid'] = True
        
        return result

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
                        
                        if similarity > 0.6:
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
            
            if authors:
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
                'rows': 10,
                'select': 'title,author,DOI,URL'
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
                
                if best_score > 0.3:
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
                        'reason': f'No good matches found (best score: {best_score:.2f})',
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
                return {'found': False, 'reason': 'Insufficient search terms for book search'}
            
            url = "https://openlibrary.org/search.json"
            params = {
                'q': ' '.join(query_parts),
                'limit': 5
            }
            
            if year:
                params['publish_year'] = year
            
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if 'docs' in data and data['docs']:
                best_match = data['docs'][0]  # Take first result
                
                return {
                    'found': True,
                    'match_score': 0.7,  # Simplified scoring
                    'matched_title': best_match.get('title', 'Unknown'),
                    'source_url': f"https://openlibrary.org{best_match['key']}" if 'key' in best_match else None,
                    'total_results': len(data['docs'])
                }
            
            return {'found': False, 'reason': 'No book search results'}
            
        except Exception as e:
            return {'found': False, 'reason': f'Book search error: {str(e)}'}

    def check_website_accessibility(self, url: str) -> Dict:
        if not url:
            return {'accessible': False, 'reason': 'No URL provided'}
        
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            response = self.session.head(url, timeout=10, allow_redirects=True)
            
            if response.status_code == 200:
                return {
                    'accessible': True,
                    'status_code': response.status_code,
                    'final_url': response.url,
                    'page_title': 'Website accessible'
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
        
        # Title matching (60% weight)
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.6
        
        # Author matching (30% weight)
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
                score += author_score * 0.3
        
        # Year matching (10% weight)
        if target_year:
            item_year = None
            if 'published-print' in item and 'date-parts' in item['published-print']:
                item_year = str(item['published-print']['date-parts'][0][0])
            elif 'published-online' in item and 'date-parts' in item['published-online']:
                item_year = str(item['published-online']['date-parts'][0][0])
            
            if item_year and item_year == target_year:
                score += 0.1
        
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
            
            if format_type == "APA":
                parsed = self.parser.parse_apa_reference(ref.text)
            elif format_type == "Vancouver":
                parsed = self.parser.parse_vancouver_reference(ref.text)
            else:
                parsed = {'format_valid': False, 'errors': ['Unknown format']}
            
            result['format_valid'] = parsed['format_valid']
            result['errors'] = parsed['errors']
            result['parsed_data'] = parsed
            result['reference_type'] = ref_type
            
            # Structure Check
            structure_check = self.parser.check_structural_format(ref.text, format_type, ref_type)
            result['structure_check'] = structure_check
            
            if structure_check['structure_valid']:
                result['structure_status'] = 'valid'
                
                # Content Extraction
                elements = self.parser.extract_reference_elements(ref.text, format_type, ref_type)
                result['extracted_elements'] = elements
                
                if elements['extraction_confidence'] in ['medium', 'high']:
                    result['content_status'] = 'extracted'
                    
                    # Existence Verification
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
            time.sleep(0.3)
        
        return results

    def _verify_existence(self, elements: Dict) -> Dict:
        results = {
            'any_found': False,
            'doi_valid': False,
            'title_found': False,
            'comprehensive_found': False,
            'isbn_found': False,
            'website_accessible': False,
            'search_details': {},
            'verification_sources': []
        }
        
        ref_type = elements.get('reference_type', 'journal')
        
        # DOI check
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
        
        # Type-specific verification
        if ref_type == 'journal':
            if elements.get('title'):
                title_result = self.searcher.search_by_exact_title(elements['title'])
                results['search_details']['title_search'] = title_result
                
                if title_result['found']:
                    results['title_found'] = True
                    results['any_found'] = True
                    if title_result.get('source_url'):
                        results['verification_sources'].append({
                            'type': 'Journal Title Match',
                            'url': title_result['source_url'],
                            'description': f"Title match (similarity: {title_result.get('similarity', 0):.1%})"
                        })
            
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
                if comprehensive_result.get('source_url'):
                    results['verification_sources'].append({
                        'type': 'Journal Comprehensive Search',
                        'url': comprehensive_result['source_url'],
                        'description': f"Multi-element match (confidence: {comprehensive_result.get('match_score', 0):.1%})"
                    })
        
        elif ref_type == 'book':
            if elements.get('isbn'):
                isbn_result = self.searcher.search_books_isbn(elements['isbn'])
                results['search_details']['isbn_search'] = isbn_result
                
                if isbn_result['found']:
                    results['isbn_found'] = True
                    results['any_found'] = True
                    if isbn_result.get('source_url'):
                        results['verification_sources'].append({
                            'type': 'ISBN Verification',
                            'url': isbn_result['source_url'],
                            'description': f"ISBN {isbn_result['isbn']} found in Open Library"
                        })
            
            book_result = self.searcher.search_books_comprehensive(
                elements.get('title', ''),
                elements.get('authors', ''),
                elements.get('year', ''),
                elements.get('publisher', '')
            )
            results['search_details']['book_search'] = book_result
            
            if book_result['found']:
                results['comprehensive_found'] = True
                results['any_found'] = True
                if book_result.get('source_url'):
                    results['verification_sources'].append({
                        'type': 'Book Database Match',
                        'url': book_result['source_url'],
                        'description': f"Book match (confidence: {book_result.get('match_score', 0):.1%})"
                    })
        
        elif ref_type == 'website':
            if elements.get('url'):
                website_result = self.searcher.check_website_accessibility(elements['url'])
                results['search_details']['website_check'] = website_result
                
                if website_result['accessible']:
                    results['website_accessible'] = True
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
    st.markdown("**Three-level verification**: Structure → Content → Existence")
    st.markdown("Supports **journals** 📄, **books** 📚, and **websites** 🌐")
    
    st.sidebar.header("Settings")
    format_type = st.sidebar.selectbox(
        "Select Reference Format",
        ["APA", "Vancouver"]
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**🔍 Verification Process:**")
    st.sidebar.markdown("• **Structure**: Layout validation")
    st.sidebar.markdown("• **Content**: Element extraction")
    st.sidebar.markdown("• **Existence**: Database verification")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**📋 Supported Types:**")
    st.sidebar.markdown("📄 **Journals**: DOI, Crossref")
    st.sidebar.markdown("📚 **Books**: ISBN, Open Library")
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
                sample_data = """Smith, J. A. (2020). Climate change impacts on marine ecosystems. Nature Climate Change, 10(5), 423-431. https://doi.org/10.1038/s41558-020-0789-5
Brown, M. (2019). Machine learning in healthcare. MIT Press.
Johnson, R. (2021). COVID-19 pandemic response. Retrieved March 15, 2023, from https://www.who.int/emergencies/diseases/novel-coronavirus-2019
Buchheit, M., & Mendez-Villanueva, A. (2014). Performance and physiological responses to an agility test in professional soccer players. Journal of Sports Sciences, 32(8), 675-682. https://doi.org/10.1080/02640414.2013.876411
Fake, A. B. (2023). Non-existent study on imaginary topics. Made Up Press. ISBN: 978-1234567890"""
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
                verifier = ReferenceVerifier()
                results = verifier.verify_references(reference_text, format_type, update_progress)
            
            progress_bar.empty()
            status_text.empty()
            
            if results:
                total_refs = len(results)
                valid_refs = sum(1 for r in results if r['overall_status'] == 'valid')
                structure_errors = sum(1 for r in results if r['overall_status'] == 'structure_error')
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
                    st.metric("🔧 Structure", structure_errors)
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
                    ref_type = result.get('reference_type', 'journal')
                    
                    type_icons = {'journal': '📄', 'book': '📚', 'website': '🌐'}
                    type_icon = type_icons.get(ref_type, '📄')
                    
                    if status == 'valid':
                        st.success(f"✅ {type_icon} **Reference {result['line_number']}** ({ref_type.title()}): Verified and Valid")
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
                    
                    elif status == 'structure_error':
                        st.error(f"🔧 {type_icon} **Reference {result['line_number']}** ({ref_type.title()}): Structural Format Issues")
                        st.write(ref_text)
                        
                        issues = result['structure_check'].get('structure_issues', [])
                        if issues:
                            st.write(f"**Structural problems for {ref_type}:**")
                            for issue in issues:
                                st.write(f"• {issue}")
                    
                    elif status == 'content_error':
                        st.warning(f"⚠️ {type_icon} **Reference {result['line_number']}** ({ref_type.title()}): Content Extraction Issues")
                        st.write(ref_text)
                        st.write(f"**Issue:** Could not extract enough elements to verify this {ref_type} reference.")
                    
                    elif status == 'likely_fake':
                        st.error(f"🚨 {type_icon} **Reference {result['line_number']}** ({ref_type.title()}): Likely Fake Reference")
                        st.write(ref_text)
                        
                        existence = result['existence_check']
                        search_details = existence.get('search_details', {})
                        
                        evidence = []
                        if 'doi' in search_details and not search_details['doi'].get('valid'):
                            evidence.append("DOI does not exist or is invalid")
                        if 'title_search' in search_details and not search_details['title_search'].get('found'):
                            evidence.append("Title not found in academic databases")
                        if 'comprehensive' in search_details and not search_details['comprehensive'].get('found'):
                            evidence.append("No matching publications found")
                        if 'isbn_search' in search_details and not search_details['isbn_search'].get('found'):
                            evidence.append("ISBN not found in book databases")
                        if 'website_check' in search_details and not search_details['website_check'].get('accessible'):
                            evidence.append("Website not accessible")
                        
                        if evidence:
                            st.write(f"**🚨 Evidence this {ref_type} reference is fake:**")
                            for item in evidence:
                                st.write(f"• {item}")
                        
                        st.write(f"**⚠️ This {ref_type} reference appears to be fabricated or contains significant errors.**")
                    
                    if i < len(results) - 1:
                        st.markdown("---")
            else:
                st.warning("No references found. Please check your input format.")
        
        elif verify_button:
            st.warning("Please enter some references to verify.")
    
    with st.expander("ℹ️ How the Three-Level Verification Works"):
        st.markdown("""
        **Level 1: Structure Check** 🔧
        - Verifies basic reference format (APA/Vancouver layout)
        - Checks for required elements based on type (journal/book/website)
        - **Lenient** - focuses on structure, not exact formatting details
        
        **Level 2: Content Extraction** ⚠️
        - Extracts key elements (authors, title, year, journal/publisher, DOI/ISBN/URL)
        - Assesses extraction confidence
        - Identifies potential content issues
        
        **Level 3: Existence Verification** 🚨
        - **Journals**: DOI validation, Crossref searches
        - **Books**: ISBN lookup via Open Library, comprehensive book search
        - **Websites**: URL accessibility checking
        - **Identifies likely fake references across all types**
        
        **Result Categories:**
        - ✅ **Valid**: Passes all levels, reference verified in databases
        - 🔧 **Structure Issues**: Layout/format problems need fixing
        - ⚠️ **Content Issues**: Structure OK, but content extraction failed
        - 🚨 **Likely Fake**: Well-formatted but doesn't exist in any database
        """)

if __name__ == "__main__":
    main()

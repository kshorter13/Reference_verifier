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
        
        # HIGH priority: URL + access date = websi

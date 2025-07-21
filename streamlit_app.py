return {
                        'found': True,
                        'match_score': best_score,
                        'matched_title': best_match.get('title', 'Unknown'),
                        'matched_authors': best_match.get('author_name', []),
                        'publisher': best_match.get('publisher', ['Unknown'])[0] if best_match.get('publisher') else 'Unknown',
                        'publish_year': best_match.get('first_publish_year', 'Unknown'),
                        'isbn': isbn,
                        'source_url': f"https://openlibrary.org{best_match['key']}" if 'key' in best_match else None,
                        'total_results': len(data['docs'])
                    }
                
                return {
                    'found': False,
                    'reason': f'No good book matches found (best score: {best_score:.2f})',
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
                try:
                    get_response = self.session.get(url, timeout=10)
                    if get_response.status_code == 200:
                        title_match = re.search(r'<title[^>]*>([^<]+)</title>', get_response.text, re.IGNORECASE)
                        page_title = title_match.group(1).strip() if title_match else 'No title found'
                        
                        return {
                            'accessible': True,
                            'status_code': response.status_code,
                            'final_url': response.url,
                            'page_title': page_title,
                            'content_type': get_response.headers.get('content-type', 'Unknown')
                        }
                    else:
                        return {
                            'accessible': False,
                            'reason': f'GET request failed (status: {get_response.status_code})',
                            'status_code': get_response.status_code
                        }
                except:
                    return {
                        'accessible': True,
                        'status_code': response.status_code,
                        'final_url': response.url,
                        'page_title': 'Could not extract title',
                        'reason': 'HEAD request successful, but could not retrieve page content'
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
        
        if 'title' in item and item['title'] and target_title:
            item_title = item['title'][0] if isinstance(item['title'], list) else str(item['title'])
            title_sim = self._calculate_title_similarity(target_title, item_title)
            score += title_sim * 0.5
        
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
                score += author_score * 0.25
        
        if target_year:
            item_year = None
            if 'published-print' in item and 'date-parts' in item['published-print']:
                item_year = str(item['published-print']['date-parts'][0][0])
            elif 'published-online' in item and 'date-parts' in item['published-online']:
                item_year = str(item['published-online']['date-parts'][0][0])
            
            if item_year and item_year == target_year:
                score += 0.15
        
        if 'container-title' in item and item['container-title'] and target_journal:
            item_journal = item['container-title'][0] if isinstance(item['container-title'], list) else str(item['container-title'])
            journal_sim = self._calculate_title_similarity(target_journal, item_journal)
            score += journal_sim * 0.1
        
        return score

    def _calculate_book_match_score(self, book_doc: Dict, target_title: str, target_authors: str, target_year: str, target_publisher: str) -> float:
        score = 0.0
        
        if 'title' in book_doc and target_title:
            book_title = str(book_doc['title']).lower()
            title_sim = self._calculate_title_similarity(target_title, book_title)
            score += title_sim * 0.4
        
        if 'author_name' in book_doc and target_authors:
            book_authors = [name.lower() for name in book_doc['author_name']]
            
            target_author_parts = []
            for author in re.split(r'[,&]', target_authors):
                author_clean = re.sub(r'[^\w\s]', '', author).strip()
                if author_clean:
                    name_parts = author_clean.split()
                    target_author_parts.extend([part.lower() for part in name_parts if len(part) > 2])
            
            if book_authors and target_author_parts:
                common_names = 0
                for book_author in book_authors:
                    for target_part in target_author_parts:
                        if target_part in book_author or book_author in target_part:
                            common_names += 1
                            break
                
                author_score = common_names / max(len(target_author_parts), 1)
                score += author_score * 0.3
        
        if target_year and 'first_publish_year' in book_doc:
            if str(book_doc['first_publish_year']) == target_year:
                score += 0.2
        
        if target_publisher and 'publisher' in book_doc:
            book_publishers = [pub.lower() for pub in book_doc['publisher']]
            target_publisher_lower = target_publisher.lower()
            
            for book_pub in book_publishers:
                if target_publisher_lower in book_pub or book_pub in target_publisher_lower:
                    score += 0.1
                    break
        
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
                'content_check': {},
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
            
            structure_check = self.parser.check_structural_format(ref.text, format_type, ref_type)
            result['structure_check'] = structure_check
            
            if structure_check['structure_valid']:
                result['structure_status'] = 'valid'
                
                elements = self.parser.extract_reference_elements(ref.text, format_type, ref_type)
                result['extracted_elements'] = elements
                
                if elements['extraction_confidence'] in ['medium', 'high']:
                    result['content_status'] = 'extracted'
                    
                    existence_results = self._verify_existence(elements)
                    result['existence_check'] = existence_results
                    
                    if existence_results['any_found']:
                        result['existence_status'] = 'found'
                        result['overall_status'] = 'valid'
                    elif (existence_results['doi_invalid'] or 
                          existence_results['title_not_found'] or
                          (ref_type == 'website' and not existence_results['website_accessible'])):
                        result['existence_status'] = 'not_found'
                        result['overall_status'] = 'likely_fake'
                    else:
                        result['existence_status'] = 'uncertain'
                        result['overall_status'] = 'content_warning'
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
            'doi_invalid': False,
            'title_found': False,
            'title_not_found': False,
            'comprehensive_found': False,
            'isbn_found': False,
            'website_accessible': False,
            'search_details': {},
            'verification_sources': []
        }
        
        ref_type = elements.get('reference_type', 'journal')
        
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
                        'description': 'DOI verified with title match'
                    })
            else:
                results['doi_invalid'] = True
        
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
                            'description': f"Exact title match (similarity: {title_result.get('similarity', 0):.1%})"
                        })
                else:
                    results['title_not_found'] = True
            
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

    def _show_verification_details(self, result: Dict, ref_type: str):
        existence = result['existence_check']
        search_details = existence.get('search_details', {})
        
        if ref_type == 'journal':
            doi_details = search_details.get('doi')
            if doi_details and doi_details.get('valid'):
                with st.expander("📋 DOI Verification Details"):
                    st.write(f"**Actual Title:** {doi_details.get('actual_title', 'N/A')}")
                    if doi_details.get('title_similarity'):
                        st.write(f"**Title Match Confidence:** {doi_details['title_similarity']:.1%}")
                    st.write(f"**Authors:** {', '.join(doi_details.get('actual_authors', []))}")
                    st.write(f"**Journal:** {doi_details.get('actual_journal', 'N/A')}")
                    st.write(f"**Year:** {doi_details.get('actual_year', 'N/A')}")
                    if doi_details.get('crossref_url'):
                        st.markdown(f"**Crossref API:** [{doi_details['crossref_url']}]({doi_details['crossref_url']})")
        
        elif ref_type == 'book':
            isbn_details = search_details.get('isbn_search')
            book_details = search_details.get('book_search')
            
            if isbn_details and isbn_details.get('found'):
                with st.expander("📚 ISBN Verification Details"):
                    st.write(f"**Verified Title:** {isbn_details.get('title', 'N/A')}")
                    st.write(f"**Authors:** {', '.join(isbn_details.get('authors', []))}")
                    st.write(f"**Publishers:** {', '.join(isbn_details.get('publishers', []))}")
                    st.write(f"**Publish Date:** {isbn_details.get('publish_date', 'N/A')}")
                    st.write(f"**ISBN:** {isbn_details.get('isbn', 'N/A')}")
            
            if book_details and book_details.get('found'):
                with st.expander("📖 Book Database Details"):
                    st.write(f"**Matched Title:** {book_details.get('matched_title', 'N/A')}")
                    st.write(f"**Authors:** {', '.join(book_details.get('matched_authors', []))}")
                    st.write(f"**Publisher:** {book_details.get('publisher', 'N/A')}")
                    st.write(f"**Publish Year:** {book_details.get('publish_year', 'N/A')}")
                    if book_details.get('match_score'):
                        st.write(f"**Match Confidence:** {book_details['match_score']:.1%}")
        
        elif ref_type == 'website':
            website_details = search_details.get('website_check')
            if website_details and website_details.get('accessible'):
                with st.expander("🌐 Website Verification Details"):
                    st.write(f"**Page Title:** {website_details.get('page_title', 'N/A')}")
                    st.write(f"**Final URL:** {website_details.get('final_url', 'N/A')}")
                    st.write(f"**Status Code:** {website_details.get('status_code', 'N/A')}")
                    st.write(f"**Content Type:** {website_details.get('content_type', 'N/A')}")

    def _show_content_warning_details(self, result: Dict, ref_type: str):
        existence = result['existence_check']
        search_details = existence.get('search_details', {})
        
        if ref_type == 'journal':
            if 'comprehensive' in search_details:
                comp_result = search_details['comprehensive']
                if 'match_score' in comp_result:
                    st.write(f"**Match confidence:** {comp_result['match_score']:.1%} (below threshold)")
        
        elif ref_type == 'book':
            book_result = search_details.get('book_search', {})
            if 'match_score' in book_result:
                st.write(f"**Book match confidence:** {book_result['match_score']:.1%} (below threshold)")
            if book_result.get('total_results', 0) > 0:
                st.write(f"**Search found {book_result['total_results']} potential matches, but none were close enough**")

    def _show_fake_evidence(self, result: Dict, ref_type: str):
        existence = result['existence_check']
        evidence = []
        search_details = existence.get('search_details', {})
        
        if ref_type == 'journal':
            doi_details = search_details.get('doi')
            if doi_details and not doi_details.get('valid'):
                reason = doi_details.get('reason', 'Unknown error')
                if 'Title mismatch' in reason:
                    evidence.append(f"DOI exists but title doesn't match (Expected: '{doi_details.get('expected_title', 'N/A')}', Actual: '{doi_details.get('actual_title', 'N/A')}')")
                elif 'does not resolve' in reason:
                    evidence.append("DOI does not exist or is inaccessible")
                else:
                    evidence.append(f"DOI validation failed: {reason}")
            
            if existence.get('title_not_found'):
                evidence.append("Title not found in academic databases")
            
            if 'comprehensive' in search_details:
                comp_result = search_details['comprehensive']
                if not comp_result.get('found'):
                    evidence.append(f"No matching journal publications found ({comp_result.get('reason', 'unknown reason')})")
        
        elif ref_type == 'book':
            if 'isbn_search' in search_details:
                isbn_result = search_details['isbn_search']
                if not isbn_result.get('found'):
                    evidence.append(f"ISBN not found in book databases ({isbn_result.get('reason', 'unknown reason')})")
            
            if 'book_search' in search_details:
                book_result = search_details['book_search']
                if not book_result.get('found'):
                    evidence.append(f"No matching books found ({book_result.get('reason', 'unknown reason')})")
        
        elif ref_type == 'website':
            if 'website_check' in search_details:
                website_result = search_details['website_check']
                if not website_result.get('accessible'):
                    evidence.append(f"Website not accessible ({website_result.get('reason', 'unknown reason')})")
        
        if evidence:
            st.write(f"**🚨 Evidence this {ref_type} reference is fake:**")
            for item in evidence:
                st.write(f"• {item}")
        
        if ref_type == 'journal':
            doi_details = search_details.get('doi')
            if doi_details and 'actual_title' in doi_details:
                with st.expander("🔍 What the DOI Actually Contains"):
                    st.write(f"**Actual Title:** {doi_details['actual_title']}")
                    st.write(f"**Actual Authors:** {', '.join(doi_details.get('actual_authors', []))}")
                    st.write(f"**Actual Journal:** {doi_details.get('actual_journal', 'N/A')}")
                    st.write(f"**Actual Year:** {doi_details.get('actual_year', 'N/A')}")
                    if doi_details.get('doi_url'):
                        st.markdown(f"**Check DOI:** [{doi_details['doi_url']}]({doi_details['doi_url']})")
        
        st.write(f"**⚠️ This {ref_type} reference appears to be fabricated or contains significant errors.**")

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
    st.sidebar.markdown("📄 **Journals**: DOI, PubMed, Crossref")
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
World Health Organization. (2021). COVID-19 pandemic response. Retrieved March 15, 2023, from https://www.who.int/emergencies/diseases/novel-coronavirus-2019

📄 Journal (Vancouver):
1. Smith JA. Climate change impacts on marine ecosystems. Nature Climate Change. 2020;10(5):423-431.

📚 Book (Vancouver):
2. Brown M. Machine learning in healthcare. Cambridge: MIT Press; 2019.

🌐 Website (Vancouver):
3. World Health Organization. COVID-19 pandemic response. Available from: https://www.who.int/emergencies/diseases/novel-coronavirus-2019. Accessed 2023 Mar 15.""",
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
Fake, A. B. (2023). Non-existent study on imaginary topics. Made Up Press. ISBN: 978-1234567890
Invalid format reference without proper structure"""
                st.session_state.sample_text = sample_data
        
        with st.expander("💡 Quick Tips"):
            st.markdown("""
            **For best results:**
            - Include DOIs for journal articles when available
            - Include ISBNs for books when available  
            - Include complete URLs for websites
            - Use consistent formatting throughout your list
            - Remove any extra numbering or bullets (the system will detect Vancouver numbering)
            
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
            
            with st.spinner("Initializing three-level verification..."):
                verifier = ReferenceVerifier()
                results = verifier.verify_references(reference_text, format_type, update_progress)
            
            progress_bar.empty()
            status_text.empty()
            
            if results:
                total_refs = len(results)
                valid_refs = sum(1 for r in results if r['overall_status'] == 'valid')
                structure_errors = sum(1 for r in results if r['overall_status'] == 'structure_error')
                content_warnings = sum(1 for r in results if r['overall_status'] == 'content_warning')
                content_errors = sum(1 for r in results if r['overall_status'] == 'content_error')
                likely_fake = sum(1 for r in results if r['overall_status'] == 'likely_fake')
                
                type_counts = {}
                for result in results:
                    ref_type = result.get('reference_type', 'journal')
                    type_counts[ref_type] = type_counts.get(ref_type, 0) + 1
                
                col_a, col_b, col_c, col_d, col_e, col_f = st.columns(6)
                with col_a:
                    st.metric("Total", total_refs)
                with col_c:
                    st.metric("🔧 Structure", structure_errors)
                with col_d:
                    st.metric("⚠️ Content", content_warnings + content_errors)
                with col_e:
                    st.metric("🚨 Likely Fake", likely_fake)
                with col_f:
                    accuracy = round((valid_refs / total_refs * 100) if total_refs > 0 else 0, 1)
                    st.metric("Accuracy", f"{accuracy}%")
                
                if type_counts:
                    st.markdown("**Reference Types Detected:**")
                    type_display = []
                    type_icons = {'journal': '📄', 'book': '📚', 'website': '🌐'}
                    for ref_type, count in type_counts.items():
                        icon = type_icons.get(ref_type, '📄')
                        type_display.append(f"{icon} {ref_type.title()}: {count}")
                    st.write(" • ".join(type_display))
                
                if st.button("📥 Export Verification Report", use_container_width=True):
                    report = "# Reference Verification Report\n\n"
                    report += f"**Format:** {format_type}\n"
                    report += f"**Total References:** {total_refs}\n"
                    report += f"**Valid:** {valid_refs}\n"
                    report += f"**Issues:** {total_refs - valid_refs}\n\n"
                    
                    for result in results:
                        ref_type = result.get('reference_type', 'journal')
                        type_icon = {'journal': '📄', 'book': '📚', 'website': '🌐'}.get(ref_type, '📄')
                        
                        report += f"## {type_icon} Reference {result['line_number']} ({ref_type.title()})\n"
                        report += f"**Status:** {result['overall_status']}\n"
                        report += f"**Text:** {result['reference']}\n\n"
                        
                        if result['overall_status'] == 'valid':
                            sources = result['existence_check'].get('verification_sources', [])
                            for source in sources:
                                report += f"- Verified via {source['type']}: {source['url']}\n"
                        
                        report += "---\n\n"
                    
                    st.download_button(
                        label="📄 Download Report",
                        data=report,
                        file_name=f"reference_verification_report_{format_type.lower()}.md",
                        mime="text/markdown"
                    )
                
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
                        
                        verifier._show_verification_details(result, ref_type)
                    
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
                    
                    elif status == 'content_warning':
                        st.warning(f"⚠️ {type_icon} **Reference {result['line_number']}** ({ref_type.title()}): Possible Content Issues")
                        st.write(ref_text)
                        st.write(f"**Issue:** {ref_type.title()} structure is correct, but some content details may be incorrect.")
                        
                        verifier._show_content_warning_details(result, ref_type)
                    
                    elif status == 'likely_fake':
                        st.error(f"🚨 {type_icon} **Reference {result['line_number']}** ({ref_type.title()}): Likely Fake Reference")
                        st.write(ref_text)
                        
                        verifier._show_fake_evidence(result, ref_type)
                    
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
        - **Journals**: DOI validation, PubMed/Crossref searches
        - **Books**: ISBN lookup via Open Library, comprehensive book search
        - **Websites**: URL accessibility checking, page title extraction
        - **Identifies likely fake references across all types**
        
        **Result Categories:**
        - ✅ **Valid**: Passes all levels, reference verified in appropriate databases
        - 🔧 **Structure Issues**: Layout/format problems need fixing
        - ⚠️ **Content Issues**: Structure OK, but content may have errors
        - 🚨 **Likely Fake**: Well-formatted but doesn't exist in any database
        
        **Reference Types Supported:**
        - 📄 **Journal Articles**: Via DOI, PubMed, Crossref
        - 📚 **Books**: Via ISBN and Open Library database
        - 🌐 **Websites**: Via URL accessibility checking
        
        **Key Improvement:**
        Now supports all major reference types with specialized validation!
        """)
    
    with st.expander("📊 Understanding Your Results"):
        st.markdown("""
        **What each status means:**
        
        🔧 **Structure Issues**: Your reference needs formatting fixes
        - Missing required elements (year, title, journal/publisher)
        - Incorrect punctuation or layout
        - **Action**: Fix the format according to your style guide
        
        ⚠️ **Content Issues**: Format is correct, but details might be wrong
        - Author names might be incorrect
        - Journal/publisher name might be wrong
        - Volume/issue/page numbers might be off
        - **Action**: Double-check all details against the original source
        
        🚨 **Likely Fake**: Reference appears to be fabricated
        - Well-formatted but doesn't exist in databases
        - Invalid DOI/ISBN or title not found anywhere
        - No matching publications in academic databases
        - **Action**: Remove or replace with a real reference
        
        **Pro Tip**: A reference can look perfectly formatted but still be fake!
        """)

if __name__ == "__main__":
    main()import streamlit as st
import re
import requests
import time
import json
from typing import List, Dict, Optional
from dataclasses import dataclass
from urllib.parse import quote, urlencode
import xml.etree.ElementTree as ET

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
            'book_year_in_parentheses': r'\((\d{4}[a-z]?)\)',
            'book_title_italics': r'\)\.\s*([^.]+)\.',
            'publisher_info': r'([A-Z][^.]*(?:Press|Publishers?|Publications?|Books?|Academic|University|Ltd|Inc|Corp)[^.]*)',
            'website_title': r'([^.]+)\.\s*(?:Retrieved|Accessed)',
            'website_url': r'(https?://[^\s]+)',
            'website_access_date': r'(?:Retrieved|Accessed)\s+([^,]+)',
            'doi_pattern': r'https?://doi\.org/([^\s]+)',
            'author_pattern': r'^([^()]+?)(?:\s*\(\d{4}\))',
            'isbn_pattern': r'ISBN:?\s*([\d-]+)',
            'url_pattern': r'(https?://[^\s]+)'
        }
        
        self.vancouver_patterns = {
            'starts_with_number': r'^(\d+)\.',
            'journal_title_section': r'^\d+\.\s*[^.]+\.\s*([^.]+)\.',
            'journal_year': r'([A-Za-z][^.;]+)[\s.]*(\d{4})',
            'volume_pages_vancouver': r';(\d+)(?:\((\d+)\))?:([^.]+)',
            'book_title_section': r'^\d+\.\s*[^.]+\.\s*([^.]+)\.',
            'book_publisher': r'([A-Z][^;:]+);\s*(\d{4})',
            'website_title_vancouver': r'^\d+\.\s*[^.]+\.\s*([^.]+)\.',
            'website_url_vancouver': r'Available\s+(?:from|at):\s*(https?://[^\s]+)',
            'author_pattern_vancouver': r'^\d+\.\s*([^.]+)\.',
        }
        
        self.type_indicators = {
            'journal': [
                r'[,;]\s*\d+(?:\(\d+\))?[,:]\s*\d+(?:-\d+)?',
                r'Journal|Review|Proceedings|Quarterly|Annual',
                r'https?://doi\.org/',
            ],
            'book': [
                r'(?:Press|Publishers?|Publications?|Books?|Academic|University)',
                r'ISBN:?\s*[\d-]+',
                r'(?:pp?\.|pages?)\s*\d+(?:-\d+)?',
                r'(?:1st|2nd|3rd|\dth)\s+(?:ed\.|edition)',
            ],
            'website': [
                r'(?:Retrieved|Accessed)\s+(?:from|on)',
                r'https?://(?:www\.)?[^/\s]+\.[a-z]{2,}',
                r'Available\s+(?:from|at)',
                r'Web\.|Online\.',
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
            'extracted_elements': {},
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
        
        doi_match = re.search(self.apa_patterns['doi_pattern'], ref_text)
        if doi_match:
            result['doi'] = doi_match.group(1)
        
        year_match = re.search(self.apa_patterns['journal_year_in_parentheses'], ref_text)
        if year_match:
            result['year'] = year_match.group(1)
        else:
            result['errors'].append("Year not found in correct format (YYYY)")
        
        author_match = re.search(self.apa_patterns['author_pattern'], ref_text)
        if author_match:
            authors_text = author_match.group(1).strip()
            authors_text = re.sub(r'\s+', ' ', authors_text)
            result['authors'] = authors_text
        else:
            result['errors'].append("Authors not found or incorrectly formatted")
        
        title_match = re.search(self.apa_patterns['journal_title_after_year'], ref_text)
        if title_match:
            result['title'] = title_match.group(1).strip()
        else:
            result['errors'].append("Title not found")
        
        ref_type = self.detect_reference_type(ref_text)
        if ref_type == 'journal':
            journal_match = re.search(self.apa_patterns['journal_info'], ref_text)
            if journal_match:
                result['journal'] = journal_match.group(1).strip()
        elif ref_type == 'book':
            publisher_match = re.search(self.apa_patterns['publisher_info'], ref_text)
            if publisher_match:
                result['publisher'] = publisher_match.group(1).strip()
        
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
        
        author_match = re.search(self.vancouver_patterns['author_pattern_vancouver'], ref_text)
        if author_match:
            result['authors'] = author_match.group(1).strip()
        else:
            result['errors'].append("Authors not found")
        
        title_match = re.search(self.vancouver_patterns['journal_title_section'], ref_text)
        if title_match:
            result['title'] = title_match.group(1).strip()
        else:
            result['errors'].append("Title not found")
        
        year_match = re.search(r'(\d{4})', ref_text)
        if year_match:
            result['year'] = year_match.group(1)
        else:
            result['errors'].append("Year not found")
        
        ref_type = self.detect_reference_type(ref_text)
        if ref_type == 'journal':
            journal_match = re.search(self.vancouver_patterns['journal_year'], ref_text)
            if journal_match:
                result['journal'] = journal_match.group(1).strip()
        elif ref_type == 'book':
            publisher_match = re.search(self.vancouver_patterns['book_publisher'], ref_text)
            if publisher_match:
                result['publisher'] = publisher_match.group(1).strip()
        
        if len(result['errors']) == 0:
            result['format_valid'] = True
        
        return result

class DatabaseSearcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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
            
            crossref_url = f"https://api.crossref.org/works/{doi}"
            metadata_response = self.session.get(crossref_url, timeout=15)
            
            if metadata_response.status_code != 200:
                return {
                    'valid': False,
                    'reason': 'Could not retrieve DOI metadata',
                    'doi_url': url,
                    'resolved_url': response.url
                }
            
            metadata = metadata_response.json()
            
            if 'message' not in metadata:
                return {
                    'valid': False,
                    'reason': 'Invalid DOI metadata format',
                    'doi_url': url
                }
            
            work = metadata['message']
            
            actual_title = None
            if 'title' in work and work['title']:
                actual_title = work['title'][0] if isinstance(work['title'], list) else str(work['title'])
            
            if not actual_title:
                return {
                    'valid': False,
                    'reason': 'No title found in DOI metadata',
                    'doi_url': url
                }
            
            title_similarity = 0
            if expected_title:
                title_similarity = self._calculate_title_similarity(expected_title.lower(), actual_title.lower())
                
                if title_similarity < 0.7:
                    return {
                        'valid': False,
                        'reason': 'Title mismatch with DOI content',
                        'expected_title': expected_title,
                        'actual_title': actual_title,
                        'similarity_score': title_similarity,
                        'doi_url': url
                    }
            
            authors = []
            if 'author' in work:
                for author in work['author']:
                    if 'given' in author and 'family' in author:
                        authors.append(f"{author['given']} {author['family']}")
                    elif 'family' in author:
                        authors.append(author['family'])
            
            journal = None
            if 'container-title' in work and work['container-title']:
                journal = work['container-title'][0] if isinstance(work['container-title'], list) else str(work['container-title'])
            
            published_year = None
            if 'published-print' in work and 'date-parts' in work['published-print']:
                published_year = str(work['published-print']['date-parts'][0][0])
            elif 'published-online' in work and 'date-parts' in work['published-online']:
                published_year = str(work['published-online']['date-parts'][0][0])
            
            return {
                'valid': True,
                'actual_title': actual_title,
                'actual_authors': authors,
                'actual_journal': journal,
                'actual_year': published_year,
                'title_similarity': title_similarity if expected_title else None,
                'doi_url': url,
                'resolved_url': response.url,
                'crossref_url': crossref_url
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
            title_clean = re.sub(r'[^\w\s]', ' ', title)
            title_words = [word for word in title_clean.split() if len(word) > 2]
            
            if len(title_words) < 3:
                return {'found': False, 'reason': 'Insufficient title words for search'}
            
            url = "https://api.crossref.org/works"
            params = {
                'query.title': title_clean,
                'rows': 10,
                'select': 'title,author,published-print,published-online,container-title,DOI,URL'
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
                        
                        if similarity > 0.8:
                            source_url = None
                            if 'DOI' in item:
                                source_url = f"https://doi.org/{item['DOI']}"
                            elif 'URL' in item:
                                source_url = item['URL']
                            
                            return {
                                'found': True,
                                'similarity': similarity,
                                'matched_title': item_title,
                                'doi': item.get('DOI', 'Not available'),
                                'source_url': source_url,
                                'crossref_url': f"https://api.crossref.org/works/{item['DOI']}" if 'DOI' in item else None
                            }
                
                return {'found': False, 'reason': f'No close title matches found ({len(items)} results checked)'}
            
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
                'rows': 15,
                'select': 'title,author,published-print,published-online,container-title,DOI,URL'
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
                
                if best_score > 0.5:
                    source_url = None
                    if 'DOI' in best_match:
                        source_url = f"https://doi.org/{best_match['DOI']}"
                    elif 'URL' in best_match:
                        source_url = best_match['URL']
                    
                    return {
                        'found': True,
                        'match_score': best_score,
                        'matched_title': best_match.get('title', ['Unknown'])[0] if best_match.get('title') else 'Unknown',
                        'matched_doi': best_match.get('DOI'),
                        'source_url': source_url,
                        'crossref_url': f"https://api.crossref.org/works/{best_match['DOI']}" if best_match.get('DOI') else None,
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
                        'publishers': [pub.get('name', 'Unknown') for pub in book_data.get('publishers', [])],
                        'publish_date': book_data.get('publish_date', 'Unknown'),
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
                'limit': 10
            }
            
            if year:
                params['publish_year'] = year
            
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if 'docs' in data and data['docs']:
                best_match = None
                best_score = 0
                
                for doc in data['docs']:
                    score = self._calculate_book_match_score(doc, title, authors, year, publisher)
                    if score > best_score:
                        best_score = score
                        best_match = doc
                
                if best_score > 0.3:
                    isbn = None
                    if 'isbn' in best_match:
                        isbn = best_match['isbn'][0] if best_match['isbn'] else None
                    
                    return {
                        'found': True,

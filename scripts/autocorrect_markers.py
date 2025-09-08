#!/usr/bin/env python3
"""
Auto-correction script for finalized XML marker files.

This script analyzes finalized XML marker files and applies automatic corrections
or generates reports of issues that need manual review.

Usage:
    python autocorrect_markers.py [directory_path] [--fix] [--output report.tsv] [--verbose]
    
Options:
    --fix          Apply automatic corrections (without this, only reports issues)
    --output       Output file for the analysis report
    --verbose      Verbose output
    --backup       Create backup files before making changes
    
If no directory is provided, it searches for finalized marker files in the standard locations.
"""

import argparse
import xml.etree.ElementTree as ET
import os
import sys
import logging
import gc
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Optional, Any
import re
from pathlib import Path
import shutil
from datetime import datetime

# Import our existing modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from markerdoc import MarkerDoc, MarkerDocCollection
    from bookdoc import BookDoc
except ImportError:
    logging.warning("markerdoc or bookdoc module not available, some features may be limited")
    MarkerDoc = None
    MarkerDocCollection = None
    BookDoc = None


class MarkerAutoCorrector:
    """Auto-corrector for finalized marker files."""
    
    def __init__(self, schema_path: str, fix_mode: bool = False, create_backup: bool = True, book_dir: str = ""):
        """Initialize the auto-corrector.
        
        Args:
            schema_path: Path to the schema definition file
            fix_mode: If True, apply corrections; if False, only report issues
            create_backup: If True, create backup files before making changes
            book_dir: Directory containing book XML files for BookDoc access
        """
        self.schema_path = schema_path
        self.fix_mode = fix_mode
        self.create_backup = create_backup
        self.book_dir = book_dir or ""
        
        # Load schema if available
        self.schema_doc = None
        if MarkerDoc and os.path.exists(schema_path):
            try:
                self.schema_doc = MarkerDoc(schema_path)
            except Exception as e:
                logging.warning(f"Could not load schema: {e}")
        
        # Results storage
        self.issues_found = []
        self.corrections_applied = []
        self.statistics = defaultdict(int)
        
    def analyze_and_correct_file(self, file_path: str) -> Dict[str, Any]:
        """Analyze and optionally correct a single marker file.
        
        Args:
            file_path: Path to the XML marker file
            
        Returns:
            Dictionary containing analysis results and corrections applied
        """
        results = {
            'file': file_path,
            'issues': [],
            'corrections': [],
            'modified': False
        }
        
        try:
            # Parse the XML file
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Process each item
            items = root.findall('.//item')
            for item in items:
                item_results = self._process_item(item, file_path, bookdoc=None)
                results['issues'].extend(item_results['issues'])
                results['corrections'].extend(item_results['corrections'])
                if item_results['modified']:
                    results['modified'] = True
            
            # Save changes if modifications were made
            if results['modified'] and self.fix_mode:
                self._save_corrected_file(tree, file_path)
                
        except Exception as e:
            logging.error(f"Error processing file {file_path}: {e}")
            results['issues'].append({
                'type': 'file_error',
                'severity': 'high',
                'message': f'Failed to process file: {e}'
            })
        
        return results
    
    def _process_item(self, item: ET.Element, file_path: str, bookdoc=None) -> Dict[str, Any]:
        """Process a single item element.
        
        Args:
            item: XML item element
            file_path: Path to the source file
            bookdoc: BookDoc instance for additional context
            
        Returns:
            Dictionary with issues found and corrections applied
        """
        results = {
            'issues': [],
            'corrections': [],
            'modified': False
        }
        
        item_id = item.get('id', 'unknown')
        book_id = item.get('xml', 'unknown')
        
        # Apply correction rules
        self._check_rule_02(item, item_id, file_path, results, book_id, bookdoc)
        #self._check_rule_03(item, item_id, file_path, results, book_id, bookdoc)
        self._check_rule_04(item, item_id, file_path, results, book_id, bookdoc)
        self._check_rule_05(item, item_id, file_path, results, book_id, bookdoc)
        #self._check_rule_06(item, item_id, file_path, results, book_id, bookdoc)
        self._check_rule_10(item, item_id, file_path, results, book_id, bookdoc)
        self._check_rule_11(item, item_id, file_path, results, book_id, bookdoc)
        self._check_rule_12(item, item_id, file_path, results, book_id, bookdoc)
        self._check_rule_13(item, item_id, file_path, results, book_id, bookdoc)

        return results
    
    def _save_corrected_file(self, tree: ET.ElementTree, file_path: str):
        """Save the corrected XML file.
        
        Args:
            tree: Modified XML tree
            file_path: Original file path
        """
        if self.create_backup:
            backup_path = f"{file_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(file_path, backup_path)
            logging.info(f"Created backup: {backup_path}")
        
        # Save the corrected file
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
        logging.info(f"Saved corrected file: {file_path}")
    
    def process_directory(self, directory: str, pattern: str = "*.xml") -> Dict[str, Any]:
        """Process all XML files in a directory, grouped by book ID.
        
        Args:
            directory: Directory path to process
            pattern: File pattern to match
            
        Returns:
            Summary of all processing results
        """
        directory_path = Path(directory)
        xml_files = list(directory_path.glob(pattern))
        
        if not xml_files:
            # Try subdirectories
            xml_files = list(directory_path.glob(f"**/{pattern}"))
        
        logging.info(f"Found {len(xml_files)} XML files to process")
        
        if not xml_files:
            return {
                'files_processed': [],
                'total_issues': 0,
                'total_corrections': 0,
                'files_modified': 0,
                'summary': {}
            }
        
        # Create a collection of all marker documents
        if MarkerDocCollection is None:
            logging.warning("MarkerDocCollection not available, falling back to file-by-file processing")
            return self._process_directory_file_by_file(xml_files)
        
        logging.info("Loading all marker documents...")
        marker_collection = MarkerDocCollection([str(f) for f in xml_files])
        
        logging.info(f"Loaded {marker_collection.get_file_count()} marker documents with {marker_collection.get_total_item_count()} total items")
        
        # Group items by book ID
        items_by_book = marker_collection.get_all_items_grouped_by_book()
        book_ids = sorted(items_by_book.keys())
        
        logging.info(f"Found {len(book_ids)} unique books referenced by items")
        all_results = {
            'files_processed': [],
            'books_processed': [],
            'total_issues': 0,
            'total_corrections': 0,
            'files_modified': 0,
            'summary': {}
        }
        
        # Track which files have been modified
        modified_files = set()
        file_results = {}  # file_path -> results
        
        # Process items book by book
        for book_idx, book_id in enumerate(book_ids):
            book_items = items_by_book[book_id]
            logging.info(f"Processing book {book_idx + 1}/{len(book_ids)}: '{book_id}' with {len(book_items)} items")

            # Load BookDoc if available
            bookdoc = self._get_bookdoc(book_id)
            
            book_results = {
                'book_id': book_id,
                'items_processed': len(book_items),
                'issues': [],
                'corrections': [],
                'files_affected': set()
            }
            
            # Process all items for this book
            for file_path, item_element, marker_doc in book_items:
                # Initialize file results if needed
                if file_path not in file_results:
                    file_results[file_path] = {
                        'file': file_path,
                        'issues': [],
                        'corrections': [],
                        'modified': False
                    }
                
                # Process the item
                item_results = self._process_item(item_element, file_path, bookdoc=bookdoc)
                
                # Accumulate results
                file_results[file_path]['issues'].extend(item_results['issues'])
                file_results[file_path]['corrections'].extend(item_results['corrections'])
                if item_results['modified']:
                    file_results[file_path]['modified'] = True
                    modified_files.add(file_path)
                
                # Track book-level results
                book_results['issues'].extend(item_results['issues'])
                book_results['corrections'].extend(item_results['corrections'])
                book_results['files_affected'].add(file_path)
            
            # Clean up BookDoc to free memory
            del bookdoc
            gc.collect()  # Force garbage collection to free memory
            
            all_results['books_processed'].append(book_results)
            all_results['total_issues'] += len(book_results['issues'])
            all_results['total_corrections'] += len(book_results['corrections'])
        
        # Save modified files
        if self.fix_mode:
            for file_path in modified_files:
                try:
                    marker_doc = marker_collection.marker_docs[file_path]
                    self._save_corrected_file(marker_doc.xml, file_path)
                    logging.info(f"Saved corrections to {file_path}")
                except Exception as e:
                    logging.error(f"Failed to save {file_path}: {e}")
        
        # Convert file results to list for compatibility
        all_results['files_processed'] = list(file_results.values())
        all_results['files_modified'] = len(modified_files)
        
        # Generate summary
        all_results['summary'] = self._generate_summary(all_results)
        
        return all_results
    
    def _process_directory_file_by_file(self, xml_files) -> Dict[str, Any]:
        """Fallback method for file-by-file processing when MarkerDocCollection is not available.
        
        Args:
            xml_files: List of XML file paths
            
        Returns:
            Summary of all processing results
        """
        all_results = {
            'files_processed': [],
            'total_issues': 0,
            'total_corrections': 0,
            'files_modified': 0,
            'summary': {}
        }
        
        for file_path in xml_files:
            logging.info(f"Processing {file_path}")
            file_results = self.analyze_and_correct_file(str(file_path))
            
            all_results['files_processed'].append(file_results)
            all_results['total_issues'] += len(file_results['issues'])
            all_results['total_corrections'] += len(file_results['corrections'])
            if file_results['modified']:
                all_results['files_modified'] += 1
        
        # Generate summary
        all_results['summary'] = self._generate_summary(all_results)
        
        return all_results
    
    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate processing summary.
        
        Args:
            results: Processing results
            
        Returns:
            Summary statistics
        """
        summary = {
            'total_files': len(results['files_processed']),
            'files_with_issues': sum(1 for f in results['files_processed'] if f['issues']),
            'files_corrected': results['files_modified'],
            'total_issues': results['total_issues'],
            'total_corrections': results['total_corrections']
        }
        
        # Add book-level statistics if available
        if 'books_processed' in results:
            summary['total_books'] = len(results['books_processed'])
            summary['books_with_issues'] = sum(1 for b in results['books_processed'] if b['issues'])
            total_items = sum(b['items_processed'] for b in results['books_processed'])
            summary['total_items'] = total_items
        
        # Count issue types
        issue_types = Counter()
        correction_types = Counter()
        
        for file_result in results['files_processed']:
            for issue in file_result['issues']:
                issue_types[issue.get('type', 'unknown')] += 1
            for correction in file_result['corrections']:
                correction_types[correction.get('type', 'unknown')] += 1
        
        summary['issue_types'] = dict(issue_types)
        summary['correction_types'] = dict(correction_types)
        
        return summary
    
    def export_report(self, results: Dict[str, Any], output_path: str):
        """Export processing results to a report file.
        
        Args:
            results: Processing results
            output_path: Output file path
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write header
            #f.write("TEITOK-URL\tFile\tType\tSeverity\tItem ID\tMessage\tAction\tStatus\n")
            f.write("TEITOK-URL\tType\tSeverity\tMessage\tAction\tStatus\n")
            
            # Write results for each file
            for file_result in sorted(results['files_processed'], key=lambda x: x['file']):
                file_path = file_result['file']
                file_base = os.path.basename(file_path)
                
                # Write issues
                for issue in file_result['issues']:
                    teitok_url = f"https://quest.ms.mff.cuni.cz/teitok-dev/teitok/eemc/index.php?action=alignann&annotation=markers&aid={file_base}&annid={issue.get('item_id', '')}"
                    f.write(f"{teitok_url}\t")
                    #f.write(f"{file_path}\t")
                    f.write(f"{issue.get('type', '')}\t")
                    f.write(f"{issue.get('severity', '')}\t")
                    #f.write(f"{issue.get('item_id', '')}\t")
                    f.write(f"{issue.get('message', '')}\t")
                    f.write("ISSUE\t")
                    f.write("FOUND\n")
                
                # Write corrections
                for correction in file_result['corrections']:
                    book_id = correction.get('book_id', '')
                    f.write(f"{file_path}\t")
                    f.write(f"{book_id}\t")
                    f.write(f"{correction.get('type', '')}\t")
                    f.write("INFO\t")
                    f.write(f"{correction.get('item_id', '')}\t")
                    f.write(f"{correction.get('message', '')}\t")
                    f.write("CORRECTION\t")
                    f.write("APPLIED\n")
        
        logging.info(f"Report exported to {output_path}")
    
    def _check_rule_02(self, item: ET.Element, item_id: str, file_path: str, results: Dict[str, Any], book_id: str, bookdoc=None):
        """ Rule 2: Check if 'scope' attribute is set to 'member' and if the member is missing.
        
        When scope='member', the member must be specified.
        
        Args:
            item: XML item element
            item_id: Item identifier
            file_path: Source file path
            results: Results dictionary to update
            book_id: Book identifier
            bookdoc: BookDoc instance for additional context (optional)
        """
        scope_value = item.get('scope', '')

        # Check if scope="member"
        if scope_value != 'member':
            return

        # Check for member attributes
        member = item.get('member', '').strip()

        # member is missing or empty
        if not member:
            results['issues'].append({
                'type': '02_scope_member_missing',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'scope="{scope_value}" but no member specified',
                'attribute': 'member',
                'current_value': '',
                'suggestion': 'Add member attribute'
            })
            
    def _check_rule_03(self, item: ET.Element, item_id: str, file_path: str, results: Dict[str, Any], book_id: str, bookdoc=None):
        """ Rule 3: Check if 'commfuntype' attribute is set to 'interr' and if the use is not 'other'.
        
        When commfuntype='interr', the use is likely set to 'other'. We want to list all occurrences where this is not the case.
        
        Args:
            item: XML item element
            item_id: Item identifier
            file_path: Source file path
            results: Results dictionary to update
            book_id: Book identifier
            bookdoc: BookDoc instance for additional context (optional)
        """
        commfuntype_value = item.get('commfuntype', '')

        # Check if commfuntype="interr"
        if commfuntype_value != 'interr':
            return

        # Check for the use attribute
        use_value = item.get('use', '').strip()

        # use is missing or empty
        if not use_value:
            results['issues'].append({
                'type': '03_commfuntype_interr_missing_use',
                'severity': 'soft',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'commfuntype="{commfuntype_value}" but no use specified',
                'attribute': 'use',
                'current_value': '',
                'suggestion': 'Add use attribute'
            })
        # If use is not 'other', report it
        elif use_value != 'other':
            results['issues'].append({
                'type': '03_commfuntype_interr_wrong_use',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'commfuntype="{commfuntype_value}" but use is "{use_value}" instead of "other"',
                'attribute': 'use',
                'current_value': use_value,
                'suggestion': 'Change use to "other"'
            })

    def _check_rule_04(self, item: ET.Element, item_id: str, file_path: str, results: Dict[str, Any], book_id: str, bookdoc=None):
        """ Rule 4: Check if 'sentpos' attribute is set to 'first' and verify the word position.
        
        When sentpos='first', the referenced Czech word must be:
        (1) very first word in a sentence,
        (2) following a punctuation,
        (3) following a conjunction.
        
        Args:
            item: XML item element
            item_id: Item identifier
            file_path: Source file path
            results: Results dictionary to update
            book_id: Book identifier
            bookdoc: BookDoc instance for additional context (required for this rule)
        """
        sentpos_value = item.get('sentpos', '')
        
        # Check if sentpos="first"
        if sentpos_value != 'first':
            return
        
        # Get the Czech word ID(s) from the 'cs' attribute
        cs_value = item.get('cs', '').strip()
        if not cs_value:
            results['issues'].append({
                'type': '04_sentpos_first_missing_cs',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'sentpos="{sentpos_value}" but no Czech word ID specified in cs attribute',
                'attribute': 'cs',
                'current_value': '',
                'suggestion': 'Add cs attribute with word ID'
            })
            return
        
        # Handle multiple token IDs (space-delimited)
        token_ids = cs_value.split()
        if not token_ids:
            results['issues'].append({
                'type': '04_sentpos_first_empty_cs',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'sentpos="{sentpos_value}" but cs attribute is empty',
                'attribute': 'cs',
                'current_value': cs_value,
                'suggestion': 'Add valid word ID(s) to cs attribute'
            })
            return
        
        # For sentpos="first", we check the position of the first token in the sequence
        first_token_id = token_ids[0]
        
        # If BookDoc is not available, we can't verify the position
        if bookdoc is None:
            results['issues'].append({
                'type': '04_sentpos_first_no_bookdoc',
                'severity': 'soft',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'sentpos="{sentpos_value}" but BookDoc not available for verification',
                'attribute': 'sentpos',
                'current_value': sentpos_value,
                'suggestion': 'Provide book directory to enable verification'
            })
            return
        
        # Get token element from BookDoc (using the first token for position checking)
        try:
            token_elem = bookdoc.get_token_elem(first_token_id)
            if token_elem is None:
                results['issues'].append({
                    'type': '04_sentpos_first_word_not_found',
                    'severity': 'medium',
                    'item_id': item_id,
                    'book_id': book_id,
                    'message': f'sentpos="{sentpos_value}" but Czech word ID "{first_token_id}" (first of: {cs_value}) not found in book',
                    'attribute': 'cs',
                    'current_value': cs_value,
                    'suggestion': 'Check if word ID is correct'
                })
                return
            
            # Get the sentence element containing this token using BookDoc's method
            sentence_elem = bookdoc.get_sentence_elem_by_tokid(first_token_id)
            
            if sentence_elem is None:
                results['issues'].append({
                    'type': '04_sentpos_first_no_sentence',
                    'severity': 'medium',
                    'item_id': item_id,
                    'book_id': book_id,
                    'message': f'sentpos="{sentpos_value}" but could not find sentence for word "{first_token_id}" (first of: {cs_value})',
                    'attribute': 'cs',
                    'current_value': cs_value,
                    'suggestion': 'Check document structure'
                })
                return
            
            # Get all tokens in the sentence
            sentence_tokens = sentence_elem.findall('.//tok')
            if not sentence_tokens:
                results['issues'].append({
                    'type': '04_sentpos_first_empty_sentence',
                    'severity': 'medium',
                    'item_id': item_id,
                    'book_id': book_id,
                    'message': f'sentpos="{sentpos_value}" but sentence contains no tokens',
                    'attribute': 'cs',
                    'current_value': cs_value,
                    'suggestion': 'Check document structure'
                })
                return
            
            # Find the position of our first token in the sentence
            token_position = -1
            for i, tok in enumerate(sentence_tokens):
                if tok.get('id') == first_token_id:
                    token_position = i
                    break
            
            if token_position == -1:
                results['issues'].append({
                    'type': '04_sentpos_first_token_not_in_sentence',
                    'severity': 'medium',
                    'item_id': item_id,
                    'book_id': book_id,
                    'message': f'sentpos="{sentpos_value}" but token "{first_token_id}" (first of: {cs_value}) not found in its sentence',
                    'attribute': 'cs',
                    'current_value': cs_value,
                    'suggestion': 'Check document structure'
                })
                return
            
            # Check if this is valid for sentpos="first"
            is_valid_first = False
            reason = ""

            prev_token = None
            prev_text = ""
            prev_pos = ""
            prev_lemma = ""
            
            # Case 1: Very first word in sentence
            if token_position == 0:
                is_valid_first = True
                reason = "first word in sentence"
            else:
                # Case 2: Following a punctuation
                # Case 3: Following a conjunction
                prev_token = sentence_tokens[token_position - 1]
                prev_text = prev_token.text or ""
                prev_tag = prev_token.get('tag', '')
                prev_pos = prev_tag[0] if prev_tag else ''  # First character of tag is the POS
                prev_lemma = prev_token.get('lemma', '')
                
                # Check if previous token is punctuation
                if prev_pos == 'Z':  # Czech punctuation POS tag is 'Z'
                    is_valid_first = True
                    reason = f"following punctuation '{prev_text}'"
                # Check if previous token is conjunction
                elif prev_pos == 'J':  # Czech conjunction POS tag is 'J'
                    is_valid_first = True
                    reason = f"following conjunction '{prev_text}' ({prev_lemma})"
                ## Additional check for common conjunctions that might be tagged differently
                #elif prev_lemma.lower() in ['a', 'ale', 'nebo', 'ani', 'i', 'však', 'proto', 'tedy', 'takže']:
                #    is_valid_first = True
                #    reason = f"following conjunction '{prev_text}' ({prev_lemma})"

            if not is_valid_first:
                if not first_token_id.endswith('w1'):
                    logging.debug(f'Verifying sentpos="first" for tokens "{cs_value}": first_token="{first_token_id}" position={token_position}, prev_token="{prev_text}" tag={prev_tag} pos={prev_pos} lemma={prev_lemma}, valid={is_valid_first}')
                    logging.debug(prev_token)

                # Get context for better error message
                prev_info = ""
                if prev_token is not None:
                    prev_info = f" (preceded by '{prev_text}' tag={prev_tag} pos={prev_pos} lemma={prev_lemma})"
                
                current_token_text = token_elem.text or ""
                
                results['issues'].append({
                    'type': '04_sentpos_first_invalid_position',
                    'severity': 'medium',
                    'item_id': item_id,
                    'book_id': book_id,
                    'message': f'sentpos="{sentpos_value}" but word "{current_token_text}" (first token of: {cs_value}) is not in valid "first" position{prev_info}',
                    'attribute': 'sentpos',
                    'current_value': sentpos_value,
                    'suggestion': 'Change sentpos or verify word position'
                })
            else:
                # Log successful validation for debugging
                current_token_text = token_elem.text or ""
                logging.debug(f'sentpos="first" validated for tokens "{cs_value}": first_token="{current_token_text}" (ID:{first_token_id}): {reason}')
                
        except Exception as e:
            results['issues'].append({
                'type': '04_sentpos_first_verification_error',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'sentpos="{sentpos_value}" but error during verification: {e}',
                'attribute': 'sentpos',
                'current_value': sentpos_value,
                'suggestion': 'Check BookDoc and word ID'
            })

    def _check_rule_05(self, item: ET.Element, item_id: str, file_path: str, results: Dict[str, Any], book_id: str, bookdoc=None):
        """ Rule 5: Check if 'evidencetype' is defined and is not 'inference' and 'evidence' is defined.

        Specified evidencetype is not 'inference' iff the evidence is specified.

        Args:
            item: XML item element
            item_id: Item identifier
            file_path: Source file path
            results: Results dictionary to update
            book_id: Book identifier
            bookdoc: BookDoc instance for additional context (optional)
        """
        evidencetype_value = item.get('evidencetype', '').strip()
        evidence_value = item.get('evidence', '').strip()

        if evidencetype_value and evidencetype_value != 'inference' and not evidence_value:
            results['issues'].append({
                'type': '05_evidencetype_defined_missing_evidence',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'evidencetype="{evidencetype_value}" but no evidence specified',
                'attribute': 'evidence',
                'current_value': '',
                'suggestion': 'Add evidence attribute'
            })
        elif not evidencetype_value and evidence_value:
            results['issues'].append({
                'type': '05_evidence_without_evidencetype',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'evidence specified but no evidencetype defined',
                'attribute': 'evidencetype',
                'current_value': '',
                'suggestion': 'Add evidencetype attribute'
            })
        elif evidencetype_value == 'inference' and evidence_value:
            results['issues'].append({
                'type': '05_evidencetype_inference_with_evidence',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'evidencetype="{evidencetype_value}" but evidence is specified',
                'attribute': 'evidencetype',
                'current_value': evidencetype_value,
                'suggestion': 'Remove evidencetype attribute'
            })

    def _check_rule_06(self, item: ET.Element, item_id: str, file_path: str, results: Dict[str, Any], book_id: str, bookdoc=None):
        """ Rule 06: List all occurrences of tfpos='ownfocus'.

        When tfpos='ownfocus', it should be verified manually.

        Args:
            item: XML item element
            item_id: Item identifier
            file_path: Source file path
            results: Results dictionary to update
            book_id: Book identifier
            bookdoc: BookDoc instance for additional context (optional)
        """
        tfpos_value = item.get('tfpos', '')

        # Check if tfpos="ownfocus"
        if tfpos_value != 'ownfocus':
            return
        
        # Report the occurrence     
        results['issues'].append({
            'type': '06_tfpos_ownfocus',
            'severity': 'soft',
            'item_id': item_id,
            'book_id': book_id,
            'message': f'tfpos="{tfpos_value}" detected',
            'attribute': 'tfpos',
            'current_value': tfpos_value,
            'suggestion': 'Verify this occurrence manually'
        })

    def _check_rule_10(self, item: ET.Element, item_id: str, file_path: str, results: Dict[str, Any], book_id: str, bookdoc=None):
        """ Rule 10: Check if 'neg' attribute is set to '1' and verify if the finite verb in pred is negated.
        
        When neg='1', the finite verb in the pred attribute must be negated.
        Finite verbs have tags matching "^V[Bip]" and negation is encoded by "N" at the 11th position of the tag.
        
        Args:
            item: XML item element
            item_id: Item identifier
            file_path: Source file path
            results: Results dictionary to update
            book_id: Book identifier
            bookdoc: BookDoc instance for additional context (required for this rule)
        """
        neg_value = item.get('neg', '')
        
        # Check if neg="1"
        if neg_value != '1':
            return
        
        # Get the predicate from the 'pred' attribute
        pred_value = item.get('pred', '').strip()
        if not pred_value:
            results['issues'].append({
                'type': '10_neg_1_missing_pred',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'neg="{neg_value}" but no predicate specified in pred attribute',
                'attribute': 'pred',
                'current_value': '',
                'suggestion': 'Add pred attribute with verb ID'
            })
            return
        
        # If BookDoc is not available, we can't verify the negation
        if bookdoc is None:
            results['issues'].append({
                'type': '10_neg_1_no_bookdoc',
                'severity': 'soft',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'neg="{neg_value}" but BookDoc not available for verification',
                'attribute': 'neg',
                'current_value': neg_value,
                'suggestion': 'Provide book directory to enable verification'
            })
            return
        
        # Handle multiple token IDs (space-delimited) in pred attribute
        pred_token_ids = pred_value.split()
        
        try:
            # Extract finite verbs using the auxiliary method
            finite_verbs_found = self._extract_finite_verbs(pred_token_ids, bookdoc)
            
            # # Check for missing tokens (not handled by auxiliary method)
            # for token_id in pred_token_ids:
            #     token_elem = bookdoc.get_token_elem(token_id)
            #     if token_elem is None:
            #         results['issues'].append({
            #             'type': '10_neg_1_pred_token_not_found',
            #             'severity': 'medium',
            #             'item_id': item_id,
            #             'book_id': book_id,
            #             'message': f'neg="{neg_value}" but predicate token ID "{token_id}" not found in book',
            #             'attribute': 'pred',
            #             'current_value': pred_value,
            #             'suggestion': 'Check if predicate token ID is correct'
            #         })
            
            # Check negation for finite verbs
            negated_finite_verbs = []
            for token_id, token_text, tag in finite_verbs_found:
                # Check if the verb is negated (11th position = index 10)
                if len(tag) > 10 and tag[10] == 'N':
                    negated_finite_verbs.append((token_id, token_text, tag))
            
            # Analyze results
            if not finite_verbs_found:
                results['issues'].append({
                    'type': '10_neg_1_no_finite_verb',
                    'severity': 'medium',
                    'item_id': item_id,
                    'book_id': book_id,
                    'message': f'neg="{neg_value}" but no finite verb found in predicate "{pred_value}"',
                    'attribute': 'pred',
                    'current_value': pred_value,
                    'suggestion': 'Check if predicate contains a finite verb'
                })
            elif not negated_finite_verbs:
                # Found finite verbs but none are negated
                verb_info = ", ".join([f'"{text}" (tag: {tag})' for _, text, tag in finite_verbs_found])
                results['issues'].append({
                    'type': '10_neg_1_finite_verb_not_negated',
                    'severity': 'medium',
                    'item_id': item_id,
                    'book_id': book_id,
                    'message': f'neg="{neg_value}" but finite verb(s) in predicate are not negated: {verb_info}',
                    'attribute': 'neg',
                    'current_value': neg_value,
                    'suggestion': 'Change neg to "0" or verify verb negation'
                })
            else:
                # Found negated finite verbs - this is correct
                verb_info = ", ".join([f'"{text}" (tag: {tag})' for _, text, tag in negated_finite_verbs])
                logging.debug(f'neg="1" validated for item {item_id}: found negated finite verb(s): {verb_info}')
                
        except Exception as e:
            results['issues'].append({
                'type': '10_neg_1_verification_error',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'neg="{neg_value}" but error during verification: {e}',
                'attribute': 'neg',
                'current_value': neg_value,
                'suggestion': 'Check BookDoc and predicate token IDs'
            })
    
    def _check_rule_11(self, item: ET.Element, item_id: str, file_path: str, results: Dict[str, Any], book_id: str, bookdoc=None):
        """ Rule 11: Check if 'use' attribute is set to 'content' and if predicate is missing.

        When use='content', the predicate must be specified.

        Args:
            item: XML item element
            item_id: Item identifier
            file_path: Source file path
            results: Results dictionary to update
            book_id: Book identifier
            bookdoc: BookDoc instance for additional context (optional)
        """
        use_value = item.get('use', '')

        # Check if use="content"
        if use_value != 'content':
            return

        # Check for "pred" attribute
        pred = item.get('pred', '').strip()

        # pred is missing or empty
        if not pred:
            results['issues'].append({
                'type': '11_use_content_missing_pred',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'use="{use_value}" but no predicate specified',
                'attribute': 'pred',
                'current_value': '',
                'suggestion': 'Add pred attribute'
            })

    def _check_rule_12(self, item: ET.Element, item_id: str, file_path: str, results: Dict[str, Any], book_id: str, bookdoc=None):
        """ Rule 12: Check if 'use' attribute is set to 'other' and if communication function attributes are missing.
        
        When use='other', the communication function (the 'commfuntype' attribute) must be specified.
        
        Args:
            item: XML item element
            item_id: Item identifier
            file_path: Source file path
            results: Results dictionary to update
            book_id: Book identifier
            bookdoc: BookDoc instance for additional context (optional)
        """
        use_value = item.get('use', '')
        
        # Check if use="other"
        if use_value != 'other':
            return

        # Check for communication function attributes
        commfuntype = item.get('commfuntype', '').strip()
        commfunsubtype = item.get('commfunsubtype', '').strip()
        
        # commfuntype is missing or empty
        if not commfuntype:
            results['issues'].append({
                'type': '12_use_other_missing_commfuntype',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'use="{use_value}" but no communication function (commfuntype/commfunsubtype) specified',
                'attribute': 'commfuntype',
                'current_value': '',
                'suggestion': 'Add commfuntype and commfunsubtype attribute'
            })
        elif not commfunsubtype:
            results['issues'].append({
                'type': '12_use_other_missing_commfunsubtype',
                'severity': 'medium',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'use="{use_value}" but no communication function (commfuntype/commfunsubtype) specified',
                'attribute': 'commfuntype',
                'current_value': '',
                'suggestion': 'Add commfuntype and commfunsubtype attribute'
            })
            # If in fix mode, we could add a default value, but this requires manual review
            # For now, just report the issue
            

#        # Auto-correction: remove empty commfuntype attribute (SO FAR NOT IMPLEMENTED)
#        if self.fix_mode:
#            del item.attrib['commfuntype']
#            results['corrections'].append({
#                'type': 'removed_empty_commfuntype',
#                'item_id': item_id,
#                'message': f'Removed empty commfuntype attribute for use="{use_value}"',
#                'attribute': 'commfuntype'
#            })
#            results['modified'] = True

    def _check_rule_13(self, item: ET.Element, item_id: str, file_path: str, results: Dict[str, Any], book_id: str, bookdoc=None):
        """ Rule 13: Check if scope="sent" has a filled pred attribute containing a finite verb.
        
        If the scope attribute is set to "sent", the pred attribute must:
        1. Be present and non-empty
        2. Contain at least one token ID that references a finite verb
        
        Args:
            item: XML item element
            item_id: Item identifier
            file_path: Source file path
            results: Results dictionary to update
            book_id: Book identifier
            bookdoc: BookDoc instance for token lookup
        """
        scope_value = item.get('scope', '').strip()
        
        # Only check items with scope="sent"
        if scope_value != 'sent':
            return
        
        pred_value = item.get('pred', '').strip()
        
        # Check if pred is missing or empty
        if not pred_value:
            results['issues'].append({
                'type': '13_scope_sent_missing_pred',
                'severity': 'high',
                'item_id': item_id,
                'book_id': book_id,
                'message': f'scope="sent" but pred attribute is missing or empty',
                'attribute': 'pred',
                'current_value': pred_value,
                'suggestion': 'Add pred attribute with finite verb token IDs'
            })
            return
        
        # Check if pred contains at least one finite verb
        if bookdoc is not None:
            # Parse token IDs from pred
            token_ids = [token_id.strip() for token_id in pred_value.split() if token_id.strip()]
            
            if not token_ids:
                results['issues'].append({
                    'type': '13_scope_sent_pred_empty_tokens',
                    'severity': 'high',
                    'item_id': item_id,
                    'book_id': book_id,
                    'message': f'scope="sent" but pred contains no valid token IDs',
                    'attribute': 'pred',
                    'current_value': pred_value,
                    'suggestion': 'Add finite verb token IDs to pred attribute'
                })
                return
            
            # Extract finite verbs from the pred tokens
            finite_verbs = self._extract_finite_verbs(token_ids, bookdoc)
            
            if not finite_verbs:
                results['issues'].append({
                    'type': '13_scope_sent_pred_no_finite_verb',
                    'severity': 'high',
                    'item_id': item_id,
                    'book_id': book_id,
                    'message': f'scope="sent" but pred does not contain any finite verbs (tokens: {", ".join(token_ids)})',
                    'attribute': 'pred',
                    'current_value': pred_value,
                    'suggestion': 'Ensure pred contains at least one finite verb token ID'
                })
        else:
            # If no bookdoc available, we can only check that pred is not empty
            # (which we already did above)
            logging.debug(f"Rule 13: No BookDoc available for detailed validation of item {item_id}")


    def _extract_finite_verbs(self, token_ids: List[str], bookdoc) -> List[Tuple[str, str, str]]:
        """Extract finite verbs from a list of token IDs.
        
        Args:
            token_ids: List of token IDs to examine
            bookdoc: BookDoc instance for token lookup
            
        Returns:
            List of (token_id, token_text, tag) tuples for finite verbs found
        """
        finite_verbs_found = []
        
        if bookdoc is None:
            return finite_verbs_found
        
        for token_id in token_ids:
            token_elem = bookdoc.get_token_elem(token_id)
            if token_elem is None:
                continue
            
            # Get the tag attribute
            tag = token_elem.get('tag', '')
            if not tag:
                continue
            
            # Check if this is a finite verb (tag matches "^V[Bip]")
            if re.match(r'^V[Bip]', tag):
                token_text = token_elem.text or ""
                finite_verbs_found.append((token_id, token_text, tag))
        
        return finite_verbs_found

    def _get_bookdoc(self, book_id: str, lang: str = "cs"):
        """Get or load a BookDoc instance for the given book ID.
        
        Args:
            book_id: Book identifier
            lang: Language code (default: "cs")
            
        Returns:
            BookDoc instance or None if not available/failed to load
        """
        if BookDoc is None:
            return None
        
        # Create new instance each time to avoid memory issues
        try:
            bookdoc = BookDoc(book_id, lang=lang, bookdir=self.book_dir)
            logging.debug(f"Loaded BookDoc for {book_id} ({lang})")
            return bookdoc
        except Exception as e:
            logging.warning(f"Failed to load BookDoc for {book_id} ({lang}): {e}")
            return None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Auto-correct finalized XML marker files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze files and report issues (no changes made)
  python autocorrect_markers.py /path/to/markers

  # Apply automatic corrections
  python autocorrect_markers.py /path/to/markers --fix

  # Process with verbose output and custom report file
  python autocorrect_markers.py /path/to/markers --fix --verbose --output my_report.tsv
        """
    )
    
    parser.add_argument('directory', 
                       help='Directory containing XML marker files')
    parser.add_argument('--fix', action='store_true', 
                       help='Apply automatic corrections (default: only report issues)')
    parser.add_argument('--output', '-o', default='marker_autocorrect_report.tsv', 
                       help='Output file for the processing report')
    parser.add_argument('--schema', default='teitok/config/markers_def.xml',
                       help='Path to schema definition file')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Verbose output')
    parser.add_argument('--pattern', default='*.xml', 
                       help='File pattern to match (default: *.xml)')
    parser.add_argument('--no-backup', action='store_true', 
                       help='Do not create backup files when fixing')
    parser.add_argument('--book-dir', default='teitok/01.csen_data', 
                       help='Directory containing book XML files for BookDoc access')
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level, 
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Find directory to process
    directory = args.directory
    if not os.path.exists(directory):
        print(f"Directory not found: {directory}", file=sys.stderr)
        sys.exit(1)
    
    # Check schema file
    if not os.path.exists(args.schema):
        logging.warning(f"Schema file not found: {args.schema}")
    
    # Initialize corrector
    corrector = MarkerAutoCorrector(
        schema_path=args.schema,
        fix_mode=args.fix,
        create_backup=not args.no_backup,
        book_dir=args.book_dir
    )
    
    # Process directory
    print(f"Processing directory: {directory}")
    results = corrector.process_directory(directory, args.pattern)
    
    # Use results directly
    all_results = results
    
    # Print summary
    print(f"\nProcessing Summary:")
    print(f"Files processed: {all_results['summary']['total_files']}")
    print(f"Files with issues: {all_results['summary']['files_with_issues']}")
    
    # Show book-level statistics if available
    if 'total_books' in all_results['summary']:
        print(f"Books processed: {all_results['summary']['total_books']}")
        print(f"Books with issues: {all_results['summary']['books_with_issues']}")
        print(f"Total items processed: {all_results['summary']['total_items']}")
    
    if args.fix:
        print(f"Files corrected: {all_results['summary']['files_corrected']}")
        print(f"Total corrections applied: {all_results['summary']['total_corrections']}")
    else:
        print(f"Total issues found: {all_results['summary']['total_issues']}")
        print("Use --fix to apply automatic corrections")
    
    # Show issue breakdown
    if all_results['summary']['issue_types']:
        print(f"\nIssue breakdown:")
        for issue_type in sorted(all_results['summary']['issue_types'].keys()):
            count = all_results['summary']['issue_types'][issue_type]
            print(f"  {issue_type}: {count}")
    
    # Show correction breakdown
    if args.fix and all_results['summary']['correction_types']:
        print(f"\nCorrection breakdown:")
        for correction_type, count in all_results['summary']['correction_types'].items():
            print(f"  {correction_type}: {count}")
    
    # Export report
    corrector.export_report(all_results, args.output)
    print(f"\nDetailed report exported to: {args.output}")


if __name__ == '__main__':
    main()

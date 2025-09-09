#!/usr/bin/env python3
"""
Script to export marker annotation files to JSON format for experiments.
Uses key names instead of display names and includes surrounding context for tokens.
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from markerdoc import MarkerDoc, MarkerDocDef
from bookdoc import BookDoc


def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


def extract_expression_and_language(filename):
    """
    Extract expression and language from marker filename.
    
    Expected patterns:
    - markers_gold-cs-asi.xml -> ("asi", "cs")
    - markers_gold-en-urcite.xml -> ("urcite", "en")
    
    Args:
        filename: Name of the marker file
    
    Returns:
        Tuple (expression, language) or (None, None) if pattern not found
    """
    # Remove .xml extension
    base_name = filename.replace('.xml', '')
    
    # Pattern: markers_gold-{lang}-{expression}
    match = re.match(r'markers(?:_gold)?-([a-z]{2})-(.+)', base_name)
    if match:
        language, expression = match.groups()
        return expression, language
    
    # If no pattern matches, try to extract from the end
    # Look for -cs- or -en- pattern
    lang_match = re.search(r'-([a-z]{2})-([^-]+)$', base_name)
    if lang_match:
        language, expression = lang_match.groups()
        return expression, language
    
    logging.warning(f"Could not extract expression and language from filename: {filename}")
    return None, None


def get_token_context(bookdoc, token_ids_str, context_size=50, context_scope="document"):
    """
    Get surrounding context for given token IDs.
    
    Args:
        bookdoc: BookDoc instance
        token_ids_str: Space-separated token IDs (e.g., "book-01:s1:w5 book-01:s1:w6")
        context_size: Number of tokens before and after to include
        context_scope: Scope limitation - "sentence", "paragraph", or "none"
        
    Returns:
        String containing the context with tokens separated by spaces,
        or None if tokens not found
    """
    if not bookdoc or not token_ids_str.strip():
        return None
        
    # Parse token IDs
    token_ids = token_ids_str.strip().split()
    if not token_ids:
        return None
    
    try:
        # Get the sentence containing the first token
        first_token_id = token_ids[0]
        sentence_elem = bookdoc.get_sentence_elem_by_tokid(first_token_id)
        
        if sentence_elem is None:
            logging.warning(f"Could not find sentence for token {first_token_id}")
            return None
        
        # Determine the scope for context extraction
        if context_scope == "sentence":
            # Limited to current sentence
            scope_tokens = sentence_elem.findall('.//tok')
        elif context_scope == "paragraph":
            # Limited to current paragraph
            paragraph_elem = sentence_elem.getparent()
            if paragraph_elem is not None and paragraph_elem.tag == 'p':
                scope_tokens = paragraph_elem.findall('.//tok')
            else:
                # Fallback to sentence if no paragraph parent found
                logging.warning(f"No paragraph parent found for sentence {sentence_elem.attrib.get('id', '')}, using sentence scope")
                scope_tokens = sentence_elem.findall('.//tok')
        else:
            # No limitation - use entire document
            scope_tokens = bookdoc.xml.findall('.//tok')
        
        if not scope_tokens:
            return None
        
        # Find positions of target tokens in the scope
        scope_token_ids = [tok.attrib['id'] for tok in scope_tokens]
        target_positions = []
        
        for token_id in token_ids:
            try:
                pos = scope_token_ids.index(token_id)
                target_positions.append(pos)
            except ValueError:
                logging.warning(f"Token {token_id} not found in {context_scope} scope")
                continue
        
        if not target_positions:
            return None
        
        # Determine context range
        min_pos = min(target_positions)
        max_pos = max(target_positions)
        
        start_pos = max(0, min_pos - context_size)
        end_pos = min(len(scope_tokens), max_pos + 1 + context_size)
        
        # Extract context tokens
        context_tokens = []
        for i in range(start_pos, end_pos):
            token_text = scope_tokens[i].text or ""
            context_tokens.append(token_text)
        
        return " ".join(context_tokens)
        
    except Exception as e:
        logging.warning(f"Error getting context for tokens {token_ids_str}: {e}")
        return None


def process_marker_file(file_path, def_doc, expression, language):
    """
    Process a single marker file and return rows for JSON export.
    
    Args:
        file_path: Path to the marker XML file
        def_doc: MarkerDocDef instance for schema information
        expression: Expression extracted from filename
        language: Language extracted from filename
    
    Returns:
        List of dictionaries representing rows with key names as keys
    """
    logging.info(f"Processing marker file: {file_path}")
    
    try:
        marker_doc = MarkerDoc(file_path)
    except Exception as e:
        logging.error(f"Failed to parse {file_path}: {e}")
        return []
    
    rows = []
    
    for item_elem in marker_doc:
        # Construct TEITOK URL
        file_base = os.path.basename(file_path)
        item_id = item_elem.attrib.get("id", "")
        teitok_url = f"https://quest.ms.mff.cuni.cz/teitok-dev/teitok/eemc/index.php?action=alignann&annotation=markers&aid={file_base}&annid={item_id}"
        
        row = {
            'url': teitok_url,
            'expression': expression or '',
            'language': language or ''
        }
        
        # Add all attributes from the item element using key names (not display names)
        for attr_name, attr_value in item_elem.attrib.items():
            row[attr_name] = attr_value
        
        # Initialize context fields as None - will be filled later
        row['cs_ctx'] = None
        row['en_ctx'] = None
        
        rows.append(row)
    
    logging.info(f"Extracted {len(rows)} items from {file_path}")
    return rows


def add_contexts_to_data(all_rows, book_dir, context_size, context_scope):
    """
    Add context information to all rows, processing book by book for efficiency.
    
    Args:
        all_rows: List of dictionaries representing annotation items
        book_dir: Directory containing book XML files
        context_size: Number of context tokens to include
        context_scope: Scope limitation - "sentence", "paragraph", or "none"
    """
    # Group items by book ID
    items_by_book = {}
    for row in all_rows:
        book_id = row.get('xml', '')
        if book_id:
            if book_id not in items_by_book:
                items_by_book[book_id] = []
            items_by_book[book_id].append(row)
    
    logging.info(f"Processing contexts for {len(items_by_book)} books")
    
    # Process each book
    for book_idx, (book_id, book_items) in enumerate(items_by_book.items(), 1):
        logging.info(f"[{book_idx}/{len(items_by_book)}] Loading contexts for book {book_id} ({len(book_items)} items)")
        
        # Load Czech BookDoc for this book
        cs_bookdoc = None
        try:
            cs_bookdoc = BookDoc(book_id, lang="cs", bookdir=book_dir)
        except Exception as e:
            logging.warning(f"Could not load Czech BookDoc for {book_id}: {e}")
        
        # Load English BookDoc for this book
        en_bookdoc = None
        try:
            en_bookdoc = BookDoc(book_id, lang="en", bookdir=book_dir)
        except Exception as e:
            logging.warning(f"Could not load English BookDoc for {book_id}: {e}")
        
        # Process all items for this book
        for row in book_items:
            # Get context for Czech tokens
            cs_tokens = row.get('cs', '').strip()
            if cs_tokens and cs_bookdoc:
                cs_context = get_token_context(cs_bookdoc, cs_tokens, context_size, context_scope)
                row['cs_ctx'] = cs_context
            
            # Get context for English tokens
            en_tokens = row.get('en', '').strip()
            if en_tokens and en_bookdoc:
                en_context = get_token_context(en_bookdoc, en_tokens, context_size, context_scope)
                row['en_ctx'] = en_context


def export_to_json(marker_files, output_file, schema_file, book_dir, context_size, context_scope):
    """
    Export marker files to JSON format.
    
    Args:
        marker_files: List of marker file paths
        output_file: Path to output JSON file
        schema_file: Path to schema definition XML file
        book_dir: Directory containing book XML files
        context_size: Number of context tokens to include
        context_scope: Scope limitation - "sentence", "paragraph", or "none"
    """
    logging.info(f"Exporting {len(marker_files)} marker files to JSON")
    logging.info(f"Using schema definition: {schema_file}")
    logging.info(f"Using book directory: {book_dir}")
    logging.info(f"Context size: {context_size} tokens")
    logging.info(f"Context scope: {context_scope}")
    logging.info(f"Output will be saved to: {output_file}")
    
    # Load the schema definition
    def_doc = MarkerDocDef(schema_file)
    
    all_rows = []
    
    # Phase 1: Process each marker file to collect all data (without contexts first)
    logging.info("Phase 1: Loading marker data without contexts")
    for file_path in marker_files:
        filename = os.path.basename(file_path)
        expression, language = extract_expression_and_language(filename)
        
        if expression is None or language is None:
            logging.warning(f"Skipping {file_path} - could not determine expression/language")
            continue
        
        rows = process_marker_file(file_path, def_doc, expression, language)
        all_rows.extend(rows)
    
    logging.info(f"Phase 1 complete: Loaded {len(all_rows)} items from {len(marker_files)} files")
    
    # Phase 2: Add context information, processing book by book
    logging.info("Phase 2: Adding context information")
    add_contexts_to_data(all_rows, book_dir, context_size, context_scope)
    logging.info("Phase 2 complete: Context information added")
    
    # Create output structure
    output_data = {
        'metadata': {
            'total_items': len(all_rows),
            'files_processed': len(marker_files),
            'context_size': context_size,
            'context_scope': context_scope,
            'book_directory': book_dir,
            'schema_file': schema_file
        },
        'items': all_rows
    }
    
    # Write JSON file
    logging.info(f"Writing {len(all_rows)} total items to JSON file")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    logging.info(f"JSON export completed successfully: {output_file}")


def validate_marker_files(file_paths):
    """
    Validate that marker files exist.
    
    Args:
        file_paths: List of marker file paths
    
    Returns:
        List of valid marker file paths
    """
    valid_files = []
    
    for file_path in file_paths:
        if os.path.exists(file_path):
            valid_files.append(file_path)
        else:
            logging.error(f"File not found: {file_path}")
    
    logging.info(f"Validated {len(valid_files)} out of {len(file_paths)} marker files")
    return valid_files


def main():
    """Main function to handle command line arguments and process files"""
    parser = argparse.ArgumentParser(
        description="Export marker annotation files to JSON format for experiments"
    )
    parser.add_argument(
        "input_files",
        nargs='+',
        help="List of marker XML files to process"
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output JSON file path"
    )
    parser.add_argument(
        "-s", "--schema",
        default="teitok/config/markers_def.xml",
        help="Schema definition file (default: teitok/config/markers_def.xml)"
    )
    parser.add_argument(
        "-b", "--book-dir",
        default="teitok/01.csen_data",
        help="Directory containing book XML files (default: teitok/01.csen_data)"
    )
    parser.add_argument(
        "-c", "--context-size",
        type=int,
        default=50,
        help="Number of tokens before and after target tokens to include as context (default: 50)"
    )
    parser.add_argument(
        "--context-scope",
        choices=["sentence", "paragraph", "document"],
        default="document",
        help="Scope limitation for context extraction: 'sentence' (current sentence only), 'paragraph' (current paragraph), 'document' (entire document). Default: entire document"
    )
    
    args = parser.parse_args()
    
    setup_logging()
    
    # Validate schema file exists
    if not os.path.exists(args.schema):
        logging.error(f"Schema file not found: {args.schema}")
        sys.exit(1)
    
    # Validate book directory exists
    if not os.path.exists(args.book_dir):
        logging.error(f"Book directory not found: {args.book_dir}")
        sys.exit(1)
    
    # Validate marker files
    marker_files = validate_marker_files(args.input_files)
    
    if not marker_files:
        logging.error("No valid marker files found")
        sys.exit(1)
    
    # Ensure output directory exists
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    try:
        export_to_json(marker_files, args.output, args.schema, args.book_dir, args.context_size, args.context_scope)
        logging.info("Export completed successfully")
    except Exception as e:
        logging.error(f"Error during export: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

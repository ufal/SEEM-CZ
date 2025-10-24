#!/usr/bin/env python3
"""
Script to count occurrences of expressions in books from search result files.

Each input file should contain lines with <tok> elements that have:
- lemma attribute: the expression (will be lowercased) - used as identifier
- sword attribute: surface form (used only for "podle všeho" exception)
- id attribute: contains the book ID (format: cs:book_name:...)

Output: JSON structure with book -> expression -> count mapping, along with
additional book information (source language, total word count) extracted from
the XML files in data/ic16core_csen directory.
"""

import re
import json
import argparse
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set, Optional, Tuple


def extract_book_id(id_attr: str) -> str:
    """
    Extract book ID from the id attribute.
    Format: cs:book_name:rest... -> book_name
    """
    parts = id_attr.split(':')
    if len(parts) >= 2:
        return parts[1]  # book_name part
    return id_attr  # fallback to full id if format unexpected


def extract_expression_and_book(line: str) -> tuple[str, str] | None:
    """
    Extract expression (concatenated lowercased lemma attributes) and book ID from a line.
    Multiple <tok> elements can be separated by tabs on the same line.
    Special case: "podle všeho" uses sword instead of lemma.
    Returns (expression, book_id) or None if parsing fails.
    """
    # Find all <tok> elements in the line (they can be separated by tabs)
    # Extract sword, lemma, and id from each token
    # Make sure to match " lemma=" to avoid matching "sublemma"
    tok_matches = re.findall(r'<tok\s+[^>]*sword="([^"]*)"[^>]* lemma="([^"]*)"[^>]*id="([^"]*)"[^>]*>', line)
    
    if not tok_matches:
        return None
    
    # Extract all lemma/sword values and book IDs
    words = []
    book_ids = set()
    
    for sword, lemma, id_attr in tok_matches:
        words.append(sword.lower())  # Collect sword values for special case check
        book_id = extract_book_id(id_attr)
        book_ids.add(book_id)
    
    # All tokens should be from the same book
    if len(book_ids) != 1:
        print(f"Warning: Multiple book IDs found in line: {book_ids}", file=sys.stderr)
        return None
    
    # Check for special case "podle všeho"
    sword_expression = " ".join(words)
    if sword_expression == "podle všeho":
        expression = sword_expression
    else:
        # Use lemmas for normal cases
        lemmas = [lemma.lower() for sword, lemma, id_attr in tok_matches]
        expression = " ".join(lemmas)
    
    book_id = book_ids.pop()
    
    return expression, book_id


def process_file(file_path: Path) -> Tuple[Dict[str, Dict[str, int]], Set[str]]:
    """
    Process a single search result file.
    Returns tuple: ({book_id: {expression: count}}, {book_ids})
    """
    print(f"Processing {file_path}...", file=sys.stderr)
    
    book_expr_counts = defaultdict(lambda: defaultdict(int))
    book_ids = set()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                    
                result = extract_expression_and_book(line)
                if result:
                    expression, book_id = result
                    book_expr_counts[book_id][expression] += 1
                    book_ids.add(book_id)
                else:
                    print(f"Warning: Could not parse line {line_num} in {file_path}", file=sys.stderr)
    
    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return {}, set()
    
    # Convert defaultdicts to regular dicts for JSON serialization
    return {book_id: dict(expr_counts) for book_id, expr_counts in book_expr_counts.items()}, book_ids


def merge_results(results: list[Dict[str, Dict[str, int]]]) -> Dict[str, Dict[str, int]]:
    """
    Merge results from multiple files.
    Returns dict: {book_id: {expression: count}}
    """
    merged = defaultdict(lambda: defaultdict(int))
    
    for result in results:
        for book_id, expr_counts in result.items():
            for expression, count in expr_counts.items():
                merged[book_id][expression] += count
    
    # Convert defaultdicts to regular dicts
    return {book_id: dict(expr_counts) for book_id, expr_counts in merged.items()}


def extract_book_info(book_id: str, book_dir: Path) -> Dict[str, any]:
    """
    Extract additional book information from XML files.
    Returns dict with srclang, author, title, english_title, and word_count.
    Statistics (srclang, author, title, word_count) come from Czech version,
    english_title comes from English version.
    """
    # Priority: Czech file for main statistics
    cs_file = book_dir / f"{book_id}.cs-00.tag.xml"
    en_file = book_dir / f"{book_id}.en-00.tag.xml"
    
    # Extract main info from Czech file
    main_info = {"srclang": None, "author": None, "title": None, "english_title": None, "word_count": 0}
    
    if cs_file.exists():
        try:
            main_info = parse_book_xml(cs_file)
            main_info["english_title"] = None  # Initialize english_title
        except Exception as e:
            print(f"Warning: Error parsing {cs_file}: {e}", file=sys.stderr)
    elif en_file.exists():
        try:
            main_info = parse_book_xml(en_file)
            main_info["english_title"] = None  # Initialize english_title
        except Exception as e:
            print(f"Warning: Error parsing {en_file}: {e}", file=sys.stderr)
    
    # Extract English title from English file if available
    if en_file.exists() and main_info["srclang"] is not None:
        try:
            en_info = parse_book_xml(en_file, title_only=True)
            main_info["english_title"] = en_info.get("title")
        except Exception as e:
            print(f"Warning: Error extracting English title from {en_file}: {e}", file=sys.stderr)
    
    if main_info["srclang"] is None:
        print(f"Warning: No XML file found for book {book_id}", file=sys.stderr)
    
    return main_info


def parse_book_xml(xml_file: Path, title_only: bool = False) -> Dict[str, any]:
    """
    Parse XML file to extract srclang, author, title, and count <w> tags.
    Uses streaming approach to handle large files efficiently.
    
    Args:
        xml_file: Path to the XML file to parse
        title_only: If True, only extract title (for English version)
    """
    srclang = None
    author = None
    title = None
    word_count = 0
    
    print(f"Parsing {xml_file.name}{'(title only)' if title_only else ''}...", file=sys.stderr)
    
    with open(xml_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            
            # Extract information from <text> element (should be early in file)
            if line.startswith('<text '):
                if title_only:
                    # Only extract title for English version
                    if title is None:
                        match = re.search(r'title="([^"]*)"', line)
                        if match:
                            title = match.group(1)
                            break  # We only need the title, so we can stop here
                else:
                    # Extract all metadata for Czech version
                    if srclang is None:
                        match = re.search(r'srclang="([^"]*)"', line)
                        if match:
                            srclang = match.group(1)
                    
                    if author is None:
                        match = re.search(r'author="([^"]*)"', line)
                        if match:
                            author = match.group(1)
                    
                    if title is None:
                        match = re.search(r'title="([^"]*)"', line)
                        if match:
                            title = match.group(1)
            
            # Count <w> tags (only if not title_only mode)
            if not title_only:
                word_count += line.count('<w ')
                
                # Optimization: if we found all metadata and processed many lines, 
                # we can continue just counting words without regex matching
                if srclang and author and title and line_num > 100:
                    # Continue reading rest of file just for word counting
                    break
        
        # Continue counting words in the rest of the file (only if not title_only mode)
        if not title_only:
            for line in f:
                word_count += line.count('<w ')
    
    return {
        "srclang": srclang, 
        "author": author, 
        "title": title, 
        "word_count": word_count
    }


def get_annotated_book_ids(annot_dir: Path) -> Set[str]:
    """
    Extract book IDs from annotation files in the annotation directory.
    Returns set of book IDs that have annotations.
    """
    annotated_books = set()
    
    if not annot_dir.exists():
        print(f"Warning: Annotation directory {annot_dir} does not exist", file=sys.stderr)
        return annotated_books
    
    print(f"Reading annotation files from {annot_dir}...", file=sys.stderr)
    
    # Look for XML files in the annotation directory
    for xml_file in annot_dir.glob("*.xml"):
        try:
            with open(xml_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Look for book IDs in <item> elements with xml attribute
                    if line.startswith('<item ') and 'xml="' in line:
                        match = re.search(r'xml="([^"]*)"', line)
                        if match:
                            book_id = match.group(1)
                            annotated_books.add(book_id)
                    
                    # Also check for book IDs in cs and en attributes (they contain full paths)
                    cs_matches = re.findall(r'cs="cs:([^:]+):', line)
                    en_matches = re.findall(r'en="en:([^:]+):', line)
                    annotated_books.update(cs_matches)
                    annotated_books.update(en_matches)
                        
        except Exception as e:
            print(f"Warning: Error reading annotation file {xml_file}: {e}", file=sys.stderr)
            continue
    
    print(f"Found {len(annotated_books)} unique book IDs in annotation files", file=sys.stderr)
    return annotated_books


def main():
    parser = argparse.ArgumentParser(
        description="Count occurrences of expressions in books from search result files"
    )
    parser.add_argument(
        'files', 
        nargs='+', 
        help='Search result files to process'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output JSON file (default: stdout)'
    )
    parser.add_argument(
        '--pretty',
        action='store_true',
        help='Pretty-print JSON output'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Print summary statistics to stderr'
    )
    parser.add_argument(
        '--book-dir',
        type=Path,
        default=Path('data/ic16core_csen'),
        help='Directory containing book XML files (default: data/ic16core_csen)'
    )
    parser.add_argument(
        '--annot-dir',
        type=Path,
        default='teitok/markers/finished',
        help='Directory containing annotation files. If provided, only books with annotations will be included in the output'
    )
    
    args = parser.parse_args()
    
    # Check if book directory exists
    if not args.book_dir.exists():
        print(f"Warning: Book directory {args.book_dir} does not exist. Book info will not be extracted.", file=sys.stderr)
        extract_book_info_flag = False
    else:
        extract_book_info_flag = True
    
    # Process all files
    results = []
    all_book_ids = set()
    
    for file_path_str in args.files:
        file_path = Path(file_path_str)
        if not file_path.exists():
            print(f"Error: File {file_path} does not exist", file=sys.stderr)
            continue
        
        result, book_ids = process_file(file_path)
        if result:
            results.append(result)
            all_book_ids.update(book_ids)
    
    if not results:
        print("Error: No valid results to process", file=sys.stderr)
        sys.exit(1)
    
    # Merge results from all files
    expression_counts = merge_results(results)
    
    # Extract book information
    book_info = {}
    if extract_book_info_flag:
        print(f"Extracting book information for {len(all_book_ids)} books...", file=sys.stderr)
        for book_id in all_book_ids:
            book_info[book_id] = extract_book_info(book_id, args.book_dir)
    
    # If annotation directory is provided, filter books by annotations
    if args.annot_dir:
        annotated_book_ids = get_annotated_book_ids(args.annot_dir)
        # Filter expression_counts to only include annotated books
        filtered_expression_counts = {book_id: counts for book_id, counts in expression_counts.items() 
                                    if book_id in annotated_book_ids}
        expression_counts = filtered_expression_counts
        all_book_ids.intersection_update(annotated_book_ids)
        print(f"Filtered to {len(expression_counts)} books that have annotations", file=sys.stderr)
    
    # Create final result structure
    unique_expressions = sorted(set(expr for expr_counts in expression_counts.values() for expr in expr_counts.keys()))
    final_result = {
        "books": {},
        "metadata": {
            "total_books": len(expression_counts),
            "total_expressions": unique_expressions,
            "total_expressions_count": len(unique_expressions),
            "total_occurrences": sum(sum(expr_counts.values()) for expr_counts in expression_counts.values())
        }
    }
    
    # Build book entries
    for book_id in expression_counts:
        book_entry = {
            "expressions": expression_counts[book_id]
        }
        
        if book_id in book_info:
            book_entry.update(book_info[book_id])
        
        final_result["books"][book_id] = book_entry
    
    # Print summary if requested
    if args.summary:
        meta = final_result["metadata"]
        print(f"Summary:", file=sys.stderr)
        print(f"  Books: {meta['total_books']}", file=sys.stderr)
        print(f"  Unique expressions: {meta['total_expressions_count']}", file=sys.stderr)
        # list unique expressions sorted alphabetically
        for expr in meta['total_expressions']:
            print(f"    {expr}", file=sys.stderr)
        print(f"  Total occurrences: {meta['total_occurrences']}", file=sys.stderr)
        
        if extract_book_info_flag:
            srclang_counts = defaultdict(int)
            total_words = 0
            for book_id, info in book_info.items():
                if info["srclang"]:
                    srclang_counts[info["srclang"]] += 1
                total_words += info["word_count"]
            
            print(f"  Source languages: {dict(srclang_counts)}", file=sys.stderr)
            print(f"  Total words in corpus: {total_words:,}", file=sys.stderr)
    
    # Output JSON
    json_kwargs = {'indent': 2, 'ensure_ascii': False} if args.pretty else {'ensure_ascii': False}
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(final_result, f, **json_kwargs)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        json.dump(final_result, sys.stdout, **json_kwargs)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Script to rename commfunsubtype values in marker files using a rename table.

This script reads a rename table (TSV file) and updates commfunsubtype attributes
in all marker XML files. The rename table should have the format:
- Column 1: Frequency (ignored)
- Column 2: Old value
- Column 3: New value (if empty, keep old value)
- Remaining columns: Comments (ignored)

Usage:
    python rename_commfunsubtype.py rename_table.tsv [marker_files...]
    
If no marker files are specified, it will find all XML files in teitok/markers/
"""

import argparse
import csv
import logging
import os
import sys
import glob
from pathlib import Path
from datetime import datetime
import shutil

# Import our existing modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from markerdoc import MarkerDoc
except ImportError:
    print("Error: markerdoc module not found. Please ensure markerdoc.py is in the same directory.")
    sys.exit(1)


def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def load_rename_table(tsv_file):
    """Load the rename table from TSV file.
    
    Args:
        tsv_file: Path to TSV file with rename mappings
        
    Returns:
        Dict mapping old_value -> new_value (or None if new value is empty)
    """
    rename_map = {}
    
    with open(tsv_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        
        for line_num, row in enumerate(reader, 1):
            if len(row) < 2:
                continue
                
            # Skip empty or comment lines
            if not row[0].strip() or row[0].strip().startswith('#'):
                continue
                
            try:
                # Column 1: frequency (ignored)
                # Column 2: old value
                # Column 3: new value (optional)
                old_value = row[1].strip() if len(row) > 1 else ""
                new_value = row[2].strip() if len(row) > 2 else ""
                
                if not old_value:
                    continue
                    
                # If new value is empty, we keep the old value (no change)
                if new_value:
                    rename_map[old_value] = new_value
                else:
                    rename_map[old_value] = None  # Keep original
                    
            except (ValueError, IndexError) as e:
                logging.warning(f"Skipping invalid line {line_num} in {tsv_file}: {e}")
                continue
    
    logging.info(f"Loaded {len(rename_map)} rename mappings from {tsv_file}")
    return rename_map


def find_marker_files(base_dir="teitok/markers/finished"):
    """Find all marker XML files in the specified directory.
    
    Args:
        base_dir: Base directory to search for marker files
        
    Returns:
        List of marker file paths
    """
    if not os.path.exists(base_dir):
        logging.warning(f"Marker directory not found: {base_dir}")
        return []
    
    xml_files = glob.glob(os.path.join(base_dir, "*.xml"))
    logging.info(f"Found {len(xml_files)} XML files in {base_dir}")
    return xml_files


def update_marker_file(file_path, rename_map, create_backup=True, dry_run=False):
    """Update commfunsubtype values in a single marker file.
    
    Args:
        file_path: Path to marker XML file
        rename_map: Dict mapping old_value -> new_value
        create_backup: Whether to create backup before modifying
        dry_run: If True, only report changes without applying them
        
    Returns:
        Dict with update statistics
    """
    stats = {
        'file': file_path,
        'items_processed': 0,
        'items_updated': 0,
        'updates': [],
        'errors': []
    }
    
    try:
        marker_doc = MarkerDoc(file_path)
        logging.info(f"Processing {file_path} with {len(marker_doc.annot_elems)} items")
        
        modified = False
        
        # Process all items in the marker file
        for item_id, item_elem in marker_doc.annot_elems.items():
            stats['items_processed'] += 1
            
            # Get current commfunsubtype value
            current_value = item_elem.attrib.get('commfunsubtype', '')
            
            if not current_value:
                continue
                
            # Check if this value needs to be updated
            if current_value in rename_map:
                new_value = rename_map[current_value]
                
                # If new_value is None, keep the original (no change needed)
                if new_value is None:
                    logging.debug(f"Keeping original value '{current_value}' for item {item_id}")
                    continue
                    
                # Update the value
                if not dry_run:
                    item_elem.set('commfunsubtype', new_value)
                    modified = True
                
                stats['items_updated'] += 1
                stats['updates'].append({
                    'item_id': item_id,
                    'old_value': current_value,
                    'new_value': new_value
                })
                
                logging.info(f"Updated item {item_id}: '{current_value}' -> '{new_value}'")
        
        # Save the file if modifications were made
        if modified and not dry_run:
            if create_backup:
                backup_path = f"{file_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(file_path, backup_path)
                logging.info(f"Created backup: {backup_path}")
            
            # Save the modified XML
            marker_doc.xml.write(file_path, encoding='utf-8', xml_declaration=True)
            logging.info(f"Saved updated file: {file_path}")
        
        if stats['items_updated'] > 0:
            logging.info(f"Updated {stats['items_updated']}/{stats['items_processed']} items in {file_path}")
        
    except Exception as e:
        error_msg = f"Error processing {file_path}: {e}"
        logging.error(error_msg)
        stats['errors'].append(error_msg)
    
    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Rename commfunsubtype values in marker files using a rename table"
    )
    parser.add_argument(
        "rename_table",
        help="Path to TSV file with rename mappings (freq, old_value, new_value, comments...)"
    )
    parser.add_argument(
        "marker_files",
        nargs='*',
        help="Marker XML files to process (if none specified, searches teitok/markers/)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be changed, don't modify files"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't create backup files before making changes"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    setup_logging()
    
    # Validate rename table file
    if not os.path.exists(args.rename_table):
        logging.error(f"Rename table file not found: {args.rename_table}")
        return 1
    
    # Load rename mappings
    try:
        rename_map = load_rename_table(args.rename_table)
        if not rename_map:
            logging.error("No valid rename mappings found in the table")
            return 1
    except Exception as e:
        logging.error(f"Failed to load rename table: {e}")
        return 1
    
    # Determine marker files to process
    if args.marker_files:
        marker_files = []
        for file_path in args.marker_files:
            if os.path.exists(file_path):
                marker_files.append(file_path)
            else:
                logging.warning(f"File not found: {file_path}")
        
        if not marker_files:
            logging.error("No valid marker files found")
            return 1
    else:
        marker_files = find_marker_files()
        if not marker_files:
            logging.error("No marker files found in default location")
            return 1
    
    logging.info(f"Processing {len(marker_files)} marker files...")
    
    # Process all files
    all_stats = []
    total_processed = 0
    total_updated = 0
    
    for file_path in marker_files:
        stats = update_marker_file(
            file_path, 
            rename_map, 
            create_backup=not args.no_backup,
            dry_run=args.dry_run
        )
        all_stats.append(stats)
        total_processed += stats['items_processed']
        total_updated += stats['items_updated']
    
    # Print summary
    logging.info("=" * 60)
    logging.info("SUMMARY")
    logging.info("=" * 60)
    logging.info(f"Files processed: {len(marker_files)}")
    logging.info(f"Total items processed: {total_processed}")
    logging.info(f"Total items updated: {total_updated}")
    
    if args.dry_run:
        logging.info("DRY RUN - No files were actually modified")
    
    # Print detailed updates if verbose
    if args.verbose:
        logging.info("\nDetailed updates:")
        for stats in all_stats:
            if stats['updates']:
                logging.info(f"\n{stats['file']}:")
                for update in stats['updates']:
                    logging.info(f"  {update['item_id']}: '{update['old_value']}' -> '{update['new_value']}'")
    
    # Print any errors
    error_count = sum(len(stats['errors']) for stats in all_stats)
    if error_count > 0:
        logging.warning(f"\n{error_count} errors occurred during processing")
        for stats in all_stats:
            for error in stats['errors']:
                logging.error(f"  {error}")
        return 1
    
    logging.info("Processing completed successfully")
    return 0


if __name__ == '__main__':
    exit(main())

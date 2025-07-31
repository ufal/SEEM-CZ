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
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Optional, Any
import re
from pathlib import Path
import shutil
from datetime import datetime

# Import our existing modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from markerdoc import MarkerDoc
except ImportError:
    logging.warning("markerdoc module not available, some features may be limited")
    MarkerDoc = None


class MarkerAutoCorrector:
    """Auto-corrector for finalized marker files."""
    
    def __init__(self, schema_path: str, fix_mode: bool = False, create_backup: bool = True):
        """Initialize the auto-corrector.
        
        Args:
            schema_path: Path to the schema definition file
            fix_mode: If True, apply corrections; if False, only report issues
            create_backup: If True, create backup files before making changes
        """
        self.schema_path = schema_path
        self.fix_mode = fix_mode
        self.create_backup = create_backup
        
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
                item_results = self._process_item(item, file_path)
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
    
    def _process_item(self, item: ET.Element, file_path: str) -> Dict[str, Any]:
        """Process a single item element.
        
        Args:
            item: XML item element
            file_path: Path to the source file
            
        Returns:
            Dictionary with issues found and corrections applied
        """
        results = {
            'issues': [],
            'corrections': [],
            'modified': False
        }
        
        item_id = item.get('id', 'unknown')
        
        # Placeholder for correction methods - to be implemented based on requirements
        # Example correction methods:
        # - self._correct_attribute_order(item, results)
        # - self._correct_missing_attributes(item, results)
        # - self._correct_invalid_values(item, results)
        # - self._correct_idrefs_format(item, results)
        
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
        """Process all XML files in a directory.
        
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
            f.write("File\tType\tSeverity\tItem ID\tMessage\tAction\tStatus\n")
            
            # Write results for each file
            for file_result in results['files_processed']:
                file_path = file_result['file']
                
                # Write issues
                for issue in file_result['issues']:
                    f.write(f"{file_path}\t")
                    f.write(f"{issue.get('type', '')}\t")
                    f.write(f"{issue.get('severity', '')}\t")
                    f.write(f"{issue.get('item_id', '')}\t")
                    f.write(f"{issue.get('message', '')}\t")
                    f.write("ISSUE\t")
                    f.write("FOUND\n")
                
                # Write corrections
                for correction in file_result['corrections']:
                    f.write(f"{file_path}\t")
                    f.write(f"{correction.get('type', '')}\t")
                    f.write("INFO\t")
                    f.write(f"{correction.get('item_id', '')}\t")
                    f.write(f"{correction.get('message', '')}\t")
                    f.write("CORRECTION\t")
                    f.write("APPLIED\n")
        
        logging.info(f"Report exported to {output_path}")





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
    parser.add_argument('--schema', default='/home/mnovak/projects/seem-cz/teitok/config/markers_def.xml',
                       help='Path to schema definition file')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Verbose output')
    parser.add_argument('--pattern', default='*.xml', 
                       help='File pattern to match (default: *.xml)')
    parser.add_argument('--no-backup', action='store_true', 
                       help='Do not create backup files when fixing')
    
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
        create_backup=not args.no_backup
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
    if args.fix:
        print(f"Files corrected: {all_results['summary']['files_corrected']}")
        print(f"Total corrections applied: {all_results['summary']['total_corrections']}")
    else:
        print(f"Total issues found: {all_results['summary']['total_issues']}")
        print("Use --fix to apply automatic corrections")
    
    # Show issue breakdown
    if all_results['summary']['issue_types']:
        print(f"\nIssue breakdown:")
        for issue_type, count in all_results['summary']['issue_types'].items():
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

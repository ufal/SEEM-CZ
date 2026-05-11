#!/usr/bin/env python3
"""
Data preprocessing script for Czech epistemic markers classification.
Prepares data from experiments_ctx50.json for transformer-based classification.

Usage:
    python prepare_data.py --input experiments_ctx50.json --output-dir data/
"""

import json
import argparse
import sys
from pathlib import Path
from collections import Counter
import pandas as pd
from typing import Dict, List, Tuple


def load_json_data(json_file: str) -> Dict:
    """Load and parse the JSON file."""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"Error: File {json_file} not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {json_file}: {e}", file=sys.stderr)
        sys.exit(1)


def filter_czech_source(items: List[Dict]) -> List[Dict]:
    """Filter items that are originally Czech (not translated from English)."""
    czech_source = [item for item in items if item.get('language') == 'cs']
    print(f"Filtered {len(czech_source)} Czech-source examples from {len(items)} total")
    return czech_source


def prepare_use_type_data(items: List[Dict]) -> pd.DataFrame:
    """
    Prepare data for use type classification.

    Classes: certain, content, evidence, confirm, other, answer
    """
    records = []

    for item in items:
        use_type = item.get('use', '').strip()
        if not use_type:
            continue

        # Get the context (prefer cs_ctx, fall back to cssent)
        context = item.get('cs_ctx', '') or item.get('cssent', '')
        if not context:
            continue

        record = {
            'id': item.get('id', ''),
            'expression': item.get('expression', ''),
            'context': context,
            'sentence': item.get('cssent', ''),
            'label': use_type,
            'xml': item.get('xml', ''),  # book/document identifier
        }
        records.append(record)

    df = pd.DataFrame(records)

    # Print statistics
    print("\n=== Use Type Classification Data ===")
    print(f"Total examples: {len(df)}")
    print("\nClass distribution:")
    print(df['label'].value_counts().sort_index())
    print("\nExpression distribution (top 10):")
    print(df['expression'].value_counts().head(10))

    return df


def prepare_certainty_data(items: List[Dict]) -> pd.DataFrame:
    """
    Prepare data for certainty degree classification.
    Only for items with use='certain' (epistemic use).

    Classes: full, highmedium, medium, hesitate
    Note: 'no' class is excluded due to too few examples (only 3)
    """
    records = []

    for item in items:
        # Only include epistemic uses
        use_type = item.get('use', '').strip()
        if use_type != 'certain':
            continue

        certainty = item.get('certainty', '').strip()
        # Skip items without certainty annotation or with 'no' class
        if not certainty or certainty == 'null' or certainty == 'no':
            continue

        # Get the context
        context = item.get('cs_ctx', '') or item.get('cssent', '')
        if not context:
            continue

        record = {
            'id': item.get('id', ''),
            'expression': item.get('expression', ''),
            'context': context,
            'sentence': item.get('cssent', ''),
            'label': certainty,
            'xml': item.get('xml', ''),
            'commfuntype': item.get('commfuntype', ''),  # May be useful for analysis
        }
        records.append(record)

    df = pd.DataFrame(records)

    # Print statistics
    print("\n=== Certainty Degree Classification Data ===")
    print(f"Total examples: {len(df)}")
    print("\nClass distribution:")
    print(df['label'].value_counts().sort_index())
    print("\nExpression distribution (top 10):")
    print(df['expression'].value_counts().head(10))

    return df


def save_data(df: pd.DataFrame, output_path: Path, task_name: str):
    """Save preprocessed data to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding='utf-8')
    print(f"\n✓ Saved {len(df)} examples to {output_path}")


def print_data_summary(use_df: pd.DataFrame, certainty_df: pd.DataFrame):
    """Print overall data summary."""
    print("\n" + "="*60)
    print("DATA PREPROCESSING SUMMARY")
    print("="*60)

    print(f"\n1. Use Type Classification:")
    print(f"   - Total examples: {len(use_df)}")
    print(f"   - Number of classes: {use_df['label'].nunique()}")
    print(f"   - Classes: {', '.join(sorted(use_df['label'].unique()))}")
    print(f"   - Unique expressions: {use_df['expression'].nunique()}")

    print(f"\n2. Certainty Degree Classification:")
    print(f"   - Total examples: {len(certainty_df)}")
    print(f"   - Number of classes: {certainty_df['label'].nunique()}")
    print(f"   - Classes: {', '.join(sorted(certainty_df['label'].unique()))}")
    print(f"   - Unique expressions: {certainty_df['expression'].nunique()}")

    # Check for class imbalance
    print(f"\n3. Class Balance Analysis:")
    print(f"\n   Use Type (minority/majority ratio):")
    use_counts = use_df['label'].value_counts()
    print(f"   {use_counts.min() / use_counts.max():.3f} (min: {use_counts.min()}, max: {use_counts.max()})")

    print(f"\n   Certainty (minority/majority ratio):")
    cert_counts = certainty_df['label'].value_counts()
    print(f"   {cert_counts.min() / cert_counts.max():.3f} (min: {cert_counts.min()}, max: {cert_counts.max()})")

    print("\n" + "="*60)


def main():
    parser = argparse.ArgumentParser(
        description='Preprocess Czech epistemic markers data for classification'
    )
    parser.add_argument(
        '--input',
        default='experiments_ctx50.json',
        help='Path to input JSON file (default: experiments_ctx50.json)'
    )
    parser.add_argument(
        '--output-dir',
        default='data',
        help='Output directory for preprocessed data (default: data/)'
    )
    parser.add_argument(
        '--all-languages',
        action='store_true',
        help='Include all languages (not just Czech-source)'
    )

    args = parser.parse_args()

    # Load data
    print(f"Loading data from {args.input}...")
    data = load_json_data(args.input)
    items = data.get('items', [])

    print(f"Loaded {len(items)} total items")
    print(f"Metadata: {data.get('metadata', {})}")

    # Filter to Czech-source only (unless --all-languages specified)
    if not args.all_languages:
        items = filter_czech_source(items)
    else:
        print("Using all languages (Czech and English source)")

    # Prepare datasets
    use_df = prepare_use_type_data(items)
    certainty_df = prepare_certainty_data(items)

    # Save preprocessed data
    output_dir = Path(args.output_dir)
    save_data(use_df, output_dir / 'czech_use_type.csv', 'use_type')
    save_data(certainty_df, output_dir / 'czech_certainty.csv', 'certainty')

    # Print summary
    print_data_summary(use_df, certainty_df)

    print("\n✅ Data preprocessing complete!")


if __name__ == '__main__':
    main()

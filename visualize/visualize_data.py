#!/usr/bin/env python3
"""Create an SVG overview of annotations in teitok/export/all_finished.csv.

The export uses tab-separated fields despite its .csv extension.

Usage:
    python visualize/visualize_data.py
    python visualize/visualize_data.py --input path/to/export.csv --output overview.svg
"""

import argparse
import csv
from collections import Counter
from html import escape
from pathlib import Path


CHARTS = (
    ("Výraz", "Examples per expression", True),
    ("Jazyk", "Examples by language", False),
    ("Užití", "Annotation by use", False),
    ("Míra jistoty", "Certainty annotations", False),
    ("Typ komunikační funkce", "Communication function", False),
)


def load_rows(input_path):
    with input_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter="\t")
        missing_columns = [column for column, _, _ in CHARTS if column not in (reader.fieldnames or [])]
        if missing_columns:
            raise ValueError(f"CSV is missing required columns: {', '.join(missing_columns)}")
        return list(reader)


def render_chart(title, values, y, top=None):
    counts = Counter(
        value.strip()
        for value in values
        if value and value.strip()
    )
    entries = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    if top is not None:
        entries = entries[:top]

    chart_height = 56 + max(len(entries), 1) * 28
    parts = [
        f'<text x="20" y="{y + 22}" class="title">{escape(title)}</text>'
    ]
    if not entries:
        parts.append(f'<text x="20" y="{y + 52}" class="empty">No annotated values</text>')
        return chart_height, parts

    maximum = max(count for _, count in entries)
    bar_width = 650
    for index, (label, count) in enumerate(entries):
        row_y = y + 48 + index * 28
        width = bar_width * count / maximum
        parts.extend(
            (
                f'<text x="20" y="{row_y + 15}" class="label">{escape(label)}</text>',
                f'<rect x="340" y="{row_y}" width="{width:.1f}" height="19" rx="3" class="bar"/>',
                f'<text x="{350 + width:.1f}" y="{row_y + 15}" class="count">{count}</text>',
            )
        )
    return chart_height, parts


def create_visualization(rows, output_path, top):
    width = 1100
    y = 55
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" role="img">',
        '<style>'
        'text{font-family:Arial,sans-serif;fill:#253247}'
        '.heading{font-size:25px;font-weight:bold}'
        '.title{font-size:18px;font-weight:bold}'
        '.label,.count,.empty{font-size:14px}'
        '.bar{fill:#4c78a8}'
        '</style>',
        '<text x="20" y="35" class="heading">SEEM-CZ annotation overview</text>',
    ]

    for column, title, is_expression in CHARTS:
        chart_height, chart_parts = render_chart(
            title,
            (row.get(column, "") for row in rows),
            y,
            top=top if is_expression else None,
        )
        parts.extend(chart_parts)
        y += chart_height + 12

    parts[0] = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{y}" role="img">'
    parts.append("</svg>")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(parts), encoding="utf-8")


def main():
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Visualize annotations from the TEITOK export.")
    parser.add_argument(
        "--input",
        type=Path,
        default=repo_root / "teitok/export/all_finished.csv",
        help="Tab-delimited export file (default: teitok/export/all_finished.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "output/annotation_overview.svg",
        help="SVG output file (default: visualize/output/annotation_overview.svg)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Maximum number of expressions shown (default: 20)",
    )
    args = parser.parse_args()
    if args.top < 1:
        parser.error("--top must be a positive integer")

    try:
        rows = load_rows(args.input)
        create_visualization(rows, args.output, args.top)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Visualization saved to {args.output}")


if __name__ == "__main__":
    main()

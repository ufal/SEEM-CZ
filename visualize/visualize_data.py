#!/usr/bin/env python3
"""Plot sentence-position distributions from teitok/export/all_finished.csv.

The export uses tab-separated fields despite its .csv extension.

Usage:
    python visualize/visualize_data.py
    python visualize/visualize_data.py --input path/to/export.csv --output positions.svg
"""

import argparse
import csv
from collections import Counter
from html import escape
from pathlib import Path


POSITION_COLUMN = "Místo ve větě"
CHARTS = (
    ("Užití", "Sentence position by use"),
    ("Typ komunikační funkce", "Sentence position by communication function"),
    ("Konkrétní komunikační funkce", "Sentence position by specific communication function"),
    ("Pozice v AČ", "Sentence position by information-structure position"),
    ("Výraz", "Sentence position by expression"),
)
COLORS = ("#4c78a8", "#f58518", "#54a24b", "#e45756", "#b279a2", "#72b7b2")


def load_rows(input_path):
    with input_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter="\t")
        required_columns = (POSITION_COLUMN, *(column for column, _ in CHARTS))
        missing_columns = [column for column in required_columns if column not in (reader.fieldnames or [])]
        if missing_columns:
            raise ValueError(f"CSV is missing required columns: {', '.join(missing_columns)}")
        return list(reader)


def render_chart(rows, column, title, y, positions, top=None):
    grouped = {}
    for row in rows:
        group = (row.get(column) or "").strip()
        position = (row.get(POSITION_COLUMN) or "").strip()
        if group and position:
            grouped.setdefault(group, Counter())[position] += 1

    entries = sorted(grouped.items(), key=lambda item: (-sum(item[1].values()), item[0]))
    if top is not None:
        entries = entries[:top]

    chart_height = 62 + max(len(entries), 1) * 30
    parts = [f'<text x="20" y="{y + 23}" class="title">{escape(title)}</text>']
    if not entries:
        parts.append(f'<text x="20" y="{y + 54}" class="empty">No annotated values</text>')
        return chart_height, parts

    bar_x = 410
    bar_width = 560
    for index, (label, counts) in enumerate(entries):
        row_y = y + 43 + index * 30
        total = sum(counts.values())
        parts.append(f'<text x="20" y="{row_y + 16}" class="label">{escape(label)}</text>')
        parts.append(f'<text x="365" y="{row_y + 16}" class="count">n={total}</text>')
        offset = 0
        for position, color in zip(positions, COLORS):
            count = counts.get(position, 0)
            if not count:
                continue
            width = bar_width * count / total
            percentage = count * 100 / total
            parts.append(
                f'<rect x="{bar_x + offset:.1f}" y="{row_y}" width="{width:.1f}" '
                f'height="20" fill="{color}"><title>{escape(label)} — '
                f'{escape(position)}: {count} ({percentage:.1f}%)</title></rect>'
            )
            offset += width
    return chart_height, parts


def create_visualization(rows, output_path):
    positions = sorted(
        {
            (row.get(POSITION_COLUMN) or "").strip()
            for row in rows
            if (row.get(POSITION_COLUMN) or "").strip()
        }
    )
    if len(positions) > len(COLORS):
        raise ValueError(f"Expected at most {len(COLORS)} distinct sentence positions")

    width = 1100
    y = 75
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" role="img">',
        '<style>'
        'text{font-family:Arial,sans-serif;fill:#253247}'
        '.heading{font-size:25px;font-weight:bold}'
        '.title{font-size:18px;font-weight:bold}'
        '.label,.count,.empty{font-size:14px}'
        '</style>',
        '<text x="20" y="35" class="heading">Sentence position distributions</text>',
        '<text x="20" y="57" class="empty">Percent within each group; rows without a sentence-position annotation are excluded.</text>',
    ]

    legend_x = 20
    for position, color in zip(positions, COLORS):
        parts.extend(
            (
                f'<rect x="{legend_x}" y="67" width="13" height="13" fill="{color}"/>',
                f'<text x="{legend_x + 19}" y="79" class="label">{escape(position)}</text>',
            )
        )
        legend_x += 20 + len(position) * 9

    for column, title in CHARTS:
        chart_height, chart_parts = render_chart(
            rows,
            column,
            title,
            y,
            positions,
            top=10 if column == "Konkrétní komunikační funkce" else None,
        )
        parts.extend(chart_parts)
        y += chart_height + 16

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
        default=Path(__file__).resolve().parent / "output/sentence_position_distributions.svg",
        help="SVG output file (default: visualize/output/sentence_position_distributions.svg)",
    )
    args = parser.parse_args()

    try:
        rows = load_rows(args.input)
        create_visualization(rows, args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Visualization saved to {args.output}")


if __name__ == "__main__":
    main()

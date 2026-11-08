#!/usr/bin/env python3
"""Plot sentence-position distributions from teitok/export/all_finished.csv.

The export uses tab-separated fields despite its .csv extension.

Usage:
    python visualize/visualize_data.py
    python visualize/visualize_data.py --input path/to/export.csv --output positions.pdf
"""

import argparse
import csv
from collections import Counter
from html import escape
from pathlib import Path
import shutil
import subprocess
import tempfile


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


def create_visualization(rows):
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
    return "\n".join(parts), width, y


def save_pdf(svg, width, height, output_path):
    browser = next(
        (
            executable
            for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
            if (executable := shutil.which(name))
        ),
        None,
    )
    if browser is None:
        raise ValueError("PDF output requires Chromium or Google Chrome to be installed")

    html = (
        f"<!doctype html><html><head><style>"
        f"@page{{size:{width / 96:.4f}in {height / 96:.4f}in;margin:0}}"
        f"html,body{{margin:0;padding:0;width:{width}px;height:{height}px}}"
        f"svg{{display:block;width:{width}px;height:{height}px}}"
        f"</style></head><body>{svg}</body></html>"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary_directory:
        html_path = Path(temporary_directory) / "visualization.html"
        html_path.write_text(html, encoding="utf-8")
        try:
            subprocess.run(
                [
                    browser,
                    "--headless",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-pdf-header-footer",
                    f"--print-to-pdf={output_path.resolve()}",
                    html_path.resolve().as_uri(),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else "timed out"
            raise ValueError(f"Could not generate PDF with Chromium: {detail}") from error
    if not output_path.is_file() or output_path.read_bytes()[:5] != b"%PDF-":
        raise ValueError(f"Chromium did not produce a valid PDF at {output_path}")


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
        default=Path(__file__).resolve().parent / "output/sentence_position_distributions.pdf",
        help="PDF output file; use an .svg extension to save SVG instead",
    )
    args = parser.parse_args()
    if args.output.suffix.lower() not in (".pdf", ".svg"):
        parser.error("--output must have a .pdf or .svg extension")

    try:
        rows = load_rows(args.input)
        svg, width, height = create_visualization(rows)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.suffix.lower() == ".svg":
            args.output.write_text(svg, encoding="utf-8")
        else:
            save_pdf(svg, width, height, args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Visualization saved to {args.output}")


if __name__ == "__main__":
    main()

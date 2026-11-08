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
from pathlib import Path

import matplotlib.pyplot as plt


POSITION_COLUMN = "Místo ve větě"
CHARTS = (
    ("Užití", "Sentence position by use"),
    ("Typ komunikační funkce", "Sentence position by communication function"),
    ("Konkrétní komunikační funkce", "Sentence position by specific communication function"),
    ("Pozice v AČ", "Sentence position by information-structure position"),
    ("Výraz", "Sentence position by expression"),
)


def load_rows(input_path):
    with input_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter="\t")
        required_columns = (POSITION_COLUMN, *(column for column, _ in CHARTS))
        missing_columns = [column for column in required_columns if column not in (reader.fieldnames or [])]
        if missing_columns:
            raise ValueError(f"CSV is missing required columns: {', '.join(missing_columns)}")
        return list(reader)


def group_counts(rows, column, top=None):
    grouped = {}
    for row in rows:
        group = (row.get(column) or "").strip()
        position = (row.get(POSITION_COLUMN) or "").strip()
        if group and position:
            grouped.setdefault(group, Counter())[position] += 1

    entries = sorted(grouped.items(), key=lambda item: (-sum(item[1].values()), item[0]))
    if top is not None:
        entries = entries[:top]
    return entries


def plot_chart(axis, rows, column, title, positions, colors, top=None):
    entries = group_counts(rows, column, top=top)
    if not entries:
        axis.set_title(title, loc="left")
        axis.text(0.5, 0.5, "No annotated values", ha="center", va="center", transform=axis.transAxes)
        axis.set_axis_off()
        return

    labels = [label for label, _ in entries]
    totals = [sum(counts.values()) for _, counts in entries]
    left = [0.0] * len(entries)
    for position, color in zip(positions, colors):
        percentages = [
            100 * counts.get(position, 0) / total
            for (_, counts), total in zip(entries, totals)
        ]
        axis.barh(
            range(len(entries)),
            percentages,
            left=left,
            color=color,
            label=position,
            height=0.78,
        )
        left = [offset + value for offset, value in zip(left, percentages)]

    axis.set_yticks(range(len(entries)), [f"{label}  (n={total})" for label, total in zip(labels, totals)])
    axis.invert_yaxis()
    axis.set_xlim(0, 100)
    axis.set_xticks((0, 25, 50, 75, 100), labels=("0%", "25%", "50%", "75%", "100%"))
    axis.set_title(title, loc="left", fontsize=11, fontweight="bold", pad=6)
    axis.grid(axis="x", color="#d9d9d9", linewidth=0.6)
    axis.set_axisbelow(True)
    axis.tick_params(axis="y", labelsize=8, length=0, pad=5)
    axis.tick_params(axis="x", labelsize=8)
    for spine in ("top", "right", "left"):
        axis.spines[spine].set_visible(False)


def create_visualization(rows):
    positions = sorted(
        {
            (row.get(POSITION_COLUMN) or "").strip()
            for row in rows
            if (row.get(POSITION_COLUMN) or "").strip()
        }
    )
    chart_entries = [
        group_counts(
            rows,
            column,
            top=10 if column == "Konkrétní komunikační funkce" else None,
        )
        for column, _ in CHARTS
    ]
    figure_height = max(6, 2.2 + sum(max(len(entries), 1) * 0.27 + 0.8 for entries in chart_entries))
    figure, axes = plt.subplots(
        len(CHARTS),
        1,
        figsize=(11, figure_height),
        gridspec_kw={"height_ratios": [max(len(entries), 1) for entries in chart_entries]},
        squeeze=False,
    )
    colors = [plt.get_cmap("tab10")(index) for index in range(len(positions))]
    for axis, (column, title) in zip(axes[:, 0], CHARTS):
        plot_chart(
            axis,
            rows,
            column,
            title,
            positions,
            colors,
            top=10 if column == "Konkrétní komunikační funkce" else None,
        )

    figure.suptitle("Sentence position distributions", fontsize=16, fontweight="bold", y=0.995)
    if positions:
        handles, labels = axes[0, 0].get_legend_handles_labels()
        figure.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.985), ncol=len(positions), frameon=False)
    figure.text(
        0.5,
        0.005,
        "Percent within each group; rows without a sentence-position annotation are excluded.",
        ha="center",
        fontsize=8,
    )
    figure.tight_layout(rect=(0.02, 0.02, 0.99, 0.96 if positions else 0.97), h_pad=1.6)
    return figure


def main():
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Visualize annotations from the TEITOK export with Matplotlib.")
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
        figure = create_visualization(rows)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with plt.rc_context({"svg.fonttype": "none"}):
            figure.savefig(args.output, bbox_inches="tight")
        plt.close(figure)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Visualization saved to {args.output}")


if __name__ == "__main__":
    main()

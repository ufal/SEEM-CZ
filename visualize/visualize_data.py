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
import numpy as np
from scipy.spatial.distance import jensenshannon
from scipy.stats import bootstrap

POSITION_COLUMN = "Místo ve větě"
AC_POSITION_COLUMN = "Pozice v AČ"
SCOPE_COLUMN = "Dosah"
EXPR_COLUMN = "Výraz"

POSITION_CHARTS = [
    ("Užití",                           None,                           None),
    ("Typ komunikační funkce",          None,                           None),
    ("Konkrétní komunikační funkce",    None,                           10  ),
    ("Konkrétní komunikační funkce",    (EXPR_COLUMN, "mozna"),         None),
    ("Konkrétní komunikační funkce",    (EXPR_COLUMN, "urcite"),        None),
    ("Konkrétní komunikační funkce",    (EXPR_COLUMN, "samozrejme"),    None),
    (AC_POSITION_COLUMN,                None,                           None),
    (AC_POSITION_COLUMN,                (SCOPE_COLUMN, "věta"),         None),
    ("Výraz",                           None,                           None),
]

AC_POSITION_CHARTS = [
    ("Výraz",                           None,                           None),
]


def load_rows(input_path):
    with input_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter="\t")
        required_columns = (
            POSITION_COLUMN,
            AC_POSITION_COLUMN,
            SCOPE_COLUMN,
            *(column for column, _, _ in (*POSITION_CHARTS, *AC_POSITION_CHARTS)),
        )
        missing_columns = [column for column in required_columns if column not in (reader.fieldnames or [])]
        if missing_columns:
            raise ValueError(f"CSV is missing required columns: {', '.join(missing_columns)}")
        return list(reader)


def group_counts(rows, column, filter_params=None, top=None, value_column=POSITION_COLUMN):
    grouped = {}
    for row in rows:
        if filter_params is not None and (row.get(filter_params[0]) or "").strip() != filter_params[1]:
            continue
        group = (row.get(column) or "").strip()
        position = (row.get(value_column) or "").strip()
        if group and position:
            grouped.setdefault(group, Counter())[position] += 1

    entries = sorted(grouped.items(), key=lambda item: (-sum(item[1].values()), item[0]))
    if top is not None:
        entries = entries[:top]
    return entries


def jensen_shannon_distance(first, second):
    first_total = sum(first.values())
    second_total = sum(second.values())
    if not first_total or not second_total:
        return None

    categories = first.keys() | second.keys()
    return jensenshannon(
        [first.get(category, 0) for category in categories],
        [second.get(category, 0) for category in categories],
        base=2,
    )


def leave_one_out_distances(entries, mode="point", n_resamples=1000):
    overall_counts = Counter()
    for _, counts in entries:
        overall_counts.update(counts)

    distances = {}
    rng = None
    if mode == "ci":
        rng = np.random.default_rng(0)

    for label, counts in entries:
        comparison_counts = overall_counts - counts
        if mode == "none":
            continue
        if mode == "point":
            distances[label] = jensen_shannon_distance(counts, comparison_counts)
            continue
        if mode != "ci":
            raise ValueError(f"Unknown Jensen-Shannon mode: {mode}")

        categories = sorted(counts.keys() | comparison_counts.keys())
        if sum(counts.values()) < 2 or sum(comparison_counts.values()) < 2:
            distances[label] = None
            continue
        category_ids = {category: index for index, category in enumerate(categories)}
        group_sample = np.concatenate(
            [np.full(count, category_ids[category]) for category, count in counts.items()]
        )
        comparison_sample = np.concatenate(
            [
                np.full(count, category_ids[category])
                for category, count in comparison_counts.items()
            ]
        )

        def distance_statistic(group, comparison):
            return jensen_shannon_distance(
                dict(zip(categories, np.bincount(group, minlength=len(categories)))),
                dict(zip(categories, np.bincount(comparison, minlength=len(categories)))),
            )

        result = bootstrap(
            (group_sample, comparison_sample),
            distance_statistic,
            vectorized=False,
            n_resamples=n_resamples,
            confidence_level=0.95,
            method="percentile",
            random_state=rng,
        )
        distances[label] = (result.confidence_interval.low, result.confidence_interval.high)
    return overall_counts, distances


def plot_chart(axis, entries, title, positions, colors, overall_counts, distances, js_mode):
    if not entries:
        axis.set_title(title, loc="left")
        axis.text(0.5, 0.5, "No annotated values", ha="center", va="center", transform=axis.transAxes)
        axis.set_axis_off()
        return

    entries = [("All y values", overall_counts), *entries]

    labels = [label for label, _ in entries]
    totals = [sum(counts.values()) for _, counts in entries]
    tick_labels = []
    for label, total in zip(labels, totals):
        distance = distances.get(label)
        annotation = f"n={total}"
        if js_mode == "point":
            distance_label = "n/a" if distance is None else f"{distance:.3f}"
            annotation += f", JS={distance_label}"
        elif js_mode == "ci":
            if distance is None:
                distance_label = "n/a"
            else:
                distance_label = f"[{distance[0]:.3f}, {distance[1]:.3f}]"
            annotation += f", JS 95% CI={distance_label}"
        tick_labels.append(f"{label}  ({annotation})")
    left = [0.0] * len(entries)
    for position, color in zip(positions, colors):
        percentages = [
            100 * counts.get(position, 0) / total
            for (_, counts), total in zip(entries, totals)
        ]
        bars = axis.barh(
            range(len(entries)),
            percentages,
            left=left,
            color=color,
            label=position,
            height=0.78,
        )
        axis.bar_label(
            bars,
            labels=[f"{percentage:.1f}%" if percentage else "" for percentage in percentages],
            label_type="center",
            fontsize=7,
            color="white",
            padding=0,
        )
        left = [offset + value for offset, value in zip(left, percentages)]

    axis.set_yticks(range(len(entries)), tick_labels)
    axis.invert_yaxis()
    axis.set_xlim(0, 100)
    axis.set_title(title, loc="left", fontsize=11, fontweight="bold", pad=6)
    axis.xaxis.set_visible(False)
    axis.tick_params(axis="y", labelsize=8, length=0, pad=5)
    for spine in ("top", "right", "left", "bottom"):
        axis.spines[spine].set_visible(False)


def create_visualization(rows, js_mode="point", n_resamples=1000):
    chart_blocks = (
        (POSITION_CHARTS, POSITION_COLUMN, ""),
        (AC_POSITION_CHARTS, AC_POSITION_COLUMN, f"{AC_POSITION_COLUMN} by "),
    )
    chart_entries = []
    chart_totals = []
    chart_distances = []
    chart_specs = []
    block_positions = []
    for block_index, (charts, value_column, title_prefix) in enumerate(chart_blocks):
        positions = sorted(
            {
                (row.get(value_column) or "").strip()
                for row in rows
                if (row.get(value_column) or "").strip()
            }
        )
        block_positions.append(positions)
        for column, filter_params, top in charts:
            all_entries = group_counts(rows, column, filter_params, value_column=value_column)
            total_counts, distances = leave_one_out_distances(
                all_entries,
                mode=js_mode,
                n_resamples=n_resamples,
            )
            chart_entries.append(all_entries[:top] if top is not None else all_entries)
            chart_totals.append(total_counts)
            chart_distances.append(distances)
            chart_specs.append((column, filter_params, top, title_prefix, block_index))
    height_ratios = [
        *(max(len(entries) + 1, 1) for entries in chart_entries),
    ]
    figure_height = max(6, 2.2 + sum(ratio * 0.27 + 0.8 for ratio in height_ratios))
    figure, axes = plt.subplots(
        len(chart_specs),
        1,
        figsize=(11, figure_height),
        gridspec_kw={"height_ratios": height_ratios},
        squeeze=False,
    )
    color_blocks = [
        [plt.get_cmap("tab10")(index) for index in range(len(positions))]
        for positions in block_positions
    ]
    for (
        axis,
        entry,
        total,
        distances,
        (colname, filter_params, top, title_prefix, block_index),
    ) in zip(axes[:, 0], chart_entries, chart_totals, chart_distances, chart_specs):
        title = title_prefix + colname
        cond_strs = [
            f"{filter_params[0]} = {filter_params[1]}" if filter_params else None,
            f"top {top} values" if top is not None else None,
        ]
        cond_strs = [cond for cond in cond_strs if cond]
        if cond_strs:
            title += " (" + ", ".join(cond_strs) + ")"

        plot_chart(
            axis,
            entry,
            title,
            block_positions[block_index],
            color_blocks[block_index],
            total,
            distances,
            js_mode,
        )

    figure.suptitle("Sentence and AČ position distributions", fontsize=16, fontweight="bold", y=0.995)
    legend_y = 0.98
    for block_index, charts in enumerate(chart_blocks):
        first_axis_index = sum(len(block[0]) for block in chart_blocks[:block_index])
        handles, labels = [], []
        for axis_index in range(first_axis_index, first_axis_index + len(charts[0])):
            handles, labels = axes[axis_index, 0].get_legend_handles_labels()
            if handles:
                break
        positions = block_positions[block_index]
        if not positions or not handles:
            continue
        figure.legend(
            handles,
            labels,
            title=charts[1],
            loc="upper center",
            bbox_to_anchor=(0.5, legend_y),
            ncol=len(positions),
            frameon=False,
        )
        legend_y -= 0.035
    footer = "Percent within each group; rows without the relevant position annotation are excluded."
    if js_mode == "point":
        footer += " JS is the base-2 leave-one-out Jensen–Shannon distance."
    elif js_mode == "ci":
        footer += (
            " JS CI is the percentile-bootstrap 95% confidence interval for leave-one-out distance "
            "(n/a if either sample has fewer than 2 observations)."
        )
    figure.text(0.5, 0.005, footer, ha="center", fontsize=8)
    figure.tight_layout(rect=(0.02, 0.02, 0.99, legend_y - 0.015), h_pad=1.6)
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
    parser.add_argument(
        "--js",
        choices=("none", "point", "ci"),
        default="point",
        help="Jensen-Shannon annotation: none, point estimate, or bootstrap confidence interval (default: point)",
    )
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=1000,
        help="Number of SciPy bootstrap resamples when --js=ci (default: 1000)",
    )
    args = parser.parse_args()
    if args.output.suffix.lower() not in (".pdf", ".svg"):
        parser.error("--output must have a .pdf or .svg extension")
    if args.bootstrap_resamples < 1:
        parser.error("--bootstrap-resamples must be a positive integer")

    try:
        rows = load_rows(args.input)
        figure = create_visualization(rows, js_mode=args.js, n_resamples=args.bootstrap_resamples)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with plt.rc_context({"svg.fonttype": "none"}):
            figure.savefig(args.output, bbox_inches="tight")
        plt.close(figure)
    except (OSError, ValueError, ImportError) as error:
        parser.error(str(error))
    print(f"Visualization saved to {args.output}")


if __name__ == "__main__":
    main()

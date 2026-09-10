#!/usr/bin/env python3
"""
Evaluation and visualization script for classification results.

Generates:
- Confusion matrices (visualizations)
- Per-expression performance analysis
- LaTeX tables for paper inclusion
- Comprehensive result summaries

Usage:
    python evaluate_results.py --results models/use_type/quick_*/quick_split_results.json
    python evaluate_results.py --results models/certainty/cv_*/cv_results.json --mode cv
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


def load_results(results_path: str) -> Dict:
    """Load results from JSON file."""
    try:
        with open(results_path, 'r', encoding='utf-8') as f:
            results = json.load(f)
        return results
    except FileNotFoundError:
        print(f"Error: Results file {results_path} not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {results_path}: {e}", file=sys.stderr)
        sys.exit(1)


def plot_confusion_matrix(cm: np.ndarray, labels: List[str], output_path: Path, title: str = "Confusion Matrix"):
    """Generate and save confusion matrix visualization."""
    plt.figure(figsize=(10, 8))

    # Normalize confusion matrix
    cm_normalized = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]

    # Create heatmap
    sns.heatmap(
        cm_normalized,
        annot=True,
        fmt='.2f',
        cmap='Blues',
        xticklabels=labels,
        yticklabels=labels,
        cbar_kws={'label': 'Normalized Count'}
    )

    plt.title(title, fontsize=14, fontweight='bold')
    plt.ylabel('True Label', fontsize=12)
    plt.xlabel('Predicted Label', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.yticks(rotation=0)
    plt.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ Confusion matrix saved to {output_path}")


def generate_latex_table_quick(results: Dict, output_path: Path):
    """Generate LaTeX table for quick split results."""
    label_mapping = results['label_mapping']['id2label']
    cm = np.array(results['confusion_matrix'])

    # Calculate per-class metrics
    precision_per_class = []
    recall_per_class = []
    f1_per_class = []

    for i in range(len(label_mapping)):
        tp = cm[i, i]
        fp = cm[:, i].sum() - tp
        fn = cm[i, :].sum() - tp

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        precision_per_class.append(precision)
        recall_per_class.append(recall)
        f1_per_class.append(f1)

    # Build LaTeX table
    latex_lines = []
    latex_lines.append("\\begin{table}[htbp]")
    latex_lines.append("\\centering")
    latex_lines.append("\\begin{tabular}{|l|ccc|c|}")
    latex_lines.append("\\hline")
    latex_lines.append("\\textbf{Class} & \\textbf{Precision} & \\textbf{Recall} & \\textbf{F1} & \\textbf{Support} \\\\")
    latex_lines.append("\\hline")

    # Add per-class rows
    for i in range(len(label_mapping)):
        class_name = label_mapping[str(i)]
        support = cm[i, :].sum()
        latex_lines.append(
            f"{class_name} & {precision_per_class[i]:.3f} & {recall_per_class[i]:.3f} & "
            f"{f1_per_class[i]:.3f} & {support} \\\\"
        )

    latex_lines.append("\\hline")

    # Add overall metrics
    overall_metrics = results['test_metrics']
    latex_lines.append(
        f"\\textbf{{Weighted Avg}} & {overall_metrics['eval_precision_weighted']:.3f} & "
        f"{overall_metrics['eval_recall_weighted']:.3f} & {overall_metrics['eval_f1_weighted']:.3f} & "
        f"{cm.sum()} \\\\"
    )

    latex_lines.append("\\hline")
    latex_lines.append("\\end{tabular}")
    latex_lines.append(f"\\caption{{Classification results (Accuracy: {overall_metrics['eval_accuracy']:.3f})}}")
    latex_lines.append("\\label{tab:classification_results}")
    latex_lines.append("\\end{table}")

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(latex_lines))

    print(f"✓ LaTeX table saved to {output_path}")


def generate_latex_table_cv(results: Dict, output_path: Path):
    """Generate LaTeX table for cross-validation results."""
    label_mapping = results['label_mapping']['id2label']
    cm = np.array(results['confusion_matrix'])

    # Calculate per-class metrics
    precision_per_class = []
    recall_per_class = []
    f1_per_class = []

    for i in range(len(label_mapping)):
        tp = cm[i, i]
        fp = cm[:, i].sum() - tp
        fn = cm[i, :].sum() - tp

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        precision_per_class.append(precision)
        recall_per_class.append(recall)
        f1_per_class.append(f1)

    # Build LaTeX table
    latex_lines = []
    latex_lines.append("\\begin{table}[htbp]")
    latex_lines.append("\\centering")
    latex_lines.append("\\begin{tabular}{|l|ccc|c|}")
    latex_lines.append("\\hline")
    latex_lines.append("\\textbf{Class} & \\textbf{Precision} & \\textbf{Recall} & \\textbf{F1} & \\textbf{Support} \\\\")
    latex_lines.append("\\hline")

    # Add per-class rows
    for i in range(len(label_mapping)):
        class_name = label_mapping[str(i)]
        support = cm[i, :].sum()
        latex_lines.append(
            f"{class_name} & {precision_per_class[i]:.3f} & {recall_per_class[i]:.3f} & "
            f"{f1_per_class[i]:.3f} & {support} \\\\"
        )

    latex_lines.append("\\hline")

    # Add overall metrics with std
    metrics = results['aggregated_metrics']
    latex_lines.append(
        f"\\textbf{{Weighted Avg}} & "
        f"{metrics['eval_precision_weighted']['mean']:.3f} $\\pm$ {metrics['eval_precision_weighted']['std']:.3f} & "
        f"{metrics['eval_recall_weighted']['mean']:.3f} $\\pm$ {metrics['eval_recall_weighted']['std']:.3f} & "
        f"{metrics['eval_f1_weighted']['mean']:.3f} $\\pm$ {metrics['eval_f1_weighted']['std']:.3f} & "
        f"{cm.sum()} \\\\"
    )

    latex_lines.append("\\hline")
    latex_lines.append("\\end{tabular}")

    acc_mean = metrics['eval_accuracy']['mean']
    acc_std = metrics['eval_accuracy']['std']
    latex_lines.append(
        f"\\caption{{10-fold CV results (Accuracy: {acc_mean:.3f} $\\pm$ {acc_std:.3f})}}"
    )
    latex_lines.append("\\label{tab:cv_results}")
    latex_lines.append("\\end{table}")

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(latex_lines))

    print(f"✓ LaTeX table saved to {output_path}")


def plot_cv_fold_comparison(results: Dict, output_path: Path):
    """Plot comparison of metrics across CV folds."""
    fold_results = results['fold_results']
    metrics = ['eval_accuracy', 'eval_f1_weighted', 'eval_precision_weighted', 'eval_recall_weighted']

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()

    metric_names = {
        'eval_accuracy': 'Accuracy',
        'eval_f1_weighted': 'F1 (Weighted)',
        'eval_precision_weighted': 'Precision (Weighted)',
        'eval_recall_weighted': 'Recall (Weighted)'
    }

    for idx, metric in enumerate(metrics):
        values = [fold[metric] for fold in fold_results]
        folds = list(range(1, len(values) + 1))

        ax = axes[idx]
        ax.plot(folds, values, marker='o', linewidth=2, markersize=8)
        ax.axhline(y=np.mean(values), color='r', linestyle='--', linewidth=2,
                   label=f'Mean: {np.mean(values):.4f}')
        ax.fill_between(folds,
                        np.mean(values) - np.std(values),
                        np.mean(values) + np.std(values),
                        alpha=0.2, color='red',
                        label=f'±1 Std: {np.std(values):.4f}')

        ax.set_xlabel('Fold', fontsize=11)
        ax.set_ylabel(metric_names[metric], fontsize=11)
        ax.set_title(metric_names[metric], fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=9)
        ax.set_xticks(folds)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ CV fold comparison saved to {output_path}")


def generate_summary_report(results: Dict, output_path: Path):
    """Generate a comprehensive text summary report."""
    lines = []
    lines.append("="*80)
    lines.append("CLASSIFICATION RESULTS SUMMARY")
    lines.append("="*80)
    lines.append(f"\nModel: {results['model']}")
    lines.append(f"Mode: {results['mode']}")

    if results['mode'] == 'quick_split':
        lines.append(f"\nData Split:")
        lines.append(f"  Train: {results['data_split']['train_size']}")
        lines.append(f"  Val:   {results['data_split']['val_size']}")
        lines.append(f"  Test:  {results['data_split']['test_size']}")

        lines.append(f"\nTest Set Metrics:")
        for key, value in results['test_metrics'].items():
            if key.startswith('eval_'):
                metric_name = key.replace('eval_', '').replace('_', ' ').title()
                lines.append(f"  {metric_name}: {value:.4f}")

    else:  # cross_validation
        lines.append(f"\nNumber of Folds: {results['n_folds']}")
        lines.append(f"\nAggregated Metrics (Mean ± Std):")
        for metric, stats in results['aggregated_metrics'].items():
            metric_name = metric.replace('eval_', '').replace('_', ' ').title()
            lines.append(f"  {metric_name}: {stats['mean']:.4f} ± {stats['std']:.4f}")

    lines.append(f"\n{'-'*80}")
    lines.append("Classification Report:")
    lines.append("-"*80)
    lines.append(results['classification_report'])

    lines.append(f"\n{'-'*80}")
    lines.append("Label Mapping:")
    lines.append("-"*80)
    for label, idx in sorted(results['label_mapping']['label2id'].items(), key=lambda x: x[1]):
        lines.append(f"  {idx}: {label}")

    lines.append("\n" + "="*80)

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"✓ Summary report saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate and visualize classification results'
    )
    parser.add_argument(
        '--results',
        required=True,
        help='Path to results JSON file'
    )
    parser.add_argument(
        '--output-dir',
        default='results',
        help='Output directory for visualizations and tables (default: results/)'
    )

    args = parser.parse_args()

    # Load results
    print(f"Loading results from {args.results}...")
    results = load_results(args.results)

    mode = results['mode']
    print(f"Results mode: {mode}")

    # Create output directory
    results_path = Path(args.results)
    output_dir = Path(args.output_dir) / results_path.parent.name
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nOutput directory: {output_dir}")

    # Generate visualizations and reports
    print("\nGenerating outputs...")

    # 1. Confusion matrix
    cm = np.array(results['confusion_matrix'])
    labels = [results['label_mapping']['id2label'][str(i)] for i in range(len(cm))]
    plot_confusion_matrix(
        cm, labels,
        output_dir / 'confusion_matrix.png',
        title=f"Confusion Matrix ({mode})"
    )

    # 2. LaTeX table
    if mode == 'quick_split':
        generate_latex_table_quick(results, output_dir / 'results_table.tex')
    else:
        generate_latex_table_cv(results, output_dir / 'results_table.tex')

        # 3. CV fold comparison (only for CV mode)
        plot_cv_fold_comparison(results, output_dir / 'cv_folds_comparison.png')

    # 4. Summary report
    generate_summary_report(results, output_dir / 'summary_report.txt')

    print("\n✅ Evaluation complete!")
    print(f"\nAll outputs saved to: {output_dir}")


if __name__ == '__main__':
    main()

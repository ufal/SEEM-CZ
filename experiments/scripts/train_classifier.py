#!/usr/bin/env python3
"""
Training script for epistemic markers classification using XLM-RoBERTa.

Supports both quick train/val/test split and 10-fold cross-validation.

Usage:
    # Quick split
    python train_classifier.py --task use_type --mode quick --data data/czech_use_type.csv

    # 10-fold CV
    python train_classifier.py --task certainty --mode cv --data data/czech_certainty.csv
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from collections import Counter
from typing import Dict, List, Tuple

import torch
from torch.utils.data import Dataset
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import (
    accuracy_score, precision_recall_fscore_support,
    classification_report, confusion_matrix
)
from sklearn.utils.class_weight import compute_class_weight

from transformers import (
    AutoTokenizer, AutoModelForSequenceClassification,
    TrainingArguments, Trainer, EarlyStoppingCallback
)
import torch.nn as nn


class WeightedTrainer(Trainer):
    """Custom Trainer that uses class weights in the loss function."""

    def __init__(self, *args, class_weights=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        """Compute weighted cross-entropy loss.

        Args:
            model: The model being trained
            inputs: Input batch dict
            return_outputs: Whether to return model outputs
            num_items_in_batch: Number of items in batch (for newer transformers versions)
        """
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits

        # Apply class weights if provided
        if self.class_weights is not None:
            loss_fct = nn.CrossEntropyLoss(weight=self.class_weights.to(logits.device))
        else:
            loss_fct = nn.CrossEntropyLoss()

        loss = loss_fct(logits, labels)

        return (loss, outputs) if return_outputs else loss


class EpistemicMarkerDataset(Dataset):
    """Custom dataset for epistemic marker classification."""

    def __init__(self, texts: List[str], labels: List[int], tokenizer, max_length: int = 256):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        text = str(self.texts[idx])
        label = self.labels[idx]

        encoding = self.tokenizer(
            text,
            truncation=True,
            padding='max_length',
            max_length=self.max_length,
            return_tensors='pt'
        )

        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'labels': torch.tensor(label, dtype=torch.long)
        }


def load_and_prepare_data(data_path: str) -> Tuple[pd.DataFrame, Dict[str, int], Dict[int, str]]:
    """Load CSV data and create label mappings."""
    df = pd.read_csv(data_path, encoding='utf-8')

    print(f"Loaded {len(df)} examples from {data_path}")
    print(f"Columns: {df.columns.tolist()}")

    # Create label mappings
    unique_labels = sorted(df['label'].unique())
    label2id = {label: idx for idx, label in enumerate(unique_labels)}
    id2label = {idx: label for label, idx in label2id.items()}

    print(f"\nLabel mappings:")
    for label, idx in label2id.items():
        count = len(df[df['label'] == label])
        print(f"  {label} -> {idx} ({count} examples)")

    return df, label2id, id2label


def compute_metrics(eval_pred):
    """Compute metrics for evaluation."""
    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=1)

    accuracy = accuracy_score(labels, predictions)
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, predictions, average='weighted', zero_division=0
    )

    return {
        'accuracy': accuracy,
        'f1_weighted': f1,
        'precision_weighted': precision,
        'recall_weighted': recall,
    }


def train_quick_split(
    df: pd.DataFrame,
    label2id: Dict[str, int],
    id2label: Dict[int, str],
    model_name: str,
    output_dir: Path,
    args: argparse.Namespace
):
    """Train with a simple train/val/test split."""
    print("\n" + "="*60)
    print("QUICK SPLIT TRAINING")
    print("="*60)

    # Prepare labels
    df['label_id'] = df['label'].map(label2id)
    texts = df['context'].tolist()
    labels = df['label_id'].tolist()

    # Stratified split: 80% train, 10% val, 10% test
    X_train, X_temp, y_train, y_temp = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.5, random_state=42, stratify=y_temp
    )

    print(f"\nData split:")
    print(f"  Train: {len(X_train)} examples")
    print(f"  Val:   {len(X_val)} examples")
    print(f"  Test:  {len(X_test)} examples")

    # Initialize tokenizer and model
    print(f"\nLoading model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(label2id),
        id2label=id2label,
        label2id=label2id
    )

    # Create datasets
    train_dataset = EpistemicMarkerDataset(X_train, y_train, tokenizer, args.max_length)
    val_dataset = EpistemicMarkerDataset(X_val, y_val, tokenizer, args.max_length)
    test_dataset = EpistemicMarkerDataset(X_test, y_test, tokenizer, args.max_length)

    # Compute class weights for imbalanced data
    class_weights = compute_class_weight(
        'balanced',
        classes=np.unique(y_train),
        y=y_train
    )
    class_weights_tensor = torch.tensor(class_weights, dtype=torch.float32)
    print(f"\nClass weights: {dict(enumerate(class_weights))}")

    # Calculate steps per epoch
    steps_per_epoch = len(X_train) // (args.batch_size * args.gradient_accumulation_steps)

    # Determine evaluation settings
    if args.eval_strategy == 'epoch':
        eval_steps = None  # Not used for epoch strategy
        eval_strategy_display = f"every epoch ({steps_per_epoch} steps)"
    else:
        if args.eval_steps is None:
            eval_steps = max(10, steps_per_epoch // 2)  # Evaluate twice per epoch
        else:
            eval_steps = args.eval_steps
        eval_strategy_display = f"every {eval_steps} steps"

    print(f"\nTraining configuration:")
    print(f"  Steps per epoch: {steps_per_epoch}")
    print(f"  Total steps: {steps_per_epoch * args.epochs}")
    print(f"  Eval strategy: {eval_strategy_display}")
    print(f"  Early stopping patience: {args.early_stopping_patience}")

    # Training arguments
    training_args_dict = {
        'output_dir': str(output_dir / 'checkpoints'),
        'num_train_epochs': args.epochs,
        'per_device_train_batch_size': args.batch_size,
        'per_device_eval_batch_size': args.batch_size * 2,
        'gradient_accumulation_steps': args.gradient_accumulation_steps,
        'learning_rate': args.learning_rate,
        'warmup_ratio': args.warmup_ratio if args.warmup_steps is None else 0.0,
        'warmup_steps': args.warmup_steps if args.warmup_steps is not None else 0,
        'weight_decay': 0.01,
        'logging_dir': str(output_dir / 'logs'),
        'logging_steps': 10,
        'eval_strategy': args.eval_strategy,
        'save_strategy': args.eval_strategy,
        'save_total_limit': 2,
        'load_best_model_at_end': True,
        'metric_for_best_model': 'f1_weighted',
        'greater_is_better': True,
        'fp16': args.fp16,
        'bf16': args.bf16,
        'dataloader_num_workers': 4,
        'report_to': 'none',
    }

    # Add eval_steps only if using steps-based evaluation
    if args.eval_strategy == 'steps':
        training_args_dict['eval_steps'] = eval_steps
        training_args_dict['save_steps'] = eval_steps

    training_args = TrainingArguments(**training_args_dict)

    # Initialize trainer with class weights
    trainer = WeightedTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=args.early_stopping_patience)],
        class_weights=class_weights_tensor
    )

    # Train
    print("\nStarting training...")
    trainer.train()

    # Evaluate on test set
    print("\nEvaluating on test set...")
    test_results = trainer.evaluate(test_dataset)

    # Get predictions for detailed analysis
    predictions = trainer.predict(test_dataset)
    y_pred = np.argmax(predictions.predictions, axis=1)

    # Generate classification report
    report = classification_report(
        y_test, y_pred,
        target_names=[id2label[i] for i in range(len(id2label))],
        digits=4
    )

    # Generate confusion matrix
    cm = confusion_matrix(y_test, y_pred)

    # Save results
    results = {
        'mode': 'quick_split',
        'model': model_name,
        'test_metrics': test_results,
        'classification_report': report,
        'confusion_matrix': cm.tolist(),
        'label_mapping': {
            'label2id': label2id,
            'id2label': id2label
        },
        'data_split': {
            'train_size': len(X_train),
            'val_size': len(X_val),
            'test_size': len(X_test)
        }
    }

    results_file = output_dir / 'quick_split_results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n✓ Results saved to {results_file}")
    print(f"\nTest Set Performance:")
    print(f"  Accuracy: {test_results['eval_accuracy']:.4f}")
    print(f"  F1 (weighted): {test_results['eval_f1_weighted']:.4f}")
    print(f"\nClassification Report:")
    print(report)

    # Save model
    model_save_path = output_dir / 'best_model'
    trainer.save_model(str(model_save_path))
    tokenizer.save_pretrained(str(model_save_path))
    print(f"\n✓ Model saved to {model_save_path}")

    return results


def train_cross_validation(
    df: pd.DataFrame,
    label2id: Dict[str, int],
    id2label: Dict[int, str],
    model_name: str,
    output_dir: Path,
    args: argparse.Namespace
):
    """Train with 10-fold stratified cross-validation."""
    print("\n" + "="*60)
    print("10-FOLD CROSS-VALIDATION")
    print("="*60)

    # Prepare data
    df['label_id'] = df['label'].map(label2id)
    texts = np.array(df['context'].tolist())
    labels = np.array(df['label_id'].tolist())

    # Initialize cross-validation
    skf = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)

    all_fold_results = []
    all_predictions = []
    all_labels = []

    # Perform cross-validation
    for fold_idx, (train_idx, val_idx) in enumerate(skf.split(texts, labels), 1):
        print(f"\n{'='*60}")
        print(f"FOLD {fold_idx}/10")
        print(f"{'='*60}")

        X_train, X_val = texts[train_idx].tolist(), texts[val_idx].tolist()
        y_train, y_val = labels[train_idx].tolist(), labels[val_idx].tolist()

        print(f"Train: {len(X_train)}, Val: {len(X_val)}")

        # Initialize model for this fold
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            num_labels=len(label2id),
            id2label=id2label,
            label2id=label2id
        )

        # Create datasets
        train_dataset = EpistemicMarkerDataset(X_train, y_train, tokenizer, args.max_length)
        val_dataset = EpistemicMarkerDataset(X_val, y_val, tokenizer, args.max_length)

        # Compute class weights for this fold
        class_weights = compute_class_weight(
            'balanced',
            classes=np.unique(y_train),
            y=y_train
        )
        class_weights_tensor = torch.tensor(class_weights, dtype=torch.float32)

        # Calculate steps per epoch for this fold
        steps_per_epoch = len(X_train) // (args.batch_size * args.gradient_accumulation_steps)

        # Determine evaluation settings
        if args.eval_strategy == 'epoch':
            eval_steps = None
        else:
            if args.eval_steps is None:
                eval_steps = max(10, steps_per_epoch // 2)
            else:
                eval_steps = args.eval_steps

        # Training arguments
        fold_output_dir = output_dir / f'fold_{fold_idx}'
        training_args_dict = {
            'output_dir': str(fold_output_dir / 'checkpoints'),
            'num_train_epochs': args.epochs,
            'per_device_train_batch_size': args.batch_size,
            'per_device_eval_batch_size': args.batch_size * 2,
            'gradient_accumulation_steps': args.gradient_accumulation_steps,
            'learning_rate': args.learning_rate,
            'warmup_ratio': args.warmup_ratio if args.warmup_steps is None else 0.0,
            'warmup_steps': args.warmup_steps if args.warmup_steps is not None else 0,
            'weight_decay': 0.01,
            'logging_dir': str(fold_output_dir / 'logs'),
            'logging_steps': 10,
            'eval_strategy': args.eval_strategy,
            'save_strategy': args.eval_strategy,
            'save_total_limit': 1,
            'load_best_model_at_end': True,
            'metric_for_best_model': 'f1_weighted',
            'greater_is_better': True,
            'fp16': args.fp16,
            'bf16': args.bf16,
            'dataloader_num_workers': 4,
            'report_to': 'none',
        }

        if args.eval_strategy == 'steps':
            training_args_dict['eval_steps'] = eval_steps
            training_args_dict['save_steps'] = eval_steps

        training_args = TrainingArguments(**training_args_dict)

        # Initialize trainer with class weights
        trainer = WeightedTrainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            compute_metrics=compute_metrics,
            callbacks=[EarlyStoppingCallback(early_stopping_patience=args.early_stopping_patience)],
            class_weights=class_weights_tensor
        )

        # Train
        print(f"Training fold {fold_idx}...")
        trainer.train()

        # Evaluate
        fold_results = trainer.evaluate(val_dataset)

        # Get predictions
        predictions = trainer.predict(val_dataset)
        y_pred = np.argmax(predictions.predictions, axis=1)

        # Store results
        all_fold_results.append(fold_results)
        all_predictions.extend(y_pred.tolist())
        all_labels.extend(y_val)

        print(f"\nFold {fold_idx} results:")
        print(f"  Accuracy: {fold_results['eval_accuracy']:.4f}")
        print(f"  F1 (weighted): {fold_results['eval_f1_weighted']:.4f}")

    # Aggregate results
    print("\n" + "="*60)
    print("CROSS-VALIDATION SUMMARY")
    print("="*60)

    # Calculate mean and std for each metric
    metrics = ['eval_accuracy', 'eval_f1_weighted', 'eval_precision_weighted', 'eval_recall_weighted']
    aggregated_results = {}

    for metric in metrics:
        values = [fold[metric] for fold in all_fold_results]
        aggregated_results[metric] = {
            'mean': np.mean(values),
            'std': np.std(values),
            'values': values
        }

    print(f"\nAggregated Results (Mean ± Std):")
    for metric, stats in aggregated_results.items():
        print(f"  {metric}: {stats['mean']:.4f} ± {stats['std']:.4f}")

    # Overall classification report
    report = classification_report(
        all_labels, all_predictions,
        target_names=[id2label[i] for i in range(len(id2label))],
        digits=4
    )

    # Overall confusion matrix
    cm = confusion_matrix(all_labels, all_predictions)

    # Save results
    results = {
        'mode': 'cross_validation',
        'model': model_name,
        'n_folds': 10,
        'aggregated_metrics': aggregated_results,
        'fold_results': all_fold_results,
        'classification_report': report,
        'confusion_matrix': cm.tolist(),
        'label_mapping': {
            'label2id': label2id,
            'id2label': id2label
        }
    }

    results_file = output_dir / 'cv_results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n✓ Results saved to {results_file}")
    print(f"\nOverall Classification Report:")
    print(report)

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Train epistemic markers classifier'
    )
    parser.add_argument(
        '--task',
        required=True,
        choices=['use_type', 'certainty'],
        help='Classification task'
    )
    parser.add_argument(
        '--mode',
        required=True,
        choices=['quick', 'cv'],
        help='Training mode: quick split or cross-validation'
    )
    parser.add_argument(
        '--data',
        required=True,
        help='Path to preprocessed CSV data'
    )
    parser.add_argument(
        '--model',
        default='xlm-roberta-base',
        help='Pretrained model name (default: xlm-roberta-base)'
    )
    parser.add_argument(
        '--output-dir',
        default='models',
        help='Output directory for models and results'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=16,
        help='Training batch size (default: 16)'
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=5,
        help='Number of training epochs (default: 5)'
    )
    parser.add_argument(
        '--learning-rate',
        type=float,
        default=2e-5,
        help='Learning rate (default: 2e-5)'
    )
    parser.add_argument(
        '--max-length',
        type=int,
        default=256,
        help='Maximum sequence length (default: 256)'
    )
    parser.add_argument(
        '--gradient-accumulation-steps',
        type=int,
        default=1,
        help='Gradient accumulation steps (default: 1)'
    )
    parser.add_argument(
        '--fp16',
        action='store_true',
        help='Use mixed precision training (fp16)'
    )
    parser.add_argument(
        '--bf16',
        action='store_true',
        help='Use bfloat16 mixed precision (recommended for A100)'
    )
    parser.add_argument(
        '--warmup-ratio',
        type=float,
        default=0.1,
        help='Warmup ratio (fraction of total steps, default: 0.1)'
    )
    parser.add_argument(
        '--warmup-steps',
        type=int,
        default=None,
        help='Warmup steps (overrides warmup-ratio if set)'
    )
    parser.add_argument(
        '--eval-steps',
        type=int,
        default=None,
        help='Evaluation steps (default: auto-calculated as 10% of epoch)'
    )
    parser.add_argument(
        '--eval-strategy',
        choices=['steps', 'epoch'],
        default='epoch',
        help='Evaluation strategy: steps or epoch (default: epoch for stability)'
    )
    parser.add_argument(
        '--early-stopping-patience',
        type=int,
        default=5,
        help='Early stopping patience (default: 5)'
    )

    args = parser.parse_args()

    # Setup output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) / args.task / f"{args.mode}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output directory: {output_dir}")

    # Load data
    df, label2id, id2label = load_and_prepare_data(args.data)

    # Train based on mode
    if args.mode == 'quick':
        results = train_quick_split(df, label2id, id2label, args.model, output_dir, args)
    else:  # cv
        results = train_cross_validation(df, label2id, id2label, args.model, output_dir, args)

    print("\n✅ Training complete!")


if __name__ == '__main__':
    main()

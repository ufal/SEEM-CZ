#!/usr/bin/env python3
"""
Inter-Annotator Agreement Calculator

This script computes inter-annotator agreement for various features between
multiple independent annotation files. Annotations belonging to the same example
are determined by their "cs" value.

Usage:
    python inter_annotator_agreement.py <file1> <file2> [<file3> ...] [--features <features>]

Example:
    python inter_annotator_agreement.py \
        teitok/markers/duplicate_annot/markers_VP-cs-urcite.xml \
        teitok/markers/duplicate_annot/markers_IS-cs-urcite.xml \
        teitok/markers/duplicate_annot/markers_XY-cs-urcite.xml
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import xml.etree.ElementTree as ET
import numpy as np
from statsmodels.stats.inter_rater import cohens_kappa
from sklearn.metrics import cohen_kappa_score, confusion_matrix
import krippendorff

# Import the existing markerdoc library
from markerdoc import MarkerDoc, MarkerDocDef


class WeightMatrixDistance:
    """Custom distance metric for Krippendorff's alpha that uses a weight matrix."""
    
    def __init__(self, weight_matrix: np.ndarray, value_to_index: Dict[str, int]):
        """
        Initialize the weight matrix distance metric.
        
        Args:
            weight_matrix: Weight matrix for calculating distances
            value_to_index: Mapping from string values to numeric indices
        """
        self.weight_matrix = weight_matrix
        self.value_to_index = value_to_index
        self.index_to_value = {v: k for k, v in value_to_index.items()}
        
    def __call__(self, v1, v2, i1, i2, n_v, dtype=np.float64):
        """
        Calculate distances using the weight matrix.
        
        This function signature matches krippendorff's DistanceMetric protocol.
        
        Args:
            v1, v2: Value arrays (these are numeric indices in our case)
            i1, i2: Ordinal indices (same as v1, v2 for nominal data)
            n_v: Number of pairable elements for each value (not used in our custom metric)
            dtype: Data type for results
            
        Returns:
            Distance array with same shape as broadcasted v1, v2
        """
        # Convert to appropriate types
        v1 = np.asarray(v1, dtype=int)
        v2 = np.asarray(v2, dtype=int)
        
        # Initialize distance array
        distances = np.zeros(np.broadcast(v1, v2).shape, dtype=dtype)
        
        if self.weight_matrix.ndim == 2:
            # 2D weight matrix (e.g., for "use" feature)
            # Distance = 1 - weight (so weight=1 gives distance=0, weight=0 gives distance=1)
            
            # Handle broadcasting
            v1_broadcast, v2_broadcast = np.broadcast_arrays(v1, v2)
            
            # Calculate distances using the weight matrix
            for i in range(v1_broadcast.size):
                idx1 = v1_broadcast.flat[i]
                idx2 = v2_broadcast.flat[i]
                
                # Check bounds
                if (0 <= idx1 < self.weight_matrix.shape[0] and 
                    0 <= idx2 < self.weight_matrix.shape[1]):
                    # Distance = 1 - weight (perfect agreement has weight=1, distance=0)
                    weight = self.weight_matrix[idx1, idx2]
                    distances.flat[i] = 1.0 - weight
                else:
                    # Out of bounds - maximum distance
                    distances.flat[i] = 1.0
                    
        elif self.weight_matrix.ndim == 1:
            # 1D ordinal array (e.g., for "certainty" feature)
            # Distance based on ordinal positions
            
            # Handle broadcasting
            v1_broadcast, v2_broadcast = np.broadcast_arrays(v1, v2)
            
            max_distance = np.max(self.weight_matrix) - np.min(self.weight_matrix)
            
            for i in range(v1_broadcast.size):
                idx1 = v1_broadcast.flat[i]
                idx2 = v2_broadcast.flat[i]
                
                # Check bounds
                if (0 <= idx1 < len(self.weight_matrix) and 
                    0 <= idx2 < len(self.weight_matrix)):
                    # Distance based on ordinal difference
                    ordinal_distance = abs(self.weight_matrix[idx1] - self.weight_matrix[idx2])
                    if max_distance > 0:
                        distances.flat[i] = ordinal_distance / max_distance
                    else:
                        distances.flat[i] = 0.0 if idx1 == idx2 else 1.0
                else:
                    # Out of bounds - maximum distance
                    distances.flat[i] = 1.0
        else:
            # Fallback: nominal distance (0 if equal, 1 if different)
            distances = (v1 != v2).astype(dtype)
            
        return distances


def load_marker_doc(filepath: str) -> MarkerDoc:
    """Load a MarkerDoc.
    
    Args:
        filepath: Path to the annotation file
        
    Returns:
        MarkerDoc instance
    """
    file_path = Path(filepath)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    marker_doc = MarkerDoc(str(file_path))
    
    print(f"Loaded {len(marker_doc.annot_elems)} items from {file_path.name}")
    print(f"Annotator: {marker_doc.annotator_name} ({marker_doc.annotator_id})")
    
    return marker_doc


class FeatureDefinition:
    """Represents a feature definition from markers_def.xml with possible values and weighting."""
    
    def __init__(self, key: str, values: List[str], weight_matrix: Optional[np.ndarray] = None, disabledif: Optional[str] = None):
        self.key = key
        self.values = values
        self.value_to_index = {v: i for i, v in enumerate(values)}
        self.weight_matrix = weight_matrix
        self.disabledif = disabledif
        
    def get_weight_matrix(self) -> Optional[np.ndarray]:
        """Get the weight matrix for Cohen's Kappa calculation."""
        return self.weight_matrix
    
    def get_labels(self) -> List[str]:
        """Get all possible labels/values for this feature."""
        return self.values


def load_feature_definitions(def_file: str) -> Dict[str, FeatureDefinition]:
    """Load feature definitions from markers_def.xml using MarkerDocDef.
    
    Args:
        def_file: Path to the markers_def.xml file
        
    Returns:
        Dictionary mapping feature key to FeatureDefinition
    """
    marker_def = MarkerDocDef(def_file)
    
    definitions = {}  
    
    # Get all 'select' type attributes using the existing attr_names method
    select_attr_names = marker_def.attr_names(type='select')
    
    for key in select_attr_names:
        # Get possible values using the new get_attr_values method
        values = marker_def.get_attr_values(key)
        
        if not values:
            continue
        
        # Create weight matrix based on feature type
        weight_matrix = create_weight_matrix(key, values)
        
        # Get disabledif condition
        disabledif = marker_def.get_disabledif_condition(key)
        
        definitions[key] = FeatureDefinition(key, values, weight_matrix, disabledif)
    
    return definitions


def create_weight_matrix(feature_key: str, values: List[str]) -> Optional[np.ndarray]:
    """Create a weight matrix for a feature based on its characteristics.
    
    Args:
        feature_key: The key/name of the feature
        values: List of possible values
        
    Returns:
        Weight matrix (n_values x n_values) or None for uniform weighting
    """
    n = len(values)
    
    # For certainty: ordinal scale with linear weighting
    # TODO: not sure if this works correctly with Krippendorff's alpha
    if feature_key == 'certainty':
        # Create 1D ordinal weights, keeping the order from the definition file intact
        weights = np.arange(len(values))
        return weights
    
    # For use: group certain/evidence/confirm together
    elif feature_key == 'use':
        # Values: certain, evidence, confirm, answer, other, content
        weights = np.eye(n)  # Start with identity (perfect agreement on diagonal)
        
        # Find indices of the related values
        related_group = {'certain', 'evidence', 'confirm'}
        for i, v1 in enumerate(values):
            for j, v2 in enumerate(values):
                if v1 != v2 and v1 in related_group and v2 in related_group:
                    # 50% credit for disagreements within certain/evidence/confirm
                    weights[i, j] = 0.9
        return weights
    
    # For all other features: uniform weighting (no matrix needed)
    else:
        return None


class AgreementCalculator:
    """Calculate various agreement metrics between multiple annotators."""
    
    def __init__(self, marker_docs: List[MarkerDoc], 
                 feature_definitions: Optional[Dict[str, FeatureDefinition]] = None):
        """
        Initialize the calculator with multiple annotator files.
        
        Args:
            marker_docs: List of MarkerDoc instances
            feature_definitions: Optional feature definitions for weighted metrics
        """
        self.feature_definitions = feature_definitions or {}
        
        # Group files by annotator and merge annotations from the same annotator
        self.annotator_docs = self._group_by_annotator(marker_docs)
        self.annotators = list(self.annotator_docs.keys())
        self.annotator_count = len(self.annotators)
        
        if self.annotator_count < 2:
            raise ValueError("At least two annotators are required for agreement calculation")
        
        # Group annotations by their token ID (stored in "cs" attribute) across all annotators
        self.annotation_units = self._group_annotations_by_cs()
        
        print(f"\nLoaded {len(marker_docs)} files from {self.annotator_count} unique annotators:")
        for i, annotator_id in enumerate(self.annotators):
            files_count = len(self.annotator_docs[annotator_id])
            total_items = sum(len(doc.annot_elems) for doc in self.annotator_docs[annotator_id])
            annotator_name = self.annotator_docs[annotator_id][0].annotator_name  # Get name from first file
            print(f"  {i+1}. {annotator_name} ({annotator_id}): {files_count} file(s), {total_items} items")
        
        print(f"Found {len(self.annotation_units)} common annotation units (by token ID)")
    
    def _group_annotations_by_cs(self) -> Dict[str, Dict[str, Any]]:
        """
        Group annotations by their token ID (stored in 'cs' attribute) across all annotators.
        
        Returns:
            Dictionary mapping token_id -> {annotator_id: annotation_element}
        """
        groups = {}
        
        for annotator_id, marker_docs in self.annotator_docs.items():
            # Merge all annotations from this annotator across all their files
            for marker_doc in marker_docs:
                for item_id, item_elem in marker_doc.annot_elems.items():
                    token_id = item_elem.get('cs', '')
                    if not token_id:
                        continue  # Skip items without token ID
                    
                    if token_id not in groups:
                        groups[token_id] = {}
                    
                    # If we already have an annotation for this token_id from this annotator,
                    # we could either skip it or handle the conflict. For now, we'll use the first one.
                    if annotator_id not in groups[token_id]:
                        groups[token_id][annotator_id] = item_elem
        
        # Only keep groups that have annotations from at least 2 annotators
        filtered_groups = {
            token_id: annotator_dict 
            for token_id, annotator_dict in groups.items() 
            if len(annotator_dict) >= 2
        }
        
        return filtered_groups
    
    def _group_by_annotator(self, marker_docs: List[MarkerDoc]) -> Dict[str, List[MarkerDoc]]:
        """
        Group marker documents by annotator ID.
        
        Args:
            marker_docs: List of MarkerDoc instances
            
        Returns:
            Dictionary mapping annotator_id -> list of MarkerDoc instances
        """
        annotator_groups = {}
        
        for doc in marker_docs:
            annotator_id = doc.annotator_id
            if annotator_id not in annotator_groups:
                annotator_groups[annotator_id] = []
            annotator_groups[annotator_id].append(doc)
        
        return annotator_groups

    def get_annotation_matrix(self, feature: str) -> Tuple[np.ndarray, List[str]]:
        """
        Get an MxN matrix where M is the number of annotators and N is the number of annotation units.
        
        Args:
            feature: The XML attribute name to extract
            
        Returns:
            Tuple of (annotation_matrix, unit_labels) where:
            - annotation_matrix[i,j] contains the feature value for annotator i on unit j,
              or special values: 'UNDEF_MISSING' (unit not annotated by annotator) or 
              'UNDEF_DISABLED' (attribute disabled by another attribute's value)
            - unit_labels contains the token IDs for each column
        """
        # Use ALL annotation units (not just enabled ones)
        if not self.annotation_units:
            return np.array([]), []
        
        unit_labels = sorted(self.annotation_units.keys())
        matrix = np.full((self.annotator_count, len(unit_labels)), 'UNDEF_MISSING', dtype=object)
        
        # Create mapping from annotator_id to row index
        annotator_to_idx = {annotator_id: idx for idx, annotator_id in enumerate(self.annotators)}
        
        for col_idx, token_id in enumerate(unit_labels):
            annotator_dict = self.annotation_units[token_id]
            
            # For each annotator, determine the value for this unit
            for annotator_id in self.annotators:
                row_idx = annotator_to_idx[annotator_id]
                
                if annotator_id not in annotator_dict:
                    # Annotator didn't annotate this unit at all
                    matrix[row_idx, col_idx] = 'UNDEF_MISSING'
                else:
                    item_elem = annotator_dict[annotator_id]
                    if item_elem is None:
                        matrix[row_idx, col_idx] = 'UNDEF_MISSING'
                    else:
                        # Get all values for this item to check disabledif conditions
                        item_values = dict(item_elem.attrib) if hasattr(item_elem, 'attrib') else {}
                        
                        # Check if feature is disabled for this annotation
                        if self.is_feature_disabled(feature, item_values):
                            matrix[row_idx, col_idx] = 'UNDEF_DISABLED'
                        else:
                            # Get the actual feature value
                            value = item_elem.get(feature, '')
                            matrix[row_idx, col_idx] = value if value else ''
        
        return matrix, unit_labels
    
    def print_annotation_matrix(self, feature: str, max_cols: int = 20, max_width: int = 15) -> None:
        """
        Pretty-print the annotation matrix for a given feature.
        
        Args:
            feature: The XML attribute name to display
            max_cols: Maximum number of columns to display (to prevent overwhelming output)
            max_width: Maximum width for each cell value
        """
        matrix, unit_labels = self.get_annotation_matrix(feature)
        
        if matrix.size == 0:
            print(f"No annotation matrix for feature '{feature}'")
            return
        
        # Limit the number of columns to display
        display_cols = min(len(unit_labels), max_cols)
        display_labels = unit_labels[:display_cols]
        display_matrix = matrix[:, :display_cols]
        
        print(f"\nAnnotation Matrix for feature '{feature}':")
        print(f"Showing {display_cols} of {len(unit_labels)} annotation units")
        print("=" * 80)
        
        # Helper function to truncate and format cell values
        def format_cell(value, width=max_width):
            if value == 'UNDEF_MISSING':
                return f"{'MISSING':<{width}}"[:width]
            elif value == 'UNDEF_DISABLED':
                return f"{'DISABLED':<{width}}"[:width]
            else:
                return f"{str(value):<{width}}"[:width]
        
        # Print header with column numbers instead of token IDs
        header = f"{'Annotator':<15}"
        for i in range(display_cols):
            header += f"{f'Unit{i+1}':<{max_width+1}}"
        print(header)
        print("-" * len(header))
        
        # Print each annotator's row
        for i, annotator_id in enumerate(self.annotators):
            annotator_name = self.annotator_docs[annotator_id][0].annotator_name
            row_label = f"{annotator_name[:14]:<15}"
            
            row_values = ""
            for j in range(display_matrix.shape[1]):
                cell_value = display_matrix[i, j]
                row_values += format_cell(cell_value, max_width) + " "
            
            print(row_label + row_values)
        
        if len(unit_labels) > max_cols:
            print(f"\n... and {len(unit_labels) - max_cols} more columns")
        
        # Print summary statistics
        missing_count = np.sum(matrix == 'UNDEF_MISSING')
        disabled_count = np.sum(matrix == 'UNDEF_DISABLED')
        total_cells = matrix.size
        actual_values = total_cells - missing_count - disabled_count
        
        print(f"\nMatrix Summary:")
        print(f"  Total cells: {total_cells}")
        print(f"  Actual values: {actual_values} ({actual_values/total_cells*100:.1f}%)")
        print(f"  Missing (UNDEF_MISSING): {missing_count} ({missing_count/total_cells*100:.1f}%)")
        print(f"  Disabled (UNDEF_DISABLED): {disabled_count} ({disabled_count/total_cells*100:.1f}%)")
        print("=" * 80)
    
    def calculate_simple_agreement(self, feature: str, weighted: bool = False) -> Dict[str, Any]:
        """
        Calculate simple percentage agreement for a feature across all annotators.
        
        Args:
            feature: The XML attribute name to compare
            weighted: Whether to use weighted agreement calculation
            
        Returns:
            Dictionary with agreement statistics
        """
        matrix, unit_labels = self.get_annotation_matrix(feature)
        
        if matrix.size == 0:
            return {
                'feature': feature,
                'total_units': 0,
                'missing_units': 0,
                'disabled_units': 0,
                'agreement': None,
                'error': 'No annotation units found for this feature'
            }
        
        # Get weight matrix and feature definition for weighted calculations
        weight_matrix = None
        feature_def = None
        if weighted:
            feature_def = self.feature_definitions.get(feature)
            if feature_def:
                weight_matrix = feature_def.get_weight_matrix()
        
        # Count different types of values
        total_pairs = 0
        total_agreements = 0
        weighted_agreements = 0.0  # For weighted calculations
        missing_count = 0
        disabled_count = 0
        
        for col_idx in range(matrix.shape[1]):  # For each annotation unit
            column = matrix[:, col_idx]
            
            # Count missing values (disabled values are treated as valid annotations)
            missing_in_col = sum(1 for val in column if val == 'UNDEF_MISSING')
            disabled_in_col = sum(1 for val in column if val == 'UNDEF_DISABLED')
            missing_count += missing_in_col
            disabled_count += disabled_in_col
            
            # Get valid annotation values (exclude only UNDEF_MISSING)
            valid_values = [val for val in column if val != 'UNDEF_MISSING' and (val == 'UNDEF_DISABLED' or val.strip())]
            
            if len(valid_values) < 2:
                continue  # Skip units with fewer than 2 valid annotations
            
            # Count pairwise agreements within this unit
            for i in range(len(valid_values)):
                for j in range(i + 1, len(valid_values)):
                    total_pairs += 1
                    if valid_values[i] == valid_values[j]:
                        total_agreements += 1
                        if weighted:
                            weighted_agreements += 1.0
                    elif weighted and weight_matrix is not None and feature_def:
                        # Calculate weighted agreement for disagreements
                        val1, val2 = valid_values[i], valid_values[j]
                        if val1 in feature_def.value_to_index and val2 in feature_def.value_to_index:
                            idx1 = feature_def.value_to_index[val1]
                            idx2 = feature_def.value_to_index[val2]
                            
                            # Handle different weight matrix types
                            if weight_matrix.ndim == 2:
                                # 2D matrix (e.g., for "use" feature)
                                weight = weight_matrix[idx1, idx2]
                            elif weight_matrix.ndim == 1:
                                # 1D ordinal array (e.g., for "certainty" feature)
                                # Calculate ordinal distance-based weight
                                distance = abs(weight_matrix[idx1] - weight_matrix[idx2])
                                max_distance = np.max(weight_matrix) - np.min(weight_matrix)
                                # Linear penalty: closer values get higher weight
                                weight = 1.0 - (distance / max_distance) if max_distance > 0 else 0.0
                            else:
                                weight = 0.0  # No partial credit for unknown weight formats
                            
                            weighted_agreements += weight
        
        if total_pairs == 0:
            return {
                'feature': feature,
                'total_units': len(unit_labels),
                'missing_units': missing_count,
                'disabled_units': disabled_count,
                'agreement': None,
                'error': 'No valid annotation pairs found'
            }
        
        result = {
            'feature': feature,
            'total_units': len(unit_labels),
            'missing_units': missing_count,
            'disabled_units': disabled_count,
            'total_pairs': total_pairs,
            'agreements': total_agreements,
            'disagreements': total_pairs - total_agreements,
            'agreement_percentage': (total_agreements / total_pairs) * 100,
            'weighted': weighted
        }
        
        if weighted:
            result.update({
                'weighted_agreements': weighted_agreements,
                'weighted_agreement_percentage': (weighted_agreements / total_pairs) * 100 if total_pairs > 0 else 0
            })
        
        return result
    
    def calculate_cohens_kappa(self, feature: str) -> Dict[str, Any]:
        """
        Calculate Cohen's Kappa coefficient for a feature (only for exactly 2 annotators).
        
        Args:
            feature: The XML attribute name to compare
            
        Returns:
            Dictionary with kappa statistics
        """
        if self.annotator_count != 2:
            return {
                'feature': feature,
                'kappa': None,
                'error': f'Cohen\'s Kappa only calculated for exactly 2 annotators (found {self.annotator_count})'
            }
        
        matrix, unit_labels = self.get_annotation_matrix(feature)
        
        if matrix.size == 0:
            return {
                'feature': feature,
                'kappa': None,
                'missing_units': 0,
                'disabled_units': 0,
                'error': 'No annotation units found for this feature'
            }
        
        # Count different types of values
        missing_count = 0
        disabled_count = 0
        
        # Extract annotations for both annotators
        ann1_values = []
        ann2_values = []
        
        for col_idx in range(matrix.shape[1]):
            val1 = matrix[0, col_idx]
            val2 = matrix[1, col_idx]
            
            # Count missing values (disabled values are treated as valid annotations)
            if val1 == 'UNDEF_MISSING' or val2 == 'UNDEF_MISSING':
                missing_count += 1
            if val1 == 'UNDEF_DISABLED' or val2 == 'UNDEF_DISABLED':
                disabled_count += 1
            
            # Only include if both annotators have valid values (exclude only UNDEF_MISSING)
            if (val1 != 'UNDEF_MISSING' and (val1 == 'UNDEF_DISABLED' or val1.strip()) and
                val2 != 'UNDEF_MISSING' and (val2 == 'UNDEF_DISABLED' or val2.strip())):
                ann1_values.append(val1)
                ann2_values.append(val2)
        
        if len(ann1_values) < 2:
            return {
                'feature': feature,
                'kappa': None,
                'total_units': len(unit_labels),
                'missing_units': missing_count,
                'disabled_units': disabled_count,
                'error': 'Need at least 2 data points for kappa calculation'
            }
        
        # Calculate Cohen's Kappa using statsmodels
        try:
            # Build confusion matrix using sklearn if available, otherwise manually
            try:
                from sklearn.metrics import confusion_matrix
                # Get all unique labels
                all_labels = sorted(set(ann1_values) | set(ann2_values))
                cm = confusion_matrix(ann1_values, ann2_values, labels=all_labels)
            except ImportError:
                # Build confusion matrix manually
                all_labels = sorted(set(ann1_values) | set(ann2_values))
                label_to_idx = {label: i for i, label in enumerate(all_labels)}
                k = len(all_labels)
                cm = np.zeros((k, k))
                
                for v1, v2 in zip(ann1_values, ann2_values):
                    i = label_to_idx[v1]
                    j = label_to_idx[v2]
                    cm[i, j] += 1
            
            # Use statsmodels to calculate Cohen's Kappa
            kappa_result = cohens_kappa(cm, return_results=True)
            kappa = kappa_result.kappa
            
            return {
                'feature': feature,
                'kappa': kappa,
                'kappa_type': 'unweighted',
                'total_units': len(unit_labels),
                'missing_units': missing_count,
                'disabled_units': disabled_count,
                'valid_pairs': len(ann1_values)
            }
            
        except Exception as e:
            return {
                'feature': feature,
                'kappa': None,
                'total_units': len(unit_labels),
                'missing_units': missing_count,
                'disabled_units': disabled_count,
                'error': f'Failed to calculate kappa: {str(e)}'
            }

    def calculate_krippendorffs_alpha(self, feature: str, weighted: bool = False) -> Dict[str, Any]:
        """
        Calculate Krippendorff's Alpha for a feature.
        
        Args:
            feature: The XML attribute name to compare
            
        Returns:
            Dictionary with alpha statistics
        """
        matrix, unit_labels = self.get_annotation_matrix(feature)
        
        if matrix.size == 0:
            return {
                'feature': feature,
                'alpha': None,
                'missing_units': 0,
                'disabled_units': 0,
                'error': 'No annotation units found for this feature'
            }
        
        # Count different types of values
        missing_count = np.sum(matrix == 'UNDEF_MISSING')
        disabled_count = np.sum(matrix == 'UNDEF_DISABLED')
        
        # Prepare data for Krippendorff's alpha
        # The krippendorff library expects data in the format:
        # - rows are annotators
        # - columns are annotation units
        # - missing values should be NaN or None
        
        # Convert the matrix to the format expected by krippendorff
        alpha_matrix = np.full(matrix.shape, np.nan, dtype=object)
        
        # Get all possible values from FeatureDefinition if available, otherwise from data
        feature_def = self.feature_definitions.get(feature)
        if feature_def:
            all_values = feature_def.get_labels()
        else: 
            logging.warning(f"No feature definition found for '{feature}', using observed values only")
            all_values = set()
            for i in range(matrix.shape[0]):
                for j in range(matrix.shape[1]):
                    val = matrix[i, j]
                    if val not in ['UNDEF_MISSING', 'UNDEF_DISABLED'] and val.strip():
                        all_values.add(val)
            all_values = sorted(list(all_values))

        if len(all_values) < 2:
            return {
                'feature': feature,
                'alpha': None,
                'total_units': len(unit_labels),
                'missing_units': missing_count,
                'disabled_units': disabled_count,
                'error': 'Need at least 2 different values for alpha calculation'
            }
        
        # Create a mapping from string values to numeric indices for nominal data
        value_to_index = {val: idx for idx, val in enumerate(all_values)}
        
        # Fill the alpha matrix
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                val = matrix[i, j]
                if val == 'UNDEF_MISSING':
                    alpha_matrix[i, j] = np.nan  # Missing value
                elif val == 'UNDEF_DISABLED':
                    # For disabled values, we treat them as valid annotations
                    # Use a special index for disabled state
                    alpha_matrix[i, j] = len(all_values)  # Index beyond normal values
                elif val.strip():
                    alpha_matrix[i, j] = value_to_index[val]
                else:
                    alpha_matrix[i, j] = np.nan  # Empty values treated as missing
        
        # Convert to numeric array
        try:
            alpha_matrix_numeric = alpha_matrix.astype(float)
        except ValueError:
            return {
                'feature': feature,
                'alpha': None,
                'total_units': len(unit_labels),
                'missing_units': missing_count,
                'disabled_units': disabled_count,
                'error': 'Failed to convert data to numeric format'
            }
        
        # Count valid data points (non-NaN values)
        valid_count = np.sum(~np.isnan(alpha_matrix_numeric))
        
        if valid_count < 2:
            return {
                'feature': feature,
                'alpha': None,
                'total_units': len(unit_labels),
                'missing_units': missing_count,
                'disabled_units': disabled_count,
                'error': 'Need at least 2 valid data points for alpha calculation'
            }
        
        try:
            weight_matrix = None
            if weighted:
                weight_matrix = feature_def.get_weight_matrix()

            # Determine the level of measurement based on availability of weight matrix or feature type
            measurement_type = None
            if weight_matrix is not None:
                # Use custom distance metric based on weight matrix
                custom_distance = WeightMatrixDistance(weight_matrix, value_to_index)
                level_of_measurement = custom_distance
                measurement_type = 'weighted'
            elif feature == 'certainty':
                # Ordinal data - categorical with natural ordering
                level_of_measurement = 'ordinal'
            elif feature in ['use', 'commfuntype', 'scope', 'tfpos', 'sentpos', 'neg', 'contrast', 'modalpersp']:
                # Nominal data - categorical without natural ordering
                level_of_measurement = 'nominal'
            else:
                # Default to nominal for unknown features
                level_of_measurement = 'nominal'
            
            # Calculate Krippendorff's alpha
            alpha = krippendorff.alpha(
                reliability_data=alpha_matrix_numeric,
                level_of_measurement=level_of_measurement
            )
            
            return {
                'feature': feature,
                'alpha': alpha,
                'level_of_measurement': measurement_type or level_of_measurement,
                'weighted': weighted,
                'total_units': len(unit_labels),
                'missing_units': missing_count,
                'disabled_units': disabled_count,
                'valid_values': valid_count,
                'unique_values': len(all_values)
            }
            
        except Exception as e:
            return {
                'feature': feature,
                'alpha': None,
                'total_units': len(unit_labels),
                'missing_units': missing_count,
                'disabled_units': disabled_count,
                'error': f'Failed to calculate alpha: {str(e)}'
            }
    
    def print_summary(self, features: List[str], print_matrix: bool = False, weighted: bool = False):
        """
        Print a summary of agreement across specified features.
        
        Args:
            features: List of feature names to analyze
            print_matrix: Whether to print the annotation matrix for each feature
            weighted: Whether to use weighted agreement calculation
        """
        print("\n" + "="*80)
        print("INTER-ANNOTATOR AGREEMENT SUMMARY")
        print("="*80)
        print(f"Number of annotators: {self.annotator_count}")
        for i, annotator_id in enumerate(self.annotators):
            annotator_name = self.annotator_docs[annotator_id][0].annotator_name  # Get name from first file
            print(f"  {i+1}. {annotator_name} ({annotator_id})")
        print(f"Common annotation units: {len(self.annotation_units)}")
        print("="*80)
        
        for feature in features:
            print(f"\nFeature: {feature}")
            print("-" * 80)
            
            # Optionally print the annotation matrix
            if print_matrix:
                self.print_annotation_matrix(feature)
            
            # Calculate simple agreement
            simple_result = self.calculate_simple_agreement(feature, weighted=weighted)
            
            if 'error' in simple_result:
                if 'no enabled instances' in simple_result['error'].lower() or 'no valid annotation pairs' in simple_result['error'].lower():
                    print(f"  Skipped: {simple_result['error']}")
                else:
                    print(f"  Error: {simple_result['error']}")
                continue
            
            print(f"  Total annotation units: {simple_result['total_units']}")
            print(f"  Missing units (not annotated): {simple_result['missing_units']}")
            print(f"  Disabled units (treated as valid annotations): {simple_result['disabled_units']}")
            print(f"  Total annotation pairs: {simple_result['total_pairs']}")
            print(f"  Agreements: {simple_result['agreements']}")
            print(f"  Disagreements: {simple_result['disagreements']}")
            print(f"  Simple agreement: {simple_result['agreement_percentage']:.2f}%")
            
            if weighted and 'weighted_agreements' in simple_result:
                print(f"  Weighted agreements: {simple_result['weighted_agreements']:.1f}")
                print(f"  Weighted agreement: {simple_result['weighted_agreement_percentage']:.2f}%")
            
            # Calculate Cohen's Kappa
            kappa_result = self.calculate_cohens_kappa(feature)
            
            if 'error' in kappa_result:
                print(f"  Cohen's Kappa: {kappa_result['error']}")
                if 'total_units' in kappa_result:
                    print(f"  (Missing: {kappa_result.get('missing_units', 0)}, Disabled treated as valid: {kappa_result.get('disabled_units', 0)})")
            else:
                kappa_type = kappa_result.get('kappa_type', 'unweighted')
                valid_pairs = kappa_result.get('valid_pairs', 0)
                
                print(f"  Cohen's Kappa ({kappa_type}): {kappa_result['kappa']:.4f}")
                print(f"  Valid annotation pairs: {valid_pairs}")
                print(f"  (Missing: {kappa_result.get('missing_units', 0)}, Disabled treated as valid: {kappa_result.get('disabled_units', 0)})")
                
                # Interpretation of Kappa
                kappa = kappa_result['kappa']
                if kappa < 0:
                    interpretation = "Poor (worse than random)"
                elif kappa < 0.20:
                    interpretation = "Slight"
                elif kappa < 0.40:
                    interpretation = "Fair"
                elif kappa < 0.60:
                    interpretation = "Moderate"
                elif kappa < 0.80:
                    interpretation = "Substantial"
                else:
                    interpretation = "Almost perfect"
                print(f"  Interpretation: {interpretation}")
            
            # Calculate Krippendorff's Alpha
            alpha_result = self.calculate_krippendorffs_alpha(feature, weighted=weighted)
            
            if 'error' in alpha_result:
                print(f"  Krippendorff's Alpha: {alpha_result['error']}")
                if 'total_units' in alpha_result:
                    print(f"  (Missing: {alpha_result.get('missing_units', 0)}, Disabled treated as valid: {alpha_result.get('disabled_units', 0)})")
            else:
                level = alpha_result.get('level_of_measurement', 'nominal')
                is_weighted = alpha_result.get('weighted', False)
                valid_values = alpha_result.get('valid_values', 0)
                unique_values = alpha_result.get('unique_values', 0)
                
                print(f"  Krippendorff's Alpha ({level}): {alpha_result['alpha']:.4f}")
                print(f"  Valid data points: {valid_values}, Unique values: {unique_values}")
                print(f"  (Missing: {alpha_result.get('missing_units', 0)}, Disabled treated as valid: {alpha_result.get('disabled_units', 0)})")
                
                # Interpretation of Alpha (similar to Kappa but more conservative)
                alpha = alpha_result['alpha']
                if alpha < 0:
                    alpha_interpretation = "Poor (worse than random)"
                elif alpha < 0.20:
                    alpha_interpretation = "Slight"
                elif alpha < 0.40:
                    alpha_interpretation = "Fair"
                elif alpha < 0.60:
                    alpha_interpretation = "Moderate"
                elif alpha < 0.80:
                    alpha_interpretation = "Substantial"
                else:
                    alpha_interpretation = "Almost perfect"
                print(f"  Alpha Interpretation: {alpha_interpretation}")
    
    def is_feature_disabled(self, feature: str, item_values: Dict[str, str]) -> bool:
        """
        Check if a feature is disabled for a particular item based on disabledif conditions.
        
        Args:
            feature: The feature name to check
            item_values: Dictionary of all feature values for this item
            
        Returns:
            True if the feature is disabled, False otherwise
        """
        feature_def = self.feature_definitions.get(feature)
        if not feature_def:
            return False
        
        # Get the disabledif condition from the feature definition
        # This would need to be extracted from the XML definition
        disabledif_condition = feature_def.disabledif
        if not disabledif_condition:
            return False
        
        # Evaluate the disabledif condition
        for condition_key, condition_value in disabledif_condition:
            if item_values.get(condition_key, '') == condition_value:
                return True

        return False
    



def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Calculate inter-annotator agreement between multiple annotation files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        'files',
        type=str,
        nargs='+',
        help='Paths to annotation files (at least 2 required)'
    )
    
    parser.add_argument(
        '--features',
        type=str,
        nargs='+',
        default=['use', 'certainty', 'commfuntype', 'scope', 'tfpos', 'sentpos', 'neg', 'contrast', 'modalpersp'],
        help='List of features to analyze (default: use, certainty, commfuntype, scope, tfpos, sentpos, neg, contrast, modalpersp)'
    )
    
    parser.add_argument(
        '--def-file',
        type=str,
        default='teitok/config/markers_def.xml',
        help='Path to the markers definition file (default: teitok/config/markers_def.xml)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Optional output file for results (not yet implemented)'
    )
    
    parser.add_argument(
        '--print-matrix',
        action='store_true',
        help='Print the annotation matrix for each feature (useful for debugging)'
    )
    
    parser.add_argument(
        '--weighted',
        action='store_true',
        help='Use weighted agreement calculation (applies custom weights for "use" feature: disagreements between certain/evidence/confirm are penalized less)'
    )
    
    args = parser.parse_args()
    
    if len(args.files) < 2:
        print("Error: At least 2 annotation files are required", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Load feature definitions
        print("Loading feature definitions...")
        def_file_path = Path(args.def_file)
        if def_file_path.exists():
            feature_definitions = load_feature_definitions(str(def_file_path))
            print(f"Loaded definitions for features: {', '.join(feature_definitions.keys())}")
        else:
            print(f"Warning: Definition file not found: {def_file_path}")
            print("Proceeding without feature definitions (unweighted metrics only)")
            feature_definitions = {}
        
        # Load annotation files
        print("\nLoading annotation files...")
        marker_docs = []
        for filepath in args.files:
            marker_doc = load_marker_doc(filepath)
            marker_docs.append(marker_doc)
        
        # Calculate agreement
        calculator = AgreementCalculator(marker_docs, feature_definitions)
        calculator.print_summary(args.features, print_matrix=args.print_matrix, weighted=args.weighted)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

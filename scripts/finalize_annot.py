#!/usr/bin/env python3
"""
Script to finalize annotation files by:
1. Removing authorization tag "user"
2. Replacing obsolete "clue" attribute with "modif" attribute
3. Sorting the IDs in attributes of type="idrefs" and logging when order changes
4. Removing attributes that should be disabled according to "disabledif" rules
5. Adding missing attributes that have default values
6. Synchronizing lookup attributes with their reference attributes
"""

import argparse
import glob
import logging
import os
import sys
import xml.etree.ElementTree as ET
from markerdoc import MarkerDocDef
from bookdoc import BookDoc



def should_attribute_be_disabled(item_elem, attr_name, disabledif_conditions):
    """
    Check if an attribute should be disabled based on disabledif conditions.
    
    Args:
        item_elem: XML element for an annotation item
        attr_name: Name of the attribute to check
        disabledif_conditions: List of (attribute, value) tuples from disabledif
    
    Returns:
        True if the attribute should be disabled (removed), False otherwise
    """
    if not disabledif_conditions:
        return False
    
    # Check if any of the OR conditions are met
    for condition_attr, condition_value in disabledif_conditions:
        current_value = item_elem.attrib.get(condition_attr, "")
        if current_value == condition_value:
            return True
    
    return False

def get_dependent_lookup_attributes(attr_name, def_doc):
    """
    Get all lookup attributes that depend on a given attribute.
    
    Args:
        attr_name: Name of the attribute to find dependents for
        def_doc: MarkerDocDef instance for schema information
    
    Returns:
        List of attribute names that are lookup attributes referencing attr_name
    """
    dependent_attrs = []
    
    # Find all interp elements with type="lookup" that reference attr_name
    for interp_elem in def_doc.xml.findall(".//interp[@type='lookup']"):
        ref_attr = interp_elem.attrib.get("ref")
        if ref_attr == attr_name:
            dependent_attrs.append(interp_elem.attrib["key"])
    
    return dependent_attrs

def get_lookup_info(def_doc):
    """
    Get mapping of lookup attributes to their reference attributes and fields.
    
    Args:
        def_doc: MarkerDocDef instance for schema information
    
    Returns:
        Dict mapping lookup attribute names to (ref_attr, field) tuples
    """
    lookup_info = {}
    
    for interp_elem in def_doc.xml.findall(".//interp[@type='lookup']"):
        lookup_attr = interp_elem.attrib["key"]
        ref_attr = interp_elem.attrib.get("ref")
        field = interp_elem.attrib.get("fld", "form")  # default to "form"
        
        if ref_attr:
            lookup_info[lookup_attr] = (ref_attr, field)
    
    return lookup_info

def get_book_for_item(item_elem, books_cache, book_dir, lang="cs"):
    """
    Get BookDoc instance for the book containing this item.
    
    Args:
        item_elem: XML element for an annotation item
        books_cache: Dict cache of BookDoc instances
        book_dir: Directory containing book files
        lang: Language of the book to load ("cs" or "en")
    
    Returns:
        BookDoc instance or None if not found
    """
    book_id = item_elem.attrib.get("xml")
    if not book_id:
        return None
    
    # Create cache key that includes language
    cache_key = f"{book_id}-{lang}"
    
    if cache_key not in books_cache:
        try:
            books_cache[cache_key] = BookDoc(book_id, lang=lang, bookdir=book_dir)
        except Exception as e:
            logging.warning(f"Could not load book {book_id} for language {lang}: {e}")
            books_cache[cache_key] = None
    
    return books_cache[cache_key]

def synchronize_lookup_attributes(item_elem, def_doc, books_cache, book_dir):
    """
    Synchronize lookup attributes with their reference attributes.
    Set lookup attribute if reference exists, remove if reference doesn't exist.
    Validate and correct lookup values.
    
    Args:
        item_elem: XML element for an annotation item
        def_doc: MarkerDocDef instance for schema information
        books_cache: Dict cache of BookDoc instances
        book_dir: Directory containing book files
    
    Returns:
        True if changes were made, False otherwise
    """
    changes_made = False
    item_id = item_elem.attrib.get('id', 'unknown')
    lookup_info = get_lookup_info(def_doc)
    
    # Get file mappings from schema definition
    file_mapping = get_file_mapping(def_doc)  # e.g., {"src": "cs", "tgt": "en"}
    ref_attr_file_mapping = get_ref_attr_file_mapping(def_doc)  # e.g., {"cs": "src", "en": "tgt"}
    
    for lookup_attr, (ref_attr, field) in lookup_info.items():
        ref_value = item_elem.attrib.get(ref_attr)
        lookup_value = item_elem.attrib.get(lookup_attr)
        
        if ref_value and ref_value.strip():
            # Reference attribute exists and is not empty - lookup should be set
            
            # Check if the reference value looks like IDs rather than text
            if not looks_like_ids(ref_value):
                logging.debug(f"Item {item_id}: Reference attribute '{ref_attr}' contains text rather than IDs: '{ref_value}'. Skipping lookup synchronization for '{lookup_attr}'.")
                continue
            
            # Determine the language based on the file attribute of the reference attribute
            file_key = ref_attr_file_mapping.get(ref_attr)
            if file_key:
                lang = file_mapping.get(file_key, "cs")  # default to Czech if not found
            else:
                # Fallback: use "cs" for unknown reference attributes
                lang = "cs"
                logging.debug(f"Item {item_id}: No file mapping found for reference attribute '{ref_attr}', defaulting to Czech")
            
            # Get book for this item in the appropriate language
            book = get_book_for_item(item_elem, books_cache, book_dir, lang)
            if not book:
                logging.debug(f"Item {item_id}: Could not load {lang} book, skipping lookup synchronization for '{lookup_attr}'")
                continue
            
            expected_values = []
            
            # Get values for all referenced token IDs
            token_ids = ref_value.split()
            for token_id in token_ids:
                token_elem = book.get_token_elem(token_id)
                if token_elem is not None:
                    if field == "form":
                        # Use the text content of the token
                        token_value = token_elem.text
                    else:
                        # Use the specified attribute
                        token_value = token_elem.attrib.get(field, "")
                    
                    if token_value:
                        expected_values.append(token_value)
                else:
                    logging.warning(f"Item {item_id}: Token {token_id} not found for lookup attribute '{lookup_attr}'")
            
            expected_lookup = " ".join(expected_values)
            
            if not lookup_value:
                # Lookup attribute is missing - add it
                if expected_lookup:
                    item_elem.attrib[lookup_attr] = expected_lookup
                    logging.info(f"Item {item_id}: Added missing lookup attribute '{lookup_attr}' = '{expected_lookup}'")
                    changes_made = True
            elif lookup_value != expected_lookup:
                # Lookup attribute has wrong value - correct it
                if expected_lookup:
                    item_elem.attrib[lookup_attr] = expected_lookup
                    logging.info(f"Item {item_id}: Corrected lookup attribute '{lookup_attr}' from '{lookup_value}' to '{expected_lookup}'")
                    changes_made = True
                else:
                    # No valid tokens found - remove the lookup attribute
                    del item_elem.attrib[lookup_attr]
                    logging.info(f"Item {item_id}: Removed invalid lookup attribute '{lookup_attr}' (no valid tokens)")
                    changes_made = True
        else:
            # Reference attribute is empty or missing - lookup should not exist
            if lookup_value is not None:
                del item_elem.attrib[lookup_attr]
                logging.info(f"Item {item_id}: Removed orphaned lookup attribute '{lookup_attr}' (reference '{ref_attr}' is empty)")
                changes_made = True
    
    return changes_made

def remove_disabled_attributes(item_elem, def_doc):
    """
    Remove attributes that should be disabled according to disabledif rules,
    including their dependent lookup attributes.
    
    Args:
        item_elem: XML element for an annotation item
        def_doc: MarkerDocDef instance for schema information
    
    Returns:
        Number of attributes removed
    """
    removed_count = 0
    
    # Get all attribute names that have disabledif conditions using MarkerDocDef
    attributes_to_remove = []
    
    for attr_name in def_doc.attr_names():
        # Get the disabledif condition for this attribute using MarkerDocDef
        conditions = def_doc.get_disabledif_condition(attr_name)
        
        # Check if the attribute should be disabled
        if should_attribute_be_disabled(item_elem, attr_name, conditions):
            # Add the main attribute to removal list if it exists
            if attr_name in item_elem.attrib:
                attributes_to_remove.append(attr_name)
            
            # Also add any dependent lookup attributes
            dependent_attrs = get_dependent_lookup_attributes(attr_name, def_doc)
            for dep_attr in dependent_attrs:
                if dep_attr in item_elem.attrib:
                    attributes_to_remove.append(dep_attr)
    
    # Remove duplicates while preserving order
    attributes_to_remove = list(dict.fromkeys(attributes_to_remove))
    
    # Remove the disabled attributes
    for attr_name in attributes_to_remove:
        attr_value = item_elem.attrib[attr_name]
        del item_elem.attrib[attr_name]
        logging.info(f"Item {item_elem.attrib.get('id', 'unknown')}: "
                   f"Removed disabled attribute '{attr_name}' with value '{attr_value}'")
        removed_count += 1
    
    return removed_count

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def looks_like_ids(value):
    """
    Check if a value looks like space-separated IDs rather than text.
    
    Args:
        value: String value to check
    
    Returns:
        True if the value looks like IDs, False if it looks like text
    """
    if not value.strip():
        return False
    
    # Split by whitespace
    parts = value.split()
    
    # If only one part, check if it looks like an ID (contains colons)
    if len(parts) == 1:
        return ':' in parts[0]
    
    # For multiple parts, check if they all look like IDs
    # IDs typically contain colons and follow patterns like "cs:book:chapter:sentence:word"
    id_like_count = 0
    for part in parts:
        # Consider it ID-like if it contains colons and doesn't look like regular text
        if ':' in part and not part.endswith('.') and not part.endswith(','):
            id_like_count += 1
    
    # If most parts look like IDs, treat the whole thing as IDs
    return id_like_count >= len(parts) / 2

def check_ids_from_same_sentence(ids, item_id, attr_name):
    """
    Check if all IDs come from the same sentence (differ only in word suffix).
    
    Args:
        ids: List of ID strings
        item_id: ID of the item being checked (for logging)
        attr_name: Name of the attribute being checked (for logging)
    
    Returns:
        True if all IDs are from the same sentence, False otherwise
    """
    if len(ids) <= 1:
        return True
    
    # Extract the base part (everything before the last part which should be "w...")
    bases = []
    for id_str in ids:
        parts = id_str.split(':')
        if len(parts) >= 2 and parts[-1].startswith('w'):
            # Remove the word part to get the sentence base
            base = ':'.join(parts[:-1])
            bases.append(base)
        else:
            # If ID doesn't follow expected pattern, we can't check
            return True
    
    # Check if all bases are the same
    if len(set(bases)) > 1:
        logging.warning(f"Item {item_id}: IDs in attribute '{attr_name}' come from different sentences: {ids}")
        return False
    
    return True

def natural_sort_key(id_str):
    """
    Generate a sort key for natural sorting of IDs with numeric parts.
    
    Args:
        id_str: ID string like "cs:book:00:s1:w10"
    
    Returns:
        Tuple that can be used for natural sorting
    """
    import re
    
    # Split the ID by colons and handle each part
    parts = id_str.split(':')
    sort_key = []
    
    for part in parts:
        # Split each part into text and numeric components
        # This handles cases like "w10", "s1", etc.
        tokens = re.split(r'(\d+)', part)
        part_key = []
        for token in tokens:
            if token.isdigit():
                # Convert numeric parts to integers for proper sorting
                part_key.append(int(token))
            else:
                # Keep text parts as strings
                part_key.append(token)
        sort_key.append(tuple(part_key))
    
    return tuple(sort_key)

def sort_idrefs_in_item(item_elem, def_doc):
    """
    Sort IDs in idrefs attributes and log when order changes.
    Only sorts if the content looks like IDs rather than text.
    Uses natural sorting to handle numeric parts correctly (e.g., w9 < w10).
    
    Args:
        item_elem: XML element for an annotation item
        def_doc: MarkerDocDef instance for schema information
    """
    idrefs_attrs = def_doc.attr_names(type="idrefs")
    changes_made = False
    
    for attr_name in idrefs_attrs:
        if attr_name in item_elem.attrib:
            original_value = item_elem.attrib[attr_name]
            if original_value.strip():  # Only process non-empty values
                # Check if the content looks like IDs rather than text
                if looks_like_ids(original_value):
                    # Split IDs, remove duplicates, sort them, and rejoin
                    ids = original_value.split()
                    unique_ids = list(dict.fromkeys(ids))  # Remove duplicates while preserving order
                    
                    # Check if IDs come from the same sentence
                    check_ids_from_same_sentence(unique_ids, item_elem.attrib.get('id', 'unknown'), attr_name)
                    
                    # Use natural sorting to handle numeric parts correctly
                    sorted_ids = sorted(unique_ids, key=natural_sort_key)
                    sorted_value = " ".join(sorted_ids)
                    
                    if sorted_value != original_value:
                        # Check if we removed duplicates
                        if len(unique_ids) < len(ids):
                            duplicates_removed = len(ids) - len(unique_ids)
                            logging.info(f"Item {item_elem.attrib.get('id', 'unknown')}: "
                                       f"Removed {duplicates_removed} duplicate(s) and sorted attribute '{attr_name}' "
                                       f"from '{original_value}' to '{sorted_value}'")
                        else:
                            logging.info(f"Item {item_elem.attrib.get('id', 'unknown')}: "
                                       f"Sorted attribute '{attr_name}' from '{original_value}' "
                                       f"to '{sorted_value}'")
                        item_elem.attrib[attr_name] = sorted_value
                        changes_made = True
                else:
                    logging.debug(f"Item {item_elem.attrib.get('id', 'unknown')}: "
                                f"Skipping sort for attribute '{attr_name}' - contains text: '{original_value}'")
    
    return changes_made

def replace_clue_with_modif(item_elem):
    """
    Replace obsolete "clue" attribute with "modif" attribute.
    If both exist, keep "modif" and warn if values differ.
    
    Args:
        item_elem: XML element for an annotation item
    
    Returns:
        True if changes were made, False otherwise
    """
    changes_made = False
    item_id = item_elem.attrib.get('id', 'unknown')
    
    clue_value = item_elem.attrib.get('clue')
    modif_value = item_elem.attrib.get('modif')
    
    if clue_value is not None:  # clue attribute exists
        if modif_value is not None:  # both clue and modif exist
            if clue_value.strip() != modif_value.strip():
                logging.warning(f"Item {item_id}: 'clue' and 'modif' attributes have different values. "
                               f"clue='{clue_value}', modif='{modif_value}'. Keeping 'modif' and removing 'clue'.")
            else:
                logging.info(f"Item {item_id}: 'clue' and 'modif' attributes have the same value. "
                            f"Removing redundant 'clue' attribute.")
            
            # Remove the obsolete clue attribute
            del item_elem.attrib['clue']
            changes_made = True
            
        else:  # only clue exists, no modif
            # Replace clue with modif
            item_elem.attrib['modif'] = clue_value
            del item_elem.attrib['clue']
            logging.info(f"Item {item_id}: Replaced obsolete 'clue' attribute with 'modif'. "
                        f"Value: '{clue_value}'")
            changes_made = True
    
    return changes_made

def get_file_mapping(def_doc):
    """
    Get mapping of file keys to languages from schema definition.
    
    Args:
        def_doc: MarkerDocDef instance for schema information
    
    Returns:
        Dict mapping file keys to language extensions (e.g., {"src": "cs", "tgt": "en"})
    """
    file_mapping = {}
    
    # Find files section and extract key -> extension mapping
    for item_elem in def_doc.xml.findall(".//files/item"):
        key = item_elem.attrib.get("key")
        extension = item_elem.attrib.get("extention")  # Note: using "extention" as in the XML
        if key and extension:
            file_mapping[key] = extension
    
    return file_mapping

def get_ref_attr_file_mapping(def_doc):
    """
    Get mapping of reference attributes to their file types.
    
    Args:
        def_doc: MarkerDocDef instance for schema information
    
    Returns:
        Dict mapping reference attribute names to file keys (e.g., {"cs": "src", "en": "tgt"})
    """
    ref_attr_file_mapping = {}
    
    # Find all interp elements with type="idrefs" and extract key -> file mapping
    for interp_elem in def_doc.xml.findall(".//interp[@type='idrefs']"):
        attr_name = interp_elem.attrib.get("key")
        file_key = interp_elem.attrib.get("file")
        if attr_name and file_key:
            ref_attr_file_mapping[attr_name] = file_key
    
    return ref_attr_file_mapping

def finalize_annotation_file(input_file, output_file, def_doc, book_dir, books_cache=None, keep_author=False):
    """
    Process an annotation file by:
    1. Removing authorization tags ("user")
    2. Replacing obsolete "clue" attribute with "modif" attribute
    3. Sorting IDs in attributes of type="idrefs" and logging when order changes
    4. Removing attributes that should be disabled according to "disabledif" rules
    5. Adding missing attributes that have default values
    6. Synchronizing lookup attributes with their reference attributes
    
    Args:
        input_file: Path to input annotation XML file
        output_file: Path to output XML file
        def_doc: MarkerDocDef instance for schema definition
        book_dir: Directory containing book files for lookup validation
        books_cache: Optional shared cache for BookDoc instances
        keep_author: If True, keep the "author" attribute in the output files
    
    Returns:
        True if changes were made to the file, False otherwise
    """
    # Initialize cache if not provided
    if books_cache is None:
        books_cache = {}
    
    # Log which file is being processed
    logging.info(f"  Input: {input_file}")
    if output_file != input_file:
        logging.info(f"  Output: {output_file}")
    
    # Validate input file exists
    if not os.path.exists(input_file):
        logging.error(f"Input file not found: {input_file}")
        return False
    
    try:
        # Parse the annotation file
        tree = ET.parse(input_file)
        root = tree.getroot()
    except Exception as e:
        logging.error(f"Error parsing XML file {input_file}: {e}")
        return False
    
    changes_made = False
    
    # Remove user tags if keep_author is False
    if not keep_author:
        user_elements = root.findall('.//user')
        if user_elements:
            for user_elem in user_elements:
                root.remove(user_elem)
                logging.info(f"  Removed user element: {user_elem.attrib}")
                changes_made = True
    else:
        logging.info("  Keeping user elements as per --keep-author option")
    
    # Process each item element
    item_count = 0
    for item_elem in root.findall('.//item'):
        item_count += 1
        
        # Replace obsolete "clue" attribute with "modif"
        if replace_clue_with_modif(item_elem):
            changes_made = True
        
        if sort_idrefs_in_item(item_elem, def_doc):
            changes_made = True
        
        # Remove disabled attributes according to disabledif rules
        removed_attrs = remove_disabled_attributes(item_elem, def_doc)
        if removed_attrs > 0:
            changes_made = True
        
        # Check for missing attributes that should be present and add them with default values
        if check_missing_attributes(item_elem, def_doc):
            changes_made = True
        
        # Synchronize lookup attributes with their reference attributes
        if synchronize_lookup_attributes(item_elem, def_doc, books_cache, book_dir):
            changes_made = True
    
    logging.info(f"  Processed {item_count} annotation item(s)")
    
    # Write the modified XML to output file
    try:
        if changes_made:
            # Preserve XML declaration and formatting
            tree.write(output_file, encoding='utf-8', xml_declaration=True)
            logging.info(f"  ✓ Changes saved to: {output_file}")
        else:
            logging.info(f"  ○ No changes needed")
            # Still copy the file to output location if different
            if output_file != input_file:
                tree.write(output_file, encoding='utf-8', xml_declaration=True)
                logging.info(f"  Copied unchanged file to: {output_file}")
    except Exception as e:
        logging.error(f"Error writing output file {output_file}: {e}")
        return False
    
    return changes_made

def check_missing_attributes(item_elem, def_doc):
    """
    Check for attributes that should be present but are missing.
    An attribute should be present if it's not disabled by disabledif conditions.
    For attributes with default values, adds the missing attribute with its default value.
    
    Args:
        item_elem: XML element for an annotation item
        def_doc: MarkerDocDef instance for schema information
    
    Returns:
        True if changes were made (attributes added), False otherwise
    """
    changes_made = False
    item_id = item_elem.attrib.get('id', 'unknown')
    
    # Get all possible attribute names from the schema
    all_attr_names = def_doc.attr_names()
    
    for attr_name in all_attr_names:
        # Skip if attribute is already present
        if attr_name in item_elem.attrib:
            continue
        
        # Skip certain attribute types that are handled elsewhere or are auto-generated
        attr_type = def_doc.get_attr_type(attr_name)
        if attr_type in ["lookup", "noedit"]:
            continue
        
        # Get the disabledif condition for this attribute
        conditions = def_doc.get_disabledif_condition(attr_name)
        
        # Check if the attribute should be disabled (and thus its absence is expected)
        if should_attribute_be_disabled(item_elem, attr_name, conditions):
            # Attribute should be disabled, so its absence is correct
            continue
        
        # Check if the attribute has a default value
        default_value = def_doc.get_attr_default_value(attr_name)
        
        # If we reach here, the attribute should be present but is missing
        if default_value is not None:
            # Add the missing attribute with its default value
            item_elem.attrib[attr_name] = default_value
            logging.info(f"Item {item_id}: Added missing attribute '{attr_name}' with default value '{default_value}'")
            changes_made = True
    
    return changes_made

def main():
    """Main function to handle command line arguments and process files"""
    parser = argparse.ArgumentParser(
        description="Finalize annotation files by removing user tags, replacing obsolete 'clue' with 'modif', sorting idrefs, removing disabled attributes, adding missing attributes with default values, and synchronizing lookup attributes"
    )
    parser.add_argument(
        "input_pattern",
        help="Input annotation XML file pattern (e.g., 'markers_*.xml' or 'teitok/markers/finished/*.xml'). Can be a single file or glob pattern."
    )
    parser.add_argument(
        "-o", "--output-dir",
        help="Output directory path (default: overwrites input files in place). If specified, processed files will be saved to this directory with the same filenames."
    )
    parser.add_argument(
        "-s", "--schema",
        default="teitok/config/markers_def.xml",
        help="Schema definition file (default: teitok/config/markers_def.xml)"
    )
    parser.add_argument(
        "-b", "--book-dir",
        default="teitok/01.csen_data",
        help="Directory containing book files for lookup validation (default: teitok/01.csen_data)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what files would be processed without actually processing them"
    )
    parser.add_argument(
        "--keep-author",
        action="store_true",
        help="Keep author information in the output files"
    )
    
    args = parser.parse_args()
    
    setup_logging()
    
    # Expand glob pattern to get list of files
    input_files = glob.glob(args.input_pattern)
    
    if not input_files:
        logging.error(f"No files found matching pattern: {args.input_pattern}")
        sys.exit(1)
    
    # Sort files for consistent processing order
    input_files.sort()
    
    logging.info(f"Found {len(input_files)} file(s) matching pattern: {args.input_pattern}")
    
    if args.dry_run:
        logging.info("Dry run mode - showing files that would be processed:")
        for file_path in input_files:
            logging.info(f"  Would process: {file_path}")
        return
    
    # Validate schema file exists
    if not os.path.exists(args.schema):
        logging.error(f"Schema file not found: {args.schema}")
        sys.exit(1)
    
    # Validate book directory exists
    if not os.path.exists(args.book_dir):
        logging.error(f"Book directory not found: {args.book_dir}")
        sys.exit(1)
    
    # Create output directory if specified
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        logging.info(f"Output directory: {args.output_dir}")
    
    # Load schema definition once for all files
    logging.info(f"Loading schema definition: {args.schema}")
    def_doc = MarkerDocDef(args.schema)
    
    # Shared cache for BookDoc instances across all files
    books_cache = {}
    
    # Track statistics
    total_files = len(input_files)
    processed_files = 0
    files_with_changes = 0
    total_missing_attrs = 0
    
    # Process each file
    for input_file in input_files:
        try:
            # Determine output file path
            if args.output_dir:
                filename = os.path.basename(input_file)
                output_file = os.path.join(args.output_dir, filename)
            else:
                output_file = input_file
            
            logging.info(f"Processing file {processed_files + 1}/{total_files}: {input_file}")
            
            # Process the file
            changes_made = finalize_annotation_file(input_file, output_file, def_doc, args.book_dir, books_cache, keep_author=args.keep_author)

            if changes_made:
                files_with_changes += 1
            
            processed_files += 1
            
        except Exception as e:
            logging.error(f"Error processing file {input_file}: {e}")
            # Continue with other files instead of exiting
            continue
    
    # Print summary statistics
    logging.info(f"Processing completed:")
    logging.info(f"  Total files: {total_files}")
    logging.info(f"  Successfully processed: {processed_files}")
    logging.info(f"  Files with changes: {files_with_changes}")
    logging.info(f"  Files without changes: {processed_files - files_with_changes}")
    logging.info(f"  BookDoc cache size: {len(books_cache)} book(s)")
    
    if processed_files < total_files:
        logging.warning(f"  Failed to process: {total_files - processed_files} file(s)")
        sys.exit(1)

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Script to finalize annotation files by:
1. Removing authorization tag "user"
2. Replacing obsolete "clue" attribute with "modif" attribute
3. Sorting the IDs in attributes of type="idrefs" and logging when order changes
4. Removing attributes that should be disabled according to "disabledif" rules
5. Synchronizing lookup attributes with their reference attributes
"""

import argparse
import logging
import os
import sys
import xml.etree.ElementTree as ET
from markerdoc import MarkerDocDef
from bookdoc import BookDoc

def parse_disabledif_condition(disabledif_str):
    """
    Parse a disabledif condition string and return a list of conditions.
    
    Args:
        disabledif_str: String like "use=answer|use=other|use=content" or "scope=member|scope=ellipsis"
    
    Returns:
        List of tuples (attribute, value) representing the conditions
    """
    if not disabledif_str:
        return []
    
    conditions = []
    # Split by | for OR conditions
    parts = disabledif_str.split('|')
    for part in parts:
        if '=' in part:
            attr, value = part.split('=', 1)
            conditions.append((attr.strip(), value.strip()))
    
    return conditions

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
            if lookup_value:
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
    
    # Get all interp elements with disabledif conditions
    interp_elements = def_doc.xml.findall(".//interp[@disabledif]")
    
    attributes_to_remove = []
    
    for interp_elem in interp_elements:
        attr_name = interp_elem.attrib["key"]
        disabledif_str = interp_elem.attrib["disabledif"]
        
        # Parse the disabledif condition
        conditions = parse_disabledif_condition(disabledif_str)
        
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

def sort_idrefs_in_item(item_elem, def_doc):
    """
    Sort IDs in idrefs attributes and log when order changes.
    Only sorts if the content looks like IDs rather than text.
    
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
                    
                    sorted_ids = sorted(unique_ids)
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

def finalize_annotation_file(input_file, output_file, schema_file, book_dir):
    """
    Process an annotation file by:
    1. Removing authorization tags ("user")
    2. Replacing obsolete "clue" attribute with "modif" attribute
    3. Sorting IDs in attributes of type="idrefs" and logging when order changes
    4. Removing attributes that should be disabled according to "disabledif" rules
    5. Synchronizing lookup attributes with their reference attributes
    
    Args:
        input_file: Path to input annotation XML file
        output_file: Path to output XML file
        schema_file: Path to schema definition XML file
        book_dir: Directory containing book files for lookup validation
    """
    # Log which file is being processed
    logging.info(f"Processing annotation file: {input_file}")
    logging.info(f"Using schema definition: {schema_file}")
    logging.info(f"Using book directory: {book_dir}")
    logging.info(f"Output will be saved to: {output_file}")
    
    # Load the schema definition
    def_doc = MarkerDocDef(schema_file)
    
    # Parse the annotation file
    tree = ET.parse(input_file)
    root = tree.getroot()
    
    changes_made = False
    books_cache = {}  # Cache for BookDoc instances
    
    # Remove user tags
    user_elements = root.findall('.//user')
    if user_elements:
        for user_elem in user_elements:
            root.remove(user_elem)
            logging.info(f"Removed user element: {user_elem.attrib}")
            changes_made = True
    
    # Process each item element
    for item_elem in root.findall('.//item'):
        # Replace obsolete "clue" attribute with "modif"
        if replace_clue_with_modif(item_elem):
            changes_made = True
        
        if sort_idrefs_in_item(item_elem, def_doc):
            changes_made = True
        
        # Remove disabled attributes according to disabledif rules
        removed_attrs = remove_disabled_attributes(item_elem, def_doc)
        if removed_attrs > 0:
            changes_made = True
        
        # Synchronize lookup attributes with their reference attributes
        if synchronize_lookup_attributes(item_elem, def_doc, books_cache, book_dir):
            changes_made = True
    
    # Write the modified XML to output file
    if changes_made:
        # Preserve XML declaration and formatting
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
        logging.info(f"Finalized annotation file saved to: {output_file}")
    else:
        logging.info("No changes needed in the annotation file")
        # Still copy the file to output location
        tree.write(output_file, encoding='utf-8', xml_declaration=True)

def main():
    """Main function to handle command line arguments and process files"""
    parser = argparse.ArgumentParser(
        description="Finalize annotation files by removing user tags, replacing obsolete 'clue' with 'modif', sorting idrefs, removing disabled attributes, and synchronizing lookup attributes"
    )
    parser.add_argument(
        "input_file",
        help="Input annotation XML file (e.g., markers_gold-cs-asi.xml)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: overwrites input file)"
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
    
    args = parser.parse_args()
    
    setup_logging()
    
    # Validate input file exists
    if not os.path.exists(args.input_file):
        logging.error(f"Input file not found: {args.input_file}")
        sys.exit(1)
    
    # Validate schema file exists
    if not os.path.exists(args.schema):
        logging.error(f"Schema file not found: {args.schema}")
        sys.exit(1)
    
    # Validate book directory exists
    if not os.path.exists(args.book_dir):
        logging.error(f"Book directory not found: {args.book_dir}")
        sys.exit(1)
    
    # Determine output file
    output_file = args.output if args.output else args.input_file
    
    try:
        finalize_annotation_file(args.input_file, output_file, args.schema, args.book_dir)
        logging.info("Processing completed successfully")
    except Exception as e:
        logging.error(f"Error processing file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
from collections import defaultdict
import logging
import xml.etree.ElementTree as xmlparser

class MarkerDoc:

    def __init__(self, file):
        self.xml = xmlparser.parse(file)
        self.annot_elems = self._annots()
        self._booklist = None

    def __iter__(self):
        return iter(self.annot_elems.values())

    def _annots(self):
        return {e.attrib["id"]:e for e in self.xml.findall(".//item")}

    def _extract_booklist(self):
        return list(set([itemelem.attrib["xml"] for itemelem in self]))

    @property
    def booklist(self):
        if not self._booklist:
            self._booklist = self._extract_booklist()
        return self._booklist

    @property
    def ids(self):
        return self.annot_elems.keys()

    def annots_by_bookid(self, bookid):
        return [itemelem for itemelem in self.annot_elems.values() if itemelem.attrib["xml"] == bookid]

    def annot_by_id(self, annot_id):
        return self.annot_elems.get(annot_id)


class MarkerDocDef:

    def __init__(self, file):
        self.xml = xmlparser.parse(file)
        self._build_type_index()
        self._build_display_index()
        self._build_disabledif_index()

    def _build_display_index(self):
        self._key_display_index = {}
        self._value_display_index = {}
        for interp_elem in self.xml.findall(".//interp"):
            key = interp_elem.attrib["key"]
            self._key_display_index[key] = interp_elem.attrib["display"]
            self._value_display_index[key] = {}
            for option_elem in interp_elem.findall("./option"):
                val = option_elem.attrib["value"]
                self._value_display_index[key][val] = option_elem.attrib["display"]

    def _build_type_index(self):
        self._all_attr_names = []
        self._type_index = {}
        self._ref_index = {}
        for interp_elem in self.xml.findall(".//interp"):
            key = interp_elem.attrib["key"]
            self._all_attr_names.append(key)
            attr_type = interp_elem.attrib.get("type", "input")
            self._type_index[key] = attr_type
            if attr_type == "lookup":
                ref = interp_elem.attrib["ref"]
                self._ref_index[key] = ref

    def _build_disabledif_index(self):
        self._disabledif_index = {}
        for interp_elem in self.xml.findall(".//interp"):
            key = interp_elem.attrib["key"]
            disabledif = interp_elem.attrib.get("disabledif")
            if not key or not disabledif:
                continue
            # Parse the disabledif condition
            # Format: "use=answer|use=other|use=content"
            conditions = [condition.strip().split('=', 1) for condition in disabledif.split('|') if '=' in condition]
            self._disabledif_index[key] = conditions

    def get_display_string(self, key, value=None):
        if value is None:
            return self._key_display_index.get(key, key)
        #logging.debug(f"{value = }")
        if key not in self._value_display_index:
            return value
        split_values = value.split(",")
        split_displays = [self._value_display_index[key].get(v, v) for v in split_values]
        return ", ".join(split_displays)

    def attr_names(self, type=None, ref=None):
        names = self._all_attr_names
        if type:
            names = [name for name in names if self._type_index[name] == type]
        if ref:
            names = [name for name in names if self._ref_index[name] == ref]
        return names
    
    def get_attr_type(self, key):
        """Get the type of an attribute (e.g., 'select', 'input', 'lookup')."""
        return self._type_index.get(key, "input")
    
    def get_attr_values(self, key):
        """Get all possible values for a select-type attribute.
        
        Args:
            key: The attribute key
            
        Returns:
            List of possible values, or empty list if not a select type or no values defined
        """
        if key not in self._value_display_index:
            return []
        return list(self._value_display_index[key].keys())
    
    def get_disabledif_condition(self, key):
        """Get the disabledif condition for a given attribute key.
        
        Args:
            key: The attribute key

        Returns:
            The disabledif condition as a list of tuples (attr, value), or an empty list if not found
        """
        return self._disabledif_index.get(key, [])

class MarkerDocCollection:
    """Collection of multiple MarkerDoc instances for cross-file book grouping."""
    
    def __init__(self, file_paths=None):
        """Initialize collection with optional list of file paths.
        
        Args:
            file_paths: List of paths to marker XML files
        """
        self.marker_docs = {}  # file_path -> MarkerDoc
        self.file_paths = file_paths or []
        self._book_items_cache = None
        
        # Load files if provided
        for file_path in self.file_paths:
            self.add_file(file_path)
    
    def add_file(self, file_path):
        """Add a marker file to the collection.
        
        Args:
            file_path: Path to marker XML file
        """
        try:
            self.marker_docs[file_path] = MarkerDoc(file_path)
            self._book_items_cache = None  # Invalidate cache
        except Exception as e:
            logging.error(f"Failed to load marker file {file_path}: {e}")
    
    def get_all_book_ids(self):
        """Get all unique book IDs across all marker documents.
        
        Returns:
            Set of book IDs
        """
        all_book_ids = set()
        for marker_doc in self.marker_docs.values():
            all_book_ids.update(marker_doc.booklist)
        return all_book_ids
    
    def get_items_by_book_id(self, book_id):
        """Get all items referencing a specific book across all marker documents.
        
        Args:
            book_id: Book identifier
            
        Returns:
            List of tuples (file_path, item_element, marker_doc)
        """
        items = []
        for file_path, marker_doc in self.marker_docs.items():
            book_items = marker_doc.annots_by_bookid(book_id)
            for item in book_items:
                items.append((file_path, item, marker_doc))
        return items
    
    def get_all_items_grouped_by_book(self):
        """Get all items grouped by book ID across all marker documents.
        
        Returns:
            Dict mapping book_id -> list of (file_path, item_element, marker_doc) tuples
        """
        if self._book_items_cache is not None:
            return self._book_items_cache
        
        book_items = {}
        for book_id in self.get_all_book_ids():
            book_items[book_id] = self.get_items_by_book_id(book_id)
        
        self._book_items_cache = book_items
        return book_items
    
    def get_file_count(self):
        """Get number of loaded marker files."""
        return len(self.marker_docs)
    
    def get_total_item_count(self):
        """Get total number of items across all files."""
        return sum(len(doc.annot_elems) for doc in self.marker_docs.values())

import logging
import xml.etree.ElementTree as xmlparser

class MarkerDoc:

    def __init__(self, file):
        self.xml = xmlparser.parse(file)
        self.annot_elems = self._annots()
        self._booklist = None

    def __iter__(self):
        return iter(self.annot_elems)

    def _annots(self):
        return self.xml.findall(".//item")

    def _extract_booklist(self):
        return list(set([itemelem.attrib["xml"] for itemelem in self.annot_elems]))

    @property
    def booklist(self):
        if not self._booklist:
            self._booklist = self._extract_booklist()
        return self._booklist

    def annots_by_bookid(self, bookid):
        return [itemelem for itemelem in self.annot_elems if itemelem.attrib["xml"] == bookid]


class MarkerDocDef:

    def __init__(self, file):
        self.xml = xmlparser.parse(file)
        self._build_display_index()

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

    def get_display_string(self, key, value=None):
        if value is None:
            return self._key_display_index.get(key, key)
        #logging.debug(f"{value = }")
        if key not in self._value_display_index:
            return value
        split_values = value.split(",")
        split_displays = [self._value_display_index[key].get(v, v) for v in split_values]
        return ", ".join(split_displays)

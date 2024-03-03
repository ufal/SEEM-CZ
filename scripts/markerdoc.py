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

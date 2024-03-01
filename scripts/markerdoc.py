import xml.etree.ElementTree as xmlparser

class MarkerDoc:

    def __init__(self, file):
        self.xml = xmlparser.parse(file)
        self._booklist = None

    def _extract_booklist(self):
        return list(set([itemelem.attrib["xml"] for itemelem in self.xml.findall(".//item")]))

    @property
    def booklist(self):
        if not self._booklist:
            self._booklist = self._extract_booklist()
        return self._booklist

    def annots_by_bookid(self, bookid):
        return self.xml.findall(f".//item[@xml=\"{bookid}\"]")


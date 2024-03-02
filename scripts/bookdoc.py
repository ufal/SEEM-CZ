import xml.etree.ElementTree as xmlparser

class BookDoc:
    
    def __init__(self, file):
        self.xml = xmlparser.parse(file)
        self._sent_index = None

    def _load_sent_tok_index(self):
        sent_index = {}
        tok_index = {}
        for sentelem in self.xml.findall('.//s'):
            sid = sentelem.attrib["id"]
            for tokelem in sentelem:
                tok_index[tokelem.attrib["id"]] = 
            sent = " ".join([tokelem.text for tokelem in sentelem])
            sent_index[sid] = sent
        return sent_index

    @property
    def sent_index(self):
        if not self._sent_index:
            self._sent_index = self._load_sent_index()
        return self._sent_index

    def tok_index(self):
        if not self._tok_index:
            self._tok_index = self._load_tok_index()
        return self._tok_index
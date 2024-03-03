import logging
import os
import xml.etree.ElementTree as xmlparser

class BookDoc:
    
    def __init__(self, bookid, lang="cs", bookdir=""):
        self.id = bookid
        self.lang = lang
        filepath = os.path.join(bookdir, f"{bookid}-{lang}.xml")
        self.xml = xmlparser.parse(filepath)
        self._sent_index = None
        self._tok_index = None

    def _load_sent_tok_index(self):
        sent_index = {}
        tok_index = {}
        for sentelem in self.xml.findall('.//s'):
            sid = sentelem.attrib["id"]
            senttoks = []
            for tokelem in sentelem.findall('.//tok'):
                #logging.debug(f"{tokelem = }")
                senttoks.append(tokelem.text)
                tok_index[tokelem.attrib["id"]] = tokelem.text
            sent_index[sid] = " ".join(senttoks)
        return sent_index, tok_index

    @property
    def sent_index(self):
        if not self._sent_index:
            self._sent_index, self._tok_index = self._load_sent_tok_index()
        return self._sent_index

    @property
    def tok_index(self):
        if not self._tok_index:
            self._sent_index, self._tok_index = self._load_sent_tok_index()
        return self._tok_index

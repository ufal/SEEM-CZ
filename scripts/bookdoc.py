import logging
import os
import xml.etree.ElementTree as xmlparser

class BookDoc:
    
    def __init__(self, bookid, lang="cs", bookdir=""):
        self.id = bookid
        self.lang = lang
        filepath = os.path.join(bookdir, f"{bookid}-{lang}.xml")
        self.xml = xmlparser.parse(filepath)
        self._tok_seq, self._tok_index, self._sent_index = self._build_index()

    def _build_index(self):
        sent_index = {}
        tok_index = {}
        tok_seq = []
        tok_idx = 0
        for sentelem in self.xml.findall('.//s'):
            sent_start_idx = tok_idx
            for tokelem in sentelem.findall('.//tok'):
                #logging.debug(f"{tokelem = }")
                tok_index[tokelem.attrib["id"]] = tok_idx
                tok_seq.append(tokelem.text)
                tok_idx += 1
            sent_end_idx = tok_idx
            sid = sentelem.attrib["id"]
            sent_index[sid] = (sent_start_idx, sent_end_idx)
        return tok_seq, tok_index, sent_index

    def get_token(self, tokid):
        tokidx = self._tok_index.get(tokid)
        if not tokidx:
            return None
        return self._tok_seq[tokidx]

    def get_sentence(self, sentid):
        sent_range = self._sent_index.get(sentid)
        if not sent_range:
            return None
        sent_toks = self._tok_seq[sent_range[0]:sent_range[1]]
        return " ".join(sent_toks)

    def get_sentences_by_tokids(self, tokids):
        logging.debug(f"{tokids = }")
        sentids = list(set([":".join(tokid.split(":")[:-1]) for tokid in tokids]))
        return [self.get_sentence(sentid) for sentid in sorted(sentids)]

    @property
    def tok_index(self):
        if not self._tok_index:
            self._sent_index, self._tok_index = self._load_sent_tok_index()
        return self._tok_index

from collections import defaultdict
import logging
import os
import xml.etree.ElementTree as xmlparser

class WAlignDoc:
    
    def __init__(self, bookid, align_langs=("en", "cs"), waligndir=""):
        self.id = bookid
        self.align_langs = align_langs
        align_pair = "-".join(align_langs)
        filepath = os.path.join(waligndir, f"{bookid}_{align_pair}.xml")
        self.xml = xmlparser.parse(filepath)
        self._build_index()

    def _build_index(self):
        self._src2tgt = defaultdict(list)
        self._tgt2src = defaultdict(list)
        for linkelem in self.xml.findall('.//link'):
            #logging.debug(f"ALIGN SRC ID: {linkelem.attrib['src']}")
            #logging.debug(f"ALIGN TGT ID: {linkelem.attrib['tgt']}")
            self._src2tgt[linkelem.attrib["src"]].append(linkelem.attrib["tgt"])
            self._src2tgt[linkelem.attrib["tgt"]].append(linkelem.attrib["src"])

    def get_aligned(self, widstr, src_lang="cs"):
        if src_lang == self.align_langs[1]:
            return _process_str2str(widstr, self._src2tgt)
        if src_lang == self.align_langs[0]:
            return _process_str2str(widstr, self._tgt2src)
        return ""

def _process_str2str(wids, index):
    alignset = {align for wid in wids.split(" ") for align in index[wid]}
    return " ".join(sorted(alignset))

from collections import defaultdict
import logging
import os
import xml.etree.ElementTree as xmlparser

class BookDoc:
    
    def __init__(self, bookid, lang="cs", bookdir=""):
        self.id = bookid
        self.lang = lang
        filepath = os.path.join(bookdir, f"{bookid}-{lang}.xml")
        self.xml = xmlparser.parse(filepath)
        self._build_index()

    def _build_index(self):
        self._id_to_elem = {}
        self._sent_index = {}
        self._sent_id_to_elem = {}  # New index: sentence ID -> sentence element
        self._tok_index = {}
        self._tok_seq = []
        self._sentid_to_tuid = {}
        self._tuid_to_sentids = defaultdict(list)
        tok_idx = 0
        for sentelem in self.xml.findall('.//s'):
            sent_start_idx = tok_idx
            # Index sentence element by its ID
            sid = sentelem.attrib["id"]
            self._sent_id_to_elem[sid] = sentelem
            
            for tokelem in sentelem.findall('.//tok'):
                #logging.debug(f"{tokelem = }")
                self._id_to_elem[tokelem.attrib["id"]] = tokelem
                self._tok_index[tokelem.attrib["id"]] = tok_idx
                self._tok_seq.append(tokelem.text)
                tok_idx += 1
            sent_end_idx = tok_idx
            self._sent_index[sid] = (sent_start_idx, sent_end_idx)
            tuid = sentelem.attrib["tuid"]
            self._sentid_to_tuid[sid] = tuid
            self._tuid_to_sentids[tuid].append(sid)

    def get_token(self, tokid):
        tokidx = self._tok_index.get(tokid)
        if not tokidx:
            return None
        return self._tok_seq[tokidx]

    def get_token_elem(self, tokid):
        return self._id_to_elem.get(tokid)

    def get_sentence(self, sentid):
        sent_range = self._sent_index.get(sentid)
        if not sent_range:
            return None
        sent_toks = self._tok_seq[sent_range[0]:sent_range[1]]
        return " ".join(sent_toks)

    def get_sentences_by_tokids(self, tokids, with_tuids=False):
        sentids = list(set([":".join(tokid.split(":")[:-1]) for tokid in tokids]))
        sents = [self.get_sentence(sentid) for sentid in sorted(sentids)]
        tuids = None
        if with_tuids:
            tuids = [self._sentid_to_tuid.get(sentid) for sentid in sorted(sentids)]
        return sents, tuids

    def get_sentences_by_tuids(self, tuids):
        sentids = sorted(list(set([sentid for tuid in tuids for sentid in self._tuid_to_sentids[tuid]])))
        return [self.get_sentence(sentid) for sentid in sentids]

    def get_sentence_elem_by_tokid(self, tokid):
        """Get the sentence element containing the given token ID(s).
        
        Args:
            tokid: Token ID or space-delimited token IDs to search for
            
        Returns:
            The sentence element containing the token(s), or None if not found
        """
        # Handle multiple token IDs (space-delimited)
        token_ids = tokid.strip().split()
        
        # Use the first token ID to find the sentence
        if not token_ids:
            return None
            
        first_token_id = token_ids[0]
        
        # Extract sentence ID from first token ID (everything before the last colon)
        sentence_id = ":".join(first_token_id.split(":")[:-1])
        
        # Use the index for O(1) lookup
        return self._sent_id_to_elem.get(sentence_id)

    @property
    def tok_index(self):
        if not self._tok_index:
            self._sent_index, self._tok_index = self._load_sent_tok_index()
        return self._tok_index

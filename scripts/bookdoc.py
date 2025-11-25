from collections import defaultdict
import logging
import os
import re
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
        self._sent_id_to_prev_sent_id = {}
        self._tok_index = {}
        self._tok_seq = []
        self._sentid_to_tuid = {}
        self._tuid_to_sentids = defaultdict(list)
        tok_idx = 0
        prev_sid = None
        for sentelem in self.xml.findall('.//s'):
            sent_start_idx = tok_idx
            # Index sentence element by its ID
            sid = sentelem.attrib["id"]
            self._sent_id_to_elem[sid] = sentelem
            self._sent_id_to_prev_sent_id[sid] = prev_sid
            
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
            
            prev_sid = sid

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

    def get_extended_context_by_tokid(self, tokid, max_tok_len = 30, min_before_ratio = 0.8):
        """Given the tokid, the function returns all token elements from the current and previous sentence.

        Args:
            tokid: Token ID or space-delimited token IDs to search for
            max_tok_len: Maximum number of tokens returned. The context is trimmed from the left.

        Returns:
            A list of token elements from the context of the tokid token.
        """
        # Handle multiple token IDs (space-delimited)
        token_ids = tokid.strip().split()
        
        # Use the first token ID to find the sentence
        if not token_ids:
            return None
        first_token_id = token_ids[0]
        
        # Extract sentence ID from first token ID (everything before the last colon)
        sid = ":".join(first_token_id.split(":")[:-1])

        # Extract token elems from the current sentence
        sent_elem = self._sent_id_to_elem.get(sid)
        scope_tokens = sent_elem.findall('.//tok')

        # Extend the scope with tokens from the previous sentence
        prev_sid = self._sent_id_to_prev_sent_id.get(sid)
        if prev_sid:
            sent_elem = self._sent_id_to_elem.get(prev_sid)
            scope_tokens = sent_elem.findall('.//tok') + scope_tokens

        # Return the context if it does not exceed the maximum length
        if len(scope_tokens) <= max_tok_len:
            return scope_tokens

#        # Trim the context from the right side if needed
#        new_scope_tokens = scope_tokens[-max_tok_len:]
#
#        scope_ids = [tokelem.attrib["id"] for tokelem in new_scope_tokens]
#        logging.debug(f"TOK ID: {first_token_id}")
#        logging.debug(f"SCOPE IDS: {scope_ids}")
#        tokid_included_msg = "" if first_token_id in scope_ids else " (tokid not included)"
#        toks_to_log = [tokelem.text if tokelem.attrib["id"] != first_token_id else f"<{tokelem.text}>" for tokelem in new_scope_tokens]
#        logmsg = f"Context longer than {max_tok_len}{tokid_included_msg}: {' '.join(toks_to_log)}"
#        logging.warn(logmsg)


        # Find the index of first_token_id
        scope_ids = [tokelem.attrib["id"] for tokelem in scope_tokens]
        t_idx = scope_ids.index(first_token_id)

        # Calculate context sizes based on min_before_ratio
        # max_tok_len - 1 accounts for T itself
        available = max_tok_len - 1

        # Ideal split based on ratio
        ideal_before = int(available * min_before_ratio)
        ideal_after = available - ideal_before

        # Adjust based on actual available tokens
        actual_before = min(ideal_before, t_idx)
        actual_after = min(ideal_after, len(scope_tokens) - t_idx - 1)

        # If we can't fill the ideal amounts, redistribute
        if actual_before < ideal_before:
            # Can't get enough before, take more after
            actual_after = min(available - actual_before, len(scope_tokens) - t_idx - 1)
        elif actual_after < ideal_after:
            # Can't get enough after, take more before (favor preceding)
            actual_before = min(available - actual_after, t_idx)

        # Calculate start and end indices
        start = t_idx - actual_before
        end = t_idx + actual_after + 1  # +1 to include first_token_id
        
        new_scope_tokens = scope_tokens[start:end]
        toks_to_log = [tokelem.text if tokelem.attrib["id"] != first_token_id else f"<{tokelem.text}>" for tokelem in new_scope_tokens]
        logging.debug(f"Context longer than {max_tok_len}, adjusted: {' '.join(toks_to_log)}")

        return new_scope_tokens

    @property
    def tok_index(self):
        if not self._tok_index:
            self._sent_index, self._tok_index = self._load_sent_tok_index()
        return self._tok_index

    @classmethod
    def is_valid_token_id(cls, token_id):
        """Check if a token ID has the correct format.
        
        Token IDs should match the pattern: (en:|cs:).*w[0-9]+
        Examples: cs:book1:s1:w1, en:book2:s5:w23
        
        Args:
            token_id: String to validate as a token ID
            
        Returns:
            bool: True if the token ID format is valid, False otherwise
        """
        if not isinstance(token_id, str) or not token_id.strip():
            return False
        return bool(re.match(r"^(en:|cs:).*w[0-9]+$", token_id.strip()))

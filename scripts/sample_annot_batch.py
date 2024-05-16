import xml.etree.ElementTree as xmlparser
import sys
import os
import re
import argparse
from collections import defaultdict
import random
import logging

class QueryGroup:
    def __init__(self, path):
        self.query_map = {}
        if path is None:
            return
        with open(path) as query_group_fh:
            for line in query_group_fh:
                line = line.rstrip()
                qids = line.split()
                for qid in qids:
                    self.query_map[qid] = qids[0]
        
    def __getitem__(self, name):
        if name not in self.query_map:
            return name
        return self.query_map[name]

class SrclangIndex:
    def __init__(self, path, default_lang="unk"):
        self.default_lang = default_lang
        self.srclang_index = {}
        with open(path) as srclang_index_fh:
            for line in srclang_index_fh:
                line = line.rstrip()
                line_items = line.split()
                if len(line_items) < 2:
                    line_items.append(default_lang)
                self.srclang_index[line_items[0]] = line_items[1]
    
    def __getitem__(self, name):
        if name not in self.srclang_index:
            return self.default_lang
        return self.srclang_index[name]

class OutputDoc:
    def __init__(self):
        self.root_elem = xmlparser.Element('examples')
        self.xmldoc = xmlparser.ElementTree(element=self.root_elem)
    def append_sample(self, sample):
        for item in sample:
            self.root_elem.append(item)
    def write(self, path):
        self.xmldoc.write(path, encoding='utf-8', xml_declaration=True)


parser = argparse.ArgumentParser(description="A script to sample occurences and split them among the annotators")
parser.add_argument("--output-dir", type=str, default='.', help="Directory to generate outputs")
parser.add_argument("--annotators", nargs='+', default=["BS", "JS", "LP"], help="Names of annotators. If the annotator's name consists of multiple comma-delimited names, the same samples will be distributed to these annotators.")
parser.add_argument("--max-query-size", type=int, default=25, help="Maximum number of sampled occurences per query")
parser.add_argument("--grouped-queries", type=str, help="Path to a file with group of queries per line to be treated as a single query")
parser.add_argument("--srclang-index", type=str, help="Path to a file with srclang for each book id")
parser.add_argument("--srclangs", nargs='+', default=["unk"], help="Source languages to include; a separate file for each source language is made")
parser.add_argument("--equal-across-srclangs", action="store_true", help="Number of samples for each srclang will be the same")
args = parser.parse_args()

logging.basicConfig(level=logging.INFO)

query_group = QueryGroup(args.grouped_queries)
srclang_index = SrclangIndex(args.srclang_index)

#logging.debug(srclang_index)

items_per_srclang_rest = {l:defaultdict(list) for l in args.srclangs}

all_qids = set()

xml = xmlparser.parse(sys.stdin)
for occur_elem in xml.findall('.//item'):
    bookid = occur_elem.attrib["xml"]
    srclang = srclang_index[bookid]
    if srclang not in args.srclangs:
        continue
    qid = occur_elem.attrib["cql"]
    qid = query_group[qid]
    all_qids.add(qid)
    items_per_srclang_rest[srclang][f"{qid}"].append(occur_elem)

max_for_qid = None
if args.equal_across_srclangs:
    max_for_qid = {qid:min(len(items_per_srclang_rest[srclang][qid]) for srclang in args.srclangs) for qid in all_qids}

random.seed(1986)

annotators = args.annotators
output_docs = defaultdict(lambda: {srclang:OutputDoc() for srclang in args.srclangs})

for srclang in args.srclangs:
    for qid in sorted(items_per_srclang_rest[srclang], key=lambda x: int(x.split("-")[-1])):
        all_occurs = items_per_srclang_rest[srclang][qid]
        sample_size = min(max_for_qid[qid] if max_for_qid else len(all_occurs), args.max_query_size*len(args.annotators))
        sample = random.sample(range(len(all_occurs)), sample_size)
        random.shuffle(annotators)
        for aid, annotator in enumerate(annotators):
            annot_sample = sample[aid::len(args.annotators)]
            print(f"{srclang}/{qid}/{annotator}: {annot_sample}")
            if qid == "q-1":
                xmlparser.dump(all_occurs[annot_sample[0]])
            shared_annotators = annotator.split(",")
            for shared_annotator in shared_annotators:
                output_docs[shared_annotator][srclang].append_sample([all_occurs[i] for i in annot_sample])

os.makedirs(args.output_dir, exist_ok=True)
for annotator in output_docs:
    for srclang in args.srclangs:
        output_path = os.path.join(args.output_dir, f"markers_{annotator}-{srclang}.xml")
        output_docs[annotator][srclang].write(output_path)

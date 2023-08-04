import xml.etree.ElementTree as xmlparser
import argparse
import sys

parser = argparse.ArgumentParser(description="A script that combines a file with IDs for aligner and the aligner's output to a XML.")
parser.add_argument("for_align_ids_file", type=str, help="Path to a file with IDs for aligner.")
parser.add_argument("align_file", type=str, help="Path to the file with corresponding aligner's outputs.")
args = parser.parse_args()

root_elem = xmlparser.Element("walign")
xml = xmlparser.ElementTree(root_elem)

with open(args.for_align_ids_file, "r") as ids_f, open(args.align_file) as align_f:
    for ids_l, align_l in zip(ids_f, align_f):
        align_l = align_l.rstrip()
        ids_l = ids_l.rstrip("\n")
        if not align_l:
            continue
        src_ids, tgt_ids = [s.split(" ") for s in ids_l.split(" ||| ")]
        align_pairs = (p.split("-") for p in align_l.split(" "))
        for src_ord, tgt_ord in align_pairs:
            attrib = {
                "src": src_ids[int(src_ord)],
                "tgt": tgt_ids[int(tgt_ord)]
            }
            xmlparser.SubElement(root_elem, "link", attrib)
xml.write(sys.stdout, encoding="unicode", xml_declaration=True)

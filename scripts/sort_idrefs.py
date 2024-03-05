import argparse
import logging
import re
import sys
import xml.etree.ElementTree as xmlparser

from bookdoc import BookDoc
from markerdoc import MarkerDoc, MarkerDocDef

# setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Sort values of the idrefs type (and the lookup type accordingly)")
    parser.add_argument("annot_def", type=str, help="path to the annotation definition file")
    args = parser.parse_args()
    return args

def key_to_sort(value_bundle):
    token_id = value_bundle[0]
    tok_items = token_id.split(":")
    new_tok_items = tok_items[0:2] + [int(x) for x in tok_items[3:5]] + [int(tok_items[5].lstrip("w"))]
    return tuple(new_tok_items)

def main():
    args = parse_arguments()

    input_doc = MarkerDoc(sys.stdin)
    annot_def_doc = MarkerDocDef(args.annot_def)

    for annot_elem in input_doc.annot_elems:
        for idref_attr in annot_def_doc.attr_names(type="idrefs"):
            annot_value_items = annot_elem.attrib.get(idref_attr, "").split(" ")
            if not annot_value_items:
                continue
            if any([not re.match(r"^(en:|cs:).*w[0-9]+$", annot_value_item) for annot_value_item in annot_value_items]):
                continue
            lookup_attr_names = annot_def_doc.attr_names(type="lookup", ref=idref_attr)
            lookup_lists = [annot_elem.attrib[lookup_attr_name].split(" ") for lookup_attr_name in lookup_attr_names]
            
            bundles_to_sort = list(zip(annot_value_items, *lookup_lists))
            bundles_to_sort.sort(key=key_to_sort)
            sorted_annot_value_items, *sorted_lookup_lists = zip(*bundles_to_sort)
            
            annot_elem.attrib[idref_attr] = " ".join(sorted_annot_value_items)
            for i, lookup_attr_name in enumerate(lookup_attr_names):
                annot_elem.attrib[lookup_attr_name] = " ".join(sorted_lookup_lists[i])

    input_doc.xml.write(sys.stdout, encoding="unicode")

if __name__ == "__main__":
    main()


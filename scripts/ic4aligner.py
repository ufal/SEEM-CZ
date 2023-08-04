import xml.etree.ElementTree as xmlparser
import argparse
import sys

ns = {
    "" : "http://www.korpus.cz/imfSchema",
    "xsi" : "http://www.w3.org/2001/XMLSchema-instance",
}

def load_text_xml(path):
    text_xml = xmlparser.parse(path)
    sentid2words = {}
    for sent_node in text_xml.findall(".//s", ns):
        sentid = sent_node.attrib["id"]
        words = []
        for word_node in sent_node.findall(".//w", ns):
            words.append((word_node.attrib["id"], word_node.text))
        sentid2words[sentid] = words
    # add empty sentid
    sentid2words[""] = []
    return sentid2words

def extract_sent_from_sentidstr(sentidstr, sentid2words, print_ids=False):
    sentids = sentidstr.split(" ")
    sent = " ".join([w[0] if print_ids else w[1] for sentid in sentids for w in sentid2words[sentid]])
    return sent
        
parser = argparse.ArgumentParser(description="A script to convert the InterCorp format to the format for the Awesome Aligner or FastAlign")
parser.add_argument("salign_file", type=str, help="Path to a stand-off annotation of sentence alignment.")
parser.add_argument("src_file", type=str, help="Path to the document in the src language.")
parser.add_argument("tgt_file", type=str, help="Path to the document in the tgt language.")
parser.add_argument("--output-ids", type=str, help="File where IDs corresponding to the output tokens will be printed.")
args = parser.parse_args()

src_sentid2words = load_text_xml(args.src_file)
tgt_sentid2words = load_text_xml(args.tgt_file)

salign_xml = xmlparser.parse(args.salign_file)

if args.output_ids:
    ids_f = open(args.output_ids, "w")

for i, node in enumerate(salign_xml.findall(f".//link")):
    print(f"Processing link no. {i}", file=sys.stderr)
    src_sentidstr, tgt_sentidstr = node.attrib["xtargets"].split(";")
    src_sent = extract_sent_from_sentidstr(src_sentidstr, src_sentid2words)
    tgt_sent = extract_sent_from_sentidstr(tgt_sentidstr, tgt_sentid2words)
    print(f"{src_sent} ||| {tgt_sent}")
    if args.output_ids:
        src_ids = extract_sent_from_sentidstr(src_sentidstr, src_sentid2words, print_ids=True)
        tgt_ids = extract_sent_from_sentidstr(tgt_sentidstr, tgt_sentid2words, print_ids=True)
        print(f"{src_ids} ||| {tgt_ids}", file=ids_f)

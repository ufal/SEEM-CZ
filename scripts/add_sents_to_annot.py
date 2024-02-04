import argparse
import logging
import os
import sys
import xml.etree.ElementTree as xmlparser

def extract_booklist(annotxml):
    return list(set([itemelem.attrib["xml"] for itemelem in annotxml.findall(".//item")]))

def load_sent_index(bookfile):
    bookxml = xmlparser.parse(bookfile)
    sent_index = {}
    for sentelem in bookxml.findall('.//s'):
        sid = sentelem.attrib["id"]
        sent = " ".join([tokelem.text for tokelem in sentelem])
        sent_index[sid] = sent
    return sent_index

def extract_sentid(idstr):
    ids = idstr.split(" ")
    sentid_end = ids[0].rfind(":w")
    return ids[0][:sentid_end]

parser = argparse.ArgumentParser(description="For each annotation marker in the annotation file, the script adds the full Czech sentence which contains the marker")
parser.add_argument("--book-dir", type=str, help="Directory with books in the TEITOK format")
args = parser.parse_args()

logging.basicConfig(level=logging.INFO)

annotxml = xmlparser.parse(sys.stdin)
booklist = extract_booklist(annotxml)

for bookid in booklist:
    logging.info(f"Processing book: {bookid}")
    bookfile = os.path.join(args.book_dir, bookid + "-cs.xml")
    sent_index = load_sent_index(bookfile)
    for itemelem in annotxml.findall(f".//item[@xml=\"{bookid}\"]"):
        sentid = extract_sentid(itemelem.attrib["cs"])
        logging.debug(f"Storing sentence {sentid} into the annotation item {itemelem.attrib['id']}")
        itemelem.attrib["cssent"] = sent_index[sentid]

annotxml.write(sys.stdout, encoding="unicode")

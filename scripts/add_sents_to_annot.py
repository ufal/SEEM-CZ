import argparse
import logging
import sys
import xml.etree.ElementTree as xmlparser

from bookdoc import BookDoc
from markerdoc import MarkerDoc

# setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

def parse_arguments():
    parser = argparse.ArgumentParser(description="For each annotation marker in the annotation file, the script adds the full Czech sentence which contains the marker")
    parser.add_argument("--book-dir", type=str, help="Directory with books in the TEITOK format")
    parser.add_argument("--extended-ctx", action="store_true", help="Extract extended context and store it into the 'csctx' attribute")
    args = parser.parse_args()
    return args

def extract_booklist(annotxml):
    return list(set([itemelem.attrib["xml"] for itemelem in annotxml.findall(".//item")]))

def extract_sentid(idstr):
    ids = idstr.split(" ")
    sentid_end = ids[0].rfind(":w")
    return ids[0][:sentid_end]

def main():
    args = parse_arguments()

    input_doc = MarkerDoc(sys.stdin)

    for bookid in input_doc.booklist:
        logging.info(f"Processing book: {bookid}")
        book = BookDoc(bookid, lang="cs", bookdir=args.book_dir)
        for itemelem in input_doc.annots_by_bookid(bookid):
            sentid = extract_sentid(itemelem.attrib["cs"])
            logging.debug(f"Storing sentence {sentid} into the annotation item {itemelem.attrib['id']}")
            itemelem.attrib["cssent"] = book.get_sentence(sentid)

            if args.extended_ctx:
                ctx_token_elems = book.get_extended_context_by_tokid(itemelem.attrib["cs"], 50)
                ctx_tokens = [token_elem.text or "" for token_elem in ctx_token_elems]
                ctx_text = " ".join(ctx_tokens)
                itemelem.attrib["csctx"] = ctx_text
                logging.debug(f"Extended context for {itemelem.attrib['cs']}: {ctx_text}")

    input_doc.xml.write(sys.stdout, encoding="unicode", xml_declaration=True)

if __name__ == "__main__":
    main()

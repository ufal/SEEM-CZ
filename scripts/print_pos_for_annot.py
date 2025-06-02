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
    args = parser.parse_args()
    return args

def main():
    args = parse_arguments()

    input_doc = MarkerDoc(sys.stdin)

    for bookid in input_doc.booklist:
        logging.info(f"Processing book: {bookid}")
        book = BookDoc(bookid, lang="cs", bookdir=args.book_dir)
        for itemelem in input_doc.annots_by_bookid(bookid):
            for csid in itemelem.attrib["cs"].split(" "):
                logging.debug(f"Processing csid: {csid}")
                tokenelem = book.get_token_elem(csid)
                use = itemelem.attrib.get("use", "None")
                print(f"{use}\t{tokenelem.attrib['tag'][0:2]}")

if __name__ == "__main__":
    main()

import argparse
import logging
import sys

from markerdoc import MarkerDoc
from waligndoc import WAlignDoc

# setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

def parse_arguments():
    parser = argparse.ArgumentParser(description="For each annotation marker in the annotation file, the script adds the indices to the aligned words")
    parser.add_argument("--walign-dir", type=str, help="Directory with word alignemnts in the XML format")
    #parser.add_argument("--force", action="store_true", help="Fills in the word alignment even if it is non-empty for some items")
    args = parser.parse_args()
    return args

def main():
    args = parse_arguments()

    input_doc = MarkerDoc(sys.stdin)

    # avoid processing if there are items with the word align already pre-filled (unless forced)
    #prefilled = any([len(itemelem.attrib.get("en", "")) > 0 for itemelem in input_doc])
    #if prefilled and not self.force:
    #    logging.info("Word alignment already pre-filled. Skipping...")
    #    return

    for bookid in input_doc.booklist:
        logging.info(f"Processing book: {bookid}")
        walign = WAlignDoc(bookid, waligndir=args.walign_dir)
        for itemelem in input_doc.annots_by_bookid(bookid):
            envalue_old = itemelem.attrib.get("en", "")
            if envalue_old:
                logging.warning(f"Aligned en words already annotated for item {itemelem.attrib['id']}: {envalue_old}")
                continue
            envalue = walign.get_aligned(itemelem.attrib["cs"])
            itemelem.attrib["en"] = envalue
            logging.debug(f"Storing aligned ids {envalue} into the annotation item {itemelem.attrib['id']}")

    input_doc.xml.write(sys.stdout, encoding="unicode")

if __name__ == "__main__":
    main()

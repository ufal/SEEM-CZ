import xml.etree.ElementTree as xmlparser
import sys
import argparse

ns = {
    "" : "http://www.korpus.cz/imfSchema",
    "xsi" : "http://www.w3.org/2001/XMLSchema-instance",
}

parser = argparse.ArgumentParser(description="A script to add ids to <w> tags in the original Intercorp format.")
args = parser.parse_args()

for prefix, uri in ns.items():
    xmlparser.register_namespace(prefix, uri)

xml = xmlparser.parse(sys.stdin)

for s in xml.findall('.//s', ns):
    sent_id = s.attrib["id"]
    for i, w in enumerate(s.findall('.//w', ns)):
        w.attrib["id"] = f"{sent_id}:w{i+1}"

xml.write(sys.stdout, encoding="unicode")

import xml.etree.ElementTree as xmlparser
import sys
import re
import argparse

ns = {
    "" : "http://www.korpus.cz/imfSchema",
    "xsi" : "http://www.w3.org/2001/XMLSchema-instance",
}

tei_header_xml = """
<teiHeader>
    <fileDesc>
        <titleStmt>
            <author>{author}</author>
            <title>{title}</title>
        </titleStmt>
        <publicationStmt>
            <publisher>{publisher}</publisher>
            <pubPlace>{pubplace}</pubPlace>
            <date when="{pubDateYear}-{pubDateMonth}">{pubDateYear}</date>
        </publicationStmt>
    </fileDesc>
    <profileDesc>
        <langUsage>
            <language ident="{lang}">{langname}</language>
        </langUsage>
    </profileDesc>
</teiHeader>
"""

def change_root(xml):
    root = xml.getroot()
    root.attrib.pop("{"+ns["xsi"]+"}schemaLocation")
    root.tag = "TEI"

def add_tei_header(xml):
    attr_names = [
        "author",
        "title",
        "lang",
        "publisher",
        "pubplace",
        "pubDateYear",
        "pubDateMonth",
        "origyear",
        "isbn",
        "txtype",
        "original",
        "srclang",
        "translator",
        "transsex",
        "authsex",
    ]
    text_elem = xml.find(f"./text", ns)
    attrs = {attr: text_elem.attrib[attr] for attr in attr_names}
    lang_names = {
        "cs": "Czech",
        "en": "English",
    }
    attrs["langname"] = lang_names.get(attrs["lang"], "Other")
    root = xml.getroot()
    tei_header_elem = xmlparser.fromstring(tei_header_xml.format(**attrs))
    root.insert(0, tei_header_elem)

def remove_text_attrs(xml):
    text_elem = xml.find(f"./text", ns)
    for attr in text_elem.keys():
        if attr == "id":
            continue
        text_elem.attrib.pop(attr)

def process_tokens(xml):
    for s in xml.findall('.//s', ns):
        sent_id = s.attrib["id"]
        for i, w in enumerate(s.findall('.//w', ns)):
            # rename the token element from "w" to "tok" 
            w.tag = "tok"
            w.attrib["id"] = f"{sent_id}:w{i+1}"

def add_pagebreaks(xml, elem, step):
    pagenum = 1
    for i, node in enumerate(xml.findall(f".//{elem}", ns)):
        if i % step:
            continue
        node.insert(0, xmlparser.Element("pb", {"id": f"page-{pagenum}"}))
        pagenum += 1

def add_alignment_units(xml, salign_xml, align_ord, page_break=100):
    # removing all paragraphs as some alignment units are crossed with the paragraphs
    # TODO paragraphs could be treated similarly as pagebreaks => as empty-element tags
    #s_elems = xml.findall(f".//s", ns)
    #text_elem = xml.getroot().find('text', ns)
    #for p_elem in text_elem.findall('p', ns):
    #    text_elem.remove(p_elem)

    text_elem = xml.getroot().find('text', ns)
    ch_elems = list(text_elem)
    for ch_elem in ch_elems:
        text_elem.remove(ch_elem)

    for i, node in enumerate(salign_xml.findall(f".//link")):
        if page_break and i % page_break == 0:
            text_elem.append(xmlparser.Element("pb", {"id": f"page-{i+1}"}))
        sides = node.attrib["xtargets"].split(";")
        if sides[align_ord] == "":
            continue
        block_sent_ids = sides[align_ord].split(" ")
        au_elem = xmlparser.Element("au", {"tuid": f"au-{i+1}"})
        for sent_id in block_sent_ids:
            ch_elem = ch_elems.pop(0)
            # after paragraphs are shrunk to empty-element tags, they are at the same level as the "s" tags
            # just add them and do not check the ids
            while ch_elem.tag == "p":
                au_elem.append(ch_elem)
                ch_elem = ch_elems.pop(0)
            assert ch_elem.attrib["id"] == sent_id, f"Mismatch in order of sentences: {ch_elem.attrib['id']} vs. {sent_id}"
            au_elem.append(ch_elem)
        text_elem.append(au_elem)

def add_tuids(xml, salign_xml, align_ord):
    sid2tuid = {}
    for i, node in enumerate(salign_xml.findall(f".//link"), 1):
        sides = node.attrib["xtargets"].split(";")
        if sides[align_ord] == "":
            print(f"Skiping tuid=tu-{i}", file=sys.stderr)
            continue
        tu_sids = sides[align_ord].split(" ")
        for sid in tu_sids:
            sid2tuid[sid] = f"tu-{i}"

    s_elems = xml.findall(f".//s", ns)
    for s_elem in s_elems:
        sid = s_elem.attrib["id"]
        if not sid:
            print(f"Sentence ID = {sid} not defined.", file=sys.stderr)
        s_elem.attrib["tuid"] = sid2tuid[sid]



def shrink_paragraphs(xml):
    text_elem = xml.getroot().find('text', ns)
    for p_elem in text_elem.findall('p', ns):
        text_elem.append(xmlparser.Element("p", {"id": p_elem.attrib["id"]}))
        for ch in p_elem:
            text_elem.append(ch)
        text_elem.remove(p_elem)

parser = argparse.ArgumentParser(description="A script to convert the InterCorp format to the TEITOK format")
parser.add_argument("--salign-file", type=str, help="Path to a stand-off annotation of sentence alignment.")
parser.add_argument("--align-ord", type=int, choices=[0, 1], default=0, help="Path to a stand-off annotation of sentence alignment.")
args = parser.parse_args()

salign_xml = None
if args.salign_file is not None:
    salign_xml = xmlparser.parse(args.salign_file)

for prefix, uri in ns.items():
    xmlparser.register_namespace(prefix, uri)

xml = xmlparser.parse(sys.stdin)
change_root(xml)
add_tei_header(xml)
remove_text_attrs(xml)
process_tokens(xml)
if salign_xml:
    #shrink_paragraphs(xml)
    #add_alignment_units(xml, salign_xml, args.align_ord, page_break=100)
    add_tuids(xml, salign_xml, args.align_ord)
add_pagebreaks(xml, "p", 100)

xml.write(sys.stdout, encoding="unicode")

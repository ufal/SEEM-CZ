import argparse
import logging
import os
import xml.etree.ElementTree as xmlparser

from jinja2 import Environment, FileSystemLoader, select_autoescape

from bookdoc import BookDoc
from markerdoc import MarkerDoc, MarkerDocDef

# setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# Initialize Jinja2 environment
template_env = Environment(
    loader=FileSystemLoader('.'),
    autoescape=select_autoescape(['html', 'xml'])
)
        
ANNOT_ATTRS = [
    ("cs", "Výraz v češtině (ID)"),
    ("en", "Výraz v angličtině (ID)"),
    ("dictexample", "Příklad do slovníku"),
    ("use", "Užití"),
    ("certainty", "Míra jistoty"),
    ("certaintynote", "Poznámka (míra jistoty)"),
    ("commfuntype", "Typ komunikační funkce"),
    ("commfunsubtype", "Konkrétní komunikační funkce"),
    ("commfunnote", "Poznámka (komunikační funkce)"),
    ("scope", "Dosah"),
    ("pred", "Predikát"),
    ("predlemma", "Predikát (lemma)"),
    ("predtag", "Predikát (tag)"),
    ("predverbtag", "Predikát (verbtag)"),
    ("member", "Člen"),
    ("tfpos", "Pozice v AČ"),
    ("sentpos", "Místo ve větě"),
    ("neg", "Přítomnost negace"),
    ("modalpersp", "Perspektiva modality"),
    ("modif", "Modifikace"),
    ("evidence", "Evidence"),
    ("evidencetype", "Typ evidence"),
    ("comment", "Komentář"),
]

BASE_ATTRS = [
    ("id", "ID"),
    ("cql", "CQL dotaz"),
    ("xml", "ID dokumentu"),
    ("cst", "Výraz v češtině (formy)"),
    ("cssent", "Český text"),
    ("ensent", "Anglický text"),
]

INDEX_ATTRS = {
    "cs": ["cs", "pred", "member", "modif", "evidence"],
    "en": ["en"],
}

# Initialize template data
def init_template_data(annot_names):
    data = {
        'title': "Comparison of SEEM-CZ parallel annotations",
        'annot_names': annot_names,
        'annot_attrs': ANNOT_ATTRS,
        'base_attrs': BASE_ATTRS,
    }
    return data

def deref_attrs_by_book(annot_elem, book, attrs):
    for attr_name in attrs:
        tok_deref_str = annot_elem.attrib.get(attr_name, "")
        tok_ids = tok_deref_str.strip().split(" ")
        if tok_ids and tok_ids[0] in book.tok_index:
            tok_deref_str = " ".join([(token if (token := book.get_token(tokid)) else tokid) for tokid in tok_ids])
        elif tok_deref_str:
            tok_deref_str = f'"{tok_deref_str}"'
        annot_elem.attrib[attr_name + ".deref"] = tok_deref_str

def deref_index_attrs_all(doclist, bookdir):
    all_bookids = set(bookid for doc in doclist for bookid in doc.booklist)
    for bookid in all_bookids:
        csbook = BookDoc(bookid, "cs", bookdir)
        enbook = BookDoc(bookid, "en", bookdir)
        for annotdoc in doclist:
            book_annots = annotdoc.annots_by_bookid(bookid)
            for annot_elem in book_annots:
                #logging.debug(f"Dereferencing index attributes to the {lang} version of {bookid}")
                deref_attrs_by_book(annot_elem, csbook, INDEX_ATTRS["cs"])
                cssents, cstuids = csbook.get_sentences_by_tokids(annot_elem.attrib["cs"].split(" "), with_tuids=True)
                annot_elem.attrib["cssent"] = " ".join(cssents)
                deref_attrs_by_book(annot_elem, enbook, INDEX_ATTRS["en"])
                ensents = enbook.get_sentences_by_tuids(cstuids)
                annot_elem.attrib["ensent"] = " ".join(ensents) 

def extract_base_attrs(elem):
    return {attr_name: elem.attrib.get(attr_name, "") for attr_name, _ in BASE_ATTRS}

def extract_annot_attrs(elem_bundle):
    annot_attrs = {}
    for attr_name, _ in ANNOT_ATTRS:
        annot_values = [
            elem.attrib.get(
                deref_attr_name if (deref_attr_name := attr_name + ".deref") in elem.attrib else attr_name,
                "")
            if elem is not None else None for elem in elem_bundle
        ]
        annot_values_defined = [v for v in annot_values if v is not None]
        attr_value_dict = {
            "annots": ["" if v is None else v for v in annot_values],
            "all_same": all([v and v == annot_values_defined[0] for v in annot_values_defined]),
            "all_empty": all([not v for v in annot_values_defined]),
        }
        annot_attrs[attr_name] = attr_value_dict
    return annot_attrs

def extract_attrs(elem_bundle):
    non_empty_annots = [e for e in elem_bundle if e is not None]
    assert len(non_empty_annots) > 0
    assert len(list(set([elem.attrib["id"] for elem in non_empty_annots]))) == 1
    return {
        "base_attrs": extract_base_attrs(non_empty_annots[0]),
        "annot_attrs": extract_annot_attrs(elem_bundle),
    }

def iter_annot_bundles(doc_list):
    # Iterate over all unique IDs in the documents sorted in the order of the first document
    all_ids = []
    for doc in doc_list:
        for docid in doc.ids:
            if docid not in all_ids:
                all_ids.append(docid)

    for docid in all_ids:
        yield [doc.annot_by_id(docid) for doc in doc_list]

def configure_template(args):
    display_f = lambda k, v=None: v if v else k
    if args.annot_def:
        annot_def_doc = MarkerDocDef(args.annot_def)
        display_f = annot_def_doc.get_display_string
    template_env.globals['display_str'] = display_f

def render_template(template_name, **context):
    # Load the template
    template = template_env.get_template(template_name)
    # Render the template with the provided context
    return template.render(**context)

def parse_arguments():
    parser = argparse.ArgumentParser(description="compare input annotation of markers and output the comparison in HTML")
    parser.add_argument("input_files", nargs="+", help="input files to be compared")
    parser.add_argument("--book-dir", type=str, help="directory with books in the teitok format")
    parser.add_argument("--annot-def", type=str, help="path to the annotation definition file")
    args = parser.parse_args()
    return args

def main():
    args = parse_arguments()
    
    if len(args.input_files) < 2:
        logging.error("More than one input files must be specified.")
        exit()

    doc_list = [MarkerDoc(filepath) for filepath in args.input_files]

    deref_index_attrs_all(doc_list, args.book_dir)

    all_results = [extract_attrs(annot_bundle) for annot_bundle in iter_annot_bundles(doc_list)]

    #logging.debug(f"{all_results = }")

    # Define the data to pass to the template
    data = init_template_data(annot_names=[os.path.basename(file) for file in args.input_files])
    data["results"] = all_results
    #logging.debug(f"{data = }")

    configure_template(args)
    
    # Render the template
    rendered_html = render_template('template/compare_annot.html', **data)
    # Print or do whatever you want with the rendered HTML
    print(rendered_html)

if __name__ == "__main__":
    main()

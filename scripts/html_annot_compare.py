import argparse
import logging
import xml.etree.ElementTree as xmlparser

from jinja2 import Environment, FileSystemLoader, select_autoescape

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

# Initialize template data
def init_template_data():
    data = {
        'title': "Comparison of SEEM-CZ parallel annotations",
        'attrs_to_display': [
            #("cql", "CQL dotaz"),
            #("xml", "ID dokumentu"),
            #("cs", "Výraz v češtině (ID)"),
            #("cst", "Výraz v češtině (formy)"),
            #("en", "Výraz v angličtině (ID)"),
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
    }
    return data


def extract_attribs(elem_tuple):
    if len(elem_tags := list(set([elem.tag for elem in elem_tuple]))) > 1:
        logging.error(f"Parallel elements are not the same: {' '.join(elem_tags)}")
        exit()
    if elem_tags[0] != "item":
        return
    all_attr_names = set(k for elem in elem_tuple for k in elem.attrib)
    attr_table = {attr_name: [elem.attrib.get(attr_name, "") for elem in elem_tuple] for attr_name in all_attr_names}
    return attr_table

def render_template(template_name, **context):
    # Load the template
    template = template_env.get_template(template_name)
    # Render the template with the provided context
    return template.render(**context)

def parse_arguments():
    parser = argparse.ArgumentParser(description="compare input annotation of markers and output the comparison in HTML")
    parser.add_argument("input_files", nargs="+", help="input files to be compared")
    parser.add_argument("--book-dir", type=str, help="directory with books in the teitok format")
    args = parser.parse_args()
    return args

def main():
    args = parse_arguments()
    
    if len(args.input_files) < 2:
        logging.error("More than one input files must be specified.")
        exit()

    xml_list = [xmlparser.iterparse(filepath) for filepath in args.input_files]
    
    all_results = [attrs for elem_bundle in zip(*xml_list) if (attrs := extract_attribs([elem for _, elem in elem_bundle]))]

    #logging.debug(f"{all_results = }")

    # Define the data to pass to the template
    data = init_template_data()
    data["results"] = all_results
    
    # Render the template
    rendered_html = render_template('template/compare_annot.html', **data)
    # Print or do whatever you want with the rendered HTML
    print(rendered_html)

if __name__ == "__main__":
    main()

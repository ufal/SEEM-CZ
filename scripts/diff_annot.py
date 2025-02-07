import xml.etree.ElementTree as xmlparser
import sys
import argparse

parser = argparse.ArgumentParser(description="Find differences in annotations.")
parser.add_argument("file1", type=argparse.FileType('r'), help="The first file to compare.")
parser.add_argument("file2", type=argparse.FileType('r'), help="The second file to compare.")
args = parser.parse_args()

# get all "item" elements from both files
xml1 = xmlparser.parse(args.file1)
item_elements1 = xml1.findall(".//item")
xml2 = xmlparser.parse(args.file2)
item_elements2 = xml2.findall(".//item")

if len(item_elements1) != len(item_elements2):
    print("The two files have different numbers of items.")
    sys.exit(1)

# compare the two lists of items
for i, (item1, item2) in enumerate(zip(item_elements1, item_elements2)):
    for attr1 in item1.attrib:
        if attr1 not in item2.attrib:
            print(f"Item {i}: File 2 is missing attribute {attr1}.")
        elif item1.attrib[attr1] != item2.attrib[attr1]:
            print(f"Item {i}: Attribute {attr1} differs, values are '{item1.attrib[attr1]}' and '{item2.attrib[attr1]}'.")
    for attr2 in item2.attrib:
        if attr2 not in item1.attrib:
            print(f"Item {i}: File 1 is missing attribute {attr2}.")


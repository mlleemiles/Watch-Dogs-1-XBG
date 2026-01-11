from XBGParser import XBGParser

parser = XBGParser(r".\low_grassnexus_a_8x4.xbg")
meta_data = parser.parse()
print(f"Successfully parsed XBG file! LOD count: {meta_data['geomParams']['lodCount']}")
"""Fetch all stock items from Tally and save to Excel"""
import requests
import re
import xml.etree.ElementTree as ET
import pandas as pd

TALLY_URL = "http://localhost:9000"

# Step 1: Get company name
print("Fetching company name...")
company_xml = '''<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>CompanyList</ID></HEADER>
<BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES>
<TDL><TDLMESSAGE><COLLECTION NAME="CompanyList" ISMODIFY="No" ISINITIALIZE="Yes">
<TYPE>Company</TYPE><NATIVEMETHOD>Name</NATIVEMETHOD>
</COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'''

r = requests.post(TALLY_URL, data=company_xml.encode('utf-8'), 
                   headers={'Content-Type': 'text/xml; charset=utf-8'}, timeout=15)
root = ET.fromstring(r.text)
company = ''
for name in root.iter('NAME'):
    if name.text and name.text.strip():
        company = name.text.strip()
        break
print(f"Company: {company}")

# Step 2: Fetch all stock items
print("Fetching stock items...")
xml_request = f'''<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>Stock Items</ID></HEADER>
<BODY><DESC><STATICVARIABLES>
<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
</STATICVARIABLES>
<TDL><TDLMESSAGE>
<COLLECTION NAME="Stock Items" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes">
<TYPE>StockItem</TYPE>
<NATIVEMETHOD>Name</NATIVEMETHOD>
<NATIVEMETHOD>Parent</NATIVEMETHOD>
<NATIVEMETHOD>BaseUnits</NATIVEMETHOD>
</COLLECTION>
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'''

r = requests.post(TALLY_URL, data=xml_request.encode('utf-8'),
                   headers={'Content-Type': 'text/xml; charset=utf-8'}, timeout=60)

# Clean invalid XML character references (e.g. &#4;)
clean_text = re.sub(
    r'&#(\d+);',
    lambda m: m.group() if int(m.group(1)) in (9, 10, 13) or int(m.group(1)) > 31 else '',
    r.text
)

root = ET.fromstring(clean_text)

items = []
coll = root.find('.//COLLECTION')
if coll is not None:
    for si in coll.findall('STOCKITEM'):
        name = si.get('NAME', '')
        parent = si.findtext('PARENT', '')
        units = si.findtext('BASEUNITS', '')
        if name:
            items.append({'Name': name.strip(), 'Group': parent.strip(), 'Unit': units.strip()})

print(f"Found {len(items)} stock items")

# Step 3: Save to Excel
df = pd.DataFrame(items)
df.index = range(1, len(df) + 1)
df.index.name = 'S.No'
output_file = 'tally_stock_items.xlsx'
df.to_excel(output_file)
print(f"Saved to {output_file}")
print()
print("First 15 items:")
print(df.head(15).to_string())

input("\nPress Enter to exit...")

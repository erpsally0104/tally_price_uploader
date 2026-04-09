"""Debug script: try multiple voucher query approaches and save raw responses."""
import requests
import re
import xml.etree.ElementTree as ET

TALLY_URL = "http://localhost:9000"

# Step 1: Get company name
print("Fetching company name...")
company_xml = '''<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>CompanyList</ID></HEADER>
<BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES>
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

DATE = "20260401"

queries = {
    "Q1_CHILDOF_Sales": f'''<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>CustomVch</ID></HEADER>
<BODY><DESC><STATICVARIABLES>
<SVEXPORTFORMAT>$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
<SVFROMDATE>{DATE}</SVFROMDATE>
<SVTODATE>{DATE}</SVTODATE>
</STATICVARIABLES>
<TDL><TDLMESSAGE>
<COLLECTION NAME="CustomVch" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes">
<TYPE>Voucher : VoucherType</TYPE>
<CHILDOF>Sales</CHILDOF>
<NATIVEMETHOD>VoucherNumber</NATIVEMETHOD>
<NATIVEMETHOD>Date</NATIVEMETHOD>
<NATIVEMETHOD>PartyLedgerName</NATIVEMETHOD>
<NATIVEMETHOD>Amount</NATIVEMETHOD>
</COLLECTION>
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>''',

    "Q2_Filter_Sales": f'''<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>CustomVch2</ID></HEADER>
<BODY><DESC><STATICVARIABLES>
<SVEXPORTFORMAT>$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
<SVFROMDATE>{DATE}</SVFROMDATE>
<SVTODATE>{DATE}</SVTODATE>
</STATICVARIABLES>
<TDL><TDLMESSAGE>
<COLLECTION NAME="CustomVch2" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes">
<TYPE>Voucher</TYPE>
<NATIVEMETHOD>VoucherNumber</NATIVEMETHOD>
<NATIVEMETHOD>Date</NATIVEMETHOD>
<NATIVEMETHOD>VoucherTypeName</NATIVEMETHOD>
<NATIVEMETHOD>PartyLedgerName</NATIVEMETHOD>
<NATIVEMETHOD>Amount</NATIVEMETHOD>
<FILTERS>VchTypeFilter</FILTERS>
</COLLECTION>
<SYSTEM TYPE="Formulae" NAME="VchTypeFilter">$VoucherTypeName = "Sales"</SYSTEM>
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>''',

    "Q3_AllVouchers_NoFilter": f'''<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>CustomVch3</ID></HEADER>
<BODY><DESC><STATICVARIABLES>
<SVEXPORTFORMAT>$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
<SVFROMDATE>{DATE}</SVFROMDATE>
<SVTODATE>{DATE}</SVTODATE>
</STATICVARIABLES>
<TDL><TDLMESSAGE>
<COLLECTION NAME="CustomVch3" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes">
<TYPE>Voucher</TYPE>
<NATIVEMETHOD>VoucherNumber</NATIVEMETHOD>
<NATIVEMETHOD>Date</NATIVEMETHOD>
<NATIVEMETHOD>VoucherTypeName</NATIVEMETHOD>
<NATIVEMETHOD>PartyLedgerName</NATIVEMETHOD>
</COLLECTION>
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>''',

    "Q4_DayBook_Report": f'''<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE><ID>Day Book</ID></HEADER>
<BODY><DESC><STATICVARIABLES>
<SVEXPORTFORMAT>$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
<SVFROMDATE>{DATE}</SVFROMDATE>
<SVTODATE>{DATE}</SVTODATE>
</STATICVARIABLES></DESC></BODY></ENVELOPE>''',
}

print(f"\nTesting voucher queries for date: {DATE}")
print("=" * 60)

for name, xml in queries.items():
    print(f"\n--- {name} ---")
    try:
        r = requests.post(TALLY_URL, data=xml.encode('utf-8'),
                          headers={'Content-Type': 'text/xml; charset=utf-8'}, timeout=120)
        resp = r.text
        # Save to file
        filename = f"debug_{name}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(resp)
        print(f"Status: {r.status_code} | Response length: {len(resp)} chars")
        print(f"Saved to {filename}")
        # Show first 2000 chars
        print(resp[:2000])
        if len(resp) > 2000:
            print(f"... ({len(resp) - 2000} more chars)")
    except requests.exceptions.ReadTimeout:
        print("TIMED OUT")
    except Exception as e:
        print(f"ERROR: {e}")

input("\nPress Enter to exit...")

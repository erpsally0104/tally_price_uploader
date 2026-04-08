"""Debug script to find the correct XML query for price levels in Tally"""
import requests

TALLY_URL = "http://localhost:9000"

queries = {
    "Query 1 - Company Features": """<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Object</TYPE><ID>Company</ID></HEADER>
<BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES>
<FETCHLIST><FETCH>PRICELEVELLIST</FETCH><FETCH>Name</FETCH></FETCHLIST>
</DESC></BODY></ENVELOPE>""",

    "Query 2 - Stock Items with PriceLevel": """<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>PL1</ID></HEADER>
<BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES>
<TDL><TDLMESSAGE>
<COLLECTION NAME="PL1" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes">
<TYPE>StockItem</TYPE>
<NATIVEMETHOD>Name</NATIVEMETHOD>
<NATIVEMETHOD>PriceLevelList</NATIVEMETHOD>
</COLLECTION>
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>""",

    "Query 3 - Export stock item to see structure": """<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>StkItems</ID></HEADER>
<BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES>
<TDL><TDLMESSAGE>
<COLLECTION NAME="StkItems" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes">
<TYPE>StockItem</TYPE>
<NATIVEMETHOD>*</NATIVEMETHOD>
<FILTERS>FirstOnly</FILTERS>
</COLLECTION>
<SYSTEM TYPE="Formulae" NAME="FirstOnly">$$Line &lt; 2</SYSTEM>
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>""",
}

print("=" * 60)
print("Tally Price Level Debug")
print("=" * 60)

for name, xml in queries.items():
    print(f"\n--- {name} ---")
    try:
        r = requests.post(TALLY_URL, data=xml.encode('utf-8'), 
                         headers={'Content-Type': 'text/xml; charset=utf-8'}, timeout=15)
        resp = r.text
        print(f"Status: {r.status_code}")
        # Print relevant parts
        if len(resp) > 5000:
            # Find price-related content
            lower = resp.lower()
            for keyword in ['pricelevel', 'price level', 'pricelist', 'price list']:
                idx = lower.find(keyword)
                if idx >= 0:
                    start = max(0, idx - 100)
                    end = min(len(resp), idx + 500)
                    print(f"Found '{keyword}' at position {idx}:")
                    print(resp[start:end])
                    print("...")
                    break
            else:
                print(f"Response length: {len(resp)} chars")
                print("First 2000 chars:")
                print(resp[:2000])
        else:
            print(resp)
    except Exception as e:
        print(f"ERROR: {e}")

# Also try to get just one stock item fully exported
print("\n\n--- Full export of first stock item ---")
try:
    xml = """<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Object</TYPE><ID>AJWAIN</ID></HEADER>
<BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT><SVFROMDATE>20260401</SVFROMDATE><SVTODATE>20270331</SVTODATE></STATICVARIABLES>
<FETCHLIST><FETCH>*</FETCH></FETCHLIST>
</DESC></BODY></ENVELOPE>"""
    r = requests.post(TALLY_URL, data=xml.encode('utf-8'),
                     headers={'Content-Type': 'text/xml; charset=utf-8'}, timeout=15)
    resp = r.text
    # Find PRICELEVEL references
    lower = resp.lower()
    for kw in ['pricelevel', 'pricelist', 'price']:
        idx = lower.find(kw)
        if idx >= 0:
            start = max(0, idx - 50)
            end = min(len(resp), idx + 500)
            print(f"Found '{kw}':")
            print(resp[start:end])
            break
    else:
        print(f"No price info found. Response ({len(resp)} chars):")
        print(resp[:3000])
except Exception as e:
    print(f"ERROR: {e}")

input("\nPress Enter to exit...")

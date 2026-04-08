"""Fetch vouchers from Tally for a single day.

Usage:
    python get_vouchers_day.py --date 2026-04-01 --type Sales
    python get_vouchers_day.py --date 2026-04-15 --type Purchase
    python get_vouchers_day.py --date 2026-04-01              (all types)

Common voucher types in Tally:
    Sales, Purchase, Receipt, Payment, Journal, Contra,
    Credit Note, Debit Note, Sales Order, Purchase Order
"""
import argparse
import sys
import requests
import re
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime

TALLY_URL = "http://localhost:9000"


def get_company_name():
    """Fetch the active company name from Tally."""
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
    return company


def clean_xml(text):
    """Remove invalid XML character references (e.g. &#4;)."""
    return re.sub(
        r'&#(\d+);',
        lambda m: m.group() if int(m.group(1)) in (9, 10, 13) or int(m.group(1)) > 31 else '',
        text
    )


def save_raw(text, filename='raw_voucher_response.txt'):
    """Save raw response for debugging."""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(text[:10000])
    print(f"Saved raw response preview to {filename}")


def fetch_vouchers_day(date_str, voucher_type=""):
    """Fetch vouchers from Tally for a single day."""
    company = get_company_name()

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    tally_date = dt.strftime("%Y%m%d")

    type_label = voucher_type if voucher_type else "All"
    print(f"Fetching {type_label} vouchers for {dt.strftime('%d-%b-%Y')}...")

    # Use Object export for each voucher type - this is the reliable method
    # First get the list of voucher types if not specified
    if voucher_type:
        vch_types = [voucher_type]
    else:
        vch_types = ['Sales', 'Purchase', 'Receipt', 'Payment', 'Journal',
                     'Contra', 'Credit Note', 'Debit Note']

    all_vouchers = []
    for vtype in vch_types:
        print(f"  Trying {vtype}...")
        vouchers = fetch_by_type(company, tally_date, vtype)
        if vouchers:
            print(f"    Found {len(vouchers)} {vtype} vouchers")
            all_vouchers.extend(vouchers)

    print(f"\nTotal: {len(all_vouchers)} vouchers")
    return all_vouchers, dt


def fetch_by_type(company, tally_date, voucher_type):
    """Fetch vouchers of a specific type for a single day using XMLREQUEST format."""
    xml_request = f'''<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>CustomVch</ID></HEADER>
<BODY><DESC><STATICVARIABLES>
<SVEXPORTFORMAT>$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
<SVFROMDATE>{tally_date}</SVFROMDATE>
<SVTODATE>{tally_date}</SVTODATE>
</STATICVARIABLES>
<TDL><TDLMESSAGE>
<COLLECTION NAME="CustomVch" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes">
<TYPE>Voucher : VoucherType</TYPE>
<CHILDOF>{voucher_type}</CHILDOF>
<NATIVEMETHOD>VoucherNumber</NATIVEMETHOD>
<NATIVEMETHOD>Date</NATIVEMETHOD>
<NATIVEMETHOD>PartyLedgerName</NATIVEMETHOD>
<NATIVEMETHOD>Amount</NATIVEMETHOD>
</COLLECTION>
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'''

    try:
        r = requests.post(TALLY_URL, data=xml_request.encode('utf-8'),
                          headers={'Content-Type': 'text/xml; charset=utf-8'}, timeout=60)
        clean_text = clean_xml(r.text)
        save_raw(clean_text)
        root = ET.fromstring(clean_text)

        vouchers = []
        coll = root.find('.//COLLECTION')
        if coll is not None:
            for v in coll.findall('VOUCHER'):
                vch_number = v.findtext('VOUCHERNUMBER', '')
                date = v.findtext('DATE', '')
                party = v.findtext('PARTYLEDGERNAME', '')
                amount = v.findtext('AMOUNT', '')

                if date or party or vch_number:
                    vouchers.append({
                        'VoucherNumber': (vch_number or '').strip(),
                        'Date': (date or '').strip(),
                        'VoucherType': voucher_type,
                        'PartyName': (party or '').strip(),
                        'Amount': (amount or '').strip(),
                    })
        return vouchers
    except ET.ParseError:
        print(f"    XML parse error for {voucher_type}, trying alternate query...")
        return fetch_by_type_alt(company, tally_date, voucher_type)
    except requests.exceptions.ReadTimeout:
        print(f"    Timeout for {voucher_type}, skipping...")
        return []
    except Exception as e:
        print(f"    Error for {voucher_type}: {e}")
        return []


def fetch_by_type_alt(company, tally_date, voucher_type):
    """Alternate method using filter instead of CHILDOF."""
    xml_request = f'''<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>CustomVch2</ID></HEADER>
<BODY><DESC><STATICVARIABLES>
<SVEXPORTFORMAT>$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
<SVFROMDATE>{tally_date}</SVFROMDATE>
<SVTODATE>{tally_date}</SVTODATE>
</STATICVARIABLES>
<TDL><TDLMESSAGE>
<COLLECTION NAME="CustomVch2" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes">
<TYPE>Voucher</TYPE>
<NATIVEMETHOD>VoucherNumber</NATIVEMETHOD>
<NATIVEMETHOD>Date</NATIVEMETHOD>
<NATIVEMETHOD>PartyLedgerName</NATIVEMETHOD>
<NATIVEMETHOD>Amount</NATIVEMETHOD>
<FILTERS>TypeFilter</FILTERS>
</COLLECTION>
<SYSTEM TYPE="Formulae" NAME="TypeFilter">$$VchTypeSales = "{voucher_type}"</SYSTEM>
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'''

    try:
        r = requests.post(TALLY_URL, data=xml_request.encode('utf-8'),
                          headers={'Content-Type': 'text/xml; charset=utf-8'}, timeout=60)
        clean_text = clean_xml(r.text)
        root = ET.fromstring(clean_text)

        vouchers = []
        coll = root.find('.//COLLECTION')
        if coll is not None:
            for v in coll.findall('VOUCHER'):
                vch_number = v.findtext('VOUCHERNUMBER', '')
                date = v.findtext('DATE', '')
                party = v.findtext('PARTYLEDGERNAME', '')
                amount = v.findtext('AMOUNT', '')

                if date or party or vch_number:
                    vouchers.append({
                        'VoucherNumber': (vch_number or '').strip(),
                        'Date': (date or '').strip(),
                        'VoucherType': voucher_type,
                        'PartyName': (party or '').strip(),
                        'Amount': (amount or '').strip(),
                    })
        return vouchers
    except Exception as e:
        print(f"    Alternate also failed for {voucher_type}: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Fetch vouchers from Tally for a single day")
    parser.add_argument("--date", type=str, required=True, help="Date in YYYY-MM-DD format (e.g. 2026-04-01)")
    parser.add_argument("--type", type=str, default="",
                        help="Voucher type: Sales, Purchase, Receipt, Payment, Journal, etc. Leave empty for all.")
    args = parser.parse_args()

    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print("Error: Date must be in YYYY-MM-DD format (e.g. 2026-04-01)")
        sys.exit(1)

    vouchers, dt = fetch_vouchers_day(args.date, args.type)
    if not vouchers:
        print("No vouchers found for the given date.")
        input("\nPress Enter to exit...")
        return

    df = pd.DataFrame(vouchers)
    df.index = range(1, len(df) + 1)
    df.index.name = 'S.No'

    type_suffix = f"_{args.type}" if args.type else "_All"
    output_file = f"tally_vouchers_{dt.strftime('%Y%m%d')}{type_suffix}.xlsx"
    df.to_excel(output_file)
    print(f"Saved to {output_file}")

    # Summary by type
    print(f"\nSummary by voucher type:")
    for vtype, group in df.groupby("VoucherType"):
        print(f"  {vtype}: {len(group)} vouchers")

    print(f"\nFirst 15 vouchers:")
    print(df.head(15).to_string())

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()

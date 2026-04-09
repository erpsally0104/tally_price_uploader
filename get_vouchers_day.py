"""Fetch vouchers from Tally for a single day.

Usage:
    python get_vouchers_day.py --date 2026-04-08 --type Sales
    python get_vouchers_day.py --date 2026-04-15 --type Purchase
    python get_vouchers_day.py --date 2026-04-08              (all types)

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
    """Remove invalid XML character references AND raw control characters."""
    # Remove invalid XML character references like &#4;
    text = re.sub(
        r'&#(\d+);',
        lambda m: m.group() if int(m.group(1)) in (9, 10, 13) or int(m.group(1)) > 31 else '',
        text
    )
    # Also remove raw control characters (bytes 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text


def fetch_vouchers_day(date_str, voucher_type=""):
    """Fetch vouchers from Tally for a single day."""
    company = get_company_name()

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    tally_date = dt.strftime("%Y%m%d")

    type_label = voucher_type if voucher_type else "All"
    print(f"Fetching {type_label} vouchers for {dt.strftime('%d-%b-%Y')}...")

    # Use TDL Collection with FETCH (not NATIVEMETHOD) to get compact output
    # and use a custom report definition to extract only needed fields
    xml_request = f'''<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>MyVouchers</ID></HEADER>
<BODY><DESC><STATICVARIABLES>
<SVEXPORTFORMAT>$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
<SVFROMDATE>{tally_date}</SVFROMDATE>
<SVTODATE>{tally_date}</SVTODATE>
</STATICVARIABLES>
<TDL><TDLMESSAGE>
<COLLECTION NAME="MyVouchers" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes">
<TYPE>Voucher</TYPE>
<FETCH>VoucherNumber</FETCH>
<FETCH>Date</FETCH>
<FETCH>VoucherTypeName</FETCH>
<FETCH>PartyLedgerName</FETCH>
<FETCH>Amount</FETCH>
<FETCH>Narration</FETCH>
</COLLECTION>
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'''

    print("Sending request...")
    try:
        r = requests.post(TALLY_URL, data=xml_request.encode('utf-8'),
                          headers={'Content-Type': 'text/xml; charset=utf-8'}, timeout=300)
    except requests.exceptions.ReadTimeout:
        print("Request timed out.")
        input("\nPress Enter to exit...")
        return [], dt

    # Save raw response for debugging
    with open('raw_voucher_response.txt', 'w', encoding='utf-8') as f:
        f.write(r.text[:50000])
    print(f"Response length: {len(r.text)} chars (saved preview to raw_voucher_response.txt)")

    clean_text = clean_xml(r.text)

    try:
        root = ET.fromstring(clean_text)
    except ET.ParseError as e:
        print(f"XML parse error: {e}")
        print("First 500 chars:")
        print(clean_text[:500])
        print("\n...trying to extract data with regex fallback...")
        vouchers = regex_parse_vouchers(clean_text, voucher_type)
        return vouchers, dt

    vouchers = []
    # Try COLLECTION first (TDL collection response)
    coll = root.find('.//COLLECTION')
    if coll is not None:
        for v in coll.findall('VOUCHER'):
            vch_number = v.get('NAME', '') or v.findtext('VOUCHERNUMBER', '')
            date = v.findtext('DATE', '')
            vch_type = v.findtext('VOUCHERTYPENAME', '')
            party = v.findtext('PARTYLEDGERNAME', '')
            amount = v.findtext('AMOUNT', '')
            narration = v.findtext('NARRATION', '')

            if date or party or vch_number:
                vouchers.append({
                    'VoucherNumber': (vch_number or '').strip(),
                    'Date': (date or '').strip(),
                    'VoucherType': (vch_type or '').strip(),
                    'PartyName': (party or '').strip(),
                    'Amount': (amount or '').strip(),
                    'Narration': (narration or '').strip(),
                })

    # If COLLECTION was empty, try TALLYMESSAGE (Day Book style)
    if not vouchers:
        for v in root.iter('VOUCHER'):
            vch_number = v.findtext('VOUCHERNUMBER', '')
            date = v.findtext('DATE', '')
            vch_type = v.findtext('VOUCHERTYPENAME', '')
            party = v.findtext('PARTYLEDGERNAME', '')
            amount = v.findtext('AMOUNT', '')
            narration = v.findtext('NARRATION', '')

            if not amount:
                for entry in v.findall('.//ALLLEDGERENTRIES.LIST'):
                    amt = entry.findtext('AMOUNT', '')
                    if amt:
                        amount = amt
                        break

            if date or party or vch_number:
                vouchers.append({
                    'VoucherNumber': (vch_number or '').strip(),
                    'Date': (date or '').strip(),
                    'VoucherType': (vch_type or '').strip(),
                    'PartyName': (party or '').strip(),
                    'Amount': (amount or '').strip(),
                    'Narration': (narration or '').strip(),
                })

    # Filter by type if specified
    if voucher_type and vouchers:
        vouchers = [v for v in vouchers if v['VoucherType'].lower() == voucher_type.lower()]

    print(f"Found {len(vouchers)} vouchers")
    return vouchers, dt


def regex_parse_vouchers(text, voucher_type=""):
    """Fallback: extract voucher data using regex when XML parsing fails."""
    print("Using regex fallback parser...")
    vouchers = []

    # Find all VOUCHER blocks
    pattern = r'<VOUCHER[^>]*>(.*?)</VOUCHER>'
    matches = re.findall(pattern, text, re.DOTALL)

    for block in matches:
        def extract(tag):
            m = re.search(rf'<{tag}>(.*?)</{tag}>', block, re.DOTALL)
            return m.group(1).strip() if m else ''

        vch_number = extract('VOUCHERNUMBER')
        date = extract('DATE')
        vch_type = extract('VOUCHERTYPENAME')
        party = extract('PARTYLEDGERNAME')
        amount = extract('AMOUNT')
        narration = extract('NARRATION')

        if date or party or vch_number:
            vouchers.append({
                'VoucherNumber': vch_number,
                'Date': date,
                'VoucherType': vch_type,
                'PartyName': party,
                'Amount': amount,
                'Narration': narration,
            })

    if voucher_type and vouchers:
        vouchers = [v for v in vouchers if v['VoucherType'].lower() == voucher_type.lower()]

    print(f"Regex fallback found {len(vouchers)} vouchers")
    return vouchers


def main():
    parser = argparse.ArgumentParser(description="Fetch vouchers from Tally for a single day")
    parser.add_argument("--date", type=str, required=True, help="Date in YYYY-MM-DD format (e.g. 2026-04-08)")
    parser.add_argument("--type", type=str, default="",
                        help="Voucher type: Sales, Purchase, Receipt, Payment, Journal, etc. Leave empty for all.")
    args = parser.parse_args()

    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print("Error: Date must be in YYYY-MM-DD format (e.g. 2026-04-08)")
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

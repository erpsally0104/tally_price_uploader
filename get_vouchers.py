"""Fetch vouchers from Tally for a given month and voucher type.

Usage:
    python get_vouchers.py --month 4 --year 2026 --type Sales
    python get_vouchers.py --month 4 --year 2026 --type Purchase
    python get_vouchers.py --month 4 --year 2026              (all types)

Common voucher types in Tally:
    Sales, Purchase, Receipt, Payment, Journal, Contra,
    Credit Note, Debit Note, Sales Order, Purchase Order
"""
import argparse
import calendar
import sys
import requests
import re
import xml.etree.ElementTree as ET
import pandas as pd

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


def fetch_vouchers(month, year, voucher_type=""):
    """Fetch vouchers from Tally for the given month/year and optional type."""
    company = get_company_name()

    _, last_day = calendar.monthrange(year, month)
    from_date = f"{year}{month:02d}01"
    to_date = f"{year}{month:02d}{last_day:02d}"

    type_label = voucher_type if voucher_type else "All"
    print(f"Fetching {type_label} vouchers for {calendar.month_name[month]} {year}...")
    print(f"  Date range: {from_date} to {to_date}")

    # Build filter if voucher type specified
    filter_block = ""
    if voucher_type:
        filter_block = f"""<FILTERS>VchTypeFilter</FILTERS>
</COLLECTION>
<SYSTEM TYPE="Formulae" NAME="VchTypeFilter">$VoucherTypeName = "{voucher_type}"</SYSTEM>"""
    else:
        filter_block = "</COLLECTION>"

    xml_request = f'''<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>VoucherList</ID></HEADER>
<BODY><DESC><STATICVARIABLES>
<SVEXPORTFORMAT>$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
<SVFROMDATE>{from_date}</SVFROMDATE>
<SVTODATE>{to_date}</SVTODATE>
</STATICVARIABLES>
<TDL><TDLMESSAGE>
<COLLECTION NAME="VoucherList" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes">
<TYPE>Voucher</TYPE>
<NATIVEMETHOD>VoucherNumber</NATIVEMETHOD>
<NATIVEMETHOD>Date</NATIVEMETHOD>
<NATIVEMETHOD>VoucherTypeName</NATIVEMETHOD>
<NATIVEMETHOD>PartyLedgerName</NATIVEMETHOD>
<NATIVEMETHOD>Amount</NATIVEMETHOD>
<NATIVEMETHOD>Narration</NATIVEMETHOD>
<NATIVEMETHOD>Reference</NATIVEMETHOD>
{filter_block}
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'''

    r = requests.post(TALLY_URL, data=xml_request.encode('utf-8'),
                      headers={'Content-Type': 'text/xml; charset=utf-8'}, timeout=60)
    clean_text = clean_xml(r.text)
    root = ET.fromstring(clean_text)

    vouchers = []
    coll = root.find('.//COLLECTION')
    if coll is not None:
        for v in coll.findall('VOUCHER'):
            vch_number = v.get('REMOTEID', '') or v.findtext('VOUCHERNUMBER', '')
            date = v.findtext('DATE', '')
            vch_type = v.findtext('VOUCHERTYPENAME', '')
            party = v.findtext('PARTYLEDGERNAME', '')
            amount = v.findtext('AMOUNT', '')
            narration = v.findtext('NARRATION', '')
            reference = v.findtext('REFERENCE', '')

            if vch_number or date or party:
                vouchers.append({
                    'VoucherNumber': vch_number.strip(),
                    'Date': date.strip(),
                    'VoucherType': vch_type.strip(),
                    'PartyName': party.strip(),
                    'Amount': amount.strip(),
                    'Narration': narration.strip(),
                    'Reference': (reference or '').strip(),
                })

    print(f"Found {len(vouchers)} vouchers")
    return vouchers


def main():
    parser = argparse.ArgumentParser(description="Fetch vouchers from Tally")
    parser.add_argument("--month", type=int, required=True, help="Month number (1-12)")
    parser.add_argument("--year", type=int, required=True, help="Year (e.g. 2026)")
    parser.add_argument("--type", type=str, default="",
                        help="Voucher type: Sales, Purchase, Receipt, Payment, Journal, etc. Leave empty for all.")
    args = parser.parse_args()

    if not 1 <= args.month <= 12:
        print("Error: Month must be between 1 and 12.")
        sys.exit(1)

    vouchers = fetch_vouchers(args.month, args.year, args.type)
    if not vouchers:
        print("No vouchers found for the given criteria.")
        input("\nPress Enter to exit...")
        return

    df = pd.DataFrame(vouchers)
    df.index = range(1, len(df) + 1)
    df.index.name = 'S.No'

    type_suffix = f"_{args.type}" if args.type else "_All"
    output_file = f"tally_vouchers_{args.year}_{args.month:02d}{type_suffix}.xlsx"
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

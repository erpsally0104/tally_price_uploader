"""Fetch all ledgers (parties) from Tally and save to Excel.

Usage:
    python get_ledgers.py
    python get_ledgers.py --group "Sundry Debtors"
    python get_ledgers.py --group "Sundry Creditors"
"""
import argparse
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


def fetch_ledgers(group_filter=""):
    """Fetch ledgers from Tally, optionally filtered by group."""
    company = get_company_name()

    label = f"'{group_filter}'" if group_filter else "all"
    print(f"Fetching {label} ledgers...")

    # Build filter if group specified
    filter_block = ""
    if group_filter:
        filter_block = f"""<FILTERS>GroupFilter</FILTERS>
</COLLECTION>
<SYSTEM TYPE="Formulae" NAME="GroupFilter">$Parent = "{group_filter}"</SYSTEM>"""
    else:
        filter_block = "</COLLECTION>"

    xml_request = f'''<ENVELOPE>
<HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>LedgerList</ID></HEADER>
<BODY><DESC><STATICVARIABLES>
<SVEXPORTFORMAT>$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
</STATICVARIABLES>
<TDL><TDLMESSAGE>
<COLLECTION NAME="LedgerList" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes">
<TYPE>Ledger</TYPE>
<NATIVEMETHOD>Name</NATIVEMETHOD>
<NATIVEMETHOD>Parent</NATIVEMETHOD>
<NATIVEMETHOD>OpeningBalance</NATIVEMETHOD>
<NATIVEMETHOD>ClosingBalance</NATIVEMETHOD>
<NATIVEMETHOD>Address</NATIVEMETHOD>
<NATIVEMETHOD>LedStateName</NATIVEMETHOD>
<NATIVEMETHOD>LedgerPhone</NATIVEMETHOD>
<NATIVEMETHOD>LedgerContact</NATIVEMETHOD>
<NATIVEMETHOD>Email</NATIVEMETHOD>
<NATIVEMETHOD>GSTRegistrationType</NATIVEMETHOD>
<NATIVEMETHOD>PartyGSTIN</NATIVEMETHOD>
{filter_block}
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'''

    r = requests.post(TALLY_URL, data=xml_request.encode('utf-8'),
                      headers={'Content-Type': 'text/xml; charset=utf-8'}, timeout=30)
    clean_text = clean_xml(r.text)
    root = ET.fromstring(clean_text)

    ledgers = []
    coll = root.find('.//COLLECTION')
    if coll is not None:
        for ledger in coll.findall('LEDGER'):
            name = ledger.get('NAME', '')
            parent = ledger.findtext('PARENT', '')
            opening = ledger.findtext('OPENINGBALANCE', '')
            closing = ledger.findtext('CLOSINGBALANCE', '')
            state = ledger.findtext('LEDSTATENAME', '')
            gstin = ledger.findtext('PARTYGSTIN', '')
            phone = ledger.findtext('LEDGERPHONE', '')
            email = ledger.findtext('EMAIL', '')
            contact = ledger.findtext('LEDGERCONTACT', '')

            if name:
                ledgers.append({
                    'Name': name.strip(),
                    'Group': parent.strip(),
                    'OpeningBalance': opening.strip(),
                    'ClosingBalance': closing.strip(),
                    'State': state.strip(),
                    'GSTIN': gstin.strip(),
                    'Phone': phone.strip(),
                    'Contact': contact.strip(),
                    'Email': email.strip(),
                })

    print(f"Found {len(ledgers)} ledgers")
    return ledgers


def main():
    parser = argparse.ArgumentParser(description="Fetch ledgers/parties from Tally")
    parser.add_argument("--group", type=str, default="",
                        help="Filter by group e.g. 'Sundry Debtors', 'Sundry Creditors'. Leave empty for all.")
    args = parser.parse_args()

    ledgers = fetch_ledgers(args.group)
    if not ledgers:
        print("No ledgers found.")
        input("\nPress Enter to exit...")
        return

    df = pd.DataFrame(ledgers)
    df.index = range(1, len(df) + 1)
    df.index.name = 'S.No'

    suffix = f"_{args.group.replace(' ', '_')}" if args.group else ""
    output_file = f"tally_ledgers{suffix}.xlsx"
    df.to_excel(output_file)
    print(f"Saved to {output_file}")

    # Summary by group
    print(f"\nLedgers by group:")
    for group, grp_df in df.groupby("Group"):
        print(f"  {group}: {len(grp_df)}")

    print(f"\nFirst 15 ledgers:")
    print(df.head(15).to_string())

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()

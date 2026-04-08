"""
Tally Prime Gold - Price List Uploader
Flask backend that:
1. Reads Excel price lists
2. Fetches stock items from Tally via XML API
3. Allows mapping Excel items to Tally items
4. Generates and pushes price list XML to Tally
"""

import os
import json
import requests
import pandas as pd
import openpyxl
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from io import BytesIO

app = Flask(__name__, static_folder='static')
CORS(app)

# --- Configuration ---
TALLY_URL = os.environ.get('TALLY_URL', 'http://localhost:9000')
MAPPING_FILE = os.path.join(os.path.dirname(__file__), 'item_mappings.json')
CURRENT_COMPANY = ''  # Set when health check succeeds

# --- Helper Functions ---

def load_mappings():
    """Load saved item mappings from file."""
    if os.path.exists(MAPPING_FILE):
        with open(MAPPING_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_mappings(mappings):
    """Save item mappings to file."""
    with open(MAPPING_FILE, 'w') as f:
        json.dump(mappings, f, indent=2)

def similarity(a, b):
    """Calculate similarity ratio between two strings."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

def smart_read_excel(source):
    """
    Intelligently read an Excel file, auto-detecting the header row.
    Handles files where the actual data table doesn't start at row 1.
    
    source: filepath string or file-like object
    Returns: (DataFrame, header_row_index, info_dict)
    """
    # Load workbook with openpyxl to inspect structure
    if isinstance(source, str):
        wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
        source_for_pandas = source
    else:
        # File upload - read bytes
        file_bytes = source.read()
        source.seek(0)
        wb = openpyxl.load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
        source_for_pandas = BytesIO(file_bytes)
    
    ws = wb.active
    sheet_name = ws.title
    
    # Strategy: find the row that looks like a header
    # A header row typically has multiple text values that look like column names
    header_keywords = [
        'name', 'item', 'product', 'description', 'particular',
        'rate', 'price', 'amount', 'mrp', 'cost',
        'qty', 'quantity', 'unit', 'uom',
        'gst', 'tax', 'hsn', 'sno', 's.no', 'sr', 'sl',
        'discount', 'disc'
    ]
    
    header_row = 0  # 0-indexed for pandas
    best_score = 0
    title_info = []
    
    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=min(20, ws.max_row), values_only=True)):
        # Count how many cells in this row match header-like patterns
        non_empty = [str(v).strip().lower() for v in row if v is not None and str(v).strip()]
        if len(non_empty) < 2:
            # Title/info rows typically have 1 value spanning merged cells
            if non_empty:
                title_info.append(non_empty[0])
            continue
        
        score = 0
        for cell_val in non_empty:
            for kw in header_keywords:
                if kw in cell_val:
                    score += 1
                    break
        
        # Also boost if row has 3+ non-empty cells (likely a header)
        if len(non_empty) >= 3:
            score += 1
        
        if score > best_score:
            best_score = score
            header_row = row_idx
    
    wb.close()
    
    # Now read with pandas using detected header row
    df = pd.read_excel(source_for_pandas, header=header_row, sheet_name=0)
    
    # Clean up column names: strip whitespace, handle unnamed
    df.columns = [str(c).strip() for c in df.columns]
    
    # Remove completely empty rows
    df = df.dropna(how='all')
    
    # Remove rows where the "name" column (likely the widest text column) is NaN
    # This handles footer notes etc.
    
    info = {
        'sheet_name': sheet_name,
        'header_row': header_row + 1,  # 1-indexed for display
        'title_info': title_info[:5],  # First few title lines
        'original_rows': len(df)
    }
    
    return df, header_row, info

def fetch_tally_stock_items():
    """Fetch all stock items from Tally Prime via XML API."""
    company_name = CURRENT_COMPANY or '##SVCurrentCompany'
    xml_request = f"""
    <ENVELOPE>
        <HEADER>
            <VERSION>1</VERSION>
            <TALLYREQUEST>Export</TALLYREQUEST>
            <TYPE>Collection</TYPE>
            <ID>Stock Items</ID>
        </HEADER>
        <BODY>
            <DESC>
                <STATICVARIABLES>
                    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                    <SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>
                </STATICVARIABLES>
                <TDL>
                    <TDLMESSAGE>
                        <COLLECTION NAME="Stock Items" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes" ISOPTION="No" ISINTERNAL="No">
                            <TYPE>StockItem</TYPE>
                            <NATIVEMETHOD>Name</NATIVEMETHOD>
                            <NATIVEMETHOD>Parent</NATIVEMETHOD>
                            <NATIVEMETHOD>BaseUnits</NATIVEMETHOD>
                            <NATIVEMETHOD>Alias1</NATIVEMETHOD>
                        </COLLECTION>
                    </TDLMESSAGE>
                </TDL>
            </DESC>
        </BODY>
    </ENVELOPE>
    """.strip()

    try:
        response = requests.post(
            TALLY_URL,
            data=xml_request.encode('utf-8'),
            headers={'Content-Type': 'text/xml; charset=utf-8'},
            timeout=60
        )
        response.raise_for_status()

        # Clean invalid XML character references (e.g. &#4; which Tally sometimes includes)
        import re
        clean_text = re.sub(
            r'&#(\d+);',
            lambda m: m.group() if int(m.group(1)) in (9, 10, 13) or int(m.group(1)) > 31 else '',
            response.text
        )
        
        root = ET.fromstring(clean_text)
        items = []

        # Stock item names are in the NAME attribute, not a child element
        coll = root.find('.//COLLECTION')
        if coll is not None:
            for item in coll.findall('STOCKITEM'):
                name = item.get('NAME', '')
                parent = item.findtext('PARENT', '')
                base_units = item.findtext('BASEUNITS', '')

                if name:
                    items.append({
                        'name': name.strip(),
                        'group': parent.strip(),
                        'unit': base_units.strip(),
                        'alias': ''
                    })

        # Fallback: try child NAME element if attribute approach found nothing
        if not items:
            for item in root.iter('STOCKITEM'):
                name = item.get('NAME', '') or (item.findtext('NAME', '') or '')
                parent = item.findtext('PARENT', '')
                base_units = item.findtext('BASEUNITS', '')
                if name:
                    items.append({
                        'name': name.strip(),
                        'group': parent.strip(),
                        'unit': base_units.strip(),
                        'alias': ''
                    })

        print(f"[INFO] Fetched {len(items)} stock items from Tally")
        return items
    except requests.exceptions.ConnectionError:
        return None  # Tally not running
    except Exception as e:
        print(f"Error fetching stock items: {e}")
        return None

def fetch_tally_price_levels():
    """Load price levels from local cache. 
    Tally doesn't expose price level names via a lightweight XML query,
    so we maintain a local list that gets populated as users type them."""
    cache_file = os.path.join(os.path.dirname(__file__), 'price_levels.json')
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            return json.load(f)
    return []

def save_price_level(name):
    """Save a price level name to the local cache."""
    cache_file = os.path.join(os.path.dirname(__file__), 'price_levels.json')
    levels = []
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            levels = json.load(f)
    if name and name not in levels:
        levels.append(name)
        with open(cache_file, 'w') as f:
            json.dump(levels, f, indent=2)
    return levels

def build_price_list_xml(items_with_prices, price_level, applicable_from):
    """
    Build XML to import price list into Tally.
    
    Uses the stock item alteration approach - each stock item gets its 
    PRICELEVEL.LIST updated with the rate for the given price level.
    """
    envelope = ET.Element('ENVELOPE')
    header = ET.SubElement(envelope, 'HEADER')
    ET.SubElement(header, 'VERSION').text = '1'
    ET.SubElement(header, 'TALLYREQUEST').text = 'Import'
    ET.SubElement(header, 'TYPE').text = 'Data'
    ET.SubElement(header, 'ID').text = 'All Masters'

    body = ET.SubElement(envelope, 'BODY')
    desc = ET.SubElement(body, 'DESC')
    static_vars = ET.SubElement(desc, 'STATICVARIABLES')
    # Use actual company name - this is critical for Tally to find stock items
    company_name = CURRENT_COMPANY or '##SVCurrentCompany'
    ET.SubElement(static_vars, 'SVCURRENTCOMPANY').text = company_name

    importdata = ET.SubElement(body, 'DATA')
    tallymsg = ET.SubElement(importdata, 'TALLYMESSAGE')
    tallymsg.set('xmlns:UDF', 'TallyUDF')

    for item in items_with_prices:
        tally_name = item['tally_name']
        rate = item['rate']
        unit = item.get('unit', 'Nos')

        stock_item = ET.SubElement(tallymsg, 'STOCKITEM')
        stock_item.set('NAME', tally_name)
        stock_item.set('ACTION', 'Alter')
        ET.SubElement(stock_item, 'NAME').text = tally_name

        # Price level list
        price_level_list = ET.SubElement(stock_item, 'PRICELEVEL.LIST')
        ET.SubElement(price_level_list, 'NAME').text = price_level

        # Rate list within price level
        rate_list = ET.SubElement(price_level_list, 'RATELIST.LIST')
        ET.SubElement(rate_list, 'DATE').text = applicable_from.replace('-', '')
        ET.SubElement(rate_list, 'RATE').text = f"{rate}/{unit}"

    return ET.tostring(envelope, encoding='unicode', xml_declaration=True)

def push_to_tally(xml_data):
    """Push XML data to Tally."""
    try:
        response = requests.post(
            TALLY_URL,
            data=xml_data.encode('utf-8'),
            headers={'Content-Type': 'text/xml; charset=utf-8'},
            timeout=60
        )
        response.raise_for_status()
        
        # Parse response to check for errors
        root = ET.fromstring(response.text)
        
        # Check for import status
        status = root.find('.//LINEERROR')
        created = root.find('.//CREATED')
        altered = root.find('.//ALTERED')
        errors = root.find('.//ERRORS')
        
        result = {
            'success': True,
            'raw_response': response.text[:2000],
            'created': created.text if created is not None else '0',
            'altered': altered.text if altered is not None else '0',
            'errors': errors.text if errors is not None else '0',
        }
        
        if status is not None and status.text:
            result['line_error'] = status.text
            
        return result
    except requests.exceptions.ConnectionError:
        return {'success': False, 'error': 'Cannot connect to Tally. Make sure Tally Prime is running with HTTP server enabled on the configured port.'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# --- API Routes ---

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    """Check if Tally is reachable."""
    try:
        # Simple request to check Tally connectivity
        xml_request = """
        <ENVELOPE>
            <HEADER>
                <VERSION>1</VERSION>
                <TALLYREQUEST>Export</TALLYREQUEST>
                <TYPE>Collection</TYPE>
                <ID>CompanyList</ID>
            </HEADER>
            <BODY>
                <DESC>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                    </STATICVARIABLES>
                    <TDL>
                        <TDLMESSAGE>
                            <COLLECTION NAME="CompanyList" ISMODIFY="No" ISFIXED="No" ISINITIALIZE="Yes">
                                <TYPE>Company</TYPE>
                                <NATIVEMETHOD>Name</NATIVEMETHOD>
                            </COLLECTION>
                        </TDLMESSAGE>
                    </TDL>
                </DESC>
            </BODY>
        </ENVELOPE>
        """.strip()
        
        response = requests.post(
            TALLY_URL,
            data=xml_request.encode('utf-8'),
            headers={'Content-Type': 'text/xml; charset=utf-8'},
            timeout=10
        )
        
        companies = []
        root = ET.fromstring(response.text)
        for name in root.iter('NAME'):
            if name.text and name.text.strip():
                companies.append(name.text.strip())
        
        global CURRENT_COMPANY
        if companies:
            CURRENT_COMPANY = companies[0]
            print(f"[INFO] Current company: {CURRENT_COMPANY}")
        
        return jsonify({
            'connected': True,
            'tally_url': TALLY_URL,
            'companies': companies
        })
    except Exception as e:
        return jsonify({
            'connected': False,
            'tally_url': TALLY_URL,
            'error': str(e)
        })

@app.route('/api/stock-items', methods=['GET'])
def get_stock_items():
    """Get all stock items from Tally."""
    items = fetch_tally_stock_items()
    if items is None:
        return jsonify({'error': 'Cannot connect to Tally'}), 503
    return jsonify({'items': items})

@app.route('/api/price-levels', methods=['GET'])
def get_price_levels():
    """Get saved price levels."""
    levels = fetch_tally_price_levels()
    return jsonify({'levels': levels})

@app.route('/api/price-levels', methods=['POST'])
def add_price_level():
    """Add a price level to local cache."""
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    levels = save_price_level(name)
    return jsonify({'levels': levels})

@app.route('/api/upload-excel', methods=['POST'])
def upload_excel():
    """Upload and parse an Excel file with smart header detection."""
    uploaded_file = None
    filepath = None
    
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        uploaded_file = file
    else:
        filepath = request.form.get('filepath', '').strip()
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'No file provided or file not found'}), 400

    try:
        source = filepath if filepath else uploaded_file
        df, header_row, info = smart_read_excel(source)
        
        # If file was uploaded, save it temporarily for later parse step
        if uploaded_file:
            uploaded_file.seek(0)
            temp_path = os.path.join(os.path.dirname(__file__), '_temp_upload.xlsx')
            uploaded_file.save(temp_path)
            info['temp_path'] = temp_path
        else:
            info['filepath'] = filepath

        columns = list(df.columns)
        preview = df.head(15).fillna('').to_dict('records')
        total_rows = len(df)

        return jsonify({
            'columns': columns,
            'preview': preview,
            'total_rows': total_rows,
            'info': info
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Cannot read file: {str(e)}'}), 400

@app.route('/api/parse-excel', methods=['POST'])
def parse_excel():
    """Parse Excel with specified column mappings and return items with prices."""
    data = request.json
    filepath = data.get('filepath', '')
    name_column = data.get('name_column')
    price_column = data.get('price_column')
    unit_column = data.get('unit_column', '')

    if not name_column or not price_column:
        return jsonify({'error': 'Please specify name and price columns'}), 400

    try:
        # Try the provided path, then temp upload path
        source = None
        if filepath and os.path.exists(filepath):
            source = filepath
        else:
            temp_path = os.path.join(os.path.dirname(__file__), '_temp_upload.xlsx')
            if os.path.exists(temp_path):
                source = temp_path
        
        if not source:
            return jsonify({'error': 'File not found. Please re-upload.'}), 400

        df, header_row, info = smart_read_excel(source)

        items = []
        for _, row in df.iterrows():
            name = str(row.get(name_column, '')).strip()
            price = row.get(price_column)
            unit = str(row.get(unit_column, '')).strip() if unit_column else ''
            
            # Skip empty names, header-like rows, note rows
            if not name or name.lower() in ('nan', 'none', '') or name.lower().startswith('note'):
                continue
            
            if pd.notna(price):
                try:
                    price = float(price)
                    item = {'excel_name': name, 'price': price}
                    if unit and unit.lower() not in ('nan', 'none', ''):
                        item['unit'] = unit
                    items.append(item)
                except (ValueError, TypeError):
                    continue

        return jsonify({'items': items, 'total_parsed': len(items)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400

@app.route('/api/suggest-mappings', methods=['POST'])
def suggest_mappings():
    """Suggest mappings between Excel items and Tally stock items."""
    data = request.json
    excel_items = data.get('excel_items', [])

    # Load saved mappings
    saved_mappings = load_mappings()

    # Fetch tally stock items
    tally_items = fetch_tally_stock_items()
    if tally_items is None:
        return jsonify({'error': 'Cannot connect to Tally'}), 503

    tally_names = [item['name'] for item in tally_items]

    suggestions = []
    for excel_item in excel_items:
        excel_name = excel_item['excel_name']

        # Check saved mappings first
        if excel_name in saved_mappings:
            mapped_tally = saved_mappings[excel_name]
            if mapped_tally in tally_names:
                suggestions.append({
                    'excel_name': excel_name,
                    'price': excel_item['price'],
                    'suggested_tally_name': mapped_tally,
                    'confidence': 1.0,
                    'source': 'saved_mapping'
                })
                continue

        # Find best match by similarity
        best_match = None
        best_score = 0
        for tally_name in tally_names:
            score = similarity(excel_name, tally_name)
            if score > best_score:
                best_score = score
                best_match = tally_name

        # Also check aliases
        for tally_item in tally_items:
            if tally_item.get('alias'):
                alias_score = similarity(excel_name, tally_item['alias'])
                if alias_score > best_score:
                    best_score = alias_score
                    best_match = tally_item['name']

        suggestions.append({
            'excel_name': excel_name,
            'price': excel_item['price'],
            'suggested_tally_name': best_match if best_score > 0.3 else None,
            'confidence': round(best_score, 2),
            'source': 'auto_match'
        })

    return jsonify({
        'suggestions': suggestions,
        'tally_items': tally_items
    })

@app.route('/api/mappings', methods=['GET'])
def get_mappings():
    """Get all saved mappings."""
    return jsonify(load_mappings())

@app.route('/api/mappings', methods=['POST'])
def save_mapping():
    """Save a single mapping."""
    data = request.json
    excel_name = data.get('excel_name')
    tally_name = data.get('tally_name')

    if not excel_name or not tally_name:
        return jsonify({'error': 'Both excel_name and tally_name are required'}), 400

    mappings = load_mappings()
    mappings[excel_name] = tally_name
    save_mappings(mappings)

    return jsonify({'success': True, 'mappings': mappings})

@app.route('/api/mappings/bulk', methods=['POST'])
def save_bulk_mappings():
    """Save multiple mappings at once."""
    data = request.json
    new_mappings = data.get('mappings', {})

    mappings = load_mappings()
    mappings.update(new_mappings)
    save_mappings(mappings)

    return jsonify({'success': True, 'mappings': mappings})

@app.route('/api/mappings/<excel_name>', methods=['DELETE'])
def delete_mapping(excel_name):
    """Delete a mapping."""
    mappings = load_mappings()
    if excel_name in mappings:
        del mappings[excel_name]
        save_mappings(mappings)
    return jsonify({'success': True, 'mappings': mappings})

@app.route('/api/push-prices', methods=['POST'])
def push_prices():
    """Push price list to Tally."""
    data = request.json
    items = data.get('items', [])
    price_level = data.get('price_level', '')
    applicable_from = data.get('applicable_from', '')

    if not items:
        return jsonify({'error': 'No items to push'}), 400
    if not price_level:
        return jsonify({'error': 'Price level is required'}), 400
    if not applicable_from:
        return jsonify({'error': 'Applicable from date is required'}), 400

    # Build items list for XML
    items_with_prices = []
    for item in items:
        if item.get('tally_name') and item.get('price'):
            items_with_prices.append({
                'tally_name': item['tally_name'],
                'rate': item['price'],
                'unit': item.get('unit', 'Nos')
            })

    if not items_with_prices:
        return jsonify({'error': 'No valid mapped items found'}), 400

    # Build and push XML
    xml_data = build_price_list_xml(items_with_prices, price_level, applicable_from)

    # Save the price level for future dropdown use
    save_price_level(price_level)

    # Save mappings for all items being pushed
    mappings = load_mappings()
    for item in items:
        if item.get('excel_name') and item.get('tally_name'):
            mappings[item['excel_name']] = item['tally_name']
    save_mappings(mappings)

    result = push_to_tally(xml_data)
    result['xml_preview'] = xml_data[:3000]  # Send preview of XML for debugging
    result['items_count'] = len(items_with_prices)

    return jsonify(result)

@app.route('/api/preview-xml', methods=['POST'])
def preview_xml():
    """Preview the XML that would be sent to Tally without actually sending it."""
    data = request.json
    items = data.get('items', [])
    price_level = data.get('price_level', '')
    applicable_from = data.get('applicable_from', '')

    items_with_prices = []
    for item in items:
        if item.get('tally_name') and item.get('price'):
            items_with_prices.append({
                'tally_name': item['tally_name'],
                'rate': item['price'],
                'unit': item.get('unit', 'Nos')
            })

    xml_data = build_price_list_xml(items_with_prices, price_level, applicable_from)
    return jsonify({'xml': xml_data})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print(f"\n{'='*60}")
    print(f"  Tally Price List Uploader")
    print(f"  Server running at: http://localhost:{port}")
    print(f"  Tally URL: {TALLY_URL}")
    print(f"  Mappings file: {MAPPING_FILE}")
    print(f"{'='*60}\n")
    app.run(host='0.0.0.0', port=port, debug=True)

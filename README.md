# Tally Prime Gold - Price List Uploader

Automates uploading price lists from Excel to Tally Prime Gold, with intelligent item mapping between your Excel product names and Tally stock items.

## Features

- **Excel Upload**: Load price lists from file path or drag-and-drop
- **Smart Column Detection**: Auto-detects name and price columns
- **Intelligent Mapping**: Fuzzy-matches Excel items to Tally stock items
- **Persistent Mappings**: Saves item mappings for future use (no re-mapping needed)
- **Price Level Support**: Push prices to any Tally price level
- **XML Preview**: See the exact XML before pushing to Tally
- **Error Handling**: Clear feedback on success/failure with Tally response details

## Prerequisites

1. **Python 3.8+** installed
2. **Tally Prime Gold** running with HTTP server enabled
3. **Price Levels** already created in Tally (F11 > Inventory Features > Enable Multiple Price Levels)

## Setup Tally Prime

1. Open Tally Prime
2. Go to **F1 (Help) > Settings > Advanced Configuration**
3. **Enable the HTTP Server** (default port: **9000**)
4. Load your company

## Quick Start

### Windows
```
Double-click run.bat
```

### Manual
```bash
pip install flask flask-cors pandas openpyxl requests
python app.py
```

Then open **http://localhost:5050** in your browser.

## How It Works

### Step 1: Upload Excel
- Provide the file path to your Excel price list, OR
- Upload the file directly via drag-and-drop
- The app reads all columns and shows a preview

### Step 2: Map Columns
- Select which column contains **product names**
- Select which column contains **prices**
- Choose the **Price Level** in Tally (e.g., Wholesale, Retail)
- Set the **Applicable From** date

### Step 3: Map Items
This is the key step. Your Excel product names might differ from Tally stock item names. For example:
- Excel: "Basmati Rice 1kg" → Tally: "Rice Basmati Premium 1 KG"
- Excel: "Toor Dal" → Tally: "Arhar Dal (Toor)"

The app:
1. Fetches all stock items from your Tally company
2. Uses **fuzzy matching** to suggest the best Tally match for each Excel item
3. Shows a confidence score for each suggestion
4. Lets you manually select/correct any mapping
5. **Saves all mappings** to `item_mappings.json` — next time you upload, previously mapped items are auto-matched!

### Step 4: Push to Tally
- Review all mapped items and prices
- Preview the XML that will be sent
- Push to Tally with one click
- See results (created/altered/errors)

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `TALLY_URL` | `http://localhost:9000` | Tally Prime HTTP server URL |
| `PORT` | `5050` | Web app port |

### Custom Tally URL
If Tally runs on a different machine or port:
```bash
# Windows
set TALLY_URL=http://192.168.1.100:9000
python app.py

# Linux/Mac
TALLY_URL=http://192.168.1.100:9000 python app.py
```

## File Structure

```
tally_price_uploader/
├── app.py              # Flask backend (API + Tally XML communication)
├── requirements.txt    # Python dependencies
├── run.bat             # Windows launcher
├── run.sh              # Linux/Mac launcher
├── item_mappings.json  # Saved item mappings (auto-created)
├── static/
│   └── index.html      # Frontend UI (single-page app)
└── README.md           # This file
```

## Mapping File

The `item_mappings.json` stores your Excel-to-Tally mappings:

```json
{
  "Basmati Rice 1kg": "Rice Basmati Premium 1 KG",
  "Toor Dal": "Arhar Dal (Toor)",
  "Sugar 5kg": "Sugar Loose 5 KG"
}
```

You can also edit this file manually to pre-load mappings.

## Tally XML Format

The app pushes price lists by altering each stock item's `PRICELEVEL.LIST`. The XML format:

```xml
<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>All Masters</ID>
  </HEADER>
  <BODY>
    <DATA>
      <TALLYMESSAGE>
        <STOCKITEM NAME="Rice Basmati" ACTION="Alter">
          <NAME>Rice Basmati</NAME>
          <PRICELEVEL.LIST>
            <NAME>Wholesale</NAME>
            <RATELIST.LIST>
              <DATE>20260408</DATE>
              <RATE>120/KG</RATE>
            </RATELIST.LIST>
          </PRICELEVEL.LIST>
        </STOCKITEM>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Cannot connect to Tally" | Ensure Tally is running, HTTP server is enabled on port 9000, and the company is loaded |
| "Import failed" | Check that stock item names in mapping exactly match Tally. Check Tally.imp log file |
| "Price level not found" | Create the price level in Tally first (F11 > Inventory Features > Price Levels) |
| No stock items returned | Ensure inventory features are enabled and stock items exist in the loaded company |

## Notes

- The app runs locally — your data never leaves your machine
- Works with both Tally Prime and Tally Prime Gold
- Excel files must have .xlsx or .xls extension
- Price levels must be pre-created in Tally before pushing

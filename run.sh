#!/bin/bash
echo "============================================"
echo "  Tally Price List Uploader - Setup & Run"
echo "============================================"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install flask flask-cors pandas openpyxl requests --break-system-packages 2>/dev/null || pip install flask flask-cors pandas openpyxl requests
echo "Dependencies installed."
echo ""

# Set Tally URL
export TALLY_URL=${1:-http://localhost:9000}

echo "Tally URL: $TALLY_URL"
echo ""
echo "Starting server at http://localhost:5050"
echo "Open your browser and go to http://localhost:5050"
echo ""

python3 app.py

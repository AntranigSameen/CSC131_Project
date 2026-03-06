#!/bin/bash
# Stop if anything fails
set -e

echo "Creating virtual environment..."
python3 -m venv .venv

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Upgrading pip..."
python -m pip install --upgrade pip

echo "Installing packages..."
pip install msal requests python-dotenv
pip install gspread google-auth google-auth-oauthlib google-auth-httplib2
##pip install imapclient
##pip install pyzmail36
pip install pyinstaller
pip install flask msal requests

echo "Setup complete ✅"

# Stop if anything fails
$ErrorActionPreference = "Stop"

Write-Host "Creating virtual environment..."
python -m venv .venv

Write-Host "Activating virtual environment..."
& .\.venv\Scripts\Activate.ps1

Write-Host "Upgrading pip..."
python -m pip install --upgrade pip

Write-Host "Installing dependencies..."
pip install msal requests python-dotenv
pip install gspread google-auth google-auth-oauthlib google-auth-httplib2
##pip install imapclient
##pip install pyzmail36
pip install pyinstaller
pip install playwright
pip install pystray pillow
pip install ttkbootstrap

Write-Host "Setup complete ✅"

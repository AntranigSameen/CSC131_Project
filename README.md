## CSC131_Project

This script reads unread emails from an IMAP inbox and extracts basic lead information.
Matching emails are parsed and automatically appended to a Google Sheets worksheet.
Credentials and filters are configured using environment variables (.env).


The application was refactored from legacy IMAP-based email retrieval to Microsoft Graph API using OAuth2 Client Credentials Flow. This transition improves security by eliminating stored passwords and leveraging Azure App Registration for authentication. The system now securely reads Outlook emails and integrates them into Google Sheets using a fully automated pipeline.

## Setup

After cloning this repository, run the appropriate setup script for your operating system to install all required dependencies: 

**Mac/Linux:**
```bash
./scripts/setup.sh
```

**Windows:** (only run this if it doesnt auto run in your powershell if done will prompt user to hit any key)
```powershell
.\scripts\setup.ps1
```

This will:
- Create a virtual environment (`.venv`)
- Install all required Python packages
- Set up the development environment

## Running the Application

### Development Mode

To run the application in development mode, activate the virtual environment and run the main script:

**Mac/Linux:**
```bash
source .venv/bin/activate
python Proper_MS/master_control.py
```

**Windows:**
```powershell
.venv\Scripts\activate
python Proper_MS\master_control.py
```

### Running Individual Modules

To run the RQI Email-to-Sheets module independently:
```bash
# Make sure you're in the project root directory
cd /path/to/CSC131_Project
python RQI_EmailSheets/email_to_sheets.py
```

## Building Executable

Run this command from the **project root directory** before building to ensure a clean spec-based build:

```powershell
pyinstaller master_control.spec --clean
```

To create a standalone executable using PyInstaller, run the following command from the **project root directory**:

**Mac/Linux:**
```bash
pyinstaller --onefile --windowed Proper_MS/master_control.py \
--name "CSC131_Automation" \
--icon icon.png \
--paths Proper_MS \
--paths RQI_EmailSheets \
--paths Scheduling \
--add-data "service_account.json:." \
--add-data "google_sheet_api_key.json:." \
--add-data ".env:." \
--add-data "icon.png:." \
--collect-submodules RQI_EmailSheets \
--collect-submodules Proper_MS \
--collect-submodules Scheduling \
--collect-all ttkbootstrap \
--collect-all playwright \
--hidden-import msal \
--hidden-import pystray \
--hidden-import PIL \
--hidden-import gspread \
--hidden-import requests \
--hidden-import dotenv \
--hidden-import google.oauth2.service_account
```

**Windows:**
```powershell
pyinstaller --onefile --windowed Proper_MS\master_control.py `
--name "CSC131_Automation" `
--icon icon.png `
--paths Proper_MS `
--paths RQI_EmailSheets `
--paths Scheduling `
--add-data "service_account.json;." `
--add-data "google_sheet_api_key.json;." `
--add-data ".env;." `
--add-data "icon.png;." `
--collect-submodules RQI_EmailSheets `
--collect-submodules Proper_MS `
--collect-submodules Scheduling `
--collect-all ttkbootstrap `
--collect-all playwright `
--hidden-import msal `
--hidden-import pystray `
--hidden-import PIL `
--hidden-import gspread `
--hidden-import requests `
--hidden-import dotenv `
--hidden-import google.oauth2.service_account
```

**Note:** The executable will be created in the `dist/` folder as `CSC131_Automation`.

### Post-Build Steps

After building, Playwright requires browser binaries. Install them with:
```bash
playwright install
```

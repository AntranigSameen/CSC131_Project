## CSC131_Project

**Complete Automation Machine** - A GUI application for automated email-to-sheets processing and web-based training course management.

### Features

- **GUI Control Panel** with real-time dashboard, live logs, and system tray integration
- **RQI Email Processing**: Reads Outlook emails via Microsoft Graph API, extracts lead information, appends to Google Sheets, and creates calendar events
- **AHA Training Automation**: Automates course registration and data entry for the American Heart Association platform
- **Independent Controls**: Pause/resume each automation system independently
- **Secure OAuth2 Authentication**: No stored passwords, uses Azure App Registration

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

## Configuration

Required credentials (GUI Settings panel allows editing without manually modifying `.env`):

1. **Azure App Registration**: `CLIENT_ID`, `TENANT_ID`, `AUTHORITY`, `SCOPES`
2. **Google Sheets Service Accounts**: `service_account.json`, `google_sheet_api_key.json`
3. **Google Sheets**: `SPREADSHEET_ID`, `WORKSHEET_NAME`
4. **AHA Credentials**: Prompted on first run if not configured

## Running the Application

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

The GUI opens with a dashboard, settings panel, live logs, and system tray icon. On first run, you'll be prompted for AHA credentials if needed.

## Building Executable

Build from the **project root directory** using the included spec file:

```bash
pyinstaller master_control.spec --clean
```

The executable will be created in `dist/CSC131_Automation` and launches the GUI control panel. After building, install Playwright browser binaries:

```bash
playwright install
```

<details>
<summary>Advanced: Manual PyInstaller Build Commands</summary>

**Mac/Linux:**
```bash
pyinstaller --onefile --windowed Proper_MS/master_control.py \
--name "CSC131_Automation" --icon icon.png \
--paths Proper_MS --paths RQI_EmailSheets --paths Scheduling \
--add-data "service_account.json:." --add-data "google_sheet_api_key.json:." \
--add-data ".env:." --add-data "icon.png:." \
--collect-submodules RQI_EmailSheets --collect-submodules Proper_MS \
--collect-submodules Scheduling --collect-all ttkbootstrap --collect-all playwright \
--hidden-import msal --hidden-import pystray --hidden-import PIL \
--hidden-import gspread --hidden-import requests --hidden-import dotenv \
--hidden-import google.oauth2.service_account
```

**Windows:**
```powershell
pyinstaller --onefile --windowed Proper_MS\master_control.py `
--name "CSC131_Automation" --icon icon.png `
--paths Proper_MS --paths RQI_EmailSheets --paths Scheduling `
--add-data "service_account.json;." --add-data "google_sheet_api_key.json;." `
--add-data ".env;." --add-data "icon.png;." `
--collect-submodules RQI_EmailSheets --collect-submodules Proper_MS `
--collect-submodules Scheduling --collect-all ttkbootstrap --collect-all playwright `
--hidden-import msal --hidden-import pystray --hidden-import PIL `
--hidden-import gspread --hidden-import requests --hidden-import dotenv `
--hidden-import google.oauth2.service_account
```
</details>

## Using the Application

**GUI Pages** (left sidebar):
- 🏠 **Dashboard**: Real-time status cards and mini live log
- ⚙️ **Settings**: Edit environment variables and credentials
- 📋 **Logs**: Full log viewer with search/filter
- ℹ️ **About**: Application info

**System Tray**: Left-click opens GUI, right-click for pause/resume/quit menu. Runs unobtrusively in the background.

**Automation Controls**: Pause/resume all systems together, or control AHA and RQI independently. Runs in cycles at configured interval (default 10 seconds).

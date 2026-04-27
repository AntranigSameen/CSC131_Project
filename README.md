# CSC131 Automation Project

A comprehensive automation suite with a user-friendly GUI for streamlining email processing and training course management workflows.

## 📋 Overview

This project automates repetitive business processes through two main systems:

1. **RQI Email Processing System** - Automatically monitors your Outlook inbox, extracts lead information from specific emails, logs data to Google Sheets, and creates calendar reminders
2. **AHA Training Course Automation** - Handles registration and data entry for American Heart Association training courses through automated web browser interactions

Both systems run independently with their own start/stop controls, accessible through a modern GUI dashboard.

## ✨ Key Features

- **📊 Interactive GUI Dashboard** - Real-time status monitoring, live activity logs, and independent start/stop controls for each automation
- **🔒 Secure Authentication** - OAuth2-based login for Outlook (no passwords stored locally)
- **📧 Email Integration** - Connects to Outlook via Microsoft Graph API with automatic lead extraction
- **📈 Google Sheets Integration** - Automatically appends extracted data to configured spreadsheets
- **📅 Calendar Management** - Creates events and reminders automatically from email data
- **🌐 Web Automation** - Playwright-based browser automation for AHA course registration
- **🔔 System Tray Integration** - Run minimized with quick access menu and desktop notifications
- **⚙️ Settings Panel** - Configure all credentials and automation settings through the GUI (no manual file editing needed)

## 🔧 Prerequisites

### Software Requirements
- **Python 3.8 or higher** ([Download Python](https://www.python.org/downloads/))
- **Internet connection** (required for API calls and web automation)

### Service Accounts & Credentials
You'll need access to the following services. Configuration can be done through the GUI after installation:

- **Microsoft Outlook** with Azure App Registration
  - Client ID, Tenant ID, and API permissions (Mail.Read, Calendars.ReadWrite)
- **Google Cloud Service Account** for Sheets API
  - Service account JSON key files
  - Sheets API enabled in your Google Cloud project
- **AHA Platform Credentials** (only if using training automation)

## 🚀 Installation

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd CSC131_Project
```

### Step 2: Run the Setup Script

The setup script automatically creates a Python virtual environment and installs all dependencies.

**On Mac/Linux:**
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

**On Windows:**
```powershell
.\scripts\setup.ps1
```

> **Note for Windows users**: The script may run automatically when you open the folder in PowerShell. If prompted, press any key to continue.

The setup script will:
- ✅ Create a virtual environment in `.venv/`
- ✅ Install all required Python packages (playwright, gspread, msal, ttkbootstrap, etc.)
- ✅ Download Playwright browser binaries for web automation

## ⚙️ Configuration

You'll need to set up credentials for the various services. The good news is that most of this can be done through the **GUI Settings Panel** after launching the app!

### Required Configuration Files

1. **Azure App Registration** (for Outlook/Email access)
   - `CLIENT_ID` - Your Azure app client ID
   - `TENANT_ID` - Your Azure tenant ID
   - `AUTHORITY` - Azure authority URL
   - `SCOPES` - API permission scopes (e.g., `Mail.Read Calendars.ReadWrite`)

2. **Google Sheets API**
Most configuration can be done through the **GUI Settings Panel** - no manual file editing required!

### Required Credentials

1. **Azure App Registration** (for Outlook/Email access)
   - CLIENT_ID, TENANT_ID, AUTHORITY URL
   - SCOPES: `Mail.Read Calendars.ReadWrite`

2. **Google Sheets API**
   - Place `service_account.json` and `google_sheet_api_key.json` in project root
   - SPREADSHEET_ID (from your Google Sheet URL)
   - WORKSHEET_NAME (sheet tab name)

3. **AHA Platform** - Enter credentials when prompted or via Settings panel

### Setup Options

**GUI Settings Panel (Recommended):**
1. Launch the app and click "Settings"
2. Enter your credentials
3. Click "Save Settings"

**Manual .env File:**
```env
CLIENT_ID=your-azure-client-id
TENANT_ID=your-azure-tenant-id
AUTHORITY=https://login.microsoftonline.com/your-tenant-id
SCOPES=Mail.Read Calendars.ReadWrite
SPREADSHEET_ID=your-google-sheet-id
WORKSHEET_NAME=Sheet1
AUTO_FLIP_ACUITY_REGISTRATION=true
AUTO_FLIP_CHECK_INTERVAL_MINUTES=5
``

   **On Windows:**
   ```powershell
   .venv\Scripts\activate
   ```

2. *Activate Virtual Environment

**Mac/Linux:**
```bash
source .venv/bin/activate
```

**Windows:**
```powershell
.venv\Scripts\activate
```

### Launch the Application

```bash
python Proper_MS/master_control.py
```

The GUI opens with three main tabs:
- **Dashboard** - System status cards and automation controls
- **Settings** - Credential and configuration management  
- **Logs** - Real-time activity viewer with search/filter

### First Run Setup

1. Microsoft OAuth login opens in your browser automatically
2. Authorize the application to access your Outlook account
3. Token is cached locally (`.token_cache`) for future sessions
4. Configure remaining credentials via Settings tab if not already done
### Starting AHA Training Automation

1. Ensure AHA credentials are configured
2. Click **"Start AHA Automation"** button
3. The system will:
   - Open an automated browser session
   -Using the Automation Systems

**RQI Email Processing:**
1. Click **"Start RQI Email Processing"**
2. Monitors inbox → Extracts lead data → Updates Google Sheet → Creates calendar events
3. View live updates in Logs tab

**AHA Training Automation:**
1. Click **"Start AHA Automation"**  
2. Automated browser navigates platform → Completes registration forms → Submits data
3. Monitor progress in Logs tab

**Controls:**
- Pause/resume each automation independently
- Run minimized via system tray with desktop notifications
- Right-click tray icon for quick access menu
python manual_flip_registration.py --first-name John --last-name Doe

# Batch flip from CSV (FirstName,LastName columns)
python manual_flip_registration.py --batch students.csv

# Scan and flip all pending
python manual_flip_registration.py --scan-all
```

## 📦 Building a Standalone Executable

If you want to distribute the app without requiring Python installation:

### Using the Spec File (Recommended)

1. **Navigate to the project root directory**
2. **Run PyInstaller with the included spec file:**

   ```bash
   pyinstaller master_control.spec --clean
   ```

3. **Install Playwright browsers in the built app:**

   ```bash
   playwright install
   ```

4. **Find your executable:**
   - **Output location:** `dist/CSC131_Automation/`
   - The folder contains the executable and all required files
To distribute without requiring Python installation:

```bash
pyinstaller master_control.spec --clean
```

Output: `dist/CSC131_Automation/` (distribute entire folder)

**What's Bundled:**
- All Python dependencies and libraries
- Configuration files (`.env`, service account JSONs, GUI assets)
- Playwright browsers

> **⚠️ Security**: Credential files are bundled into the executable and can be extracted. Only distribute to trusted users
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

## 🎯 How It Works

### GUI Components

**Navigation Panel** (left sidebar):
- 🏠 **Dashboard** - Real-time status cards showing system health and quick start/stop controls
- ⚙️ **Settings** - Edit environment variables, API credentials, and automation settings
- 📋 **Logs** - Full log viewer with search/filter capabilities
- ℹ️ **About** - Application version and information

**System Tray Integration**:
- Left-click the tray icon to open/restore the GUI window
- Right-click for quick menu (pause/resume/quit controls)
- Runs unobtrusively in the background with notification support

**Automation Controls**:
- Pause/resume all automation systems together
- Control AHA and RQI modules independently
- Runs in continuous cycles at configured intervals (default: 10 seconds)

## 🗂️ Project Structure

```
CSC131_Project/
├── Proper_MS/              # Main application module
│   ├── gui.py             # GUI interface (ttkbootstrap)
│   ├── master_control.py  # Main entry point and controller
│   ├── read_emails.py     # Outlook email reading via Microsoft Graph
│   ├── parser.py          # Email content parsing and data extraction
│   ├── store_data.py      # Google Sheets integration
│   ├── outlook_authentication.py  # OAuth2 authentication
│   └── run_automation.py  # Automation orchestration
│
├── RQI_EmailSheets/       # Email-to-Sheets automation module
│   └── email_to_sheets.py # Email processing pipeline
│
├── Scheduling/            # AHA training automation module
│   ├── scheduling.py      # Web automation with Playwright
│   └── apikey.json        # AHA API configuration
**Email Processing Workflow:**
1. Monitors Outlook inbox via Microsoft Graph API
2. Parses emails matching configured criteria  
3. Extracts lead data (names, dates, course details)
4. Appends to Google Sheets via service account
5. Creates calendar events for important dates

**AHA Automation Workflow:**
1. Launches headless Playwright browser
2. Navigates to AHA training platform
3. Fills registration forms with course data
4. Submits and confirms completion

**GUI Controls:**
- Independent start/stop for each automation system
- Continuous monitoring cycles (configurable intervals)
- System tray for background operation with notificationsnv:
  ```bash
  python3 -m venv .venv
  ```

**Problem: "Module not found" errors**
- **Solution**: Ensure the virtual environment is activated and dependencies are installed:
  ```bash
  source .venv/bin/activate  # or .venv\Scripts\activate on Windows
  pip install -r requirements.txt
  ```

**Problem: Microsoft authentication fails**
- **Solution**: 
  - Verify your `CLIENT_ID` and `TENANT_ID` are correct
  - Check that your Azure app has the correct API permissions
  - Clear cached tokens (delete `.token_cache` file) and try again
  - Ensure internet connection is stable

**Problem: Google Sheets not updating**
- **Solution**:
  - Verify `service_account.json` is in the project root
  - Check that the service account has edit access to the spreadsheet
  - Confirm `SPREADSHEET_ID` and `WORKSHEET_NAME` are correct
  - Check the Logs tab for specific error messages

**Problem: Playwright browser fails to launch**
- **Solution**: Run `playwright install` to download browser binaries:
  ```bash
  playwright install
  ```
| Issue | Solution |
|-------|----------|
| **Virtual environment fails** | Ensure Python 3.8+ installed: `python3 -m venv .venv` |
| **Module not found** | Activate venv and reinstall: `pip install -r requirements.txt` |
| **Microsoft auth fails** | Verify CLIENT_ID/TENANT_ID, check Azure API permissions, delete `.token_cache` and retry |
| **Sheets not updating** | Verify `service_account.json` in project root, confirm service account has edit access, check SPREADSHEET_ID/WORKSHEET_NAME |
| **Playwright fails** | Run `playwright install` with venv activated |
| **GUI won't open** | Linux: `sudo apt-get install python3-tk`<br>Check terminal for errors |
| **No system tray icon** | macOS: Grant accessibility permissions<br>Windows: Enable system tray icons<br>Linux: Check desktop environment tray support |

**Getting Help:** Check Logs tab for detailed errors, review terminal output, verify all credentials are configured- **ttkbootstrap** - Modern themed GUI framework
- **playwright** - Web automation
- **msal** - Microsoft authentication  
- **gspread** - Google Sheets API
- **pystray** - System tray integration
- **python-dotenv** - Environment variable management
- **Pillow** - Icon image processing

## 🔐 Security Notes

- Add `.env`, `service_account.json`, `google_sheet_api_key.json`, and `.token_cache` to `.gitignore`
- Never commit credential files to version control
- Bundled executables contain extractable credentials - distribute only to trusted users
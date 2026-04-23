# CSC131 Automation Project

A comprehensive automation suite with a user-friendly GUI for streamlining email processing and training course management workflows.

## 📋 Overview

This project automates repetitive business processes through two main systems:

1. **RQI Email Processing System** - Automatically monitors your Outlook inbox, extracts lead information from specific emails, logs data to Google Sheets, and creates calendar reminders
2. **AHA Training Course Automation** - Handles registration and data entry for American Heart Association training courses through automated web browser interactions

Both systems run independently with their own start/stop controls, accessible through a modern GUI dashboard.

## ✨ Key Features

- **📊 Interactive GUI Dashboard** - Real-time status monitoring, live activity logs, and easy control buttons
- **🔒 Secure Authentication** - OAuth2-based login (no passwords stored locally)
- **📧 Email Integration** - Connects to Outlook via Microsoft Graph API
- **📈 Google Sheets Integration** - Automatically updates spreadsheets with extracted data
- **📅 Calendar Management** - Creates events and reminders automatically
- **🌐 Web Automation** - Browser-based automation for AHA course registration
- **🔔 System Tray Integration** - Run minimized in the background with notification support
- **⚙️ Settings Panel** - Configure all credentials and settings through the GUI

## 🔧 Prerequisites

Before installing, make sure you have:

- **Python 3.8 or higher** ([Download Python](https://www.python.org/downloads/))
- **Microsoft Outlook account** with email access
- **Azure App Registration** (for Outlook API access)
  - Client ID
  - Tenant ID
  - Appropriate API permissions (Mail.Read, Calendars.ReadWrite)
- **Google Cloud Service Account** (for Sheets access)
  - Service account JSON key file
  - Sheets API enabled
- **AHA Platform Credentials** (if using training automation)
- **Internet connection** (required for API calls and web automation)

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
- ✅ Install all required Python packages (tkinter, playwright, gspread, msal, etc.)
- ✅ Set up the development environment

### Step 3: Install Playwright Browsers

After the Python packages are installed, run:

```bash
# Activate the virtual environment first (see "Running the Application" below)
playwright install
```

This downloads the browser binaries needed for web automation.

## ⚙️ Configuration

You'll need to set up credentials for the various services. The good news is that most of this can be done through the **GUI Settings Panel** after launching the app!

### Required Configuration Files

1. **Azure App Registration** (for Outlook/Email access)
   - `CLIENT_ID` - Your Azure app client ID
   - `TENANT_ID` - Your Azure tenant ID
   - `AUTHORITY` - Azure authority URL
   - `SCOPES` - API permission scopes (e.g., `Mail.Read Calendars.ReadWrite`)

2. **Google Sheets API**
   - `service_account.json` - Google service account credentials
   - `google_sheet_api_key.json` - Additional API key file
   - `SPREADSHEET_ID` - The ID of your Google Sheet (found in the sheet URL)
   - `WORKSHEET_NAME` - The specific worksheet/tab name

3. **AHA Platform**
   - Credentials will be prompted on first run
   - Can be saved through the Settings panel

### Setting Up Credentials

**Option 1: Using the GUI (Recommended)**
1. Launch the application (see "Running the Application" below)
2. Click the "Settings" button
3. Enter your credentials in the form fields
4. Click "Save Settings"

**Option 2: Manual Configuration**
Create/edit a `.env` file in the project root with your credentials:

```env
CLIENT_ID=your-azure-client-id
TENANT_ID=your-azure-tenant-id
AUTHORITY=https://login.microsoftonline.com/your-tenant-id
SCOPES=Mail.Read Calendars.ReadWrite
SPREADSHEET_ID=your-google-sheet-id
WORKSHEET_NAME=Sheet1

# Acuity Registration Flipping
AUTO_FLIP_ACUITY_REGISTRATION=true          # Auto-flip when processing emails (true/false)
AUTO_FLIP_CHECK_INTERVAL_MINUTES=5          # Check every X minutes (0 to disable)
```

Place your Google service account JSON files in the project root:
- `service_account.json`
- `google_sheet_api_key.json`

## ▶️ Running the Application

### Development Mode

1. **Activate the virtual environment:**

   **On Mac/Linux:**
   ```bash
   source .venv/bin/activate
   ```

   **On Windows:**
   ```powershell
   .venv\Scripts\activate
   ```

2. **Launch the application:**
   ```bash
   pyinstaller master_control.spec --clean
   ```

The GUI window will open with:
- **Dashboard Tab** - Shows system status and control buttons
- **Settings Tab** - Configure all credentials and settings
- **Logs Tab** - View real-time activity logs
- **System Tray Icon** - Minimize to tray and get notifications

### First Run

On your first run:
1. The app will prompt you to authenticate with Microsoft (for Outlook access)
2. A browser window will open for OAuth2 login
3. After authorization, the token is cached for future use
4. If AHA automation is needed, you'll be prompted for those credentials

## 📖 Usage Guide

### Starting Email Processing

1. Ensure your Outlook credentials are configured
2. Click **"Start RQI Email Processing"** button
3. The system will:
   - Monitor your inbox for new emails matching specific criteria
   - Extract lead information (names, dates, course details)
   - Append data to the configured Google Sheet
   - Create calendar events for important dates
4. View live updates in the **Logs** tab

### Starting AHA Training Automation

1. Ensure AHA credentials are configured
2. Click **"Start AHA Automation"** button
3. The system will:
   - Open an automated browser session
   - Navigate to the AHA training platform
   - Complete registration forms
   - Submit course data
4. Monitor progress in the **Logs** tab

### Pausing/Stopping

- Each automation can be **paused** and **resumed** independently
- Use the corresponding control buttons for each system
- Logs show when systems are paused or stopped

### Running in the Background

- Click the **minimize to tray** button to run in the background
- The app continues running and shows notifications
- Right-click the system tray icon for quick access

### Acuity Registration Flipping

Flip Acuity Registration status from "No" to "Yes" using one of three methods:

**1. Email-Triggered (Automatic)**
- Set `AUTO_FLIP_ACUITY_REGISTRATION=true` in `.env`
- Flips automatically when processing emails

**2. Scheduled Checking (Time-Based)**
- Set `AUTO_FLIP_CHECK_INTERVAL_MINUTES=5` in `.env`
- Compares AHA sheet vs RQI sheet every X minutes
- Run standalone: `python registration_scheduler.py`

**3. Manual (On-Demand)**
```bash
# Flip single person
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
   - You can distribute this entire folder

### What Gets Bundled

The executable includes:
- All Python dependencies
- Configuration files (`.env`, service account JSONs)
- GUI assets and icons
- Required libraries (ttkbootstrap, playwright, msal, etc.)

> **Important**: The `.env` and JSON credential files are bundled into the executable. Make sure they contain the correct credentials before building.

<details>
<summary>📝 Advanced: Manual PyInstaller Build Commands</summary>

If you need to customize the build process, use these manual commands:

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
│
├── scripts/               # Setup and installation scripts
│   ├── setup.sh          # macOS/Linux setup
│   └── setup.ps1         # Windows PowerShell setup
│
├── .env                   # Environment variables (create this)
├── service_account.json   # Google Sheets credentials (add this)
├── google_sheet_api_key.json  # Google API key (add this)
└── master_control.spec    # PyInstaller build configuration
```

## 🐛 Troubleshooting

### Common Issues

**Problem: Virtual environment activation fails**
- **Solution**: Make sure Python 3.8+ is installed. Try recreating the venv:
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

**Problem: GUI doesn't open**
- **Solution**: 
  - On Linux, ensure tkinter is installed: `sudo apt-get install python3-tk`
  - Verify you're using `--windowed` flag in PyInstaller for GUI apps
  - Check for error messages in the terminal

**Problem: System tray icon not appearing**
- **Solution**:
  - macOS: Grant accessibility permissions in System Preferences
  - Windows: Check if system tray icons are enabled in taskbar settings
  - Linux: Some desktop environments require additional tray support

### Getting Help

- Check the **Logs tab** in the application for detailed error messages
- Review the terminal output when running in development mode
- Ensure all prerequisites are met and credentials are configured correctly

## 📄 Dependencies

Main Python packages used:
- `ttkbootstrap` - Modern themed tkinter GUI
- `playwright` - Web automation framework
- `msal` - Microsoft authentication library
- `gspread` - Google Sheets API client
- `pystray` - System tray integration
- `python-dotenv` - Environment variable management
- `Pillow` - Image processing for icons

## 🔐 Security Notes

- **Never commit** `.env`, `service_account.json`, or `google_sheet_api_key.json` to version control
- These files contain sensitive credentials
- Add them to `.gitignore`
- OAuth tokens are cached locally - keep `.token_cache` secure
- When distributing executables, be aware that bundled credentials can be extracted

## 📝 License

This project was created for CSC131 coursework.

## 🤝 Contributing

This is an academic project. For improvements or issues, please contact the development team.

---

**Built with ❤️ for CSC131**

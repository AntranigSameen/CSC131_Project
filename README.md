# CSC131 Automation Project

## Overview

This is an automated system designed to streamline the management of RQI (Resuscitation Quality Improvement) training programs and AHA (American Heart Association) certification registrations. The application automates email processing, student registration, Google Sheets integration, and reminder notifications through a user-friendly GUI interface.

## Key Features

### 📧 Email Automation
- **Automated Email Processing**: Monitors Microsoft Outlook inbox for student registration requests
- **Email-to-Sheets Integration**: Automatically extracts employee information (LocationID, Name, Email, HireDate) from emails and appends to Google Sheets
- **Template-Based Responses**: Location-specific email templates for automated communications
- **Reminder System**: Automatically sends reminder emails to students after configurable periods (default: 7 days)
- **Manual Email Handling**: GUI interface for sending custom emails when needed

### 📝 Registration Management
- **AHA Registration Automation**: Automatically registers students for AHA training courses using Playwright browser automation
- **Acuity Integration**: Manages training schedules and appointments
- **Course Availability Checking**: Validates available training slots before registration
- **Registration Tracking**: Maintains detailed logs of all registration attempts and outcomes

### 📊 Data Management
- **Google Sheets Integration**: Real-time synchronization with Google Sheets for student data
- **CSV Export**: Generate and upload CSV reports for tracking and analysis
- **Location-Based Tracking**: Separate tracking for different training locations
- **SFTP Upload**: Automated file transfer capabilities for data sharing

### 🖥️ User Interface
- **Modern GUI**: PySide6-based graphical interface for easy operation
- **System Tray Integration**: Runs minimized in system tray for background operation
- **Settings Management**: Comprehensive settings panel for configuration without editing files
- **Real-time Logs**: Live log viewer to monitor automation activities
- **Multi-Location Support**: Manage multiple training locations with unique configurations

## Prerequisites

Before installing this project, ensure you have:

- **Python 3.8+** installed on your system
- **Microsoft Azure AD Application** with appropriate permissions for:
  - Microsoft Graph API (Mail.Read, Mail.Send, Calendar.ReadWrite)
  - Proper Client ID and Tenant ID configured
- **Google Cloud Service Account** with:
  - Google Sheets API enabled
  - Service account JSON key file
- **AHA Training Portal Account** with proper credentials
- **Operating System**: Windows, macOS, or Linux

## Installation

### Automated Setup (Recommended)

#### For macOS/Linux:
```bash
# Navigate to the project directory
cd CSC131_Project

# Run the setup script
chmod +x scripts/setup.sh
./scripts/setup.sh
```

#### For Windows:
```powershell
# Navigate to the project directory
cd CSC131_Project

# Run the setup script
.\scripts\setup.ps1
```

### Manual Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd CSC131_Project
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**:
   - **Windows**: `.venv\Scripts\activate`
   - **macOS/Linux**: `source .venv/bin/activate`

4. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install msal requests python-dotenv
   pip install gspread google-auth google-auth-oauthlib google-auth-httplib2
   pip install PySide6 playwright
   pip install pyinstaller flask
   python -m playwright install chromium
   ```

## Configuration

### 1. Google Sheets API Setup

1. Place your Google Service Account JSON key file in the project root directory
2. Rename it to `google_sheet_api_key.json` or update the path in your `.env` file
3. Share your Google Sheet with the service account email address (found in the JSON file)

### 2. Microsoft Azure AD Configuration

Create a `.env` file in the project root with the following variables:

```env
# Microsoft Authentication
CLIENT_ID=your-azure-client-id
TENANT_ID=your-azure-tenant-id
AUTHORITY=https://login.microsoftonline.com/your-tenant-id
SCOPES=["https://graph.microsoft.com/.default"]

# Google Sheets
SERVICE_ACCOUNT_AHA_JSON=google_sheet_api_key.json
GOOGLE_SHEET_URL=your-google-sheet-url

# AHA Portal Settings
ORG_NAME=Your Organization Name

# Automation Settings
INTERVAL=10                           # Check interval in seconds
EMAIL_REFRESH_ON_START=1              # 1=refresh on startup, 0=skip
FORCE_RUN=0                           # 1=always process latest, 0=normal
PAUSE_AT_END=1                        # 1=keep browser open, 0=close
PW_TIMEOUT_MS=10000                   # Playwright timeout in milliseconds
ADVANCE_INDEX_ON_NO_COURSES=1         # Move to next email if no courses available
REMINDER_EMAIL_DAYS=7                 # Days before sending reminder

# GUI Settings
IS_HEADLESS=0                         # 1=run browser headless, 0=show browser
```

### 3. Location Configuration

The application supports multiple training locations. Configuration files are automatically created:

- **location_keys.txt**: Maps location IDs to names
- **location_email_templates.json**: Email templates per location
- **location_email_tracker.json**: Tracks sent emails per location

These can be managed through the GUI Settings panel.

## Usage

### Starting the Application

1. **Activate your virtual environment**:
   ```bash
   source .venv/bin/activate  # macOS/Linux
   .venv\Scripts\activate     # Windows
   ```

2. **Run the main application**:
   ```bash
   python Proper_MS/master_control.py
   ```

3. **First-time setup**:
   - The application will prompt for AHA portal credentials
   - Authenticate with Microsoft when prompted
   - Configure settings through the GUI settings panel

### Main Features

#### Automated Mode
- Click **"Start Automation"** to begin monitoring emails and processing registrations
- The system will:
  1. Check for new registration emails
  2. Extract student information
  3. Register students in available AHA courses
  4. Log to Google Sheets
  5. Send confirmation emails
  6. Schedule reminder emails

#### Manual Operations
- **Send Manual Email**: Compose and send custom emails through the GUI
- **Manual Registration**: Manually trigger registration for specific students
- **Generate CSV**: Export current data to CSV format
- **Upload to SFTP**: Transfer files to configured SFTP server

#### Monitoring
- **View Logs**: Real-time log viewer shows all automation activities
- **Check Status**: Dashboard displays current system status and recent activities
- **Email Tracker**: Review all sent emails organized by location

## Project Structure

```
CSC131_Project/
├── Proper_MS/                      # Main application package
│   ├── master_control.py          # Main entry point and orchestration
│   ├── gui.py                     # PySide6 GUI implementation
│   ├── run_automation.py          # AHA registration automation
│   ├── read_emails.py             # Email monitoring and parsing
│   ├── reminder_emailer.py        # Automated reminder system
│   ├── outlook_authentication.py  # Microsoft OAuth2 handling
│   ├── location_keys.py           # Location management
│   ├── location_email_templates.py# Email template management
│   ├── location_email_tracker.py  # Email tracking system
│   ├── store_data.py              # Data persistence
│   ├── utils.py                   # Utility functions
│   └── ...                        # Additional modules
├── RQI_EmailSheets/               # Email to Sheets integration
│   └── email_to_sheets.py         # Email extraction and Sheets API
├── scripts/                       # Setup scripts
│   ├── setup.sh                   # macOS/Linux setup
│   └── setup.ps1                  # Windows setup
├── google_sheet_api_key.json      # Google service account key (not in git)
├── .env                           # Environment configuration (not in git)
└── README.md                      # This file
```

## Key Components Explained

### Master Control (`master_control.py`)
The main orchestration script that:
- Initializes all subsystems
- Manages the automation loop
- Coordinates between email processing, registration, and notifications
- Handles GUI initialization and system tray integration

### GUI (`gui.py`)
Provides a comprehensive interface for:
- Starting/stopping automation
- Configuring settings without editing files
- Viewing real-time logs
- Managing location templates and keys
- Sending manual emails

### Registration Automation (`run_automation.py`)
Uses Playwright to:
- Log into the AHA training portal
- Search for available courses
- Fill registration forms
- Handle course availability issues
- Capture screenshots for debugging

### Email Processing (`read_emails.py`, `email_to_sheets.py`)
- Connects to Microsoft Graph API
- Filters unread emails matching criteria
- Extracts structured data using regex patterns
- Updates Google Sheets with new entries
- Marks emails as read after processing

### Reminder System (`reminder_emailer.py`)
- Tracks registration dates
- Calculates due dates for reminders
- Sends automated follow-up emails
- Manages location-specific reminder templates

## Troubleshooting

### Common Issues

**Authentication Errors**
- Verify your Azure AD Client ID and Tenant ID are correct
- Ensure proper API permissions are granted in Azure Portal
- Delete cached tokens and re-authenticate

**Google Sheets Not Updating**
- Confirm service account has edit access to the sheet
- Check that the sheet URL in `.env` is correct
- Verify the service account JSON file path

**Browser Automation Fails**
- Ensure Playwright browsers are installed: `python -m playwright install`
- Check if AHA portal structure has changed
- Review screenshots in the `shots/` folder for debugging

**No Emails Being Processed**
- Verify Outlook permissions are granted
- Check email filter criteria in settings
- Ensure emails are unread and in the correct folder

## Building Executables

To create a standalone executable:

```bash
# Activate virtual environment first
pyinstaller master_control.spec
```

The executable will be created in the `dist/` folder.

## Security Notes

⚠️ **Important**: Never commit sensitive files to version control:
- `.env` file (contains credentials)
- `google_sheet_api_key.json` (service account credentials)
- `aha_auth.json` (saved login state)
- Any files containing passwords or tokens

Add these to your `.gitignore` file.

## Contributing

This project was developed as part of CSC131 (Software Engineering). For contributions:
1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request with detailed description

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review log files in the application
3. Check console output for error messages
4. Contact the development team

## License

[Specify your license here]

---

**Last Updated**: May 2026  
**Version**: 1.0  
**Developed By**: CSC131 Team


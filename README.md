# CSC131 Automation Project

## Overview

An automated system for streamlining RQI (Resuscitation Quality Improvement) training programs and AHA (American Heart Association) certification registrations. The application automates email processing, student registration, Google Sheets integration, reminder notifications, and Acuity scheduling through a modern GUI interface.

## Key Features

### 📧 Email Automation
- **Automated Email Processing**: Monitors Microsoft Outlook inbox for student registration requests via Microsoft Graph API
- **Email-to-Sheets Integration**: Automatically extracts employee information (LocationID, Name, Email, HireDate) and appends to Google Sheets
- **Template-Based Responses**: Location-specific email templates with automatic variable substitution
- **Reminder System**: Configurable reminder emails sent after specified periods (default: 7 days)
- **Manual Email Handling**: GUI interface for sending custom emails with template support

### 📝 Registration Management
- **AHA Registration Automation**: Playwright browser automation registers students for AHA training courses
- **Acuity Integration**: Automatic status syncing between AHA registration sheet and RQI tracking sheet
- **Auto-Flip Scheduler**: Background service that periodically scans and updates Acuity registration status
- **Manual Registration Tools**: Command-line tool for manually flipping registration status for specific students
- **Course Availability Checking**: Validates available training slots before registration attempts
- **Registration Tracking**: Maintains detailed logs with screenshots of all registration attempts

### 📊 Data Management & Analytics
- **Google Sheets Integration**: Real-time bidirectional synchronization with Google Sheets
- **CSV Export & Upload**: Generate and upload CSV reports with configurable scheduling
- **SFTP Upload**: Automated file transfer to remote servers
- **Dashboard Metrics**: Daily tracking of registrations and payments with automatic reset
- **Location-Based Tracking**: Separate tracking and configuration for multiple training locations
- **Email Deduplication**: Hash-based tracking prevents duplicate reminder emails

### 🖥️ User Interface
- **Modern GUI**: PySide6-based interface with clean, intuitive layout
- **System Tray Integration**: Runs minimized in system tray for seamless background operation
- **Settings Management**: Comprehensive settings panel for all configurations without editing files
- **Real-time Logs**: Live log viewer with split logging (separate logs for different services)
- **Multi-Location Support**: Manage unlimited training locations with unique templates and settings
- **Dashboard Events**: Live activity feed showing current automation status

## Prerequisites

### Required Software
- **Python 3.8+** installed on your system
- **Operating System**: Windows, macOS, or Linux

### Required Accounts & Credentials
- **Microsoft Azure AD Application** with:
  - Microsoft Graph API permissions: `Mail.Read`, `Mail.Send`, `Calendar.ReadWrite`
  - Client ID and Tenant ID from Azure Portal
  
- **Google Cloud Service Account** with:
  - Google Sheets API enabled
  - Service account JSON key file downloaded
  - Service account email granted edit access to your Google Sheets
  
- **AHA Training Portal Account** with valid login credentials

### Optional Services
- **SFTP Server** (if using automated CSV upload feature)
- **Acuity Scheduling** (if using appointment integration)

## Installation

### Automated Setup (Recommended)

#### macOS/Linux:
```bash
cd CSC131_Project
chmod +x scripts/setup.sh
./scripts/setup.sh
```

#### Windows:
```powershell
cd CSC131_Project
.\scripts\setup.ps1
```

The setup scripts will:
- Create a Python virtual environment
- Install all required dependencies
- Install Playwright browser automation (Chromium)

### Manual Setup

If you prefer manual installation or the automated scripts don't work:

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd CSC131_Project
   ```

2. **Create and activate virtual environment**:
   ```bash
   python -m venv .venv
   
   # Activate (macOS/Linux):
   source .venv/bin/activate
   
   # Activate (Windows):
   .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   # Core dependencies
   pip install --upgrade pip
   pip install msal requests python-dotenv flask
   
   # Google Sheets
   pip install gspread google-auth google-auth-oauthlib google-auth-httplib2
   
   # GUI and system tray
   pip install PySide6 pystray pillow ttkbootstrap
   
   # Browser automation
   pip install playwright
   python -m playwright install chromium
   
   # File transfer and data processing
   pip install paramiko openpyxl
   
   # Build tools (optional, for creating executables)
   pip install pyinstaller
   ```

## Configuration

### 1. Google Sheets API Setup

1. Download your Google Service Account JSON key file from Google Cloud Console
2. Place it in the project root directory as `google_sheet_api_key.json`
3. Share your target Google Sheet with the service account email (found in the JSON file under `client_email`)
4. Grant **Editor** access to the service account

### 2. Environment Variables Configuration

Create a `.env` file in the project root (`CSC131_Project/.env`) with these variables:

```env
# ==========================================
# Microsoft Authentication
# ==========================================
CLIENT_ID=your-azure-client-id
TENANT_ID=your-azure-tenant-id
AUTHORITY=https://login.microsoftonline.com/your-tenant-id
SCOPES=["https://graph.microsoft.com/.default"]
SENDER_EMAIL=source.email@example.com              # Email address to monitor for incoming registrations

# ==========================================
# Google Sheets Configuration
# ==========================================
SERVICE_ACCOUNT_AHA_JSON=google_sheet_api_key.json
GOOGLE_SHEET_URL=your-google-sheet-url-or-id
AHA_REGISTRATION_WORKSHEET=AHA Registration         # Worksheet name for AHA registrations
RQI_WORKSHEET=RQI Data                              # Worksheet name for RQI tracking

# ==========================================
# AHA Portal Settings
# ==========================================
ORG_NAME=Your Organization Name

# ==========================================
# Automation Settings
# ==========================================
INTERVAL=10                                         # Email check interval (seconds)
EMAIL_REFRESH_ON_START=1                            # 1=refresh on startup, 0=skip
FORCE_RUN=0                                         # 1=always process latest, 0=normal
PAUSE_AT_END=1                                      # 1=keep browser open for debugging, 0=close
PW_TIMEOUT_MS=10000                                 # Playwright timeout (milliseconds)
ADVANCE_INDEX_ON_NO_COURSES=1                       # Move to next email if no courses available
IS_HEADLESS=0                                       # 1=run browser headless, 0=show browser

# ==========================================
# Reminder Email Settings
# ==========================================
REMINDER_EMAIL_DAYS=7                               # Days after registration before sending reminder

# ==========================================
# Acuity Auto-Flip Settings
# ==========================================
AUTO_FLIP_ACUITY_REGISTRATION=true                  # Enable automatic registration status flipping
AUTO_FLIP_CHECK_INTERVAL_MINUTES=30                 # Interval for auto-flip checks (0 to disable)

# ==========================================
# SFTP Settings (Optional)
# ==========================================
SFTP_HOST=sftp.example.com
SFTP_PORT=22
SFTP_USERNAME=your_username
SFTP_PASSWORD=your_password
SFTP_REMOTE_PATH=/uploads/
```

### 3. Location Configuration

The application supports multiple training locations with unique configurations:

#### location_keys.txt
Maps location IDs to location names:
```
101=San Francisco Bay Area
102=Los Angeles Metro
103=San Diego County
```

#### location_email_templates.json
Defines email templates per location with variable substitution:
```json
{
  "101": {
    "subject": "Welcome to RQI Training - {{LOCATION}}",
    "body": "Dear {{NAME}},\n\nYour training at {{LOCATION}} is confirmed...",
    "reminder_subject": "Reminder: Complete Your Training",
    "reminder_body": "This is a friendly reminder..."
  }
}
```

#### location_email_tracker.json
Automatically tracks sent emails to prevent duplicates (auto-generated).

**Note**: These files can be created and managed through the GUI Settings panel.

## Usage

### Starting the Application

1. **Activate virtual environment**:
   ```bash
   # macOS/Linux
   source .venv/bin/activate
   
   # Windows
   .venv\Scripts\activate
   ```

2. **Run the application**:
   ```bash
   python Proper_MS/master_control.py
   ```

3. **First-time setup**:
   - Provide AHA portal credentials when prompted
   - Authenticate with Microsoft Graph API (browser window will open)
   - Configure settings through GUI Settings panel if needed

### Core Features

#### 🤖 Automated Mode
Click **"Start Automation"** to activate the full automation cycle:

1. **Email Monitoring**: Checks for new student registration emails
2. **Data Extraction**: Parses email content for student information
3. **AHA Registration**: Automatically registers students in available courses
4. **Google Sheets Logging**: Records all registrations with timestamps
5. **Confirmation Emails**: Sends location-specific confirmation messages
6. **Reminder Scheduling**: Queues reminder emails for future delivery
7. **Acuity Auto-Flip**: Background scheduler syncs registration status every 30 minutes (configurable)

#### 📋 Manual Operations

**Send Manual Email**
- Compose custom emails with template variables
- Select location-specific templates
- Send to individual or multiple recipients

**Manual Registration Flip**
- Use GUI or command-line tool to manually update registration status
- Useful for correcting data or handling exceptions

**CSV Generation & Upload**
- Generate current data snapshot as CSV
- Automatically upload to SFTP server (if configured)
- Configurable scheduling for regular exports

**Dashboard Monitoring**
- View real-time metrics (registrations today, payments today)
- Monitor live activity feed with recent events
- Check system status and automation health

### Command-Line Tools

#### Manual Registration Flip Tool

For manual control over Acuity registration status:

```bash
# Flip registration for a single person
python Proper_MS/manual_flip_registration.py --first-name John --last-name Doe

# Flip with specific worksheet
python Proper_MS/manual_flip_registration.py --first-name Jane --last-name Smith --worksheet "AHA Registration"

# Batch flip from CSV file (requires FirstName,LastName columns)
python Proper_MS/manual_flip_registration.py --batch students.csv

# Scan and automatically flip all pending registrations
python Proper_MS/manual_flip_registration.py --scan-all
```

### Monitoring & Logs

- **Live Log Viewer**: Real-time log display in GUI shows all automation activities
- **Split Logging**: Separate log files for different services (email, registration, reminders)
- **Dashboard Events**: Human-readable activity feed for quick status checks
- **Screenshots**: Playwright captures screenshots during registration for debugging (saved in `shots/` folder)
- **Email Tracker**: Review sent email history organized by location

## Project Structure

```
CSC131_Project/
├── Proper_MS/                          # Main application package
│   ├── __init__.py                    # Package initialization
│   ├── master_control.py              # Main entry point and orchestration
│   ├── gui.py                         # PySide6 GUI implementation
│   │
│   ├── # Core Automation Modules
│   ├── run_automation.py              # AHA registration browser automation
│   ├── run_helper.py                  # Automation cycle helper functions
│   ├── read_emails.py                 # Email monitoring via Microsoft Graph API
│   ├── reminder_emailer.py            # Automated reminder email system
│   ├── registration_scheduler.py      # Background Acuity auto-flip scheduler
│   │
│   ├── # Registration Management
│   ├── acuity_registration.py         # Acuity-to-AHA registration sync
│   ├── manual_flip_registration.py    # CLI tool for manual registration flipping
│   │
│   ├── # Email & Communication
│   ├── outlook_authentication.py      # Microsoft OAuth2 authentication
│   ├── manual_email_handler.py        # Manual email composition interface
│   ├── send_manual_email.py           # Email sending functionality
│   ├── location_email_templates.py    # Location-based template management
│   ├── location_email_tracker.py      # Email deduplication tracking
│   │
│   ├── # Data & Configuration
│   ├── store_data.py                  # Data persistence layer
│   ├── parser.py                      # Email content parsing
│   ├── name_date_pull.py              # Email data extraction
│   ├── location_keys.py               # Location ID mapping
│   ├── dashboard_events.py            # Dashboard activity logging
│   ├── dashboard_metrics.py           # Daily metrics tracking
│   │
│   ├── # Utilities
│   ├── utils.py                       # Common utility functions
│   ├── split_logging.py               # Multi-service logging setup
│   ├── setup_login.py                 # AHA portal login validation
│   │
│   ├── # Configuration Files
│   ├── location_keys.txt              # Location ID to name mappings
│   ├── location_email_templates.json  # Email templates per location
│   ├── location_email_tracker.json    # Sent email tracking (auto-generated)
│   ├── .env                           # Local environment overrides
│   │
│   ├── # Assets
│   ├── checkmark.svg                  # GUI icon assets
│   │
│   └── email_templates/               # Email body templates
│       ├── acuity_registered_email_body.txt
│       └── acuity_not_registered_email_body.txt
│
├── RQI_EmailSheets/                   # Email-to-Sheets integration
│   ├── __init__.py
│   └── email_to_sheets.py             # Email extraction and Sheets API
│
├── scripts/                           # Setup automation scripts
│   ├── setup.sh                       # macOS/Linux setup script
│   └── setup.ps1                      # Windows PowerShell setup script
│
├── # Root Configuration Files
├── .env                               # Environment variables (not in git)
├── google_sheet_api_key.json          # Google service account key (not in git)
├── master_control.spec                # PyInstaller build specification
├── .gitignore                         # Git ignore rules
└── README.md                          # This file
```

## Key Components Explained

### Core Orchestration

**master_control.py**
- Application entry point and main orchestration engine
- Initializes all subsystems (email monitoring, registration, reminders, GUI)
- Manages the automation loop and coordinates between services
- Handles system tray integration and application lifecycle
- Configures SSL certificates and environment variable loading

**gui.py**
- Modern PySide6-based graphical user interface
- Settings panel for configuring all options without editing files
- Real-time log viewer with automatic scrolling
- System tray icon with context menu
- Manual email composition interface
- Dashboard with live metrics and activity feed

### Registration & Automation

**run_automation.py**
- Playwright browser automation for AHA portal interactions
- Automatically logs into AHA training portal
- Searches for available course slots by location
- Fills and submits registration forms
- Captures screenshots at each step for debugging
- Handles course availability and error conditions

**acuity_registration.py**
- Syncs Acuity Registration status between AHA and RQI sheets
- Automatically updates "Acuity Registration" column from "No" to "Yes"
- Name-based matching with normalization for reliable lookups
- Supports both automatic (via scheduler) and manual (via CLI) updates
- Prevents duplicate updates with smart row detection

**registration_scheduler.py**
- Background thread that runs periodic registration status checks
- Configurable interval (default: 30 minutes)
- Automatically scans for pending registrations and flips status
- Independent of email processing cycle
- Can be enabled/disabled via environment variable

**manual_flip_registration.py**
- Command-line tool for manual registration status management
- Single person flip, batch CSV processing, or full scan modes
- Useful for troubleshooting and exception handling
- Detailed logging of all flip operations

### Email Processing

**read_emails.py** & **name_date_pull.py**
- Connects to Microsoft Graph API with OAuth2 authentication
- Filters unread emails from specified sender address
- Extracts structured data using regex patterns
- Marks emails as read after successful processing
- Supports configurable email refresh on startup

**outlook_authentication.py**
- Handles Microsoft OAuth2 authentication flow
- Manages token caching and refresh
- Opens browser for user consent when needed
- Provides access tokens for Graph API requests

**reminder_emailer.py**
- Tracks registration dates from Google Sheets
- Calculates reminder due dates based on configurable period
- Sends automated follow-up emails using location templates
- Hash-based deduplication prevents sending duplicate reminders
- Supports both initial confirmation and reminder email types

**location_email_templates.py** & **location_email_tracker.py**
- Manages location-specific email templates with variable substitution
- Tracks sent emails per location using JSON storage
- Prevents duplicate emails using content-based hashing
- Supports template variables: `{{NAME}}`, `{{LOCATION}}`, `{{EMAIL}}`, etc.

### Data Management

**email_to_sheets.py** (in RQI_EmailSheets package)
- Background worker thread for email-to-sheets synchronization
- Extracts employee data from emails (LocationID, Name, Email, HireDate)
- Appends new entries to Google Sheets in real-time
- Generates CSV exports on demand or schedule
- Handles SFTP upload for automated file sharing
- Validates SFTP settings before upload attempts

**store_data.py**
- Provides data persistence layer for application state
- Manages serialization/deserialization of configuration
- Handles file I/O with proper error handling

**dashboard_metrics.py**
- Tracks daily metrics (registrations, payments)
- Automatically resets counters at midnight
- Persists metrics to JSON file
- Integrates with Google Sheets to count total records
- Provides real-time statistics for GUI dashboard

**dashboard_events.py**
- Simple logging interface for human-readable activity events
- Feeds the live activity dashboard in GUI
- Separates high-level events from detailed debug logs

### Utilities & Support

**utils.py**
- Common utility functions used across modules
- Path resolution for PyInstaller bundled executables
- Resource loading helpers
- Settings management and validation
- Cross-platform directory management

**split_logging.py**
- Configures separate log files for different services
- Enables parallel log viewing and debugging
- Maintains clean separation of concerns in logging

**setup_login.py**
- Validates AHA portal credentials on startup
- Prompts for credentials if not saved
- Stores encrypted authentication state

## Troubleshooting

### Authentication Issues

**Microsoft Graph API Authentication Fails**
- Verify `CLIENT_ID` and `TENANT_ID` in `.env` file are correct
- Check Azure AD app has required API permissions granted (and admin consent given)
- Delete cached token files (`token_cache.json`, `aha_auth.json`) and re-authenticate
- Ensure the redirect URI in Azure matches what the application uses

**AHA Portal Login Fails**
- Verify credentials through manual browser login first
- Check if portal structure has changed (may need code updates)
- Review screenshots in `shots/` folder to see where automation failed
- Try running with `IS_HEADLESS=0` to watch browser automation

### Google Sheets Issues

**Sheets Not Updating**
- Confirm service account email has **Editor** access to the sheet
- Verify `GOOGLE_SHEET_URL` or sheet ID in `.env` is correct
- Check `google_sheet_api_key.json` file path and permissions
- Ensure Google Sheets API is enabled in Google Cloud Console
- Look for errors in logs mentioning "gspread" or "Google Sheets"

**Wrong Worksheet**
- Verify `AHA_REGISTRATION_WORKSHEET` and `RQI_WORKSHEET` names match exactly (case-sensitive)
- Check for extra spaces in worksheet names
- Ensure worksheets exist in the specified Google Sheet

### Email Processing Problems

**No Emails Being Processed**
- Verify `SENDER_EMAIL` matches the email address sending registrations
- Check that emails are unread and in the Inbox folder
- Ensure Microsoft Graph API permissions include `Mail.Read`
- Confirm email filter criteria in code matches your email format
- Check logs for email fetch errors

**Duplicate Reminder Emails**
- Check `location_email_tracker.json` for corruption
- Verify hash generation is working correctly in logs
- Delete and recreate tracker file if necessary (will resend some reminders)

**Template Variables Not Substituting**
- Ensure template uses correct variable format: `{{VARIABLE_NAME}}`
- Check `location_email_templates.json` syntax is valid JSON
- Verify location ID in email matches a key in templates file

### Browser Automation Issues

**Playwright/Chromium Not Working**
- Reinstall Playwright browsers: `python -m playwright install chromium`
- Check system dependencies for Chromium (Linux may need additional packages)
- Try running with `IS_HEADLESS=0` to see browser window
- Review `shots/` folder screenshots to identify where automation breaks

**Registration Fails Silently**
- Enable detailed logging by checking console output
- Set `PAUSE_AT_END=1` to keep browser open after automation
- Increase `PW_TIMEOUT_MS` if pages load slowly
- Check if AHA portal HTML structure changed (may need selector updates)

### Acuity Auto-Flip Issues

**Auto-Flip Not Running**
- Verify `AUTO_FLIP_ACUITY_REGISTRATION=true` in `.env`
- Check `AUTO_FLIP_CHECK_INTERVAL_MINUTES` is greater than 0
- Look for scheduler logs in console output
- Ensure RQI and AHA worksheet names are configured correctly

**Manual Flip Tool Not Finding Records**
- Check name spelling matches exactly what's in Google Sheets
- Try using the `--scan-all` option to see if automatic matching works
- Verify worksheet name with `--worksheet` parameter if using non-default
- Check logs for normalization details (spaces, case differences)

### Data Export & SFTP Issues

**CSV Generation Fails**
- Ensure Google Sheets is accessible
- Check file permissions in output directory
- Verify sufficient disk space

**SFTP Upload Fails**
- Test SFTP credentials manually using an SFTP client
- Verify `SFTP_HOST`, `SFTP_PORT`, `SFTP_USERNAME`, `SFTP_PASSWORD` are correct
- Check `SFTP_REMOTE_PATH` exists on server and has write permissions
- Ensure firewall allows outbound connections on SFTP port
- Try with `validate_sftp_settings()` function for detailed diagnosis

### GUI & System Tray Issues

**GUI Won't Start**
- Verify PySide6 is installed: `pip list | grep PySide6`
- Check for Qt-related errors in console
- Try running without system tray integration (modify code if needed)

**System Tray Icon Not Appearing**
- Check `pystray` and `pillow` are installed
- Verify icon file (`checkmark.svg` or `icon.png`) exists
- Some Linux desktop environments require specific system tray support

### General Debugging

**Application Crashes on Startup**
- Check all required files exist (`.env`, `google_sheet_api_key.json`)
- Review error messages in console output
- Try running with Python directly (not as executable) for better error messages
- Check Python version is 3.8 or higher

**Logs Show Strange Errors**
- Enable DEBUG level logging in code for more detail
- Check `split_logging.py` configuration
- Review individual service log files if using split logging
- Look for SSL certificate errors (check `certifi` is installed)

**Performance Issues**
- Reduce `INTERVAL` to process emails less frequently
- Increase `AUTO_FLIP_CHECK_INTERVAL_MINUTES` to reduce Google Sheets API calls
- Check system resources (CPU, memory, network)
- Review log files for excessive API calls or loops

## Building Standalone Executables

To create a standalone executable that doesn't require Python installation:

### Using PyInstaller

1. **Ensure PyInstaller is installed**:
   ```bash
   pip install pyinstaller
   ```

2. **Build from project root**:
   ```bash
   pyinstaller master_control.spec --clean
   ```

3. **Locate the executable**:
   - Output folder: `dist/Automation Machine/`
   - Executable name: `Automation Machine` (or `Automation Machine.exe` on Windows)

### What Gets Bundled

The `.spec` file includes:
- All Python modules from `Proper_MS` and `RQI_EmailSheets`
- PySide6 GUI libraries
- Configuration files (`.env`, service account JSON, location configs)
- Icon files
- Email templates

### Important Notes

- ⚠️ **Security**: The bundled `.env` and credential files will be included in the executable directory
- 📦 **Size**: Executable will be ~150-200MB due to bundled Python interpreter and libraries
- 🖥️ **Platform**: Build on the target OS (Windows `.exe` must be built on Windows, etc.)
- 🔧 **Updates**: Rebuild after any code or dependency changes

### Distributing the Executable

When distributing to users:
1. Copy the entire `dist/Automation Machine/` folder
2. Users should create their own `.env` file with credentials
3. Include the `google_sheet_api_key.json` separately (not in version control)
4. Provide setup instructions for first-time configuration

## Security & Best Practices

### Protecting Sensitive Data

⚠️ **CRITICAL**: Never commit these files to version control:

| File | Contains | Risk Level |
|------|----------|-----------|
| `.env` | API credentials, passwords | 🔴 Critical |
| `google_sheet_api_key.json` | Service account private key | 🔴 Critical |
| `service_account.json` | Alternative service account key | 🔴 Critical |
| `aha_auth.json` | Saved AHA portal session | 🟡 Medium |
| `token_cache.json` | OAuth access tokens | 🟡 Medium |
| `*.pem`, `*.key` | SSL/SSH private keys | 🔴 Critical |
| `location_email_tracker.json` | May contain email addresses | 🟢 Low |

All these files are already listed in `.gitignore`. **Verify before committing!**

### Credential Management

**Best Practices:**
- Use environment variables for all credentials (`.env` file)
- Rotate service account keys periodically
- Use separate Azure AD apps for dev/staging/production
- Never hardcode passwords or API keys in source code
- Review `.gitignore` before each commit

**Service Account Security:**
- Grant minimum required permissions to Google Sheets
- Don't share service account JSON files via email or messaging
- Store backups in secure, encrypted locations
- Revoke compromised service accounts immediately in Google Cloud Console

### Application Security

- The application stores some data in plaintext (logs, trackers)
- Consider encrypting sensitive data at rest
- Use HTTPS/TLS for all API communications (already configured)
- Review log files before sharing; they may contain PII
- Sanitize data when debugging or sharing screenshots

### Production Deployment

For production environments:
1. Use dedicated service accounts with minimal permissions
2. Enable audit logging in Azure AD and Google Cloud
3. Monitor API usage for anomalies
4. Implement log rotation to prevent disk space issues
5. Use secure SFTP credentials (consider SSH keys over passwords)
6. Run as a non-privileged user account
7. Keep dependencies updated for security patches

## Development & Contributing

### Project Background

This project was developed as part of **CSC131 (Software Engineering)** to automate RQI training program management and AHA certification registration processes.

### Development Setup

1. Fork the repository
2. Clone your fork locally
3. Follow the installation instructions above
4. Create a feature branch: `git checkout -b feature/your-feature-name`
5. Make your changes with clear, descriptive commit messages
6. Test thoroughly with both automated and manual scenarios
7. Update documentation if adding new features
8. Submit a pull request with detailed description

### Code Style Guidelines

- Follow PEP 8 for Python code style
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Comment complex logic and business rules
- Keep functions focused and modular
- Handle errors gracefully with try/except blocks
- Log important events and errors appropriately

### Testing Checklist

Before submitting changes:
- [ ] Test email processing with sample emails
- [ ] Verify Google Sheets integration
- [ ] Test AHA registration automation
- [ ] Check GUI functionality (all buttons and panels)
- [ ] Verify system tray integration
- [ ] Test reminder email sending
- [ ] Validate Acuity auto-flip feature
- [ ] Test manual flip CLI tool
- [ ] Verify SFTP upload (if configured)
- [ ] Check CSV generation
- [ ] Review logs for errors or warnings
- [ ] Test on target operating system

### Building for Development & Testing

During development, you may want to test the application as a standalone executable:

```bash
# Ensure you're in the project root and have activated your virtual environment
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

# Build the executable
pyinstaller master_control.spec --clean
```

**Development Build Notes:**
- The `--clean` flag removes cached build files for a fresh build
- Output will be in `dist/Automation Machine/`
- Useful for testing deployment scenarios
- Verifies all dependencies are correctly bundled
- Test the executable on target platforms before distribution

See the [Building Standalone Executables](#building-standalone-executables) section for more details.

### Adding New Features

**Common Extensions:**
- Additional email template variables
- New location configurations
- Custom email filters
- Different reminder schedules
- Additional metrics tracking
- Alternative data export formats
- Integration with other scheduling systems

**When adding features:**
1. Update relevant configuration files
2. Add environment variables to `.env` example in this README
3. Update documentation with usage instructions
4. Add appropriate error handling and logging
5. Consider backward compatibility

## Support & Resources

### Getting Help

**When encountering issues:**

1. **Check this README** - especially the Troubleshooting section
2. **Review log files** - check console output and log viewer in GUI
3. **Examine screenshots** - `shots/` folder shows browser automation steps
4. **Verify configuration** - double-check `.env` and JSON config files
5. **Test components individually** - use command-line tools to isolate issues

### Useful Resources

- [Microsoft Graph API Documentation](https://docs.microsoft.com/en-us/graph/)
- [Google Sheets API Documentation](https://developers.google.com/sheets/api)
- [Playwright Documentation](https://playwright.dev/python/)
- [PySide6 Documentation](https://doc.qt.io/qtforpython/)
- [Azure AD App Registration Guide](https://docs.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app)

### Contact & Reporting Issues

For issues, questions, or contributions:
1. Check existing issues in the repository
2. Create a detailed issue report including:
   - Steps to reproduce
   - Expected vs actual behavior
   - Relevant log excerpts
   - Environment details (OS, Python version)
   - Screenshots if applicable
3. Contact the development team

### Debug Mode

For detailed troubleshooting, enable debug logging:

```python
# In master_control.py or relevant module
logging.basicConfig(level=logging.DEBUG)
```

This will provide verbose output about:
- API requests and responses
- Email processing details
- Browser automation steps
- Data transformations
- Error stack traces

## Future Enhancements

Potential improvements for future versions:

- [ ] Web-based dashboard for remote monitoring
- [ ] Multi-user support with role-based access
- [ ] Integration with additional scheduling platforms
- [ ] Advanced reporting and analytics
- [ ] Mobile app for monitoring and manual operations
- [ ] Automated testing suite
- [ ] Database backend for improved data management
- [ ] Webhook support for real-time integrations
- [ ] Multi-language support for email templates
- [ ] API for programmatic access

## Changelog

### Version 1.0 (May 2026)
- Initial release
- Core automation features (email processing, AHA registration, reminders)
- PySide6 GUI with system tray integration
- Location-based email templates
- Google Sheets bidirectional integration
- Acuity auto-flip scheduler
- Manual flip CLI tool
- Dashboard metrics and events
- SFTP upload support
- CSV generation and export
- Split logging for multiple services

## License

None (CSUS student license)

---

**Last Updated**: May 12, 2026  
**Version**: 5.0.0  
**Developed By**: CSC131 Team  
**Project**: RQI Training Automation System

For additional documentation, examples, or advanced configurations, please refer to the project repository or contact the development team.


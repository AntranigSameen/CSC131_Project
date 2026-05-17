# CSC131 Automation Project

## Project Overview

This is an automated system developed for streamlining RQI (Resuscitation Quality Improvement) training programs and AHA (American Heart Association) certification registrations. The application monitors Microsoft Outlook emails for student registration requests, automatically processes the data, registers students on the AHA portal using browser automation, updates Google Sheets in real-time, and sends confirmation and reminder emails using location-specific templates.

The system features a modern PySide6 GUI with system tray integration, allowing users to monitor automation status, view live logs, manually send emails, and manage multiple training locations. Background services handle periodic tasks like Acuity registration status synchronization and reminder email scheduling. All operations are logged with detailed tracking and screenshot capture for troubleshooting.

## Installation & Setup

### Prerequisites

- **Python 3.8+** installed on your system
- **Microsoft Azure AD Application** with Microsoft Graph API permissions (`Mail.Read`, `Mail.Send`, `Calendar.ReadWrite`)
- **Google Cloud Service Account** with Google Sheets API enabled and JSON key file
- **AHA Training Portal Account** with valid credentials
- **Operating System**: Windows

### Installation Steps

#### Option 1: Automated Setup (Recommended)

```powershell
cd CSC131_Project
.\scripts\setup.ps1
```

The setup script will create a Python virtual environment, install all dependencies, and set up Playwright browser automation.

#### Option 2: Manual Installation

```powershell
# 1. Navigate to the project directory
cd CSC131_Project

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install core dependencies
pip install --upgrade pip
pip install msal requests python-dotenv flask
pip install gspread google-auth google-auth-oauthlib google-auth-httplib2
pip install PySide6 pystray pillow ttkbootstrap
pip install playwright paramiko openpyxl pyinstaller

# 4. Install Playwright browsers
python -m playwright install chromium
```

### Configuration

#### 1. Google Sheets Setup
1. Download your Google Service Account JSON key file
2. Place it in the project root as `google_sheet_api_key.json`
3. Share your Google Sheet with the service account email (found in the JSON under `client_email`)
4. Grant **Editor** access

#### 2. Environment Variables
**Note:** Environment variables are provided for grading. If you need to modify them or recreate the configuration, use the following format.

Create a `.env` file in both the project root and the `Proper_MS` folder with the following:

```env
# Microsoft Authentication
CLIENT_ID=your-azure-client-id
TENANT_ID=your-azure-tenant-id
AUTHORITY=https://login.microsoftonline.com/your-tenant-id
SCOPES=["https://graph.microsoft.com/.default"]
SENDER_EMAIL=source.email@example.com

# Google Sheets
SERVICE_ACCOUNT_AHA_JSON=google_sheet_api_key.json
GOOGLE_SHEET_URL=your-google-sheet-url-or-id
AHA_REGISTRATION_WORKSHEET=AHA Registration
RQI_WORKSHEET=RQI Data

# AHA Portal
ORG_NAME=Your Organization Name

# Automation Settings
INTERVAL=10
EMAIL_REFRESH_ON_START=1
IS_HEADLESS=0
REMINDER_EMAIL_DAYS=7
AUTO_FLIP_ACUITY_REGISTRATION=true
AUTO_FLIP_CHECK_INTERVAL_MINUTES=30

# SFTP (Optional)
SFTP_HOST=sftp.example.com
SFTP_PORT=22
SFTP_USERNAME=your_username
SFTP_PASSWORD=your_password
SFTP_REMOTE_PATH=/uploads/
```

#### 3. Location Configuration
**Note:** Location configuration files are provided for grading. The following shows the required format for deployment.

Create `Proper_MS/location_keys.txt` to map location IDs to names:
```
101=San Francisco Bay Area
102=Los Angeles Metro
```

Create `Proper_MS/location_email_templates.json` for email templates:
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

## How to Run the Project

### Starting the Application

1. **Activate the virtual environment:**
   ```powershell
   .venv\Scripts\activate
   ```

2. **Run the application:**
   ```powershell
   python Proper_MS/master_control.py
   ```

3. **First-time setup:**
   - Enter AHA portal credentials when prompted
   - Authenticate with Microsoft Graph API (browser window will open)
   - Configure settings through the GUI if needed

### Using the Application

**Automated Mode:**
- Click **"Start Automation"** to begin the full automation cycle
- The system will monitor emails, register students, update Google Sheets, and send confirmations
- View live logs in the GUI and check the Dashboard for metrics

**Manual Operations:**
- **Send Manual Email**: Compose and send emails with template variables
- **Manual Registration Flip**: Update Acuity registration status via GUI or CLI
- **CSV Export**: Generate and optionally upload data to SFTP server

**Command-Line Tools:**
```powershell
# Manual registration flip for a single person
python Proper_MS/manual_flip_registration.py --first-name John --last-name Doe

# Scan and flip all pending registrations
python Proper_MS/manual_flip_registration.py --scan-all
```

### Accessing the Application

- **GUI**: Main window opens automatically when you run `master_control.py`
- **System Tray**: Icon appears in system tray for minimized operation
- **Logs**: View real-time logs in the "Logs" tab of the GUI
- **Dashboard**: Monitor metrics and activity in the "Dashboard" tab

## Demo Instructions

After completing installation and building the application, all testing and demonstration can be performed directly through the application's GUI interface. Use the built-in features to test email processing, registration automation, and other functionality.

## Known Issues & Limitations

This section documents known limitations and issues that users should be aware of when using the automation system.

### Current Limitations

#### Platform & Deployment

**Operating System Compatibility**
- ✅ **Windows**: Fully tested and supported
- 🔴 **macOS/Linux**: Not supported - application is designed for Windows only

**Resource Requirements**
- Requires stable internet connection for API calls (Microsoft Graph, Google Sheets, AHA portal)
- Minimum 4GB RAM recommended when browser automation is running
- Approximately 500MB disk space for dependencies and logs
- Browser automation requires Chromium (~150MB after Playwright install)

**Building Standalone Executable**

To create a standalone `.exe` file that doesn't require Python installation:

```powershell
# Ensure you're in the project root with virtual environment activated
.venv\Scripts\activate

# Build the executable
pyinstaller master_control.spec --clean
```

The executable will be created in the `dist/Automation Machine/` folder. The `--clean` flag ensures a fresh build by removing cached files.

#### API & Service Limitations

**Microsoft Graph API**
- ⚠️ **Rate Limits**: Subject to Microsoft's throttling policies (typically not an issue with normal usage)
- ⚠️ **Authentication Token Expiry**: Tokens expire after 1 hour; refresh handled automatically but may fail if offline
- ⚠️ **Shared Mailboxes**: Not tested with shared mailboxes, may require additional permissions
- 🔴 **Email Format Dependency**: Relies on specific email format; unstructured emails may not parse correctly

**Google Sheets API**
- ⚠️ **Rate Limits**: 300 requests per minute per project (100 requests per minute per user)
- ⚠️ **Cell Count Limit**: Google Sheets has max 5 million cells per spreadsheet
- ⚠️ **Concurrent Access**: Race conditions possible if multiple instances modify same sheet simultaneously
- 🔴 **Large Datasets**: Performance degrades with sheets containing >10,000 rows

**AHA Portal Browser Automation**
- 🔴 **Portal Changes**: Automation will break if AHA updates their website HTML structure
- ⚠️ **Course Availability**: Cannot register if no courses available; requires manual intervention
- ⚠️ **Network Latency**: Timeout errors possible on slow connections (adjust `PW_TIMEOUT_MS`)
- ⚠️ **CAPTCHA**: Not designed to handle CAPTCHAs; will fail if portal adds this protection
- 🔴 **Session Expiry**: Long-running browser sessions may expire; requires restart

#### Feature-Specific Limitations

**Email Processing**
- 🔴 **Single Sender Only**: Only monitors emails from one sender address (`SENDER_EMAIL`)
- ⚠️ **Inbox Folder Only**: Does not check subfolders, sent items, or other folders
- ⚠️ **Email Format**: Requires structured format with specific keywords (LocationID, Name, Email, HireDate)
- 🔴 **No Attachments**: Does not process email attachments
- ⚠️ **Plain Text**: HTML emails may not parse correctly; designed for plain text

**Registration & Acuity Integration**
- ⚠️ **Name Matching**: Auto-flip relies on exact name matching (after normalization); variations may not match
- 🔴 **No Partial Matches**: Middle names, nicknames, or spelling variations will not be automatically matched
- ⚠️ **Single Worksheet**: Each location must use same worksheet structure
- 🔴 **No Undo**: Manual flip operations are permanent; no rollback mechanism

**Reminder System**
- 🔴 **Fixed Schedule**: Reminders sent based on fixed day count
- ⚠️ **Hash-Based Tracking**: If hash algorithm changes, may send duplicate reminders
- ⚠️ **No Retry Logic**: Failed reminder emails are logged but not automatically retried
- 🔴 **Timezone**: All dates use system timezone; no multi-timezone support

**Data Export & SFTP**
- ⚠️ **Password Authentication Only**: SFTP uses password authentication; SSH key auth not implemented
- 🔴 **No Resume**: Large file uploads that fail midway cannot resume
- ⚠️ **Single Server**: Only supports one SFTP destination
- 🔴 **No Encryption at Rest**: Generated CSV files stored in plaintext

### Known Bugs & Workarounds

#### High Priority

**Issue: Browser Automation Randomly Fails with Timeout**
- **Symptoms**: Playwright throws timeout errors even though portal loads fine manually
- **Cause**: Network latency or slow portal response times
- **Workaround**: Increase `PW_TIMEOUT_MS` to `30000` (30 seconds) or higher in `.env`
- **Status**: ⚠️ Not fixed, planned for future optimization

**Issue: Google Sheets API "Quota Exceeded" Error**
- **Symptoms**: Error message about quota limits when processing many emails rapidly
- **Cause**: Google Sheets API rate limiting (100 requests/min per user)
- **Workaround**: Increase `INTERVAL` to slow down processing, or batch sheet updates
- **Status**: ⚠️ Not fixed, consider implementing batch writes in future

**Issue: Duplicate Reminder Emails Sent After Tracker File Corruption**
- **Symptoms**: Students receive multiple reminder emails unexpectedly
- **Cause**: `location_email_tracker.json` becomes corrupted or is deleted
- **Workaround**: Backup tracker file regularly; validate JSON syntax before deletion
- **Status**: 🟢 Partially mitigated with better error handling in v1.0

#### Medium Priority

**Issue: AHA Registration Status Not Updated After Manual Portal Changes**
- **Symptoms**: Student manually registered on portal, but automation doesn't detect this
- **Cause**: System only tracks registrations it performs; no portal scraping implemented
- **Workaround**: Use manual flip tool to update Google Sheets: `python Proper_MS/manual_flip_registration.py --first-name John --last-name Doe`
- **Status**: ⚠️ By design (would require additional portal scraping)

**Issue: Email Template Variables Not Case-Sensitive**
- **Symptoms**: `{{name}}` and `{{NAME}}` treated as different variables
- **Cause**: Template substitution uses exact string matching
- **Workaround**: Always use uppercase: `{{NAME}}`, `{{EMAIL}}`, `{{LOCATION}}`
- **Status**: 🟡 Could be fixed with case-insensitive matching

#### Low Priority

**Issue: Log Files Grow Large Over Time**
- **Symptoms**: Log files in `logs/` directory consume significant disk space after weeks of use
- **Cause**: No automatic log rotation implemented
- **Workaround**: Manually delete or archive old log files periodically
- **Status**: ⚠️ Planned enhancement (log rotation) for future version

**Issue: Dashboard Metrics Don't Persist After Application Restart**
- **Symptoms**: "Registered Today" counter resets to 0 when app restarts
- **Cause**: Metrics stored in memory only, not persisted to disk
- **Workaround**: None; this is by design for daily tracking
- **Status**: 🔵 Feature request (optional persistence)

**Issue: GUI Freezes During Long-Running Operations**
- **Symptoms**: GUI becomes unresponsive when processing many emails or large CSV exports
- **Cause**: Heavy operations run on main thread
- **Workaround**: Wait for operation to complete; consider running in headless mode via CLI
- **Status**: 🟡 Could improve with better threading architecture

### Security Considerations

**Credential Storage**
- 🔴 **Plaintext Storage**: `.env` file and `aha_auth.json` store credentials in plaintext
- **Impact**: Anyone with file system access can read credentials
- **Mitigation**: Set appropriate file permissions in Windows; use OS-level encryption or folder-level security
- **Future**: Consider using Windows Credential Manager integration

**Logging Sensitive Data**
- ⚠️ **PII in Logs**: Log files may contain names, email addresses, and other PII
- **Impact**: Privacy concerns if logs are shared or stored insecurely
- **Mitigation**: Review and sanitize logs before sharing; implement log retention policy
- **Future**: Add option to mask PII in logs

**SFTP Password in Environment Variables**
- 🔴 **Password Storage**: SFTP password stored in plaintext in `.env` file
- **Impact**: Credentials exposed if `.env` file is compromised
- **Mitigation**: Use SSH key authentication instead (not yet implemented); restrict file permissions
- **Future**: Implement SSH key support

### Compatibility & Dependencies

**Python Version**
- ✅ **Tested**: Python 3.9, 3.10, 3.11
- ⚠️ **Minimum**: Python 3.8 (not extensively tested)
- 🔴 **Not Supported**: Python 3.7 and below (missing required features)

**Browser Automation**
- ✅ **Supported**: Chromium (via Playwright)
- 🔴 **Not Supported**: Firefox, Safari, Edge (could be added but not tested)

**Email Providers**
- ✅ **Supported**: Microsoft 365 / Outlook.com via Graph API
- 🔴 **Not Supported**: Gmail, custom IMAP/POP3 servers
- **Future**: Could add IMAP support for broader compatibility

### Performance Benchmarks

Under typical usage conditions:
- **Email Processing**: ~2-5 seconds per email (including parsing and Sheets update)
- **AHA Registration**: ~30-60 seconds per student (depends on portal response time)
- **Google Sheets Update**: ~0.5-2 seconds per row write
- **Reminder Email Sending**: ~1-3 seconds per email
- **CSV Generation**: ~5-15 seconds for sheets with 1,000-5,000 rows
- **Auto-Flip Scan**: ~10-30 seconds for 100-500 records

**Scalability Limits:**
- Can reliably process ~500-1,000 emails per day
- Google Sheets limited to ~10,000 students before performance issues
- Concurrent registrations limited by browser automation (single-threaded)

### Reporting Issues

When reporting issues, please include:
1. **Error Type**: Is it a bug, limitation, or enhancement request?
2. **Steps to Reproduce**: Detailed steps to trigger the issue
3. **Expected vs Actual**: What should happen vs what actually happens
4. **Environment**: OS, Python version, relevant .env settings
5. **Logs**: Relevant log excerpts (sanitize PII first)
6. **Screenshots**: If GUI-related, include screenshots
7. **Workaround Used**: If you found a temporary solution

### Future Roadmap

Issues planned to be addressed in future versions:
- [ ] Implement batch Google Sheets writes to improve quota efficiency
- [ ] Add log rotation and automatic cleanup
- [ ] Improve GUI responsiveness with better threading
- [ ] Add SSH key support for SFTP
- [ ] Implement optional PII masking in logs
- [ ] Add support for IMAP email providers (Gmail, etc.)
- [ ] Improve name matching with fuzzy logic
- [ ] Add rollback/undo capability for manual flips
- [ ] Implement health check dashboard with alerting
- [ ] Add multi-timezone support for international deployments

---

**Developed By**: CSC131 Team  
**Project**: RQI Training Automation System



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

The setup script will create a Python virtual environment, install all dependencies, and set up Playwright browser automation. This should run automatically whenever this project is loaded into Visual Studio Code. This script is only for Windows and will NOT work for Mac.

#### Option 2: Manual Installation

```powershell
# 1. Navigate to the project directory
cd CSC131_Project

# 2. Create and activate virtual environment
python -m venv .venv
& .\.venv\Scripts\Activate.ps1

# 3. Install core dependencies
python -m pip install --upgrade pip
pip install msal requests python-dotenv
pip install gspread google-auth google-auth-oauthlib google-auth-httplib2
pip install pyinstaller
pip install playwright
pip install pystray pillow
pip install ttkbootstrap
pip install paramiko
pip install openpyxl
python -m playwright install

# 4. Install Playwright browsers
python -m playwright install chromium
```

### Configuration

#### 1. Google Sheets Setup
**Note:** Google sheets will be provided for grading.

1. We provide a `google_sheet_api_key.json` for our testing google sheets site
2. Located in the project root as `google_sheet_api_key.json`
4. **Editor** access is already granted to anyone with the link. Please reach out if there are any issues.
5. AHA sheet link: `https://docs.google.com/spreadsheets/d/143-IvGetu1Lz8InKi9lqNcJCiCziSvtD2954sgxxZRk/edit?gid=0#gid=0`
6. RQI sheet link: `https://docs.google.com/spreadsheets/d/13_cxh-bfXh9ZCITZTaz3bsUWLLJHyHeoHpyvYB_DuFI/edit?gid=482560077#gid=482560077` `(SPREADSHEET_ID=13_cxh-bfXh9ZCITZTaz3bsUWLLJHyHeoHpyvYB_DuFI)`

**Alternatively:**

1. Download your Google Service Account JSON key file
2. Place it in the project root as `google_sheet_api_key.json`
3. Share your Google Sheet with the service account email (found in the JSON under `client_email`)
4. Grant **Editor** access


#### 2. Environment Variables
**Note:** Environment variables are provided for grading. If you need to modify them or recreate the configuration, use the following format. If you want to use our env, please ask

Create a `.env` file in the project root folder with the following:

```env
# Microsoft Authentication
CLIENT_ID=your-azure-client-id
TENANT_ID=your-azure-tenant-id
AUTHORITY=https://login.microsoftonline.com/your-tenant-id
SCOPES=Mail.ReadWrite,Mail.Send,User.Read,Calendars.ReadWrite
CACHE_FILE=                               # Leave Empty

# Google Sheets
EMAIL_PROVIDER=outlook
SERVICE_ACCOUNT_AHA_JSON=google_sheet_api_key.json
GOOGLE_SHEET_URL=your-AHA-google-sheet-url
WORKSHEET_NAME=RQI Data
SERVICE_ACCOUNT_RQI_JSON=service_account.json
SPREADSHEET_ID=your-RQI-sheet-id
SENDER_EMAIL=source.email@example.com
SENDER_EMAIL_RQI=source.email@example.com

# APP General
KEYWORD_NAME=Dear
AHA_URL=https://atlas.heart.org/location
ORG_NAME=Your Organization Name
IS_HEADLESS=True
APP_THEME=dark

# Automation Settings
INTERVAL=60                               # Must be at least 60 seconds
ACUITY_NOT_REGISTERED_REMINDER_DAYS=7
REMINDER_EMAIL_DAYS=7
ACUITY_REGISTERED_REMINDER_YEARS=1
REMINDER_MAX_EMAILS_PER_RUN=25
REMINDER_SEND_DELAY_SECONDS=10            # Must be at least 10 seconds
AHA_LOCATION_EMAIL_ENABLED=True

# SFTP
RQI_CSV_EXPORT_DIR=C:\Your\CSV\Save\Path
RQI_CSV_FILENAME=filename.csv
RQI_CSV_BATCH_MINUTES=1

RQI_SFTP_HOST=sftp.example.com
RQI_SFTP_PORT=22
RQI_SFTP_USERNAME=your_username
RQI_SFTP_PASSWORD=your_password
RQI_SFTP_REMOTE_PATH=/uploads
RQI_SFTP_FILE_NAME=filename.csv
RQI_SFTP_FILE_TYPE=csv
RQI_CLEAN_CORRUPT_ROWS=1
```

#### 3. Location Configuration
**Note:** Location configuration files are provided for grading. The following shows the required format for deployment. All of these can be configured in the app.

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

1. **Activate the virtual environment (This should happen automatically through setup.ps1 script):**
   ```powershell
   .venv\Scripts\activate
   ```

2. **Create the application:**
**Note:** Make sure you are in the project root and `master_control.spec` exists
   ```powershell
   pyinstaller master_control.spec --clean
   ```

The executable will be created in the `dist/Automation Machine/` folder. The `--clean` flag ensures a fresh build by removing cached files.

3. **Run the application:**
   - Go into the dist folder created within the project root
   - Go into the application folder
   - Run the .exe that is generated through pyinstaller

4. **First-time setup:**
   - Enter AHA portal credentials when prompted
   - Authenticate with Microsoft Graph API (browser window will open)
   - Configure settings through the GUI if needed

5. **Accessing config files:**
**NOTE**: ALL SYSTEM FILES ARE STORED IN APPDATA
   - Press `Windows + R` to open the run dialog box
   - Type `%APPDATA%` and press enter
   - Look for a folder named `Automation Machine`
   - All config and data files are stored here by default

### Using the Application

**Automated Mode:**
- The system will monitor emails, register students, update Google Sheets, and send confirmations from the moment all logins are validated
- View live logs in the GUI and check the Dashboard for metrics

**Manual Operations:**
- **Pause All Automation**: Click on the pause button to stop all email automation
- **Send Manual Email**: Compose and send emails with template variables
- **CSV Export**: Generate and optionally upload data to SFTP server

### Accessing the Application

- **GUI**: Main window opens automatically when you run `master_control.py`
- **System Tray**: Icon appears in system tray for minimized operation
- **Logs**: View real-time logs in the "Logs" tab of the GUI
- **Dashboard**: Monitor metrics and activity in the "Dashboard" tab

## Demo Instructions

After completing installation and building the application, all testing and demonstration can be performed directly through the application's GUI interface. Use the built-in features to test email processing, registration automation, and other functionality.

### Steps to replicate demo:
   - After running the app, Log in using your AHA credentials on the popup
   - Authorize the app on Microsoft Graph the use of the app through the browser popup (ONLY WORKS FOR ORGANIZATION EMAILS NOT PERSONAL ONES)
   - Configure settings for SFTP, CSV (recommended 5 minute batch time for testing), Sender Emails, Timers through the GUI (if not already done through env)
   - Sign up for a class through the AHA website
   - Send an email to the outlook account, the app is connected to, using the client's student registration email format. Make sure the instructor name and date of class match the class that you signed up for
   - Wait `INTERVAL` seconds (default is `60`) for the app to run a cycle, accept the student, and add them to the AHA google sheet
   - Send an email to the outlook account, the app is connected to, using the client's RQI payment confirmation email template. It does not matter which one.
   - After the automation cycle runs again, the RQI sheet will update a new row with the student information. The student will also be added to the csv for that batch window
   - Check the csv through the `CSV Viewer tab`. Press `Refresh CSVs`, then `Select CSV` --> choose the file, Press `Load CSV`. The new student will show up in the CSV
   - Press the `Upload to SFTP Now` button and check through winscp
   - Check the calendar on the Microsoft account to make sure a calendar event was also made for the class date and time that the RQI email defined
   - In the `Locations` tab add a new `Key` and `Location`.
   - Add a new email template for your new location in the `Location template` tab and save it
   - In the `Reminder Emails` tab go to the `Manual Emailer`
   - Send an email to the same outlook account the app is connected to (In our testing we found our emails get sent but don't get received because our account is too new/scam-like). However, if you send the email to the same account, it works. It will work perfectly for the client as he has a well established account. When you send the email make sure you use the new template you created for testing
   - Closing the app with the "x" button in the top right corner will **NOT** close the app. It lives in the system tray and runs indefinitely. Close the app with the `Quit` button

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
- Approximately 1000MB disk space for dependencies and logs
- Browser automation requires Chromium (~150MB after Playwright install)

#### API & Service Limitations

**Microsoft Graph API**
- ⚠️ **Rate Limits**: Subject to Microsoft's throttling policies (typically not an issue with normal usage)
- ⚠️ **Authentication Token Expiry**: Tokens expire after 1 hour; refresh handled automatically but may fail if offline
- ⚠️ **Shared Mailboxes**: Not tested with shared mailboxes, may require additional permissions
- 🔴 **Email Format Dependency**: Relies on specific email format; unstructured emails may not parse correctly

**Google Sheets API**
- ⚠️ **Rate Limits**: 300 requests per minute per project (100 requests per minute per user)
- ⚠️ **Cell Count Limit**: Google Sheets has max 5 million cells per spreadsheet
- ⚠️ **Concurrent Access**: Race conditions inevitable if multiple instances modify same sheet simultaneously

**AHA Portal Browser Automation**
- ⚠️ **Course Availability**: Cannot register if no courses available; requires manual intervention
- ⚠️ **Session Expiry**: Long-running browser sessions may expire; refresh handled automatically but may fail if offline; requires restart

#### Feature-Specific Limitations

**Email Processing**
- 🔴 **Single Sender Only**: Only monitors emails from one sender address for each email type (`SENDER_EMAIL`, `SENDER_EMAIL_RQI`)
- ⚠️ **Inbox Folder Only**: Does not check subfolders, sent items, or other folders
- ⚠️ **Email Format**: Requires structured format with specific keywords (LocationID, Name, Email, `KEYWORD=Dear`)
- 🔴 **No Attachments**: Does not process email attachments
- ⚠️ **Plain Text**: Designed for plain text

**Registration & Acuity Integration**
- 🔴 **No Partial Matches**: Middle names, nicknames, or spelling variations will not be automatically matched
- 🔴 **No Undo**: Manual flip operations are permanent; no rollback mechanism

**Reminder System**
- ⚠️ **No Retry Logic**: Failed reminder emails are logged but not automatically retried
- ⚠️ **Timezone**: All dates use system timezone; no multi-timezone support

**Data Export & SFTP**
- ⚠️ **Password Authentication Only**: SFTP uses password authentication; SSH key auth not implemented
- 🔴 **No Resume**: Large file uploads that fail midway cannot resume
- ⚠️ **Single Server**: Only supports one SFTP destination
- 🔴 **No Encryption at Rest**: Generated CSV files stored in plaintext

### Known Bugs & Workarounds

#### High Priority

**Issue: Google Sheets API "Quota Exceeded" Error**
- **Symptoms**: Error message about quota limits when processing many emails rapidly
- **Cause**: Google Sheets API rate limiting (100 requests/min per user)
- **Workaround**: Increase `INTERVAL` to slow down processing, or batch sheet updates

#### Medium Priority

**Issue: AHA Registration Status Not Updated After Manual Portal Changes**
- **Symptoms**: Student manually registered on portal, but automation doesn't detect this and will not add student to sheet
- **Cause**: System only tracks registrations it performs; no portal scraping implemented
- **Status**: ⚠️ By design (would require additional portal scraping)

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
- **Workaround**: Wait for operation to complete; consider running in headless mode
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
- ✅ **Tested**: Python 3.14
- ⚠️ **Minimum**: Python 3.8 (not extensively tested)
- 🔴 **Not Supported**: Python 3.7 and below (missing required features)

**Browser Automation**
- ✅ **Supported**: Chromium (via Playwright)
- 🔴 **Not Supported**: Firefox, Safari, Edge (could be added but not tested)

**Email Providers**
- ✅ **Supported**: Microsoft 365 / Outlook.com via Graph API
- 🔴 **Not Supported**: Gmail, custom IMAP/POP3 servers

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
- [ ] Add log rotation and automatic cleanup
- [ ] Improve GUI responsiveness with better threading
- [ ] Add SSH key support for SFTP
- [ ] Implement optional PII masking in logs
- [ ] Implement health check dashboard with alerting
- [ ] Add multi-timezone support for international deployments

---

**Developed By**: Antranig Sameen, Sherri Tao, Nathan Kahahane (CSC131 Team 3: SentientGrok)
**Project**: RQI Training Automation System (Automation Machine)



<<<<<<< Updated upstream
# =================
# Outlook -> Sheets (Graph)
# =================
=======
# ====================================================================
# Email to Google Sheets Integration
# ====================================================================
# This script reads unread emails from Microsoft Outlook using the
# Microsoft Graph API and automatically extracts employee information
# (LocationID, Name, Email, HireDate, etc.) to append as rows in a 
# Google Sheet. It also creates Office 365 calendar events for 
# HireDate or ActiveDate.
# ====================================================================
>>>>>>> Stashed changes

import os
import re
import time
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
from html import unescape
import html.parser

import requests
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials


from authentication import authenticate  # uses your locked device-flow auth.py
# =====================
# Load environment vars
# =====================

load_dotenv()

PROVIDER = (os.getenv("EMAIL_PROVIDER") or "").strip().lower()
SENDER_EMAIL = (os.getenv("SENDER_EMAIL") or "").strip()  # used to filter messages (optional)

<<<<<<< Updated upstream
# Google Sheets settings
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Leads")
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON", "service_account.json")
=======
# Optional: Filter emails to only process those from specific senders
# Can be a single email or comma-separated list
SENDER_EMAIL = (os.getenv("SENDER_EMAIL") or "").strip()
SENDER_EMAILS = [email.strip().lower() for email in SENDER_EMAIL.split(",") if email.strip()]
>>>>>>> Stashed changes

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


# ---------------
# Helpers
# ---------------

def strip_html_tags(html_content: str) -> str:
    """
    Remove HTML tags and convert HTML entities to plain text.
    
    Args:
        html_content: String containing HTML markup
    
    Returns:
        str: Plain text with HTML tags removed
    """
    if not html_content:
        return ""
    
    # Remove HTML tags using regex
    text = re.sub(r'<[^>]+>', '', html_content)
    
    # Decode HTML entities (e.g., &nbsp; -> space, &amp; -> &)
    text = unescape(text)
    
    return text

def extract_labeled_field(text: str, label: str) -> str:
    """
    Extract a field value that follows a label pattern like "Label: Value".
    
    Args:
        text: The normalized text to search in
        label: The field label to search for (case-insensitive)
    
    Returns:
        str: The extracted value, or empty string if not found
    """
    # Try to find "Label: Value" pattern
    # Matches everything after the colon until end of line or next label pattern
    pattern = rf"\b{re.escape(label)}\s*:\s*([^\n\r]+?)(?=\s+\w+\s*:|$)"
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""

def extract_fields(text: str) -> dict:
    """
<<<<<<< Updated upstream
    Normalize email body so Google Sheets doesn't split it across columns:
    - tabs -> spaces (tabs cause column splitting)
    - newlines -> spaces (keep notes in one cell)
    - collapse repeated whitespace
    """
    clean = (text or "").replace("\r", "")
=======
    Extract employee information from email body text using regex patterns.
    
    This function normalizes the text and extracts:
    - LocationID, LocationName
    - UserID
    - FirstName, MiddleName, LastName
    - Email
    - JobCode, JobName
    - HireDate, Status, DateOfBirth, Gender, YearsOfExperience
    - ActiveDate, InactiveDate
    - Group
    
    Text normalization:
    - Strips HTML tags and decodes HTML entities
    - Removes tabs and newlines to prevent improper cell splitting in Sheets
    - Collapses repeated whitespace into single spaces
    - Strips leading/trailing whitespace
    
    Returns:
        dict: Contains all employee field keys
    """
    # Step 0: Strip HTML tags and entities (if the email body is HTML)
    text = strip_html_tags(text or "")
    
    # Step 1: Normalize the text
    # Remove carriage returns, convert tabs and newlines to spaces
    clean = text.replace("\r", "")
>>>>>>> Stashed changes
    clean = clean.replace("\t", " ")
    clean = clean.replace("\n", " ")
    clean = re.sub(r"\s+", " ", clean).strip()

<<<<<<< Updated upstream
    # Email
    email = None
    m = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", clean, re.I)
    if m:
        email = m.group(0)

    # Phone
    phone = None
    m = re.search(r"(\+?1[\s\-\.]?)?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}", clean)
    if m:
        phone = m.group(0)

    # Date (tries "Date: MM/DD/YYYY" first, then any MM/DD/YYYY or MM-DD-YYYY)
    date_found = None
    m = re.search(r"\bdate\s*:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", clean, re.IGNORECASE)
    if m:
        date_found = m.group(1)
    else:
        m = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", clean)
=======
    # Step 2: Extract all labeled fields
    fields = {
        "LocationID": extract_labeled_field(clean, "LocationID"),
        "LocationName": extract_labeled_field(clean, "LocationName"),
        "UserID": extract_labeled_field(clean, "UserID"),
        "FirstName": extract_labeled_field(clean, "FirstName"),
        "MiddleName": extract_labeled_field(clean, "MiddleName"),
        "LastName": extract_labeled_field(clean, "LastName"),
        "Email": extract_labeled_field(clean, "Email"),
        "JobCode": extract_labeled_field(clean, "JobCode"),
        "JobName": extract_labeled_field(clean, "JobName"),
        "HireDate": extract_labeled_field(clean, "HireDate"),
        "Status": extract_labeled_field(clean, "Status"),
        "DateOfBirth": extract_labeled_field(clean, "DateOfBirth"),
        "Gender": extract_labeled_field(clean, "Gender"),
        "YearsOfExperience": extract_labeled_field(clean, "YearsOfExperience"),
        "ActiveDate": extract_labeled_field(clean, "ActiveDate"),
        "InactiveDate": extract_labeled_field(clean, "InactiveDate"),
        "Group": extract_labeled_field(clean, "Group"),
    }

    # Step 3: Fallback to find email if not labeled
    if not fields["Email"]:
        m = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", clean, re.I)
>>>>>>> Stashed changes
        if m:
            fields["Email"] = m.group(0)

<<<<<<< Updated upstream
    # Name
    name = None
    m = re.search(r"\bname\s*:\s*((?:[A-Za-z]+)(?:\s+[A-Za-z]+)*)", clean, re.IGNORECASE)
    if m:
        words = m.group(1).split()
        valid_words = [w for w in words if w.isalpha() and 2 <= len(w) <= 15]
        name = " ".join(valid_words[:3]) if valid_words else None

    notes = clean[:400]
    return {"name": name, "email": email, "phone": phone, "date": date_found, "notes": notes}
=======
    return fields
>>>>>>> Stashed changes


def setup_logging():
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).parent
    else:
        base_dir = Path(__file__).parent

    log_file = base_dir / "email_to_sheets.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)],
    )
    logging.info("Logging initialized. Log file: %s", log_file)


def get_worksheet():
    if not SPREADSHEET_ID:
        raise RuntimeError("Missing SPREADSHEET_ID in .env")

    if not os.path.exists(SERVICE_ACCOUNT_JSON):
        raise FileNotFoundError(
            f"Missing {SERVICE_ACCOUNT_JSON}. Put it in email-to-sheets folder."
        )

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
<<<<<<< Updated upstream
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_JSON, scopes=scopes)
    gc = gspread.authorize(creds)

=======
    
    # Authenticate using service account credentials
    logging.info("Connecting to Google Sheets...")
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_JSON, scopes=scopes)
    gc = gspread.authorize(creds)

    # Open the spreadsheet by its ID
    logging.info(f"Opening spreadsheet: {SPREADSHEET_ID}")
>>>>>>> Stashed changes
    sh = gc.open_by_key(SPREADSHEET_ID)
    logging.info(f"Successfully opened spreadsheet: {sh.title}")

    try:
        ws = sh.worksheet(WORKSHEET_NAME)
        logging.info(f"Found worksheet: {WORKSHEET_NAME}")
    except gspread.WorksheetNotFound:
        logging.info(f"Creating new worksheet: {WORKSHEET_NAME}")
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=20)

<<<<<<< Updated upstream
    # Header row in the exact order the sheet needs (only if empty)
    if not ws.get_all_values():
        ws.append_row(
            [
                "EMAIL",
                "First Name",
                "Last Name",
                "Phone Number",
                "Course",
                "Date",
                "Acuity Registered",
                "AHA Registered",
                "Reminder Email Sent",
=======
    # Initialize header row if worksheet is empty
    # This ensures the sheet has the correct column structure before adding data
    existing_values = ws.get_all_values()
    if not existing_values:
        logging.info("Worksheet is empty, adding header row...")
        ws.append_row(
            [
                "LocationID",
                "LocationName",
                "UserID",
                "FirstName",
                "MiddleName",
                "LastName",
                "Email",
                "JobCode",
                "JobName",
                "HireDate",
                "Status",
                "DateOfBirth",
                "Gender",
                "YearsOfExperience",
                "ActiveDate",
                "InactiveDate",
                "Group",
>>>>>>> Stashed changes
            ],
            value_input_option="RAW",
        )
        logging.info("Header row added successfully")
    else:
        logging.info(f"Worksheet has {len(existing_values)} existing rows")

    return ws

def graph_get(token: str, url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    if not r.ok:
        raise RuntimeError(f"GET failed {r.status_code}: {r.text}")
    return r.json()

def graph_patch(token: str, url: str, body: Dict[str, Any]) -> None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    r = requests.patch(url, headers=headers, json=body, timeout=30)
    if not r.ok:
        # show the real Graph error message
        raise RuntimeError(f"PATCH failed {r.status_code}: {r.text}")

def graph_post(token: str, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make a POST request to Microsoft Graph API to create a resource.
    
    Args:
        token: OAuth2 access token for authorization
        url: Full Graph API endpoint URL
        body: JSON body data for the POST request
    
    Returns:
        dict: JSON response from the API
    
    Raises:
        RuntimeError: If the request fails (includes Graph API error message)
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    r = requests.post(url, headers=headers, json=body, timeout=30)
    if not r.ok:
        raise RuntimeError(f"POST failed {r.status_code}: {r.text}")
    return r.json()

def parse_appointment_when(when_str: str) -> tuple[str, str] | None:
    """
    Parse appointment 'When' field to extract date, time, and duration.
    
    Args:
        when_str: String like "Friday, March 6, 2026 8:00am (1 hour)"
    
    Returns:
        tuple: (start_datetime, end_datetime) in ISO 8601 format, or None if parsing fails
    """
    if not when_str:
        return None
    
    try:
        # Extract duration if present (e.g., "(1 hour)", "(2 hours)", "(30 minutes)")
        duration_hours = 1  # Default
        duration_match = re.search(r'\((\d+)\s*(hour|hr)s?\)', when_str, re.IGNORECASE)
        if duration_match:
            duration_hours = int(duration_match.group(1))
        else:
            # Check for minutes
            duration_match = re.search(r'\((\d+)\s*(minute|min)s?\)', when_str, re.IGNORECASE)
            if duration_match:
                duration_hours = int(duration_match.group(1)) / 60.0
        
        # Remove the duration part for parsing
        clean_when = re.sub(r'\([^)]+\)', '', when_str).strip()
        
        # Try parsing various date/time formats
        # Format: "Friday, March 6, 2026 8:00am"
        formats = [
            "%A, %B %d, %Y %I:%M%p",      # Friday, March 6, 2026 8:00am
            "%A, %B %d, %Y %I%p",          # Friday, March 6, 2026 8am
            "%B %d, %Y %I:%M%p",           # March 6, 2026 8:00am
            "%m/%d/%Y %I:%M%p",            # 03/06/2026 8:00am
            "%m-%d-%Y %I:%M%p",            # 03-06-2026 8:00am
        ]
        
        parsed_start = None
        for fmt in formats:
            try:
                parsed_start = datetime.strptime(clean_when.strip(), fmt)
                break
            except ValueError:
                continue
        
        if not parsed_start:
            logging.warning(f"Could not parse when string: {when_str}")
            return None
        
        # Calculate end time based on duration
        end_time = parsed_start + timedelta(hours=duration_hours)
        
        # Format in ISO 8601
        start_str = parsed_start.strftime("%Y-%m-%dT%H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%S")
        
        return (start_str, end_str)
        
    except Exception as e:
        logging.warning(f"Error parsing when string '{when_str}': {e}")
        return None


def extract_appointment_fields(text: str) -> dict:
    """
    Extract appointment scheduling fields from email body.
    
    Looks for patterns like:
    - For: Kailey Crawford
    - What: Online ACLS with Skills Check
    - When: Friday, March 6, 2026 8:00am (1 hour)
    - Where: 3576 Covington Highway, Suite 206, Office B, Decatur, GA 30032
    
    Args:
        text: Email body text
    
    Returns:
        dict with keys: for_name, what, when, where
    """
    appointment = {
        "for_name": "",
        "what": "",
        "when": "",
        "where": ""
    }
    
    # Strip HTML tags first
    text = strip_html_tags(text or "")
    
    # Clean up the text
    clean = text.replace("\r", "")
    
    # Extract "For" field (person's name) - stop at next field or LocationID
    for_match = re.search(r'\bFor:\s*([^\n]+?)(?=\s*(?:What:|LocationID:|$))', clean, re.IGNORECASE)
    if for_match:
        appointment["for_name"] = for_match.group(1).strip()
    
    # Extract "What" field (appointment type) - stop at next field
    what_match = re.search(r'\bWhat:\s*([^\n]+?)(?=\s*(?:When:|LocationID:|$))', clean, re.IGNORECASE)
    if what_match:
        appointment["what"] = what_match.group(1).strip()
    
    # Extract "When" field (date/time) - stop at next field
    when_match = re.search(r'\bWhen:\s*([^\n]+?)(?=\s*(?:Where:|LocationID:|$))', clean, re.IGNORECASE)
    if when_match:
        appointment["when"] = when_match.group(1).strip()
    
    # Extract "Where" field (location) - stop at LocationID or end
    # Allow multiline for address, but stop at LocationID
    where_match = re.search(r'\bWhere:\s*(.+?)(?=\s*LocationID:|$)', clean, re.IGNORECASE | re.DOTALL)
    if where_match:
        # Clean up the where field - remove any trailing whitespace/newlines
        where_text = where_match.group(1).strip()
        # Remove any location fields that may have leaked in
        where_text = re.split(r'\s*LocationID:', where_text)[0].strip()
        appointment["where"] = where_text
    
    return appointment

def create_calendar_event(token: str, email_body: str, lead_name: str = "", lead_email: str = "") -> bool:
    """
    Create an Office 365 calendar event from appointment email.
    
    Extracts appointment details (For, What, When, Where) from the email body
    and creates a calendar event with proper date/time and location.
    
    Args:
        token: OAuth2 access token for authorization
        email_body: Full email body text containing appointment details
        lead_name: Name from employee fields (fallback if 'For' not found)
        lead_email: Email from employee fields (for attendee)
    
    Returns:
        bool: True if event was created successfully, False otherwise
    """
    try:
        # Extract appointment fields from email
        appointment = extract_appointment_fields(email_body)
        
        # Log what was extracted for debugging
        logging.info(f"Appointment extraction: For='{appointment['for_name']}' What='{appointment['what']}' When='{appointment['when']}' Where='{appointment['where']}'")
        
        # Parse the When field to get start/end times
        date_times = parse_appointment_when(appointment["when"])
        if not date_times:
            logging.warning(f"Skipping calendar event - could not parse when: {appointment['when']}")
            return False
        
        start_datetime, end_datetime = date_times
        
        # Use 'For' name if available, otherwise fall back to lead_name
        person_name = appointment["for_name"] or lead_name or "Appointment"
        
        # Construct event subject: "Person Name - Appointment Type"
        subject = f"{person_name} - {appointment['what']}" if appointment["what"] else person_name
        
        # Construct event body with appointment details
        body_content = ""
        if person_name:
            body_content += f"Student: {person_name}\n"
        if appointment["what"]:
            body_content += f"Class: {appointment['what']}\n"
        if appointment["where"]:
            body_content += f"\nLocation:\n{appointment['where']}\n"
        if lead_email:
            body_content += f"\nEmail: {lead_email}\n"
        
        event_body = {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body_content
            },
            "start": {
                "dateTime": start_datetime,
                "timeZone": "America/Los_Angeles"  # Pacific Time
            },
            "end": {
                "dateTime": end_datetime,
                "timeZone": "America/Los_Angeles"
            },
            "location": {
                "displayName": appointment["where"] if appointment["where"] else "See details"
            },
            "isReminderOn": True,
            "reminderMinutesBeforeStart": 60  # 1 hour before
        }
        
        # Create the event via Graph API
        url = f"{GRAPH_BASE}/me/calendar/events"
        result = graph_post(token, url, event_body)
        
        event_id = result.get("id")
        logging.info(f"Calendar event created successfully. Event ID: {event_id}")
        return True
        
    except Exception as e:
        logging.exception(f"Failed to create calendar event: {e}")
        return False

def list_all_mail_folders(token: str) -> List[Dict[str, Any]]:
    """
    List all mail folders to help debug where unread emails might be located.
    """
    try:
        url = f"{GRAPH_BASE}/me/mailFolders"
        params = {"$select": "id,displayName,unreadItemCount,totalItemCount"}
        data = graph_get(token, url, params=params)
        folders = data.get("value", []) or []
        
        logging.info("=== Available Mail Folders ===")
        for folder in folders:
            name = folder.get("displayName", "Unknown")
            unread = folder.get("unreadItemCount", 0)
            total = folder.get("totalItemCount", 0)
            folder_id = folder.get("id", "")
            logging.info(f"  📁 {name}: {unread} unread / {total} total (ID: {folder_id[:20]}...)")
        
        return folders
    except Exception as e:
        logging.error(f"Failed to list mail folders: {e}")
        return []

def fetch_unread_messages(token: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Fetch unread messages from Inbox. If SENDER_EMAIL is set, filter to that sender in Python
    (more reliable than Graph nested $filter).
    """
<<<<<<< Updated upstream
    url = f"{GRAPH_BASE}/me/mailFolders/Inbox/messages"
=======
    # First, list all folders to see where unread emails might be
    list_all_mail_folders(token)
    
    # If SENDER_EMAILS is specified, check if ANY messages (read or unread) exist from those senders
    if SENDER_EMAILS:
        check_url = f"{GRAPH_BASE}/me/messages"
        check_params = {
            "$top": "10",
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,receivedDateTime,isRead,from"
        }
        try:
            check_data = graph_get(token, check_url, params=check_params)
            all_msgs = check_data.get("value", []) or []
            
            def get_sender(m):
                return (m.get("from", {}) or {}).get("emailAddress", {}).get("address", "") or ""
            
            matching_msgs = [m for m in all_msgs if get_sender(m).lower() in SENDER_EMAILS]
            
            for m in matching_msgs:
                status = "UNREAD" if not m.get("isRead", True) else "read"
                subject = m.get("subject", "")
                received = m.get("receivedDateTime", "")[:10]
                logging.info(f"Found [{status}] message from sender: {subject} ({received})")
        except Exception as e:
            logging.error(f"Failed to check for messages from sender: {e}")
    
    # Construct API endpoint - search ALL messages, not just Inbox
    # This will find unread emails in any folder (Inbox, Focused, Other, subfolders, etc.)
    url = f"{GRAPH_BASE}/me/messages"
    logging.info("🔍 Searching for unread emails across ALL mail folders...")
>>>>>>> Stashed changes

    params: Dict[str, Any] = {
        "$top": str(limit),
        "$orderby": "receivedDateTime desc",
        "$filter": "isRead eq false",
        "$select": "id,subject,receivedDateTime,from,bodyPreview",
    }

    data = graph_get(token, url, params=params)
    msgs = data.get("value", []) or []
    
    logging.info(f"Total unread messages found (before sender filter): {len(msgs)}")
    
    # Helper function to safely extract sender email from message object
    def sender_addr(m: Dict[str, Any]) -> str:
        return (m.get("from", {}) or {}).get("emailAddress", {}).get("address", "") or ""
    
    # Log all unread emails
    for i, m in enumerate(msgs, 1):
        sender = sender_addr(m)
        subject = m.get("subject", "")
        logging.info(f"  #{i} From={sender} | Subject={subject}")

<<<<<<< Updated upstream
    if SENDER_EMAIL:
        sender_lower = SENDER_EMAIL.lower()
        def sender_addr(m: Dict[str, Any]) -> str:
            return (m.get("from", {}) or {}).get("emailAddress", {}).get("address", "") or ""
        msgs = [m for m in msgs if sender_addr(m).lower() == sender_lower]

=======
    # Optional: Filter by specific sender email addresses
    if SENDER_EMAILS:
        # Filter messages to only include those from the specified senders (case-insensitive)
        msgs = [m for m in msgs if sender_addr(m).lower() in SENDER_EMAILS]
        senders_display = ", ".join(SENDER_EMAILS)
        logging.info(f"Found {len(msgs)} unread message(s) from: {senders_display}")
    else:
        logging.info(f"Found {len(msgs)} unread message(s) across all folders")
    
>>>>>>> Stashed changes
    return msgs


def message_sender_address(msg: Dict[str, Any]) -> str:
    try:
        return msg.get("from", {}).get("emailAddress", {}).get("address", "") or ""
    except Exception:
        return ""


<<<<<<< Updated upstream
# ---------------
# Main
# ---------------

def main():
=======
def get_message_body(token: str, message_id: str) -> str:
    """
    Fetch the full body text of a specific message.
    
    Args:
        token: OAuth2 access token for authorization
        message_id: The ID of the message to fetch
    
    Returns:
        str: The full body text, or empty string if not available
    """
    try:
        url = f"{GRAPH_BASE}/me/messages/{message_id}"
        params = {"$select": "body"}
        data = graph_get(token, url, params=params)
        
        # Extract body - it comes as {"contentType": "Text" or "HTML", "content": "..."}
        body_obj = data.get("body", {}) or {}
        body_content = body_obj.get("content", "") or ""
        
        return body_content
    except Exception as e:
        logging.warning(f"Failed to fetch message body for {message_id}: {e}")
        return ""


# ====================================================================
# Main Processing Logic
# ====================================================================

def main():
    """
    Main processing function - one complete cycle of checking and processing emails.
    
    Process flow:
    1. Validate configuration (EMAIL_PROVIDER must be 'outlook')
    2. Connect to Google Sheets
    3. Authenticate with Microsoft Graph API
    4. Fetch unread messages from Inbox
    5. For each message:
       - Extract employee information (LocationID, Name, Email, HireDate, etc.)
       - Append a new row to the Google Sheet
       - Create Office 365 calendar event for HireDate/ActiveDate
       - Mark the message as read to avoid reprocessing
    
    This function is called repeatedly in a loop to continuously monitor for new emails.
    """
>>>>>>> Stashed changes
    if PROVIDER != "outlook":
        raise RuntimeError("EMAIL_PROVIDER must be 'outlook' (this script is Outlook-only).")

    logging.info("Starting Outlook(Graph) -> Sheets processing...")

<<<<<<< Updated upstream
=======
    # Step 1: Connect to Google Sheets
    print("\n📊 Connecting to Google Sheets...")
>>>>>>> Stashed changes
    ws = get_worksheet()
    print(f"✓ Connected to spreadsheet: {WORKSHEET_NAME}")
    print(f"   Sheet ID: {SPREADSHEET_ID}")
    print(f"   URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")

    # Authenticate once per cycle (your auth caches)
    token = authenticate()
    if not token:
        raise RuntimeError("Authentication failed: no access token returned.")
    
    # Display which account is currently authenticated
    try:
        user_url = f"{GRAPH_BASE}/me"
        user_data = graph_get(token, user_url, params={"$select": "mail,userPrincipalName,displayName"})
        user_email = user_data.get("mail") or user_data.get("userPrincipalName", "Unknown")
        user_name = user_data.get("displayName", "")
        
        print(f"\n✓ Logged in as: {user_email}")
        logging.info(f"Authenticated user: {user_name} ({user_email})")
        
        if SENDER_EMAILS:
            if len(SENDER_EMAILS) == 1:
                print(f"📧 Checking for emails from: {SENDER_EMAILS[0]}")
            else:
                print(f"📧 Checking for emails from {len(SENDER_EMAILS)} senders")
    except Exception as e:
        logging.warning(f"Could not fetch user profile: {e}")

<<<<<<< Updated upstream
    msgs = fetch_unread_messages(token, limit=25)
    logging.info("Found %d unread messages (sender filter=%r)", len(msgs), SENDER_EMAIL)
    print(f"Found {len(msgs)} unread messages (sender filter={SENDER_EMAIL!r})")
=======
    # Step 3: Fetch unread messages from Outlook
    msgs = fetch_unread_messages(token, limit=50)
    logging.info("Found %d unread messages", len(msgs))
    
    if SENDER_EMAILS:
        if len(msgs) == 0:
            if len(SENDER_EMAILS) == 1:
                print(f"\n📭 No new emails from {SENDER_EMAILS[0]}")
            else:
                print(f"\n📭 No new emails from specified senders")
        else:
            if len(SENDER_EMAILS) == 1:
                print(f"\n📬 Found {len(msgs)} new email(s) from {SENDER_EMAILS[0]}")
            else:
                print(f"\n📬 Found {len(msgs)} new email(s) from specified senders")
    else:
        if len(msgs) == 0:
            print(f"\n📭 No new emails")
        else:
            print(f"\n📬 Found {len(msgs)} new email(s)")

    # Track calendar events created
    calendar_events_created = 0
    calendar_events_skipped = 0
    calendar_events_failed = 0
>>>>>>> Stashed changes

    for msg in msgs:
        msg_id = msg.get("id")
        subject = msg.get("subject") or ""
        sender = message_sender_address(msg)
        
        # Fetch full email body for accurate parsing
        body_text = get_message_body(token, msg_id) if msg_id else ""
        if not body_text:
            # Fallback to preview if full body unavailable
            body_text = msg.get("bodyPreview") or ""

<<<<<<< Updated upstream
        fields = extract_fields(body_preview)
        logging.info("Extracted fields from msg %s: %s", msg_id, fields)

        # Split full name into first/last
        full_name = (fields.get("name") or "").strip()
        first_name, last_name = "", ""
        if full_name:
            parts = full_name.split()
            first_name = parts[0]
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        row = [
            fields.get("email") or "",
            first_name,
            last_name,
            fields.get("phone") or "",
            "",  # Course
            fields.get("date") or "",
            "Yes",  # Acuity Registered
            "Yes",  # AHA Registered
            "No",   # Reminder Email Sent
        ]

        ws.append_row(row, value_input_option="RAW")
=======
        # Extract employee information from the email body
        fields = extract_fields(body_text)
        logging.info("Extracted fields from msg %s: %s", msg_id, fields)

        # Construct full name for display and calendar
        full_name = " ".join(filter(None, [
            fields.get("FirstName", ""),
            fields.get("MiddleName", ""),
            fields.get("LastName", "")
        ])).strip()

        # Construct row data matching the Google Sheets column structure
        # Column order: LocationID, LocationName, UserID, FirstName, MiddleName, LastName,
        #               Email, JobCode, JobName, HireDate, Status, DateOfBirth, Gender,
        #               YearsOfExperience, ActiveDate, InactiveDate, Group
        row = [
            fields.get("LocationID", ""),
            fields.get("LocationName", ""),
            fields.get("UserID", ""),
            fields.get("FirstName", ""),
            fields.get("MiddleName", ""),
            fields.get("LastName", ""),
            fields.get("Email", ""),
            fields.get("JobCode", ""),
            fields.get("JobName", ""),
            fields.get("HireDate", ""),
            fields.get("Status", ""),
            fields.get("DateOfBirth", ""),
            fields.get("Gender", ""),
            fields.get("YearsOfExperience", ""),
            fields.get("ActiveDate", ""),
            fields.get("InactiveDate", ""),
            fields.get("Group", ""),
        ]

        # Append the row to the Google Sheet
        try:
            row_count_before = len(ws.get_all_values())
            ws.append_row(row, value_input_option="RAW")
            row_count_after = len(ws.get_all_values())
            
            if row_count_after > row_count_before:
                logging.info(f"✅ Row appended to sheet for {sender}. Total rows: {row_count_after}")
                subject_display = subject[:50] + "..." if len(subject) > 50 else subject
                print(f"  ✓ {subject_display} → Added to Google Sheets")
            else:
                logging.error(f"❌ Row was NOT added to sheet. Row count unchanged: {row_count_before}")
                print(f"  ✗ {subject} → FAILED to add to Google Sheets")
                continue
        except Exception as e:
            logging.error(f"❌ Failed to append row to sheet: {e}")
            print(f"  ✗ {subject} → ERROR: {e}")
            continue

        # Create Office 365 calendar event after successful sheet upload
        # Extract appointment details from email body
        event_created = create_calendar_event(
            token=token,
            email_body=body_text,
            lead_name=full_name,
            lead_email=fields.get("Email") or ""
        )
        if event_created:
            logging.info(f"📅 Calendar event created for {full_name}")
            calendar_events_created += 1
        else:
            logging.warning(f"⚠️  Failed to create calendar event for {full_name}")
            calendar_events_failed += 1
>>>>>>> Stashed changes

        # Mark as read so it won't be processed again
        if msg_id:
            try:
                graph_patch(token, f"{GRAPH_BASE}/me/messages/{msg_id}", {"isRead": True})
                logging.info(f"✓ Marked email as read: {subject}")
            except Exception as e:
                logging.error(f"✗ Failed to mark email as read: {e}")
    
    # Display summary
    if msgs:
        print(f"\n✅ Successfully processed {len(msgs)} email(s)")
        print(f"   📊 Added {len(msgs)} row(s) to Google Sheets")
        if calendar_events_created > 0:
            print(f"   📅 Created {calendar_events_created} calendar event(s)")


if __name__ == "__main__":
    setup_logging()
<<<<<<< Updated upstream
    INTERVAL = int(os.getenv("INTERVAL", "10"))

    try:
        while True:
            try:
                main()
            except Exception:
                logging.exception("Error in main loop...")

            logging.info("Waiting for %s seconds before checking for new emails...", INTERVAL)
            time.sleep(INTERVAL)

    except KeyboardInterrupt:
        logging.info("Stopped by user")
=======
    
    try:
        # Run one complete processing cycle
        main()
    except KeyboardInterrupt:
        # Allow graceful shutdown with Ctrl+C
        logging.info("Stopped by user")
    except Exception:
        # Log errors
        logging.exception("Error in main...")
>>>>>>> Stashed changes

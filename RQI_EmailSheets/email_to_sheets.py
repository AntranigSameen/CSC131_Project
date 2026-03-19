# ====================================================================
# Email to Google Sheets Integration
# ====================================================================
# This script reads unread emails from Microsoft Outlook using the
# Microsoft Graph API and automatically extracts employee information
# (LocationID, Name, Email, HireDate, etc.) to append as rows in a
# Google Sheet. It can also create Office 365 calendar events from
# appointment details found in the email body.
# ====================================================================

# Standard library imports for file handling, pattern matching, timing, and logging
import os
import re
import time
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List

# Third-party imports
import requests  # For making HTTP requests to Microsoft Graph API
import gspread  # For Google Sheets integration
#from dotenv import load_dotenv  # For loading environment variables from .env file
from google.oauth2.service_account import Credentials  # For Google Sheets authentication

# Authentication module from Proper_MS(handles Microsoft OAuth2 device flow)
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "RQI_EmailSheets"))

from Proper_MS.outlook_authentication import authenticate
from Proper_MS.utils import resource_path

# =====================
# Environment Variables
# =====================
# Load configuration from .env file in the same directory

#load_dotenv()
INTERVAL = os.getenv("INTERVAL", "10") # Defaults to 10 Seconds


# Email provider configuration (must be 'outlook' for this script)
PROVIDER = (os.getenv("EMAIL_PROVIDER") or "").strip().lower()

# Optional: Filter emails to only process those from a specific sender
SENDER_EMAIL = (os.getenv("SENDER_EMAIL_RQI") or "").strip()
SENDER_EMAILS = [email.strip().lower() for email in SENDER_EMAIL.split(",") if email.strip()]

# Google Sheets configuration
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")  # The ID from the Google Sheets URL
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Leads")  # Name of the worksheet tab
SERVICE_ACCOUNT_JSON_NAME = PROJECT_ROOT / os.getenv("SERVICE_ACCOUNT_RQI_JSON", "service_account.json")

# Build absolute path to service account file relative to this script's location
# This ensures the file can be found regardless of where the script is run from
SCRIPT_DIR = Path(__file__).parent
SERVICE_ACCOUNT_JSON = resource_path(SERVICE_ACCOUNT_JSON_NAME.name if hasattr(SERVICE_ACCOUNT_JSON_NAME, 'name') else SERVICE_ACCOUNT_JSON_NAME)

# Microsoft Graph API base URL for making API calls
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


# ====================================================================
# Helper Functions
# ====================================================================

def strip_html_tags(html_content: str) -> str:
    """
    Remove HTML tags and convert HTML entities to plain text.
    """
    if not html_content:
        return ""

    text = re.sub(r"<[^>]+>", "", html_content)
    try:
        html_module = __import__("html")
        text = html_module.unescape(text)
    except Exception:
        pass
    return text


def extract_labeled_field(text: str, label: str) -> str:
    """
    Extract a field value that follows a label pattern like "Label: Value".
    """
    pattern = rf"\b{re.escape(label)}\s*:\s*([^\n\r]+?)(?=\s+\w+\s*:|$)"
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def extract_fields(text: str) -> dict:
    """
    Extract employee information from email body text using regex patterns.

    Returns:
        dict: Contains employee field keys used by the Google Sheet.
    """
    text = strip_html_tags(text or "")

    clean = text.replace("\r", "")
    clean = clean.replace("\t", " ")
    clean = clean.replace("\n", " ")
    clean = re.sub(r"\s+", " ", clean).strip()

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

    if not fields["Email"]:
        m = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", clean, re.I)
        if m:
            fields["Email"] = m.group(0)

    return fields


def extract_appointment_fields(text: str) -> dict:
    """
    Extract appointment scheduling fields from email body.
    """
    appointment = {
        "for_name": "",
        "what": "",
        "when": "",
        "where": ""
    }

    text = strip_html_tags(text or "")
    clean = text.replace("\r", "")

    for_match = re.search(r"\bFor:\s*([^\n]+?)(?=\s*(?:What:|LocationID:|$))", clean, re.IGNORECASE)
    if for_match:
        appointment["for_name"] = for_match.group(1).strip()

    what_match = re.search(r"\bWhat:\s*([^\n]+?)(?=\s*(?:When:|LocationID:|$))", clean, re.IGNORECASE)
    if what_match:
        appointment["what"] = what_match.group(1).strip()

    when_match = re.search(r"\bWhen:\s*([^\n]+?)(?=\s*(?:Where:|LocationID:|$))", clean, re.IGNORECASE)
    if when_match:
        appointment["when"] = when_match.group(1).strip()

    where_match = re.search(r"\bWhere:\s*(.+?)(?=\s*LocationID:|$)", clean, re.IGNORECASE | re.DOTALL)
    if where_match:
        where_text = where_match.group(1).strip()
        where_text = re.split(r"\s*LocationID:", where_text)[0].strip()
        appointment["where"] = where_text

    return appointment


def parse_appointment_when(when_str: str):
    """
    Parse appointment 'When' field to extract ISO start/end datetimes.
    """
    if not when_str:
        return None

    try:
        datetime_mod = __import__("datetime")
        datetime_cls = datetime_mod.datetime
        timedelta_cls = datetime_mod.timedelta

        duration_hours = 1
        duration_match = re.search(r"\((\d+)\s*(hour|hr)s?\)", when_str, re.IGNORECASE)
        if duration_match:
            duration_hours = int(duration_match.group(1))
        else:
            duration_match = re.search(r"\((\d+)\s*(minute|min)s?\)", when_str, re.IGNORECASE)
            if duration_match:
                duration_hours = int(duration_match.group(1)) / 60.0

        clean_when = re.sub(r"\([^)]+\)", "", when_str).strip()

        formats = [
            "%A, %B %d, %Y %I:%M%p",
            "%A, %B %d, %Y %I%p",
            "%B %d, %Y %I:%M%p",
            "%m/%d/%Y %I:%M%p",
            "%m-%d-%Y %I:%M%p",
        ]

        parsed_start = None
        for fmt in formats:
            try:
                parsed_start = datetime_cls.strptime(clean_when.strip(), fmt)
                break
            except ValueError:
                continue

        if not parsed_start:
            logging.warning("Could not parse when string: %s", when_str)
            return None

        end_time = parsed_start + timedelta_cls(hours=duration_hours)

        start_str = parsed_start.strftime("%Y-%m-%dT%H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%S")

        return (start_str, end_str)

    except Exception as e:
        logging.warning("Error parsing when string '%s': %s", when_str, e)
        return None


def setup_logging():
    """
    Configure logging to both file and console.

    The log file will be created in the same directory as this script
    (or next to the executable if running as a compiled .exe).
    All INFO level messages and above will be logged.
    """
    # Determine base directory (different for compiled vs script execution)
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
    """
    Connect to Google Sheets and return the target worksheet.
    """
    if not SPREADSHEET_ID:
        raise RuntimeError("Missing SPREADSHEET_ID in .env")

    if not os.path.exists(SERVICE_ACCOUNT_JSON):
        raise FileNotFoundError(
            f"Missing {SERVICE_ACCOUNT_JSON}. Put it in email-to-sheets folder."
        )

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_JSON, scopes=scopes)
    gc = gspread.authorize(creds)

    sh = gc.open_by_key(SPREADSHEET_ID)
    logging.info("Successfully opened spreadsheet: %s", sh.title)

    try:
        ws = sh.worksheet(WORKSHEET_NAME)
        logging.info("Found worksheet: %s", WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        logging.info("Creating new worksheet: %s", WORKSHEET_NAME)
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=20)

    if not ws.get_all_values():
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
            ],
            value_input_option="RAW",
        )
        logging.info("Header row added successfully")

    return ws


def graph_get(token: str, url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Make a GET request to Microsoft Graph API.
    """
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    if not r.ok:
        raise RuntimeError(f"GET failed {r.status_code}: {r.text}")
    return r.json()


def graph_patch(token: str, url: str, body: Dict[str, Any]) -> None:
    """
    Make a PATCH request to Microsoft Graph API to update a resource.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    r = requests.patch(url, headers=headers, json=body, timeout=30)
    if not r.ok:
        raise RuntimeError(f"PATCH failed {r.status_code}: {r.text}")


def graph_post(token: str, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make a POST request to Microsoft Graph API to create a resource.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    r = requests.post(url, headers=headers, json=body, timeout=30)
    if not r.ok:
        raise RuntimeError(f"POST failed {r.status_code}: {r.text}")
    return r.json()


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
            logging.info("  Folder %s: %s unread / %s total (ID: %s...)", name, unread, total, folder_id[:20])

        return folders
    except Exception as e:
        logging.error("Failed to list mail folders: %s", e)
        return []


def fetch_unread_messages(token: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Fetch unread messages from Outlook. Searches all folders.
    """
    list_all_mail_folders(token)

    url = f"{GRAPH_BASE}/me/messages"
    params: Dict[str, Any] = {
        "$top": str(limit),
        "$orderby": "receivedDateTime desc",
        "$filter": "isRead eq false",
        "$select": "id,subject,receivedDateTime,from,bodyPreview",
    }

    data = graph_get(token, url, params=params)
    msgs = data.get("value", []) or []

    logging.info("Total unread messages found (before sender filter): %d", len(msgs))

    def sender_addr(m: Dict[str, Any]) -> str:
        return (m.get("from", {}) or {}).get("emailAddress", {}).get("address", "") or ""

    for i, m in enumerate(msgs, 1):
        sender = sender_addr(m)
        subject = m.get("subject", "")
        logging.info("  #%d From=%s | Subject=%s", i, sender, subject)

    if SENDER_EMAILS:
        msgs = [m for m in msgs if sender_addr(m).lower() in SENDER_EMAILS]
        logging.info("Found %d unread message(s) from configured sender list", len(msgs))
    else:
        logging.info("Found %d unread message(s) across all folders", len(msgs))

    return msgs


def get_message_body(token: str, message_id: str) -> str:
    """
    Fetch the full body text of a specific message.
    """
    try:
        url = f"{GRAPH_BASE}/me/messages/{message_id}"
        params = {"$select": "body"}
        data = graph_get(token, url, params=params)

        body_obj = data.get("body", {}) or {}
        body_content = body_obj.get("content", "") or ""

        return body_content
    except Exception as e:
        logging.warning("Failed to fetch message body for %s: %s", message_id, e)
        return ""


def create_calendar_event(token: str, email_body: str, lead_name: str = "", lead_email: str = "") -> bool:
    """
    Create an Office 365 calendar event from appointment email.
    """
    try:
        appointment = extract_appointment_fields(email_body)
        logging.info(
            "Appointment extraction: For='%s' What='%s' When='%s' Where='%s'",
            appointment["for_name"],
            appointment["what"],
            appointment["when"],
            appointment["where"],
        )

        date_times = parse_appointment_when(appointment["when"])
        if not date_times:
            logging.warning("Skipping calendar event - could not parse when: %s", appointment["when"])
            return False

        start_datetime, end_datetime = date_times
        person_name = appointment["for_name"] or lead_name or "Appointment"
        subject = f"{person_name} - {appointment['what']}" if appointment["what"] else person_name

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
                "timeZone": "America/Los_Angeles"
            },
            "end": {
                "dateTime": end_datetime,
                "timeZone": "America/Los_Angeles"
            },
            "location": {
                "displayName": appointment["where"] if appointment["where"] else "See details"
            },
            "isReminderOn": True,
            "reminderMinutesBeforeStart": 60
        }

        url = f"{GRAPH_BASE}/me/calendar/events"
        result = graph_post(token, url, event_body)

        event_id = result.get("id")
        logging.info("Calendar event created successfully. Event ID: %s", event_id)
        return True

    except Exception as e:
        logging.exception("Failed to create calendar event: %s", e)
        return False


def message_sender_address(msg: Dict[str, Any]) -> str:
    """
    Safely extract the sender's email address from a message object.
    """
    try:
        return msg.get("from", {}).get("emailAddress", {}).get("address", "") or ""
    except Exception:
        return ""


# ====================================================================
# Main Processing Logic
# ====================================================================

def main():
    """
    Main processing function - one complete cycle of checking and processing emails.
    """
    if PROVIDER != "outlook":
        raise RuntimeError("EMAIL_PROVIDER must be 'outlook' (this script is Outlook-only).")

    logging.info("Starting Outlook(Graph) -> Sheets processing...")

    ws = get_worksheet()

    token = authenticate()
    if not token:
        raise RuntimeError("Authentication failed: no access token returned.")

    try:
        user_url = f"{GRAPH_BASE}/me"
        user_data = graph_get(token, user_url, params={"$select": "mail,userPrincipalName,displayName"})
        user_email = user_data.get("mail") or user_data.get("userPrincipalName", "Unknown")
        user_name = user_data.get("displayName", "")
        logging.info("Authenticated user: %s (%s)", user_name, user_email)
        print(f"✓ Logged in as: {user_email}")
    except Exception as e:
        logging.warning("Could not fetch user profile: %s", e)

    msgs = fetch_unread_messages(token, limit=50)
    logging.info("Found %d unread messages", len(msgs))

    if SENDER_EMAILS:
        print(f"Found {len(msgs)} unread messages (sender filter={SENDER_EMAILS!r})")
    else:
        print(f"Found {len(msgs)} unread messages")

    calendar_events_created = 0
    calendar_events_failed = 0

    for msg in msgs:
        msg_id = msg.get("id")
        subject = msg.get("subject") or ""
        sender = message_sender_address(msg)

        body_text = get_message_body(token, msg_id) if msg_id else ""
        if not body_text:
            body_text = msg.get("bodyPreview") or ""

        fields = extract_fields(body_text)
        logging.info("Extracted fields from msg %s: %s", msg_id, fields)

        full_name = " ".join(filter(None, [
            fields.get("FirstName", ""),
            fields.get("MiddleName", ""),
            fields.get("LastName", "")
        ])).strip()

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

        try:
            ws.append_row(row, value_input_option="RAW")
            logging.info("Appended row to sheet for message subject: %s", subject)
        except Exception as e:
            logging.error("Failed to append row to sheet: %s", e)
            print(f"✗ Failed to append row / subject: {subject} / from: {sender}")
            continue

        event_created = create_calendar_event(
            token=token,
            email_body=body_text,
            lead_name=full_name,
            lead_email=fields.get("Email") or ""
        )
        if event_created:
            calendar_events_created += 1
        else:
            calendar_events_failed += 1

        if msg_id:
            try:
                graph_patch(token, f"{GRAPH_BASE}/me/messages/{msg_id}", {"isRead": True})
                logging.info("Marked email as read: %s", subject)
            except Exception as e:
                logging.error("Failed to mark email as read: %s", e)

        print(f"✅ Appended row / subject: {subject} / from: {sender}")

    if msgs:
        print(f"\n✅ Successfully processed {len(msgs)} email(s)")
        print(f"   📊 Added {len(msgs)} row(s) to Google Sheets")
        if calendar_events_created > 0:
            print(f"   📅 Created {calendar_events_created} calendar event(s)")
        if calendar_events_failed > 0:
            print(f"   ⚠️ Calendar event failures: {calendar_events_failed}")


# ====================
# Runs Script Forever
# ====================

def run_forever(interval=INTERVAL):
    setup_logging()

    while True:
        try:
            main()
        except Exception:
            logging.exception("Email to sheets error")

        time.sleep(int(interval))


# ====================================================================
# Script Entry Point
# ====================================================================

if __name__ == "__main__":
    setup_logging()

    try:
        main()
    except KeyboardInterrupt:
        logging.info("Stopped by user")
    except Exception:
        logging.exception("Error in main...")
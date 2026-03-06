# ====================================================================
# Email to Google Sheets Integration
# ====================================================================
# This script reads unread emails from Microsoft Outlook using the
# Microsoft Graph API and automatically extracts lead information
# (name, email, phone, date) to append as rows in a Google Sheet.
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
from dotenv import load_dotenv  # For loading environment variables from .env file
from google.oauth2.service_account import Credentials  # For Google Sheets authentication

# Local authentication module (handles Microsoft OAuth2 device flow)
from authentication import authenticate

# =====================
# Environment Variables
# =====================
# Load configuration from .env file in the same directory

load_dotenv()

# Email provider configuration (must be 'outlook' for this script)
PROVIDER = (os.getenv("EMAIL_PROVIDER") or "").strip().lower()

# Optional: Filter emails to only process those from a specific sender
SENDER_EMAIL = (os.getenv("SENDER_EMAIL") or "").strip()

# Google Sheets configuration
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")  # The ID from the Google Sheets URL
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Leads")  # Name of the worksheet tab
SERVICE_ACCOUNT_JSON_NAME = os.getenv("SERVICE_ACCOUNT_JSON", "service_account.json")

# Build absolute path to service account file relative to this script's location
# This ensures the file can be found regardless of where the script is run from
SCRIPT_DIR = Path(__file__).parent
SERVICE_ACCOUNT_JSON = str(SCRIPT_DIR / SERVICE_ACCOUNT_JSON_NAME)

# Microsoft Graph API base URL for making API calls
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


# ====================================================================
# Helper Functions
# ====================================================================

def extract_fields(text: str) -> dict:
    """
    Extract lead information from email body text using regex patterns.
    
    This function normalizes the text and extracts:
    - Name: looks for "Name: John Doe" pattern
    - Email: finds email addresses using standard pattern
    - Phone: finds US phone numbers in various formats
    - Date: finds dates in MM/DD/YYYY or MM-DD-YYYY format
    - Notes: keeps first 400 characters of cleaned text
    
    Text normalization:
    - Removes tabs and newlines to prevent improper cell splitting in Sheets
    - Collapses repeated whitespace into single spaces
    - Strips leading/trailing whitespace
    
    Returns:
        dict: Contains 'name', 'email', 'phone', 'date', and 'notes' keys
    """
    # Step 1: Normalize the text
    # Remove carriage returns, convert tabs and newlines to spaces
    clean = (text or "").replace("\r", "")
    clean = clean.replace("\t", " ")
    clean = clean.replace("\n", " ")
    # Collapse multiple spaces into single spaces and trim
    clean = re.sub(r"\s+", " ", clean).strip()

    # Step 2: Extract email address
    # Pattern matches standard email format: username@domain.tld
    # Example: john.doe+label@example.com
    email = None
    m = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", clean, re.I)
    if m:
        email = m.group(0)

    # Step 3: Extract phone number
    # Pattern matches US phone numbers in various formats:
    # - (555) 123-4567
    # - 555-123-4567
    # - 555.123.4567
    # - +1 555 123 4567
    phone = None
    m = re.search(r"(\+?1[\s\-\.]?)?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}", clean)
    if m:
        phone = m.group(0)

    # Step 4: Extract date
    # First tries to find "Date: MM/DD/YYYY" pattern with label
    # If not found, looks for any date in MM/DD/YYYY or MM-DD-YYYY format
    # Examples: "Date: 12/31/2023", "01/15/24", "3-5-2023"
    date_found = None
    m = re.search(r"\bdate\s*:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", clean, re.IGNORECASE)
    if m:
        date_found = m.group(1)  # Extract just the date part, not the "Date:" label
    else:
        # Fallback: find any date pattern without label
        m = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", clean)
        if m:
            date_found = m.group(0)

    # Step 5: Extract name
    # Looks for "Name: John Doe" pattern
    # Validates that name contains only alphabetic words between 2-15 characters
    # Limits to first 3 words to avoid capturing too much text
    name = None
    m = re.search(r"\bname\s*:\s*((?:[A-Za-z]+)(?:\s+[A-Za-z]+)*)", clean, re.IGNORECASE)
    if m:
        words = m.group(1).split()
        # Filter out invalid words (too short, too long, or containing non-letters)
        valid_words = [w for w in words if w.isalpha() and 2 <= len(w) <= 15]
        # Take at most 3 words for the name (first, middle, last)
        name = " ".join(valid_words[:3]) if valid_words else None

    # Step 6: Truncate cleaned text to use as notes (first 400 characters)
    # This preserves the full context of the email for reference

    notes = clean[:400]
    return {"name": name, "email": email, "phone": phone, "date": date_found, "notes": notes}


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
    
    This function:
    1. Validates required configuration (SPREADSHEET_ID and service account file)
    2. Authenticates with Google Sheets API using service account credentials
    3. Opens the specified spreadsheet and worksheet
    4. Creates the worksheet if it doesn't exist
    5. Adds header row if the worksheet is empty
    
    Returns:
        gspread.Worksheet: The worksheet object ready for data operations
    
    Raises:
        RuntimeError: If SPREADSHEET_ID is not configured
        FileNotFoundError: If service_account.json is missing
    """
    if not SPREADSHEET_ID:
        raise RuntimeError("Missing SPREADSHEET_ID in .env")

    if not os.path.exists(SERVICE_ACCOUNT_JSON):
        raise FileNotFoundError(
            f"Missing {SERVICE_ACCOUNT_JSON}. Put it in email-to-sheets folder."
        )

    # Define required API scope for Google Sheets access
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    
    # Authenticate using service account credentials
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_JSON, scopes=scopes)
    gc = gspread.authorize(creds)

    # Open the spreadsheet by its ID
    sh = gc.open_by_key(SPREADSHEET_ID)

    # Try to get the worksheet; create it if it doesn't exist
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=20)

    # Initialize header row if worksheet is empty
    # This ensures the sheet has the correct column structure before adding data
    if not ws.get_all_values():
        ws.append_row(
            [
                "EMAIL",                # Column A: Lead's email address
                "First Name",           # Column B: Lead's first name
                "Last Name",            # Column C: Lead's last name
                "Phone Number",         # Column D: Lead's phone number
                "Course",               # Column E: Course information (currently unused)
                "Date",                 # Column F: Date extracted from email
                "Acuity Registered",    # Column G: Acuity registration status
                "AHA Registered",       # Column H: AHA registration status
                "Reminder Email Sent",  # Column I: Whether reminder was sent
            ],
            value_input_option="RAW",
        )

    return ws

def graph_get(token: str, url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Make a GET request to Microsoft Graph API.
    
    Args:
        token: OAuth2 access token for authorization
        url: Full Graph API endpoint URL
        params: Optional query parameters
    
    Returns:
        dict: JSON response from the API
    
    Raises:
        RuntimeError: If the request fails
    """
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    if not r.ok:
        raise RuntimeError(f"GET failed {r.status_code}: {r.text}")
    return r.json()

def graph_patch(token: str, url: str, body: Dict[str, Any]) -> None:
    """
    Make a PATCH request to Microsoft Graph API to update a resource.
    
    Used primarily to mark messages as read after processing.
    
    Args:
        token: OAuth2 access token for authorization
        url: Full Graph API endpoint URL
        body: JSON body data for the PATCH request
    
    Raises:
        RuntimeError: If the request fails (includes Graph API error message)
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    r = requests.patch(url, headers=headers, json=body, timeout=30)
    if not r.ok:
        raise RuntimeError(f"PATCH failed {r.status_code}: {r.text}")

def fetch_unread_messages(token: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Fetch unread messages from the user's Outlook Inbox.
    
    This function queries the Microsoft Graph API to retrieve unread messages,
    ordered by most recent first. If SENDER_EMAIL is configured, it filters
    the results to only include messages from that specific sender.
    
    Note: Sender filtering is done in Python (not in the API query) because
    Graph API's nested filters can be unreliable.
    
    Args:
        token: OAuth2 access token for authorization
        limit: Maximum number of messages to retrieve (default: 25)
    
    Returns:
        list: List of message objects containing id, subject, date, sender, and preview
    """
    # Construct API endpoint for accessing user's Inbox folder
    url = f"{GRAPH_BASE}/me/mailFolders/Inbox/messages"

    # Build OData query parameters for the Graph API request
    params: Dict[str, Any] = {
        "$top": str(limit),                              # Limit number of messages returned
        "$orderby": "receivedDateTime desc",             # Most recent messages first
        "$filter": "isRead eq false",                    # Only fetch unread messages
        "$select": "id,subject,receivedDateTime,from,bodyPreview",  # Only fetch needed fields
    }

    # Execute the API request and extract message array from response
    data = graph_get(token, url, params=params)
    msgs = data.get("value", []) or []

    # Optional: Filter by specific sender email address
    # This is done client-side because Graph API's nested filtering can be unreliable
    if SENDER_EMAIL:
        sender_lower = SENDER_EMAIL.lower()
        
        # Helper function to safely extract sender email from message object
        def sender_addr(m: Dict[str, Any]) -> str:
            return (m.get("from", {}) or {}).get("emailAddress", {}).get("address", "") or ""
        
        # Filter messages to only include those from the specified sender (case-insensitive)
        msgs = [m for m in msgs if sender_addr(m).lower() == sender_lower]

    return msgs


def message_sender_address(msg: Dict[str, Any]) -> str:
    """
    Safely extract the sender's email address from a message object.
    
    Args:
        msg: Message object from Graph API
    
    Returns:
        str: Sender's email address, or empty string if not found
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
    
    Process flow:
    1. Validate configuration (EMAIL_PROVIDER must be 'outlook')
    2. Connect to Google Sheets
    3. Authenticate with Microsoft Graph API
    4. Fetch unread messages from Inbox
    5. For each message:
       - Extract lead information (name, email, phone, date)
       - Split full name into first/last name
       - Append a new row to the Google Sheet
       - Mark the message as read to avoid reprocessing
    
    This function is called repeatedly in a loop to continuously monitor for new emails.
    """
    if PROVIDER != "outlook":
        raise RuntimeError("EMAIL_PROVIDER must be 'outlook' (this script is Outlook-only).")

    logging.info("Starting Outlook(Graph) -> Sheets processing...")

    # Step 1: Connect to Google Sheets
    ws = get_worksheet()

    # Step 2: Authenticate with Microsoft Graph API (authentication token is cached)
    token = authenticate()
    if not token:
        raise RuntimeError("Authentication failed: no access token returned.")

    # Step 3: Fetch unread messages from Outlook Inbox
    msgs = fetch_unread_messages(token, limit=25)
    logging.info("Found %d unread messages (sender filter=%r)", len(msgs), SENDER_EMAIL)
    print(f"Found {len(msgs)} unread messages (sender filter={SENDER_EMAIL!r})")

    # Step 4: Process each unread message
    for msg in msgs:
        # Extract message metadata
        msg_id = msg.get("id")
        subject = msg.get("subject") or ""
        sender = message_sender_address(msg)
        body_preview = msg.get("bodyPreview") or ""

        # Extract lead information from the email body
        fields = extract_fields(body_preview)
        logging.info("Extracted fields from msg %s: %s", msg_id, fields)

        # Parse full name into separate first and last name fields
        # Example: "John Doe" -> first_name="John", last_name="Doe"
        full_name = (fields.get("name") or "").strip()
        first_name, last_name = "", ""
        if full_name:
            parts = full_name.split()
            first_name = parts[0]
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        # Construct row data matching the Google Sheets column structure
        # Column order: EMAIL, First Name, Last Name, Phone Number, Course, Date,
        #               Acuity Registered, AHA Registered, Reminder Email Sent
        row = [
            fields.get("email") or "",      # EMAIL column
            first_name,                      # First Name column
            last_name,                       # Last Name column
            fields.get("phone") or "",      # Phone Number column
            "",                              # Course column (currently unused)
            fields.get("date") or "",       # Date column
            "Yes",                           # Acuity Registered (default: Yes)
            "Yes",                           # AHA Registered (default: Yes)
            "No",                            # Reminder Email Sent (default: No)
        ]

        # Append the row to the Google Sheet
        ws.append_row(row, value_input_option="RAW")

        # Mark the email as read to prevent reprocessing in future cycles
        if msg_id:
            graph_patch(token, f"{GRAPH_BASE}/me/messages/{msg_id}", {"isRead": True})

        print(f"✅ Appended row / subject: {subject} / from: {sender}")


# ====================================================================
# Script Entry Point
# ====================================================================

if __name__ == "__main__":
    # Initialize logging system
    setup_logging()
    
    # Get polling interval from environment (how often to check for new emails)
    INTERVAL = int(os.getenv("INTERVAL", "10"))  # Default: 10 seconds

    try:
        # Infinite loop: continuously monitor for new emails
        while True:
            try:
                # Run one complete processing cycle
                main()
            except Exception:
                # Log errors but don't crash - keep the loop running
                logging.exception("Error in main loop...")

            # Wait before checking again
            logging.info("Waiting for %s seconds before checking for new emails...", INTERVAL)
            time.sleep(INTERVAL)

    except KeyboardInterrupt:
        # Allow graceful shutdown with Ctrl+C
        logging.info("Stopped by user")
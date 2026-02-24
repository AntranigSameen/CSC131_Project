# =================
# Outlook -> Sheets (Graph)
# =================

import os
import re
import time
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List

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

# Google Sheets settings
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Leads")
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON", "service_account.json")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


# ---------------
# Helpers
# ---------------

def extract_fields(text: str) -> dict:
    """
    Normalize email body so Google Sheets doesn't split it across columns:
    - tabs -> spaces (tabs cause column splitting)
    - newlines -> spaces (keep notes in one cell)
    - collapse repeated whitespace
    """
    clean = (text or "").replace("\r", "")
    clean = clean.replace("\t", " ")
    clean = clean.replace("\n", " ")
    clean = re.sub(r"\s+", " ", clean).strip()

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
        if m:
            date_found = m.group(0)

    # Name
    name = None
    m = re.search(r"\bname\s*:\s*((?:[A-Za-z]+)(?:\s+[A-Za-z]+)*)", clean, re.IGNORECASE)
    if m:
        words = m.group(1).split()
        valid_words = [w for w in words if w.isalpha() and 2 <= len(w) <= 15]
        name = " ".join(valid_words[:3]) if valid_words else None

    notes = clean[:400]
    return {"name": name, "email": email, "phone": phone, "date": date_found, "notes": notes}


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
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_JSON, scopes=scopes)
    gc = gspread.authorize(creds)

    sh = gc.open_by_key(SPREADSHEET_ID)

    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=20)

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
            ],
            value_input_option="RAW",
        )

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

def fetch_unread_messages(token: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Fetch unread messages from Inbox. If SENDER_EMAIL is set, filter to that sender in Python
    (more reliable than Graph nested $filter).
    """
    url = f"{GRAPH_BASE}/me/mailFolders/Inbox/messages"

    params: Dict[str, Any] = {
        "$top": str(limit),
        "$orderby": "receivedDateTime desc",
        "$filter": "isRead eq false",
        "$select": "id,subject,receivedDateTime,from,bodyPreview",
    }

    data = graph_get(token, url, params=params)
    msgs = data.get("value", []) or []

    if SENDER_EMAIL:
        sender_lower = SENDER_EMAIL.lower()
        def sender_addr(m: Dict[str, Any]) -> str:
            return (m.get("from", {}) or {}).get("emailAddress", {}).get("address", "") or ""
        msgs = [m for m in msgs if sender_addr(m).lower() == sender_lower]

    return msgs


def message_sender_address(msg: Dict[str, Any]) -> str:
    try:
        return msg.get("from", {}).get("emailAddress", {}).get("address", "") or ""
    except Exception:
        return ""


# ---------------
# Main
# ---------------

def main():
    if PROVIDER != "outlook":
        raise RuntimeError("EMAIL_PROVIDER must be 'outlook' (this script is Outlook-only).")

    logging.info("Starting Outlook(Graph) -> Sheets processing...")

    ws = get_worksheet()

    # Authenticate once per cycle (your auth caches)
    token = authenticate()
    if not token:
        raise RuntimeError("Authentication failed: no access token returned.")

    msgs = fetch_unread_messages(token, limit=25)
    logging.info("Found %d unread messages (sender filter=%r)", len(msgs), SENDER_EMAIL)
    print(f"Found {len(msgs)} unread messages (sender filter={SENDER_EMAIL!r})")

    for msg in msgs:
        msg_id = msg.get("id")
        subject = msg.get("subject") or ""
        sender = message_sender_address(msg)
        body_preview = msg.get("bodyPreview") or ""

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

        # Mark as read so it won't be processed again
        if msg_id:
            graph_patch(token, f"{GRAPH_BASE}/me/messages/{msg_id}", {"isRead": True})

        print(f"✅ Appended row / subject: {subject} / from: {sender}")


if __name__ == "__main__":
    setup_logging()
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
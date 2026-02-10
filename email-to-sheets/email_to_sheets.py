#=================
# Imports
#=================

import os
import re
import pyzmail
import gspread
import time
import logging
import sys

from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from imapclient import IMAPClient
from google.oauth2.service_account import Credentials

# =====================
# Load environment vars
# =====================

load_dotenv()

IMAP_HOST = os.getenv("IMAP_HOST", os.getenv("IMAP_SERVER", "imap.gmail.com"))
IMAP_USER = os.getenv("IMAP_USER", os.getenv("EMAIL_ADDRESS"))
IMAP_PASS = os.getenv("IMAP_PASS", os.getenv("EMAIL_PASSWORD"))
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX")

# Always make IMAP_SEARCH a list (default: UNSEEN)
IMAP_SEARCH_RAW = os.getenv("IMAP_SEARCH", "").strip()
if IMAP_SEARCH_RAW:
    IMAP_SEARCH = IMAP_SEARCH_RAW.split()
else:
    IMAP_SEARCH = ["UNSEEN"]

# Filter by sender
IMAP_FROM = os.getenv("EMAIL_FROM", "").strip()
if IMAP_FROM:
    IMAP_SEARCH += ["FROM", IMAP_FROM]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Leads")
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON", "service_account.json")


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

    email = None
    m = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", clean, re.I)
    if m:
        email = m.group(0)

    phone = None
    m = re.search(r"(\+?1[\s\-\.]?)?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}", clean)
    if m:
        phone = m.group(0)
    
    date_found = None
    m = re.search(r"\bdate\s*:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", clean, re.IGNORECASE)
    if m:
        date_found = m.group(1)                                             # Look for "Date: MM/DD/YYYY" pattern first
    else:
        # Try to find any date in MM/DD/YYYY or MM-DD-YYYY format
        m = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", clean)        # If no "Date:" label, look for any date pattern in the text
        if m:
            date_found = m.group(0)
    


    name = None
    m = re.search(r"\bname\s*:\s*((?:[A-Za-z]+)(?:\s+[A-Za-z]+)*)", clean, re.IGNORECASE)
    if m:
    # Keep only alphabetic words to avoid weird characters in names, and limit to 3 words max
        words = m.group(1).split()
        valid_words = [
            w for w in words
            if w.isalpha() and 2 <= len(w) <= 15
        ]
    name = " ".join(valid_words[:3])

    notes = clean[:400]
    return {"name": name, "email": email, "phone": phone, "date": date_found, "notes": notes}


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
        ws.append_row([
            "EMAIL",
            "First Name",
            "Last Name",
            "Phone Number",
            "Course",
            "Date",
            "Acuity Registered",
            "AHA Registered",
            "Reminder Email Sent",
        ], value_input_option="RAW")

    return ws

# Logging info to a file

def setup_logging():
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).parent      # when ran as executable
    else:
        base_dir = Path(__file__).parent            # when ran as script

    log_file = base_dir / "email_to_sheets.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

    logging.info("Logging initialized. Log file: %s", log_file)

def main():
    logging.info("Starting email to sheets processing...")
    print("Loaded env:")
    print("  IMAP_HOST =", IMAP_HOST)
    print("  IMAP_USER =", "set" if IMAP_USER else None)
    print("  SPREADSHEET_ID =", "set" if SPREADSHEET_ID else None)
    print("  SERVICE_ACCOUNT_JSON =", SERVICE_ACCOUNT_JSON)
    print("  IMAP_FOLDER =", IMAP_FOLDER)
    print("  IMAP_SEARCH =", IMAP_SEARCH)

    if not IMAP_USER or not IMAP_PASS:
        raise RuntimeError("Missing IMAP_USER or IMAP_PASS in .env")

    ws = get_worksheet()

    with IMAPClient(IMAP_HOST, ssl=True) as server:
        server.login(IMAP_USER, IMAP_PASS)
        server.select_folder(IMAP_FOLDER)

        uids = server.search(IMAP_SEARCH)
        logging.info(f"Found {len(uids)} matching emails with IMAP_SEARCH={IMAP_SEARCH!r}")     #Logs the number of matching emails found.
        print(f"Found {len(uids)} matching emails with IMAP_SEARCH={IMAP_SEARCH!r}")

        for uid in uids:
            # IMAPClient 3.1.0: no uid=True kwarg
            raw = server.fetch([uid], ["RFC822"])[uid][b"RFC822"]
            msg = pyzmail.PyzMessage.factory(raw)

            subject = msg.get_subject() or ""
            from_list = msg.get_addresses("from")
            from_str = from_list[0][1] if from_list else ""
            message_id = msg.get_decoded_header("message-id") or str(uid)

            body = ""
            if msg.text_part:
                charset = msg.text_part.charset or "utf-8"
                body = msg.text_part.get_payload().decode(charset, errors="replace")
            elif msg.html_part:
                charset = msg.html_part.charset or "utf-8"
                html = msg.html_part.get_payload().decode(charset, errors="replace")
                body = re.sub(r"<[^>]+>", " ", html)

            fields = extract_fields(body)
            logging.info("extracted fields from email UID %s: %s", uid, fields)         # logs the extracted fields from the email

            # Split full name into first/last
            full_name = (fields.get("name") or "").strip()
            first_name, last_name = "", ""
            if full_name:
                parts = full_name.split()
                first_name = parts[0]
                last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

            # Match exact sheet order:
            # EMAIL, First Name, Last Name, Phone Number, Course, Date, Acuity Registered, AHA Registered, Reminder Email Sent
            row = [
                fields.get("email") or "",       # EMAIL (from message body)
                first_name,                      # First Name
                last_name,                       # Last Name
                fields.get("phone") or "",       # Phone Number
                "",                              # Course
                fields.get("date") or "",        # Date
                "Yes",                           # Acuity Registered
                "",                              # AHA Registered
                "",                              # Reminder Email Sent
            ]

            ws.append_row(row, value_input_option="RAW")

            # Mark as seen so it won't be processed again
            server.add_flags([uid], [b"\\Seen"])
            print(f"✅ Appended row for UID {uid} / subject: {subject} / from: {from_str}")

    logging.info("Done processing emails.")


if __name__ == "__main__":
    setup_logging()
    INTERVAL = 10  # IN SECONDS - how often to check for new emails
    
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

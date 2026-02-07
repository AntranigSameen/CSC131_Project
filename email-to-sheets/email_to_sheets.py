import os
import re
from datetime import datetime, timezone

from dotenv import load_dotenv
from imapclient import IMAPClient
import pyzmail
import gspread
from google.oauth2.service_account import Credentials

# =====================
# Load environment vars
# =====================
load_dotenv()

IMAP_HOST = os.getenv("IMAP_HOST", os.getenv("IMAP_SERVER", "imap.gmail.com"))
IMAP_USER = os.getenv("IMAP_USER", os.getenv("EMAIL_ADDRESS"))
IMAP_PASS = os.getenv("IMAP_PASS", os.getenv("EMAIL_PASSWORD"))
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX")

# Always make IMAP_SEARCH a list
IMAP_SEARCH_RAW = os.getenv("IMAP_SEARCH", "").strip()
if IMAP_SEARCH_RAW:
    IMAP_SEARCH = IMAP_SEARCH_RAW.split()
else:
    IMAP_SEARCH = ["UNSEEN"]

IMAP_FROM = os.getenv("EMAIL_FROM", "").strip()
if IMAP_FROM:
    IMAP_SEARCH += ["FROM", IMAP_FROM]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Leads")
SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON", "service_account.json")

# =====================
# Helpers
# =====================
def extract_fields(text: str) -> dict:
    clean = (text or "").replace("\r", "")

    email = None
    m = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", clean, re.I)
    if m:
        email = m.group(0)

    phone = None
    m = re.search(r"(\+?1[\s\-\.]?)?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}", clean)
    if m:
        phone = m.group(0)

    name = None
    m = re.search(r"\bName:\s*(.+)", clean, re.I)
    if m:
        name = m.group(1).strip()

    notes = clean[:400].strip()
    return {
        "name": name,
        "email": email,
        "phone": phone,
        "notes": notes,
    }


def get_worksheet():
    if not SPREADSHEET_ID:
        raise RuntimeError("Missing SPREADSHEET_ID in .env")

    if not os.path.exists(SERVICE_ACCOUNT_JSON):
        raise FileNotFoundError(
            f"Missing {SERVICE_ACCOUNT_JSON}. Put it in email-to-sheets folder."
        )

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_JSON, scopes=scopes
    )
    gc = gspread.authorize(creds)

    sh = gc.open_by_key(SPREADSHEET_ID)

    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=20)

    if not ws.get_all_values():
        ws.append_row([
            "TimestampUTC",
            "From",
            "Subject",
            "Name",
            "Email",
            "Phone",
            "Notes",
            "MessageId",
        ])

    return ws

# =====================
# Main
# =====================
def main():
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
        print(f"Found {len(uids)} matching emails with IMAP_SEARCH={IMAP_SEARCH!r}")

        for uid in uids:
            # ✅ FIXED: no uid=True argument
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

            ws.append_row([
                datetime.now(timezone.utc).isoformat(),
                from_str,
                subject,
                fields["name"] or "",
                fields["email"] or "",
                fields["phone"] or "",
                fields["notes"] or "",
                message_id,
            ])

            server.add_flags([uid], [b"\\Seen"])
            print(f"✅ Appended row for UID {uid} / subject: {subject}")

    print("Done.")

# =====================
# Entry point
# =====================
if __name__ == "__main__":
    raise SystemExit(main())

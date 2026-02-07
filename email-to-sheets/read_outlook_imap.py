import imaplib
import email
from email.header import decode_header
import os
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
IMAP_SERVER = os.getenv("IMAP_SERVER", "outlook.office365.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))

def decode_mime_words(s):
    if not s:
        return ""
    parts = decode_header(s)
    decoded = []
    for part, enc in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)

def get_text_from_message(msg):
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", "")).lower()
            if ctype == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", "")).lower()
            if ctype == "text/html" and "attachment" not in disp:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return ""

def main():
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        raise RuntimeError("Missing EMAIL_ADDRESS or EMAIL_PASSWORD in .env")

    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    mail.select("INBOX")

    status, data = mail.search(None, "ALL")
    if status != "OK":
        raise RuntimeError("Failed to search inbox")

    ids = data[0].split()
    print(f"Found {len(ids)} emails.")

    latest_ids = ids[-5:]
    for i, eid in enumerate(reversed(latest_ids), start=1):
        status, msg_data = mail.fetch(eid, "(RFC822)")
        if status != "OK":
            continue

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        subject = decode_mime_words(msg.get("Subject"))
        sender = decode_mime_words(msg.get("From"))
        date = msg.get("Date", "")

        body = get_text_from_message(msg).strip()
        body_preview = body[:500] + "..." if len(body) > 500 else body

        print("\n" + "=" * 60)
        print(f"[{i}] Subject: {subject}")
        print(f"    From: {sender}")
        print(f"    Date: {date}")
        print("-" * 60)
        print(body_preview)

    mail.logout()

if __name__ == "__main__":
    main()

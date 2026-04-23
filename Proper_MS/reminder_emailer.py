# ============================================================================
# Reminder Email Automation Module
# ============================================================================
# This module handles automated reminder emails for Acuity registration.
# Sends personalized reminders based on registration status and configured
# cadence (days for non-registered, years for registered students).
# ============================================================================

import os
import requests
from datetime import datetime, timedelta
from typing import Dict, Any

# Import Google Sheets client (lazy-loaded from run_automation)
_GS_GC = None
_GS_SH = None
_GS_WS_CACHE = {}

# Environment configuration
REMINDER_EMAIL_DAYS = int(os.getenv("REMINDER_EMAIL_DAYS", "7"))
GOOGLE_SHEET_URL = os.getenv(
    "GOOGLE_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/143-IvGetu1Lz8InKi9lqNcJCiCziSvtD2954sgxxZRk/edit?gid=0#gid=0",
)


# ============================================================================
# Helper Functions
# ============================================================================

def _positive_int_env(name: str, default: int) -> int:
    """Get positive integer from environment variable."""
    raw = (os.getenv(name, str(default)) or "").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return max(1, int(default))


def _add_years(start: datetime, years: int) -> datetime:
    """Add years to a datetime, handling leap year edge cases."""
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        # Handle Feb 29 on non-leap years
        return start.replace(month=2, day=28, year=start.year + years)


def _is_truthy_yes(value: str) -> bool:
    """Check if value represents 'yes'."""
    return (value or "").strip().lower() in {"yes", "y", "true", "1"}


def _parse_sheet_date(raw: str) -> datetime | None:
    """Parse date string from Google Sheet."""
    value = (raw or "").strip()
    if not value:
        return None

    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _normalize_header(value: str) -> str:
    """Normalize header for case-insensitive column lookup."""
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _get_gsheet_worksheet(worksheet_name: str | None = None):
    """Get or create cached Google Sheets worksheet connection."""
    global _GS_GC, _GS_SH
    
    # Lazy import to avoid circular dependencies
    if _GS_GC is None:
        import gspread
        from google.oauth2.service_account import Credentials
        from utils import resource_path
        
        SERVICE_ACCOUNT_JSON = resource_path(os.getenv("SERVICE_ACCOUNT_AHA_JSON", "google_sheet_api_key.json"))
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_JSON, scopes=scopes)
        _GS_GC = gspread.authorize(creds)
        _GS_SH = _GS_GC.open_by_url(GOOGLE_SHEET_URL)

    key = (worksheet_name or "").strip() or "__sheet1__"
    if key in _GS_WS_CACHE:
        return _GS_WS_CACHE[key]

    ws = _GS_SH.worksheet(worksheet_name) if worksheet_name else _GS_SH.sheet1
    _GS_WS_CACHE[key] = ws
    return ws


def _safe_update_cell(ws, row: int, col: int, value: str):
    """Safely update a cell in Google Sheets."""
    try:
        ws.update_cell(row, col, value)
    except Exception as e:
        print(f"[REMINDER] Failed to update cell ({row}, {col}): {e!r}", flush=True)
        raise


# ============================================================================
# Email Sending Function
# ============================================================================

def send_reminder_email(token: str, recipient_email: str, subject: str, body_text: str) -> bool:
    """Send a reminder email using Microsoft Graph API.
    
    Args:
        token: Microsoft Graph API access token
        recipient_email: Recipient's email address
        subject: Email subject line
        body_text: Email body content (plain text)
    
    Returns:
        True if email sent successfully, False otherwise
    """
    url = "https://graph.microsoft.com/v1.0/me/sendMail"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body_text},
            "toRecipients": [{"emailAddress": {"address": recipient_email}}],
        },
        "saveToSentItems": True,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
    except Exception as e:
        print(f"[REMINDER] Failed sending email to {recipient_email}: {e!r}", flush=True)
        return False

    if response.status_code == 202:
        return True

    print(
        f"[REMINDER] Graph sendMail failed for {recipient_email}: "
        f"status={response.status_code}, body={response.text[:500]!r}",
        flush=True,
    )
    return False


# ============================================================================
# Main Reminder Email Processing
# ============================================================================

def process_due_reminder_emails(token: str, worksheet_name: str | None = None) -> Dict[str, int]:
    """Send reminder emails based on Acuity registration status and configured cadence.

    Cadence is environment-driven:
    - ACUITY_NOT_REGISTERED_REMINDER_DAYS: for Acuity Registration != Yes
    - ACUITY_REGISTERED_REMINDER_YEARS: for Acuity Registration == Yes

    Args:
        token: Microsoft Graph API access token
        worksheet_name: Optional worksheet name (defaults to Sheet1)

    Returns:
        Dictionary with stats: {"sent": int, "considered": int, "errors": int}
    """
    if not token:
        return {"sent": 0, "considered": 0, "errors": 0}

    days_interval = _positive_int_env("ACUITY_NOT_REGISTERED_REMINDER_DAYS", REMINDER_EMAIL_DAYS)
    years_interval = _positive_int_env("ACUITY_REGISTERED_REMINDER_YEARS", 1)

    ws = _get_gsheet_worksheet(worksheet_name)
    all_values = ws.get_all_values()
    if not all_values:
        return {"sent": 0, "considered": 0, "errors": 0}

    headers = all_values[0]
    header_index = {_normalize_header(h): idx + 1 for idx, h in enumerate(headers)}

    email_col = header_index.get("email", 1)
    first_col = header_index.get("firstname", 2)
    date_col = header_index.get("date", 6)
    acuity_col = header_index.get("acuityregistration", 7)
    reminder_col = header_index.get("reminderemail", 9)

    now = datetime.now()
    today_str = now.strftime("%m/%d/%Y")
    stats = {"sent": 0, "considered": 0, "errors": 0}

    for row_idx, row in enumerate(all_values, start=1):
        if row_idx == 1 or not row:
            continue

        email = (row[email_col - 1] if len(row) >= email_col else "").strip()
        if not email or "@" not in email:
            continue

        first_name = (row[first_col - 1] if len(row) >= first_col else "").strip()
        date_raw = (row[date_col - 1] if len(row) >= date_col else "").strip()
        acuity_value = (row[acuity_col - 1] if len(row) >= acuity_col else "").strip()
        reminder_raw = (row[reminder_col - 1] if len(row) >= reminder_col else "").strip()

        acuity_registered = _is_truthy_yes(acuity_value)
        baseline = _parse_sheet_date(reminder_raw) or _parse_sheet_date(date_raw)
        if baseline is None:
            continue

        if acuity_registered:
            due_date = _add_years(baseline, years_interval)
            subject = "Acuity Registration Renewal Reminder"
            body = (
                f"Hello {first_name or 'there'},\n\n"
                f"This is a reminder that your Acuity registration is active. "
                f"Please review and renew any required registration steps.\n\n"
                f"This reminder is sent every {years_interval} year(s)."
            )
        else:
            due_date = baseline + timedelta(days=days_interval)
            subject = "Acuity Registration Reminder"
            body = (
                f"Hello {first_name or 'there'},\n\n"
                "Our records show your Acuity registration is still incomplete. "
                "Please complete registration as soon as possible.\n\n"
                f"This reminder is sent every {days_interval} day(s) until completed."
            )

        if now < due_date:
            continue

        stats["considered"] += 1
        if send_reminder_email(token, email, subject, body):
            try:
                _safe_update_cell(ws, row_idx, reminder_col, today_str)
                stats["sent"] += 1
            except Exception as e:
                stats["errors"] += 1
                print(f"[REMINDER] Sent email but failed updating sheet for {email}: {e!r}", flush=True)
        else:
            stats["errors"] += 1

    return stats


def check_and_populate_reminder_emails(worksheet_name: str | None = None) -> int:
    """Check for students needing reminders and auto-populate Reminder Email column.
    
    Finds students where:
    - Acuity Registration = "No"
    - Reminder Email is blank
    - Student was added >= REMINDER_EMAIL_DAYS ago
    
    Auto-populates Reminder Email with today's date for those students.
    
    Args:
        worksheet_name: Optional worksheet name (defaults to Sheet1)
    
    Returns:
        Count of students updated
    """
    ws = _get_gsheet_worksheet(worksheet_name)
    
    try:
        all_values = ws.get_all_values()
        today_str = datetime.now().strftime("%m/%d/%Y")
        cutoff_date = datetime.now() - timedelta(days=REMINDER_EMAIL_DAYS)
        updated_count = 0
        
        for row_idx, row in enumerate(all_values, start=1):
            if row_idx == 1:
                # Skip header row
                continue
            
            if not row or len(row) < 9:
                continue
            
            email = (row[0] or "").strip()
            date_str = (row[5] or "").strip()  # Column 6 (index 5) is Date
            acuity_reg = (row[6] or "").strip().lower()  # Column 7 (index 6) is Acuity Registration
            reminder_email = (row[8] or "").strip()  # Column 9 (index 8) is Reminder Email
            
            if not email:
                continue
            
            # Check if this row needs a reminder
            if acuity_reg != "no" or reminder_email:
                # Skip if Acuity is not "No" or Reminder already populated
                continue
            
            # Parse the date and check if it's old enough
            try:
                # Try to parse date in mm/dd/yyyy format
                date_obj = datetime.strptime(date_str, "%m/%d/%Y")
                if date_obj <= cutoff_date:
                    # Student is old enough, populate reminder date
                    _safe_update_cell(ws, row_idx, 9, today_str)
                    updated_count += 1
                    print(f"[REMINDER] Populated reminder for {email} (added {date_str})", flush=True)
            except ValueError:
                # Skip rows with invalid date format
                continue
        
        return updated_count
    
    except Exception as e:
        print(f"[REMINDER] Error in check_and_populate_reminder_emails: {e!r}", flush=True)
        return 0

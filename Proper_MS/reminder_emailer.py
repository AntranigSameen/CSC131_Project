# ============================================================================
# Reminder Email Automation Module
# ============================================================================
# This module handles automated reminder emails for Acuity registration.
# Sends personalized reminders based on registration status and configured
# cadence (days for non-registered, months for registered students).
# ============================================================================

import os
import json
import hashlib
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, Any
from location_keys import load_location_keys
from location_email_tracker import load_tracker_hashes, append_tracker_hash
from location_email_templates import load_location_templates
from acuity_registration import update_aha_registration_status

# Import Google Sheets client (lazy-loaded from run_automation)
_GS_GC = None
_GS_SH = None
_GS_WS_CACHE = {}
_RQI_GS_GC = None
_RQI_GS_SH = None
_RQI_GS_WS_CACHE = {}


def _writeback_to_rqi_enabled() -> bool:
    return _truthy(os.getenv("LOCATION_EMAIL_WRITEBACK_TO_RQI", "false"))


def _normalize_tracking_marker(raw_marker: str) -> str:
    marker = (raw_marker or "").strip()
    if not marker:
        return ""

    parsed = _parse_sheet_date(marker)
    if parsed:
        return parsed.strftime("%Y-%m-%d")

    return marker.lower()


def _tracking_id(email: str, location: str, cycle_marker: str = "") -> str:
    """Build deterministic hashed ID for one-time send dedupe.

    Stores only hash, not raw email/location values.
    """
    secret = (os.getenv("LOCATION_EMAIL_TRACKING_SECRET") or "").strip()
    normalized_marker = _normalize_tracking_marker(cycle_marker)
    raw = (
        f"{(email or '').strip().lower()}|"
        f"{(location or '').strip().lower()}|"
        f"{normalized_marker or 'no-cycle'}|"
        f"{secret}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

# Environment configuration
REMINDER_EMAIL_DAYS = int(os.getenv("REMINDER_EMAIL_DAYS", "7"))
REMINDER_MAX_EMAILS_PER_RUN = int(os.getenv("REMINDER_MAX_EMAILS_PER_RUN", "25"))                                                     # Maximum reminder/location emails sent per automation cycle
REMINDER_SEND_DELAY_SECONDS = float(os.getenv("REMINDER_SEND_DELAY_SECONDS", "1"))                                                     # Delay between successful reminder/location sends

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


def _add_months(start: datetime, months: int) -> datetime:
    """Add months to a datetime, handling month-end edge cases."""
    month = start.month - 1 + months
    year = start.year + month // 12
    month = month % 12 + 1
    day = min(start.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return start.replace(year=year, month=month, day=day)


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


def _first_present_column(header_index: Dict[str, int], keys: tuple[str, ...], default: int = 0) -> int:
    """Return first matching 1-based column index from normalized header map."""
    for key in keys:
        idx = header_index.get(_normalize_header(key))
        if idx:
            return idx
    return default


def _cell(row: list[str], col: int) -> str:
    """Read 1-based column value from row safely."""
    if col <= 0 or len(row) < col:
        return ""
    return (row[col - 1] or "").strip()


def _truthy(value: str) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_aha_location_email_enabled() -> bool:
    return _truthy(os.getenv("AHA_LOCATION_EMAIL_ENABLED", "false"))


def _load_location_email_rules() -> Dict[str, Dict[str, str]]:
    """Load optional location-specific email rules from JSON env.

    Env example:
    {
      "Main Campus": {"subject": "...", "body": "..."},
      "Downtown": {"subject": "...", "body": "..."}
    }
    """
    raw = (os.getenv("AHA_LOCATION_EMAIL_RULES_JSON") or "").strip()
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[AHA-LOCATION-EMAIL] Invalid AHA_LOCATION_EMAIL_RULES_JSON: {e!r}", flush=True)
        return {}

    rules: Dict[str, Dict[str, str]] = {}
    if not isinstance(parsed, dict):
        return rules

    for location_key, config in parsed.items():
        if not isinstance(config, dict):
            continue
        key = (location_key or "").strip().lower()
        if not key:
            continue
        rules[key] = {
            "subject": (config.get("subject") or "").strip(),
            "body": (config.get("body") or "").strip(),
        }
    return rules


def _location_key_for_row(raw_location: str, resolved_location: str, location_pairs: Dict[str, str]) -> str:
    """Find the configured location key for this row when possible."""
    raw = (raw_location or "").strip()
    resolved = (resolved_location or "").strip()

    if raw in location_pairs:
        return raw

    raw_lower = raw.lower()
    resolved_lower = resolved.lower()

    for key, value in location_pairs.items():
        key_lower = (key or "").strip().lower()
        value_lower = (value or "").strip().lower()
        if raw_lower and raw_lower == key_lower:
            return key
        if resolved_lower and resolved_lower == value_lower:
            return key

    return ""


def _normalize_lookup_map(values: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    normalized: Dict[str, Dict[str, str]] = {}
    for key, config in (values or {}).items():
        normalized[(key or "").strip().lower()] = config
    return normalized

class _SafeTemplateDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"                                                                                                       # Leave unknown placeholders visible instead of breaking the whole template


def _render_template(template: str, context: Dict[str, str]) -> str:
    try:
        return (template or "").format_map(_SafeTemplateDict(context))                                                               # Replace known placeholders while preserving unknown ones
    except Exception:
        return template or ""                                                                                                        # Never fall back to a different template because of one bad placeholder

def _build_aha_row_context(
    email: str,
    first_name: str,
    last_name: str,
    course: str,
    date_value: str,
) -> Dict[str, str]:
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()

    return {
        "first_name": first_name or "",
        "first name": first_name or "",
        "last_name": last_name or "",
        "last name": last_name or "",
        "full_name": full_name,
        "full name": full_name,
        "name": full_name,
        "email": email or "",
        "course": course or "",
        "date": date_value or "",
        "today": datetime.now().strftime("%m/%d/%Y"),
    }

def _load_location_email_templates() -> Dict[str, Any]:
    """Load templates from file and merge legacy env JSON rules as by_location overrides."""
    templates = load_location_templates()
    env_rules = _load_location_email_rules()

    by_location = dict(templates.get("by_location") or {})
    by_location.update(env_rules)

    return {
        "default": dict(templates.get("default") or {}),
        "by_key": dict(templates.get("by_key") or {}),
        "by_location": by_location,
    }


def _compose_location_email(
    first_name: str,
    last_name: str,
    recipient_email: str,
    location: str,
    location_key: str,
    templates: Dict[str, Any],
    course: str = "",
    date_value: str = "",
) -> tuple[str, str]:
    """Compose subject/body for a recipient using key/location/default template selection."""
    full_name = " ".join(part for part in [first_name, last_name] if part).strip() or "there"

    context = {
        "first_name": first_name or "there",
        "first name": first_name or "there",
        "last_name": last_name or "",
        "last name": last_name or "",
        "full_name": full_name,
        "full name": full_name,
        "name": full_name,
        "email": recipient_email or "",
        "location_key": location_key or "",
        "location key": location_key or "",
        "location": location or "your location",
        "course": course or "",
        "date": date_value or "",
        "today": datetime.now().strftime("%m/%d/%Y"),
    }

    default_block = templates.get("default") if isinstance(templates.get("default"), dict) else {}
    default_subject = (default_block.get("subject") or "").strip() or f"AHA Update - {context['location']}"
    default_body = (default_block.get("body") or "").strip() or (
        "Hello {first_name},\n\n"
        "This is your AHA update for {location}.\n"
        "Please review the required steps for your location and complete any pending items.\n\n"
        "If you have questions, reply to this email."
    )

    by_key = _normalize_lookup_map(templates.get("by_key") if isinstance(templates.get("by_key"), dict) else {})
    by_location = _normalize_lookup_map(templates.get("by_location") if isinstance(templates.get("by_location"), dict) else {})

    selected_template: Dict[str, str] = {}
    key_lookup = (location_key or "").strip().lower()
    location_lookup = (location or "").strip().lower()

    if key_lookup and key_lookup in by_key:
        selected_template = by_key[key_lookup]
    elif location_lookup and location_lookup in by_location:
        selected_template = by_location[location_lookup]

    subject_template = (selected_template.get("subject") or "").strip() or default_subject
    body_template = (selected_template.get("body") or "").strip() or default_body

    subject = _render_template(subject_template, context)
    body = _render_template(body_template, context)

    return subject, body


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


def _get_rqi_gsheet_worksheet(worksheet_name: str | None = None):
    """Get or create cached RQI worksheet connection using SPREADSHEET_ID."""
    global _RQI_GS_GC, _RQI_GS_SH

    # Lazy import to avoid circular dependencies
    if _RQI_GS_GC is None:
        import gspread
        from google.oauth2.service_account import Credentials
        from utils import resource_path

        service_account_json = resource_path(os.getenv("SERVICE_ACCOUNT_RQI_JSON", "service_account.json"))
        spreadsheet_id = (os.getenv("SPREADSHEET_ID") or "").strip()
        if not spreadsheet_id:
            raise RuntimeError("Missing SPREADSHEET_ID for RQI location emails.")

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(service_account_json, scopes=scopes)
        _RQI_GS_GC = gspread.authorize(creds)
        _RQI_GS_SH = _RQI_GS_GC.open_by_key(spreadsheet_id)

    default_worksheet = (os.getenv("WORKSHEET_NAME") or "Leads").strip()
    key = (worksheet_name or "").strip() or default_worksheet or "__sheet1__"
    if key in _RQI_GS_WS_CACHE:
        return _RQI_GS_WS_CACHE[key]

    ws = _RQI_GS_SH.worksheet(key) if key != "__sheet1__" else _RQI_GS_SH.sheet1
    _RQI_GS_WS_CACHE[key] = ws
    return ws


def _load_aha_registered_emails() -> set[str]:
    """Return lowercase emails that are marked AHA Registration = yes in AHA sheet."""
    worksheet_name = (os.getenv("AHA_REGISTRATION_WORKSHEET") or "").strip() or None
    ws = _get_gsheet_worksheet(worksheet_name)
    all_values = ws.get_all_values()
    if not all_values:
        return set()

    headers = all_values[0]
    header_index = {_normalize_header(h): idx + 1 for idx, h in enumerate(headers)}
    email_col = _first_present_column(header_index, ("Email", "Email Address", "UserID"), default=0)
    aha_col = _first_present_column(
        header_index,
        ("AHA Registration", "AHARegistered", "AHA Status", "AHA Registration", "AHA Registration Status"),
        default=0,
    )

    if email_col == 0 or aha_col == 0:
        return set()

    registered_emails: set[str] = set()
    for row_idx, row in enumerate(all_values, start=1):
        if row_idx == 1 or not row:
            continue
        email_value = _cell(row, email_col).lower()
        aha_value = _cell(row, aha_col)
        if email_value and "@" in email_value and _is_truthy_yes(aha_value):
            registered_emails.add(email_value)

    return registered_emails


def _resolve_location_from_key_store(raw_location: str, location_pairs: Dict[str, str]) -> str:
    """Translate/validate a location token using the key store.

    Accepted inputs:
    - A key present in location_keys.txt (translated to mapped location)
    - A mapped location value already present in location_keys.txt (validated)
    """
    clean = (raw_location or "").strip()
    if not clean:
        return ""

    if clean in location_pairs:
        return (location_pairs.get(clean) or "").strip()

    lowered = clean.lower()

    for key, value in location_pairs.items():
        if (key or "").strip().lower() == lowered:
            return (value or "").strip()

    for _key, value in location_pairs.items():
        if (value or "").strip().lower() == lowered:
            return (value or "").strip()

    return ""


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
        request_id = response.headers.get("request-id", "")
        client_request_id = response.headers.get("client-request-id", "")

        print(
            f"[REMINDER] Graph sendMail response for {recipient_email}: "
            f"status={response.status_code}, request-id={request_id}, client-request-id={client_request_id}",
            flush=True,
        )
    except Exception as e:
        print(f"[REMINDER] Failed sending email to {recipient_email}: {e!r}", flush=True)
        return False

    if response.status_code == 202:
        delay_seconds = float(os.getenv("REMINDER_SEND_DELAY_SECONDS", "10") or "10")

        if delay_seconds > 0:
            print(f"[REMINDER] Email accepted for {recipient_email}. Waiting {delay_seconds} seconds before next send.", flush=True)
            time.sleep(delay_seconds)                                                                                                 # Throttle every successful Graph sendMail call

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
    - ACUITY_REGISTERED_REMINDER_MONTHS: for Acuity Registration == Yes

    Args:
        token: Microsoft Graph API access token
        worksheet_name: Optional worksheet name (defaults to Sheet1)

    Returns:
        Dictionary with stats: {"sent": int, "considered": int, "errors": int}
    """
    if not token:
        return {"sent": 0, "considered": 0, "errors": 0}

    days_interval = _positive_int_env("ACUITY_NOT_REGISTERED_REMINDER_DAYS", REMINDER_EMAIL_DAYS)
    months_interval = _positive_int_env("ACUITY_REGISTERED_REMINDER_MONTHS", 12)

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
    paid_col = _first_present_column(
        header_index,
        ("Paid Online", "Paid", "Payment Status", "Payment Complete"),
        default=0,
    )
    aha_col = _first_present_column(
        header_index,
        ("AHA Registration", "AHARegistered", "AHA Status"),
        default=0,
    )

    now = datetime.now()
    today_str = now.strftime("%m/%d/%Y")
    stats = {"sent": 0, "considered": 0, "errors": 0, "skipped": 0}

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
        paid_value = (row[paid_col - 1] if paid_col > 0 and len(row) >= paid_col else "").strip()
        aha_value = (row[aha_col - 1] if aha_col > 0 and len(row) >= aha_col else "").strip()

        acuity_registered = _is_truthy_yes(acuity_value)
        paid_complete = _is_truthy_yes(paid_value)
        aha_registered = _is_truthy_yes(aha_value)

        # Fully complete users should receive the dedicated location email flow,
        # not the legacy completion reminder from this function.
        if acuity_registered and paid_complete and aha_registered:
            continue

        reminder_date = _parse_sheet_date(reminder_raw)

        if reminder_raw and reminder_date is None:
            stats["skipped"] += 1
            continue                                                                                                                  # Skip invalid reminder dates instead of sending repeatedly

        reminder_is_due = reminder_date is None or now >= reminder_date + timedelta(days=days_interval)

        if acuity_registered:
            stats["skipped"] += 1
            continue                                                                                                                  # Registered users are handled by process_aha_location_emails()

        else:
            last_col = _first_present_column(
                header_index,
                ("Last Name", "LastName", "Last"),
                default=0,
            )

            course_col = _first_present_column(
                header_index,
                ("Course",),
                default=0,
            )

            last_name = _cell(row, last_col)
            course_value = _cell(row, course_col)

            context = _build_aha_row_context(
                email=email,
                first_name=first_name,
                last_name=last_name,
                course=course_value,
                date_value=date_raw,
            )

            subject = _render_template(
                "Acuity Registration Reminder - {course}",
                context,
            )

            body = _render_template(
                (
                    os.getenv("ACUITY_NOT_REGISTERED_EMAIL_BODY_TEMPLATE", "") or
                    "Hello {first_name},\n\n"
                    "Our records show your Acuity registration for {course} on {date} is still incomplete.\n\n"
                    "Please complete registration as soon as possible.\n\n"
                    "Thank you."
                ),
                context,
            )

        if not acuity_registered and not reminder_is_due:
            stats["skipped"] += 1
            continue

        stats["considered"] += 1
        if send_reminder_email(token, email, subject, body):
            try:
                _safe_update_cell(ws, row_idx, reminder_col, today_str)
                stats["sent"] += 1

                if stats["sent"] >= REMINDER_MAX_EMAILS_PER_RUN:
                    return stats                                                                                                      # Stop this cycle after configured batch limit
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

def sync_aha_acuity_from_rqi_sheet() -> int:
    """Flip AHA Acuity Registration from No to Yes when the person exists in the RQI sheet."""
    synced_count = 0

    try:
        rqi_ws = _get_rqi_gsheet_worksheet()
        rqi_values = rqi_ws.get_all_values()

        if not rqi_values:
            return 0

        rqi_headers = rqi_values[0]
        rqi_header_index = {_normalize_header(h): idx + 1 for idx, h in enumerate(rqi_headers)}

        email_col = _first_present_column(rqi_header_index, ("Email", "Email Address", "UserID"), default=0)
        first_col = _first_present_column(rqi_header_index, ("FirstName", "First Name", "First"), default=0)
        last_col = _first_present_column(rqi_header_index, ("LastName", "Last Name", "Last"), default=0)
        date_col = _first_present_column(rqi_header_index, ("HireDate", "Hire Date", "Date", "ActiveDate", "Active Date"), default=0)

        if email_col == 0:
            print("[AHA-SYNC] RQI sheet missing Email/UserID column.", flush=True)
            return 0

        for row_idx, row in enumerate(rqi_values, start=1):
            if row_idx == 1 or not row:
                continue

            email = _cell(row, email_col)
            if not email or "@" not in email:
                continue

            updated = update_aha_registration_status(
                email=email,
                registration_date=_cell(row, date_col),
                first_name=_cell(row, first_col),
                last_name=_cell(row, last_col),
            )

            if updated:
                synced_count += 1

        if synced_count:
            print(f"[AHA-SYNC] Updated {synced_count} AHA row(s) from RQI sheet.", flush=True)

        return synced_count

    except Exception as e:
        print(f"[AHA-SYNC] Failed syncing AHA from RQI sheet: {e!r}", flush=True)
        return 0

def process_aha_location_emails(token: str, worksheet_name: str | None = None) -> Dict[str, int]:
    """Send next-day location reminders driven by the AHA sheet."""
    stats = {"sent": 0, "considered": 0, "errors": 0, "skipped": 0, "invalid_location": 0}

    if not token:
        return stats

    if not _is_aha_location_email_enabled():
        return stats

    sync_aha_acuity_from_rqi_sheet()                                                                                                  # Ensure AHA Acuity Registration is updated before checking next-day reminders

    aha_ws = _get_gsheet_worksheet(worksheet_name)
    aha_values = aha_ws.get_all_values()

    if not aha_values:
        return stats

    aha_headers = aha_values[0]
    aha_header_index = {_normalize_header(h): idx + 1 for idx, h in enumerate(aha_headers)}

    aha_email_col = _first_present_column(aha_header_index, ("Email", "Email Address"), default=1)
    aha_first_col = _first_present_column(aha_header_index, ("First Name", "FirstName", "First"), default=0)
    aha_last_col = _first_present_column(aha_header_index, ("Last Name", "LastName", "Last"), default=0)
    aha_course_col = _first_present_column(aha_header_index, ("Course",), default=0)
    aha_date_col = _first_present_column(aha_header_index, ("Date",), default=0)
    acuity_col = _first_present_column(
        aha_header_index,
        ("Acuity Registration", "Acuity Registration", "AcuityRegistered", "Acuity Status"),
        default=0,
    )
    reminder_col = _first_present_column(aha_header_index, ("Reminder Email", "ReminderEmail"), default=0)

    if aha_email_col == 0 or aha_date_col == 0 or acuity_col == 0 or reminder_col == 0:
        print("[AHA-LOCATION-EMAIL] Missing required AHA sheet columns.", flush=True)
        stats["errors"] += 1
        return stats

    rqi_ws = _get_rqi_gsheet_worksheet()
    rqi_values = rqi_ws.get_all_values()

    if not rqi_values:
        return stats

    rqi_headers = rqi_values[0]
    rqi_header_index = {_normalize_header(h): idx + 1 for idx, h in enumerate(rqi_headers)}

    rqi_email_col = _first_present_column(rqi_header_index, ("Email", "Email Address", "UserID"), default=0)
    rqi_location_col = _first_present_column(
        rqi_header_index,
        ("LocationName", "Location Name", "Location", "Site", "Facility", "Campus"),
        default=0,
    )

    if rqi_email_col == 0 or rqi_location_col == 0:
        print("[AHA-LOCATION-EMAIL] Missing Email or LocationName column in RQI sheet.", flush=True)
        stats["errors"] += 1
        return stats

    rqi_by_email: Dict[str, list[str]] = {}

    for rqi_row_idx, rqi_row in enumerate(rqi_values, start=1):
        if rqi_row_idx == 1 or not rqi_row:
            continue

        rqi_email = _cell(rqi_row, rqi_email_col).lower()

        if rqi_email and "@" in rqi_email:
            rqi_by_email[rqi_email] = rqi_row

    location_pairs = load_location_keys()

    if not location_pairs:
        print("[AHA-LOCATION-EMAIL] No location keys configured. Add keys in the GUI Location Keys tab.", flush=True)
        stats["errors"] += 1
        return stats

    templates = _load_location_email_templates()
    tracked_ids = load_tracker_hashes()
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    today_str = datetime.now().strftime("%m/%d/%Y")

    for aha_row_idx, aha_row in enumerate(aha_values, start=1):
        if aha_row_idx == 1 or not aha_row:
            continue

        email = _cell(aha_row, aha_email_col)
        email_lower = email.lower()

        if not email or "@" not in email:
            stats["skipped"] += 1
            continue

        acuity_value = _cell(aha_row, acuity_col)
        if not _is_truthy_yes(acuity_value):
            stats["skipped"] += 1
            continue

        course_date_raw = _cell(aha_row, aha_date_col)
        course_date = _parse_sheet_date(course_date_raw)

        if not course_date or course_date.date() != tomorrow:
            stats["skipped"] += 1
            continue

        reminder_raw = _cell(aha_row, reminder_col)
        reminder_date = _parse_sheet_date(reminder_raw)

        if reminder_date and reminder_date.date() == today:
            stats["skipped"] += 1
            continue

        rqi_row = rqi_by_email.get(email_lower)

        if not rqi_row:
            stats["skipped"] += 1
            print(f"[AHA-LOCATION-EMAIL] No matching RQI row found for {email}.", flush=True)
            continue

        raw_location = _cell(rqi_row, rqi_location_col)

        if not raw_location:
            stats["invalid_location"] += 1
            stats["errors"] += 1
            print(f"[AHA-LOCATION-EMAIL] Matching RQI row has no LocationName for {email}.", flush=True)
            continue

        location = _resolve_location_from_key_store(raw_location, location_pairs)

        if not location:
            stats["invalid_location"] += 1
            stats["errors"] += 1
            print(
                f"[AHA-LOCATION-EMAIL] Location {raw_location!r} for {email} was not found in location key store.",
                flush=True,
            )
            continue

        location_key = _location_key_for_row(raw_location, location, location_pairs)

        first_name = _cell(aha_row, aha_first_col)
        last_name = _cell(aha_row, aha_last_col)
        course_value = _cell(aha_row, aha_course_col)

        dedupe_id = _tracking_id(email, location, course_date_raw)

        if dedupe_id in tracked_ids:
            stats["skipped"] += 1
            continue

        subject, body = _compose_location_email(
            first_name,
            last_name,
            email,
            location,
            location_key,
            templates,
            course=course_value,
            date_value=course_date_raw,
        )

        stats["considered"] += 1

        if send_reminder_email(token, email, subject, body):
            try:
                append_tracker_hash(dedupe_id)
                tracked_ids.add(dedupe_id)
                _safe_update_cell(aha_ws, aha_row_idx, reminder_col, today_str)
                stats["sent"] += 1

                if stats["sent"] >= REMINDER_MAX_EMAILS_PER_RUN:
                    return stats

            except Exception as e:
                stats["errors"] += 1
                print(f"[AHA-LOCATION-EMAIL] Sent but failed to persist tracking/update sheet for {email}: {e!r}", flush=True)
        else:
            stats["errors"] += 1

    return stats

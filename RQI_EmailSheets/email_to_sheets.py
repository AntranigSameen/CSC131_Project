# --------------------------------------------------------------------
# Email to Google Sheets Integration
# --------------------------------------------------------------------
# This script reads unread emails from Microsoft Outlook using the
# Microsoft Graph API and automatically extracts employee information
# (LocationID, Name, Email, HireDate, etc.) to append as rows in a
# Google Sheet. It can also create Office 365 calendar events from
# appointment details found in the email body.
# --------------------------------------------------------------------

# Standard library imports for file handling, pattern matching, timing, and logging
import os
import re
import time
import logging
import sys
import csv
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dotenv import set_key

# Third-party imports
import requests  # For making HTTP requests to Microsoft Graph API
import gspread  # For Google Sheets integration
from google.oauth2.service_account import Credentials  # For Google Sheets authentication

# Authentication module from Proper_MS(handles Microsoft OAuth2 device flow)
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "RQI_EmailSheets"))

from Proper_MS.outlook_authentication import authenticate
from Proper_MS.utils import resource_path, writable_env_file
from Proper_MS.acuity_registration import update_aha_registration_status
from Proper_MS.dashboard_events import dashboard_event

# --------------------------------------------------------------------
# Environment Variables
# --------------------------------------------------------------------
# Load configuration from .env file in the same directory

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

# --------------------------------------------------------------------
# CSV Export / SFTP Configuration
# --------------------------------------------------------------------

DEFAULT_CSV_FILENAME = "preprod_cl.csv"                                                                                               # Default CSV file name used inside each time-window folder
DEFAULT_BATCH_MINUTES = 15                                                                                                            # Default upload window length in minutes

_batch_state_lock = threading.Lock()                                                                                                  # Prevent concurrent batch state changes across worker/manual actions
_batch_window_anchor: Optional[datetime] = None                                                                                       # Optional custom upload window anchor set by manual refresh
_current_batch_start: Optional[datetime] = None                                                                                       # Currently active batch window start time
_current_batch_dir: Optional[Path] = None                                                                                             # Currently active batch folder path
_current_batch_csv_path: Optional[Path] = None                                                                                        # Currently active CSV file path
_uploaded_batch_paths: set[str] = set()                                                                                               # Prevent duplicate SFTP uploads for the same finished batch file
_last_uploaded_local_path: Optional[str] = None                                                                                       # Full local path of the most recently uploaded CSV batch
_last_uploaded_remote_path: Optional[str] = None                                                                                      # Full remote SFTP destination of the most recently uploaded CSV batch
_last_upload_time: Optional[str] = None                                                                                               # Timestamp string for the most recent successful SFTP upload
_last_upload_error: str = ""                                                                                                          # Most recent SFTP upload error message for GUI display/debugging

# --------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------

def _get_env_int(name: str, default: int) -> int:
    raw_value = (os.getenv(name) or "").strip()                                                                                       # Read integer-like env value safely
    try:
        parsed_value = int(raw_value)
        return parsed_value if parsed_value > 0 else default                                                                          # Use default when value is invalid or non-positive
    except Exception:
        return default                                                                                                                # Use default when env value cannot be parsed as integer


def _get_csv_export_dir() -> Path:
    export_dir = (os.getenv("RQI_CSV_EXPORT_DIR") or "").strip()                                                                      # Root folder chosen by user for CSV exports
    if export_dir:
        return Path(export_dir)

    return PROJECT_ROOT / "RQI_CSV_Exports"                                                                                           # Fallback export directory when user has not configured one yet


def _get_csv_filename() -> str:
    csv_filename = (os.getenv("RQI_CSV_FILENAME") or "").strip()                                                                      # Fixed CSV file name stored inside each time-window subfolder
    if csv_filename:
        return csv_filename

    return DEFAULT_CSV_FILENAME                                                                                                       # Fallback fixed CSV file name


def _get_batch_minutes() -> int:
    return _get_env_int("RQI_CSV_BATCH_MINUTES", DEFAULT_BATCH_MINUTES)                                                               # Read upload window size from env with safe fallback


def _get_sftp_host() -> str:
    return (os.getenv("RQI_SFTP_HOST") or "").strip()                                                                                 # SFTP server host name


def _get_sftp_port() -> int:
    return _get_env_int("RQI_SFTP_PORT", 22)                                                                                          # SFTP server port


def _get_sftp_username() -> str:
    return (os.getenv("RQI_SFTP_USERNAME") or "").strip()                                                                             # SFTP username


def _get_sftp_password() -> str:
    return (os.getenv("RQI_SFTP_PASSWORD") or "").strip()                                                                             # SFTP password


def _get_sftp_remote_path() -> str:
    return (os.getenv("RQI_SFTP_REMOTE_PATH") or "").strip()                                                                          # Remote server folder path

def _get_sftp_file_name() -> str:
    configured_name = (os.getenv("RQI_SFTP_FILE_NAME") or "").strip()                                                                 # Base remote file name provided by user
    configured_type = (os.getenv("RQI_SFTP_FILE_TYPE") or "").strip().lstrip(".")                                                     # Remote file extension provided by user

    if configured_name and "." in configured_name:
        return configured_name                                                                                                        # Keep full remote file name when extension already included

    if configured_name and configured_type:
        return f"{configured_name}.{configured_type}"                                                                                 # Build remote file name from name + type

    if configured_name:
        return configured_name                                                                                                        # Use plain configured file name when no type is provided

    return _get_csv_filename()                                                                                                        # Fall back to local fixed CSV file name

def validate_sftp_settings() -> List[str]:
    missing_items: List[str] = []

    if not _get_sftp_host():
        missing_items.append("Host Name")                                                                                             # Required to open the SFTP connection

    if not _get_sftp_username():
        missing_items.append("Username")                                                                                              # Required to authenticate to SFTP

    if not _get_sftp_password():
        missing_items.append("Password")                                                                                              # Required to authenticate to SFTP

    return missing_items                                                                                                              # Return all missing SFTP fields so GUI can block upload and show one clean validation message

def _floor_datetime_to_interval(now: datetime, minutes: int) -> datetime:
    floored_minute = (now.minute // minutes) * minutes                                                                                # Round current time down to nearest interval boundary
    return now.replace(minute=floored_minute, second=0, microsecond=0)                                                                # Return clean batch window start time


def _resolve_batch_start(now: Optional[datetime] = None) -> datetime:
    current_time = now or datetime.now()                                                                                              # Use current local time unless caller provides an override
    batch_minutes = _get_batch_minutes()                                                                                              # Current upload window length

    with _batch_state_lock:
        if _batch_window_anchor is None:
            return _floor_datetime_to_interval(current_time, batch_minutes)                                                           # Default schedule uses normal clock-aligned batch windows

        elapsed_seconds = max(0.0, (current_time - _batch_window_anchor).total_seconds())                                             # Seconds since manual upload-window refresh anchor
        bucket_index = int(elapsed_seconds // (batch_minutes * 60))                                                                   # Count how many full windows have elapsed since the anchor
        return _batch_window_anchor + timedelta(minutes=bucket_index * batch_minutes)                                                 # Start time of the current anchored upload window


def _format_batch_folder_name(batch_start: datetime) -> str:
    return batch_start.strftime("%Y-%m-%d_%H-%M-%S")                                                                                  # Unique subfolder name for one upload window

def _get_current_batch_end(batch_start: datetime) -> datetime:
    batch_minutes = _get_batch_minutes()                                                                                              # Current upload window size used to determine when active batch ends
    return batch_start + timedelta(minutes=batch_minutes)                                                                             # End time of the active batch window

def get_current_batch_status() -> Dict[str, Any]:
    now = datetime.now()                                                                                                              # Current local time used for countdown and active-window status
    batch_start = _resolve_batch_start(now)                                                                                           # Active batch window start time based on current anchor and interval
    batch_end = _get_current_batch_end(batch_start)                                                                                   # Active batch window end time
    seconds_remaining = max(0, int((batch_end - now).total_seconds()))                                                                # Countdown in seconds until this CSV batch window rolls over

    latest_csv_path = get_latest_batch_csv_path()                                                                                     # Most recent local CSV batch file path for GUI display

    return {
        "batch_start": batch_start.strftime("%Y-%m-%d %H:%M:%S"),                                                                     # Readable active batch window start time
        "batch_end": batch_end.strftime("%Y-%m-%d %H:%M:%S"),                                                                         # Readable active batch window end time
        "seconds_remaining": seconds_remaining,                                                                                       # Countdown value for GUI timer display
        "current_csv_path": str(_current_batch_csv_path) if _current_batch_csv_path else "",                                          # Active CSV batch path if one exists
        "latest_csv_path": str(latest_csv_path) if latest_csv_path else "",                                                           # Latest CSV batch path even if current batch state was not initialized yet
        "last_uploaded_local_path": _last_uploaded_local_path or "",                                                                  # Most recent uploaded local CSV file
        "last_uploaded_remote_path": _last_uploaded_remote_path or "",                                                                # Most recent uploaded remote SFTP destination
        "last_upload_time": _last_upload_time or "",                                                                                  # Timestamp of last successful upload
        "last_upload_error": _last_upload_error or "",                                                                                # Most recent upload error text for GUI display
    }

def _build_batch_paths(batch_start: datetime) -> Tuple[Path, Path]:
    export_dir = _get_csv_export_dir()                                                                                                # Root export directory selected by user
    batch_dir = export_dir / _format_batch_folder_name(batch_start)                                                                   # Unique subfolder for the active upload window
    csv_path = batch_dir / _get_csv_filename()                                                                                        # Fixed CSV file name inside each batch folder
    return batch_dir, csv_path


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)                                                                                           # Create directory tree when it does not already exist


def _write_csv_header_if_needed(csv_path: Path, headers: List[str]) -> None:
    needs_header = not csv_path.exists() or csv_path.stat().st_size == 0                                                             # Header is required for brand-new or empty CSV files

    if needs_header:
        with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(headers)                                                                                                  # Write one fixed header row at the top of each CSV file


def _ensure_current_batch_files(headers: List[str], force_new_batch: bool = False) -> Path:
    global _current_batch_start, _current_batch_dir, _current_batch_csv_path

    current_batch_start = _resolve_batch_start()                                                                                      # Determine the active upload window start time
    current_batch_dir, current_batch_csv_path = _build_batch_paths(current_batch_start)                                              # Build the active subfolder path and CSV path

    with _batch_state_lock:
        batch_changed = force_new_batch or _current_batch_start != current_batch_start or _current_batch_csv_path != current_batch_csv_path

        if batch_changed:
            _current_batch_start = current_batch_start                                                                                # Save active batch start time in shared state
            _current_batch_dir = current_batch_dir                                                                                    # Save active batch folder path in shared state
            _current_batch_csv_path = current_batch_csv_path                                                                          # Save active CSV file path in shared state

        _ensure_directory(_current_batch_dir)                                                                                         # Ensure the batch subfolder exists
        _write_csv_header_if_needed(_current_batch_csv_path, headers)                                                                 # Ensure CSV file exists and has header row

        return _current_batch_csv_path


def append_row_to_current_csv(row: List[str], headers: List[str]) -> Path:
    csv_path = _ensure_current_batch_files(headers)                                                                                   # Ensure current time-window folder and CSV file exist before appending

    with _batch_state_lock:
        with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(row)                                                                                                      # Append one processed lead row to the active CSV batch

    logging.info("Appended row to CSV batch: %s", csv_path)
    return csv_path


def get_latest_batch_csv_path() -> Optional[Path]:
    with _batch_state_lock:
        if _current_batch_csv_path and _current_batch_csv_path.exists():
            return _current_batch_csv_path                                                                                            # Return current active CSV when it exists

    export_dir = _get_csv_export_dir()
    if not export_dir.exists():
        return None                                                                                                                   # No export folder means no CSV files exist yet

    matching_files = sorted(export_dir.glob(f"*/{_get_csv_filename()}"))                                                             # Search all batch subfolders for the fixed CSV file name
    if not matching_files:
        return None                                                                                                                   # No batch CSV files exist yet

    return matching_files[-1]                                                                                                         # Return newest matching CSV path


def _normalize_remote_path(remote_path: str) -> str:
    normalized = remote_path.replace("\\", "/").strip()                                                                               # Convert Windows-style separators to SFTP-friendly forward slashes
    if not normalized:
        return ""                                                                                                                     # Allow empty remote path when uploading into SFTP home directory
    return normalized.strip("/")                                                                                                      # Remove leading/trailing slashes for safe recursive path creation


def _ensure_sftp_directory(sftp, remote_path: str) -> None:
    normalized = _normalize_remote_path(remote_path)                                                                                  # Clean up remote path before creating it recursively
    if not normalized:
        return                                                                                                                        # No remote directory creation needed when uploading into home directory

    current_path = ""
    for part in normalized.split("/"):
        current_path = f"{current_path}/{part}" if current_path else part                                                             # Build path one segment at a time
        try:
            sftp.stat(current_path)
        except FileNotFoundError:
            sftp.mkdir(current_path)                                                                                                  # Create missing remote directory segment


def upload_csv_to_sftp(csv_path: Path, mark_uploaded: bool = True) -> str:
    global _last_uploaded_local_path, _last_uploaded_remote_path, _last_upload_time, _last_upload_error
    
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file does not exist: {csv_path}")                                                              # Stop immediately when local file path is invalid

    host = _get_sftp_host()
    username = _get_sftp_username()
    password = _get_sftp_password()
    remote_path = _get_sftp_remote_path()
    remote_file_name = _get_sftp_file_name()
    port = _get_sftp_port()

    if not host or not username or not password:
        raise RuntimeError("Missing SFTP configuration. Set host, username, password, and remote path in the GUI first.")             # Require minimum connection settings before attempting upload

    import paramiko                                                                                                                   # Imported here so local CSV testing still works even before paramiko is installed

    transport = None
    sftp = None

    try:
        transport = paramiko.Transport((host, port))
        transport.connect(username=username, password=password)                                                                       # Open authenticated SFTP connection
        sftp = paramiko.SFTPClient.from_transport(transport)

        _ensure_sftp_directory(sftp, remote_path)                                                                                     # Create remote folder tree when needed

        normalized_remote_path = _normalize_remote_path(remote_path)
        remote_file_full_path = f"{normalized_remote_path}/{remote_file_name}" if normalized_remote_path else remote_file_name        # Full destination path for the uploaded CSV file

        sftp.put(str(csv_path), remote_file_full_path)                                                                                # Upload local CSV file to configured SFTP destination
        logging.info("Uploaded CSV to SFTP: %s -> %s", csv_path, remote_file_full_path)
        dashboard_event(f"[SFTP] CSV uploaded to SFTP: {remote_file_full_path}")                                                             # Mini dashboard event for successful SFTP upload

        _last_uploaded_local_path = str(csv_path)                                                                                     # Save most recent successfully uploaded local CSV path for GUI display
        _last_uploaded_remote_path = remote_file_full_path                                                                            # Save most recent successful remote SFTP destination for GUI display
        _last_upload_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")                                                              # Save timestamp of most recent successful upload for GUI display
        _last_upload_error = ""                                                                                                       # Clear prior upload error because latest upload succeeded

        if mark_uploaded:
            _uploaded_batch_paths.add(str(csv_path))                                                                                  # Track already-uploaded batches so auto-upload does not repeat them

        return remote_file_full_path

    except Exception as e:
        _last_upload_error = str(e)                                                                                                   # Save upload error message for GUI display and debugging
        raise

    finally:
        if sftp is not None:
            sftp.close()                                                                                                              # Close SFTP client cleanly after upload attempt
        if transport is not None:
            transport.close()                                                                                                         # Close underlying SSH transport cleanly


def maybe_roll_batch_window(headers: List[str]) -> Optional[Path]:
    global _current_batch_start, _current_batch_dir, _current_batch_csv_path

    next_batch_start = _resolve_batch_start()                                                                                         # Determine which upload window should be active right now

    with _batch_state_lock:
        previous_batch_start = _current_batch_start                                                                                   # Snapshot current batch state before deciding whether to roll
        previous_csv_path = _current_batch_csv_path

    if previous_batch_start is None:
        return _ensure_current_batch_files(headers)                                                                                   # No batch exists yet, so create the first one immediately

    if next_batch_start == previous_batch_start:
        return previous_csv_path                                                                                                      # Same upload window is still active, so keep using current CSV file

    if previous_csv_path and previous_csv_path.exists() and str(previous_csv_path) not in _uploaded_batch_paths:
        try:
            upload_csv_to_sftp(previous_csv_path, mark_uploaded=True)                                                                 # Upload completed batch automatically when window rolls over
        except Exception:
            logging.exception("Automatic SFTP upload failed for completed CSV batch: %s", previous_csv_path)

    with _batch_state_lock:
        _current_batch_start = None                                                                                                   # Clear old batch state so next ensure call creates a fresh batch window
        _current_batch_dir = None
        _current_batch_csv_path = None

    return _ensure_current_batch_files(headers, force_new_batch=True)                                                                 # Create the new batch folder and CSV file immediately


def generate_csv_now(headers: Optional[List[str]] = None) -> Path:
    effective_headers = headers or list(DEFAULT_HEADERS)                                                                              # Use caller-provided headers or default lead export headers
    csv_path = _ensure_current_batch_files(effective_headers)                                                                         # Create current batch folder/CSV immediately when requested
    logging.info("Generated current CSV batch on demand: %s", csv_path)
    dashboard_event("[RQI] Manual CSV batch generated")                                                                                     # Mini dashboard event for manual CSV generation
    return csv_path


def upload_latest_csv_now() -> str:
    csv_path = get_latest_batch_csv_path()
    if not csv_path:
        raise RuntimeError("No CSV batch file exists yet. Generate a CSV first before uploading.")                                   # Manual upload requires at least one created CSV file

    remote_destination = upload_csv_to_sftp(csv_path, mark_uploaded=False)                                                           # Manual upload should always run, even if file was uploaded before
    logging.info("Manual SFTP upload completed for CSV batch: %s", csv_path)
    return remote_destination


def refresh_upload_window(headers: Optional[List[str]] = None) -> Path:
    global _batch_window_anchor, _current_batch_start, _current_batch_dir, _current_batch_csv_path

    effective_headers = headers or list(DEFAULT_HEADERS)                                                                              # Use caller-provided headers or default lead export headers

    with _batch_state_lock:
        previous_csv_path = _current_batch_csv_path                                                                                   # Capture current batch file before starting a new anchored window

    if previous_csv_path and previous_csv_path.exists() and str(previous_csv_path) not in _uploaded_batch_paths:
        try:
            upload_csv_to_sftp(previous_csv_path, mark_uploaded=True)                                                                 # Close and upload the current batch immediately before starting a new window anchor
        except Exception:
            logging.exception("Automatic SFTP upload failed while refreshing upload window: %s", previous_csv_path)

    with _batch_state_lock:
        _batch_window_anchor = datetime.now().replace(microsecond=0)                                                                  # Start a brand-new upload window from the exact time the user requested
        _current_batch_start = None                                                                                                   # Clear current batch state so a new folder and CSV are created immediately
        _current_batch_dir = None
        _current_batch_csv_path = None

    csv_path = _ensure_current_batch_files(effective_headers, force_new_batch=True)                                                   # Create a new upload-window folder and CSV immediately
    logging.info("Upload window refreshed. New batch starts now: %s", csv_path)
    dashboard_event("[RQI] Upload window refreshed and new CSV batch started")                                                        # Mini dashboard event for upload window refresh
    return csv_path


def strip_html_tags(html_content: str) -> str:
    """
    Remove HTML tags and convert HTML entities to plain text.
    """
    if not html_content:
        return ""

    text = re.sub(r"(?i)<br\s*/?>", "\n", html_content)
    text = re.sub(r"(?i)</(p|div|li|tr|td|th|table|ul|ol|h[1-6])>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    try:
        html_module = __import__("html")
        text = html_module.unescape(text)
    except Exception:
        pass
    return text


def _compact_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _env_key_for_label(prefix: str, label: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]+", "_", (label or "").strip().upper()).strip("_")
    return f"{prefix}{clean}" if clean else prefix.rstrip("_")


def _truncate_env_value(value: str, max_len: int = 1000) -> str:
    text = (value or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len]


def persist_email_snapshot_to_env(
    fields: Dict[str, str],
    appointment: Dict[str, str],
    subject: str,
    sender: str,
    received_dt: str,
    body_text: str,
) -> None:
    """Persist the latest extracted email payload into the writable .env file."""
    env_path = writable_env_file()

    payload: Dict[str, str] = {
        "LAST_EMAIL_SUBJECT": subject or "",
        "LAST_EMAIL_SENDER": sender or "",
        "LAST_EMAIL_RECEIVED_DATETIME": received_dt or "",
        "LAST_EMAIL_BODY": _truncate_env_value(strip_html_tags(body_text or "")),
    }

    for key, value in (fields or {}).items():
        payload[_env_key_for_label("LAST_EMAIL_FIELD_", key)] = value or ""

    for key, value in (appointment or {}).items():
        payload[_env_key_for_label("LAST_EMAIL_APPOINTMENT_", key)] = value or ""

    for key, value in payload.items():
        set_key(env_path, key, str(value or ""))
        os.environ[key] = str(value or "")


def extract_mmddyyyy_for_aha_date(appointment_when: str, fallback: str = "") -> str:
    """Best-effort date normalization to mm/dd/yyyy for AHA sheet date updates."""
    date_times = parse_appointment_when(appointment_when or "")
    if date_times and date_times[0]:
        try:
            return datetime.fromisoformat(date_times[0]).strftime("%m/%d/%Y")
        except Exception:
            pass

    fallback_value = (fallback or "").strip()
    if fallback_value:
        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(fallback_value, fmt).strftime("%m/%d/%Y")
            except ValueError:
                continue

    return datetime.now().strftime("%m/%d/%Y")


DEFAULT_HEADERS = [
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
]


def build_row_from_headers(fields: Dict[str, str], headers: List[str]) -> List[str]:
    """Build a sheet row by matching sheet headers to extracted field names."""
    normalized_fields = {_compact_label(k): (v or "") for k, v in (fields or {}).items()}
    row: List[str] = []
    for header in headers:
        row.append(normalized_fields.get(_compact_label(header), ""))
    return row


def _sanitize_cell_value(value: str, max_len: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()
    if len(text) > max_len:
        return text[:max_len]
    return text


def _sanitize_fields(fields: Dict[str, str]) -> Dict[str, str]:
    return {k: _sanitize_cell_value(v) for k, v in (fields or {}).items()}


def _looks_like_appointment_payload(fields: Dict[str, str], appointment: Dict[str, str]) -> bool:
    appointment_keys = (
        "for_name", "what", "when", "where", "price", "paid_online",
        "street_address_1", "street_address_2", "city", "state", "zip",
    )
    lead_keys = (
        "LocationID", "LocationName", "FirstName", "LastName",
        "JobCode", "JobName", "HireDate", "Status", "DateOfBirth",
    )

    appointment_signals = sum(1 for key in appointment_keys if (appointment or {}).get(key))
    lead_signals = sum(1 for key in lead_keys if (fields or {}).get(key))
    # True appointment payload: significant appointment data + minimal lead data. 
    # Email-only rows (0 appointment + 0 lead) should NOT be flagged as appointment.
    return appointment_signals >= 3 and lead_signals == 0


def should_append_lead_row(fields: Dict[str, str], appointment: Dict[str, str]) -> Tuple[bool, str]:
    # Intentionally no gate: map whatever was extracted into sheet columns.
    # Keep this helper for compatibility with existing call sites.
    return True, "ok"


def has_rqi_label_signature(text: str) -> bool:
    """Return True only when message text includes key RQI labels."""
    clean = strip_html_tags(text or "")
    if not clean:
        return False

    patterns = (
        r"\blocation\s*id\s*:",
        r"\bjob\s*code\s*:",
    )
    lowered = clean.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


def _is_valid_email(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", (value or "").strip(), re.IGNORECASE))


def _row_looks_corrupt(headers: List[str], row: List[str]) -> bool:
    if not row:
        return False

    header_index = {_compact_label(h): i for i, h in enumerate(headers or [])}
    email_idx = header_index.get("email", 6)
    user_idx = header_index.get("userid", 2)

    email_value = (row[email_idx] if email_idx < len(row) else "").strip()
    user_value = (row[user_idx] if user_idx < len(row) else "").strip()
    joined = " ".join((cell or "") for cell in row).lower()

    noisy_tokens = (
        "street address line 1",
        "street address line 2",
        "cancellation/rescheduling",
        "paid online",
        "price:",
        "location =",
        "address =",
    )
    has_noise = any(token in joined for token in noisy_tokens)

    invalid_email_blob = bool(email_value) and (not _is_valid_email(email_value)) and ("@" in email_value)
    invalid_user_blob = bool(user_value) and (not _is_valid_email(user_value)) and ("@" in user_value)

    oversized_cell = any(len((cell or "").strip()) > 160 for cell in row)

    return has_noise and (invalid_email_blob or invalid_user_blob or oversized_cell)


def cleanup_corrupt_rows(ws, headers: List[str]) -> int:
    """Delete obviously malformed rows left by earlier parser bugs."""
    if os.getenv("RQI_CLEAN_CORRUPT_ROWS", "1").strip() == "0":
        return 0

    try:
        all_values = ws.get_all_values()
    except Exception as e:
        logging.warning("Could not load worksheet rows for cleanup: %s", e)
        return 0

    if len(all_values) <= 1:
        return 0

    to_delete: List[int] = []
    for row_idx, row in enumerate(all_values[1:], start=2):
        if _row_looks_corrupt(headers, row):
            to_delete.append(row_idx)

    deleted = 0
    for row_idx in reversed(to_delete):
        try:
            ws.delete_rows(row_idx)
            deleted += 1
        except Exception as e:
            logging.warning("Failed deleting corrupt row %s: %s", row_idx, e)

    return deleted


def _label_to_pattern(label: str) -> str:
    """Create a regex-safe pattern for labels allowing flexible whitespace."""
    escaped = re.escape(label.strip())
    return escaped.replace(r"\ ", r"\s*")


def _extract_values_by_known_labels(
    text: str,
    label_aliases: Dict[str, List[str]],
    stop_labels: List[str] | None = None,
) -> Dict[str, str]:
    """Extract values by slicing text between known label markers."""
    if not text:
        return {key: "" for key in label_aliases}

    compact_to_key: Dict[str, str] = {}
    all_aliases: List[str] = []
    for key, aliases in label_aliases.items():
        compact_to_key[_compact_label(key)] = key
        for alias in aliases:
            compact_to_key[_compact_label(alias)] = key
            all_aliases.append(alias)

    stop_labels = stop_labels or []
    boundary_compact_labels = {
        _compact_label(alias)
        for alias in (all_aliases + stop_labels)
        if alias and _compact_label(alias)
    }

    if not all_aliases and not stop_labels:
        return {key: "" for key in label_aliases}

    # Longer aliases first avoids partial matches such as "Date" before "Date Of Birth".
    boundary_aliases = sorted(set(all_aliases + stop_labels), key=len, reverse=True)
    alias_pattern = "|".join(_label_to_pattern(alias) for alias in boundary_aliases)
    label_re = re.compile(rf"(?P<label>{alias_pattern})\s*:\s*", re.IGNORECASE)

    clean_text = strip_html_tags(text or "")
    clean_text = clean_text.replace("\xa0", " ").replace("\r", "\n")

    matches = list(label_re.finditer(clean_text))
    extracted: Dict[str, str] = {key: "" for key in label_aliases}
    for idx, match in enumerate(matches):
        raw_label = match.group("label")
        canonical_key = compact_to_key.get(_compact_label(raw_label), "")
        if not canonical_key or extracted.get(canonical_key):
            continue

        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(clean_text)
        value = re.sub(r"\s+", " ", clean_text[start:end]).strip(" \t\n,;")
        extracted[canonical_key] = value

    # Try multi-line format for any missing values (Label on one line, Value on next)
    lines = clean_text.split("\n")
    for i, line in enumerate(lines):
        line_clean = re.sub(r"\s+", " ", line).strip()
        if not line_clean or ":" in line_clean:
            continue
        
        # Check if this line matches any of our expected labels
        normalized = _compact_label(line_clean)
        for key in label_aliases:
            if extracted.get(key):  # Skip if already extracted
                continue
            # Check if this line matches any of the aliases for this key
            for alias in label_aliases[key]:
                if _compact_label(alias) == normalized:
                    # Get the next non-empty line as the value
                    for j in range(i + 1, len(lines)):
                        next_line = re.sub(r"\s+", " ", lines[j]).strip()
                        if not next_line:
                            continue

                        # Stop only when the next line is actually another known label,
                        # not when it simply contains a time like "10:00 AM".
                        if next_line.endswith(":"):
                            trailing_label = _compact_label(next_line[:-1])
                            if trailing_label in boundary_compact_labels:
                                break

                        if ":" in next_line:
                            candidate_label, candidate_value = next_line.split(":", 1)
                            if _compact_label(candidate_label) in boundary_compact_labels:
                                break
                            extracted[key] = next_line
                            break

                        extracted[key] = next_line
                        break
                    break

    # Try same-line format without colon (e.g., "for Kaleigh Henson" on one line)
    # This handles email format where label and value are on same line without colon separator
    for line in lines:
        line_clean = re.sub(r"\s+", " ", line).strip()
        if not line_clean or ":" in line_clean:
            continue
        
        # Try to match label at start of line followed by space and value
        for key, aliases in label_aliases.items():
            if extracted.get(key):  # Skip if already extracted
                continue
            for alias in aliases:
                # Create a pattern that matches the alias at the start of the line, followed by space(s) and captures the rest
                pattern = rf"^{re.escape(alias)}\s+(.+)$"
                match = re.match(pattern, line_clean, re.IGNORECASE)
                if match:
                    extracted[key] = match.group(1)
                    break

    return extracted


def _iter_labeled_lines(text: str):
    """Yield (normalized_label, value) pairs from label:value lines."""
    text = strip_html_tags(text or "")
    text = text.replace("\xa0", " ").replace("\r", "\n")

    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or ":" not in line:
            continue

        label, value = line.split(":", 1)
        label = label.strip()
        value = value.strip()
        if not label:
            continue

        yield _compact_label(label), value


def extract_labeled_field(text: str, *labels: str) -> str:
    """
    Extract a field value that follows a label pattern like "Label: Value".
    Also handles multi-line format where label is on one line and value on next.
    Also handles same-line format without colon (e.g., "for Kaleigh Henson").
    Accepts multiple label aliases such as "FirstName" and "First Name".
    """
    expected = {_compact_label(label) for label in labels if label}
    
    # Try colon format first (Label: Value)
    for normalized_label, value in _iter_labeled_lines(text):
        if normalized_label in expected and value:
            return value
    
    # Try multi-line format and same-line format without colon
    clean = strip_html_tags(text or "")
    clean = clean.replace("\xa0", " ").replace("\r", "\n")
    lines = clean.split("\n")
    
    for i, line in enumerate(lines):
        line_clean = re.sub(r"\s+", " ", line).strip()
        if not line_clean:
            continue
        
        # Try same-line format without colon (Label Value on same line)
        for label in labels:
            pattern = rf"^{re.escape(label)}\s+(.+)$"
            match = re.match(pattern, line_clean, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # Check if this line matches any of our expected labels (for multi-line format)
        normalized = _compact_label(line_clean)
        if normalized in expected:
            # Get the next non-empty line as the value
            for j in range(i + 1, len(lines)):
                next_line = re.sub(r"\s+", " ", lines[j]).strip()
                if next_line and ":" not in next_line:  # Don't grab lines with colons (different labels)
                    return next_line
                elif ":" in next_line:
                    # Hit another label with colon format, stop
                    break
    
    return ""


def extract_fields(text: str) -> dict:
    """
    Extract employee information from email body text using regex patterns.

    Returns:
        dict: Contains employee field keys used by the Google Sheet.
    """
    text = strip_html_tags(text or "")
    clean = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()

    fields = _extract_values_by_known_labels(
        text,
        {
            "LocationID": ["LocationID", "Location ID"],
            "LocationName": ["LocationName", "Location Name"],
            "UserID": ["UserID", "User ID"],
            "FirstName": ["FirstName", "First Name"],
            "MiddleName": ["MiddleName", "Middle Name"],
            "LastName": ["LastName", "Last Name"],
            "Email": ["Email", "Email Address"],
            "JobCode": ["JobCode", "Job Code"],
            "JobName": ["JobName", "Job Name"],
            "HireDate": ["HireDate", "Hire Date"],
            "Status": ["Status"],
            "DateOfBirth": ["DateOfBirth", "Date Of Birth", "Date of Birth"],
            "Gender": ["Gender"],
            "YearsOfExperience": ["YearsOfExperience", "Years Of Experience", "Years of Experience"],
            "ActiveDate": ["ActiveDate", "Active Date"],
            "InactiveDate": ["InactiveDate", "Inactive Date"],
            "Group": ["Group"],
        },
        stop_labels=[
            "For",
            "What",
            "When",
            "Where",
            "Phone",
            "Price",
            "Paid Online",
            "Street Address Line 1",
            "Street Address Line 2",
            "City",
            "State",
            "ZIP",
            "Cancellation/Rescheduling info",
        ],
    )

    # If FirstName and LastName aren't available, try to extract from "For" field
    if not (fields.get("FirstName") or "").strip() and not (fields.get("LastName") or "").strip():
        name_value = extract_labeled_field(text, "For")
        if name_value:
            parts = name_value.split(maxsplit=1)
            fields["FirstName"] = parts[0]
            if len(parts) > 1:
                fields["LastName"] = parts[1]

    # Normalize noisy captures like "user@email.com Price: $100.00 ..." to just the email token.
    email_in_field = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", fields.get("Email", ""), re.I)
    if email_in_field:
        fields["Email"] = email_in_field.group(0)
    else:
        m = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", clean, re.I)
        if m:
            fields["Email"] = m.group(0)

    # UserID should match Email address
    if fields["Email"]:
        fields["UserID"] = fields["Email"]

    return fields


def extract_appointment_fields(text: str) -> dict:
    """
    Extract appointment scheduling fields from email body.
    """
    appointment = {
        "for_name": "",
        "what": "",
        "when": "",
        "where": "",
        "phone": "",
        "price": "",
        "paid_online": "",
        "street_address_1": "",
        "street_address_2": "",
        "city": "",
        "state": "",
        "zip": ""
    }

    fields_by_label = _extract_values_by_known_labels(
        text,
        {
            "for": ["For"],
            "what": ["What"],
            "when": ["When"],
            "where": ["Where"],
            "phone": ["Phone"],
            "price": ["Price"],
            "paid_online": ["Paid Online"],
            "street_address_1": ["Street Address Line 1"],
            "street_address_2": ["Street Address Line 2"],
            "city": ["City"],
            "state": ["State"],
            "zip": ["ZIP"],
        },
        stop_labels=[
            "LocationID", "Location ID",
            "LocationName", "Location Name",
            "UserID", "User ID",
            "FirstName", "First Name",
            "MiddleName", "Middle Name",
            "LastName", "Last Name",
            "Email", "Email Address",
            "JobCode", "Job Code",
            "JobName", "Job Name",
            "HireDate", "Hire Date",
            "Status",
            "DateOfBirth", "Date Of Birth", "Date of Birth",
            "Gender",
            "YearsOfExperience", "Years Of Experience", "Years of Experience",
            "ActiveDate", "Active Date",
            "InactiveDate", "Inactive Date",
            "Group",
        ],
    )

    appointment["for_name"] = fields_by_label.get("for", "")
    appointment["what"] = fields_by_label.get("what", "")
    appointment["when"] = fields_by_label.get("when", "")
    appointment["where"] = fields_by_label.get("where", "")
    appointment["phone"] = fields_by_label.get("phone", "")
    appointment["price"] = fields_by_label.get("price", "")
    appointment["paid_online"] = fields_by_label.get("paid_online", "")
    appointment["street_address_1"] = fields_by_label.get("street_address_1", "")
    appointment["street_address_2"] = fields_by_label.get("street_address_2", "")
    appointment["city"] = fields_by_label.get("city", "")
    appointment["state"] = fields_by_label.get("state", "")
    appointment["zip"] = fields_by_label.get("zip", "")

    return appointment


def payment_completed(payment_text: str) -> bool:
    value = (payment_text or "").strip().lower()
    if not value:
        return False

    if value in {"no", "false", "unpaid", "pending", "failed", "declined", "0"}:
        return False

    if value in {"yes", "true", "paid", "completed", "success", "successful", "1"}:
        return True

    return any(token in value for token in ("paid", "complete", "success", "approved"))


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

        normalized = re.sub(r"\s+", " ", when_str.replace("\u2013", "-").replace("\u2014", "-").replace("\xa0", " ")).strip()
        normalized = re.sub(r"\b(noon)\b", "12:00 PM", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\b(midnight)\b", "12:00 AM", normalized, flags=re.IGNORECASE)

        duration_hours = 1
        duration_match = re.search(r"\((\d+)\s*(hour|hr)s?\)", normalized, re.IGNORECASE)
        if duration_match:
            duration_hours = int(duration_match.group(1))
        else:
            duration_match = re.search(r"\((\d+)\s*(minute|min)s?\)", normalized, re.IGNORECASE)
            if duration_match:
                duration_hours = int(duration_match.group(1)) / 60.0

        clean_when = re.sub(r"\([^)]+\)", "", normalized).strip(" ,")
        clean_when = re.sub(r",?\s*(PST|PDT|MST|MDT|CST|CDT|EST|EDT|PT|MT|CT|ET)$", "", clean_when, flags=re.IGNORECASE).strip()

        if ", " in clean_when:
            clean_when = clean_when.replace(", ", ", ")

        range_match = re.search(
            r"^(?P<date>.+?\d{4})\s+(?P<start>\d{1,2}(?::\d{2})?\s*[AP]M)\s*(?:-|to)\s*(?P<end>\d{1,2}(?::\d{2})?\s*[AP]M)$",
            clean_when,
            re.IGNORECASE,
        )

        date_formats = [
            "%A, %B %d, %Y",
            "%B %d, %Y",
            "%m/%d/%Y",
            "%m-%d-%Y",
        ]

        time_formats = ["%I:%M %p", "%I %p", "%I:%M%p", "%I%p"]

        def parse_date(date_str: str):
            for fmt in date_formats:
                try:
                    return datetime_cls.strptime(date_str.strip(), fmt).date()
                except ValueError:
                    continue
            return None

        def parse_time(time_str: str):
            cleaned_time = re.sub(r"\s+", " ", time_str.strip().upper())
            cleaned_time = re.sub(r"(?<=\d)(AM|PM)$", r" \1", cleaned_time)
            for fmt in time_formats:
                try:
                    return datetime_cls.strptime(cleaned_time, fmt).time()
                except ValueError:
                    continue
            return None

        if range_match:
            parsed_date = parse_date(range_match.group("date"))
            start_time = parse_time(range_match.group("start"))
            end_time_only = parse_time(range_match.group("end"))
            if parsed_date and start_time and end_time_only:
                parsed_start = datetime_cls.combine(parsed_date, start_time)
                parsed_end = datetime_cls.combine(parsed_date, end_time_only)
                if parsed_end <= parsed_start:
                    parsed_end += timedelta_cls(days=1)

                return (
                    parsed_start.strftime("%Y-%m-%dT%H:%M:%S"),
                    parsed_end.strftime("%Y-%m-%dT%H:%M:%S"),
                )

        formats = [
            "%A, %B %d, %Y %I:%M%p",
            "%A, %B %d, %Y %I:%M %p",
            "%A, %B %d, %Y %I%p",
            "%A, %B %d, %Y %I %p",
            "%B %d, %Y %I:%M%p",
            "%B %d, %Y %I:%M %p",
            "%B %d, %Y %I %p",
            "%m/%d/%Y %I:%M%p",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%Y %I %p",
            "%m-%d-%Y %I:%M%p",
            "%m-%d-%Y %I:%M %p",
            "%m-%d-%Y %I %p",
        ]

        parsed_start = None
        for fmt in formats:
            try:
                parsed_start = datetime_cls.strptime(clean_when.strip(), fmt)
                break
            except ValueError:
                continue

        if not parsed_start:
            logging.warning("Could not parse when string: raw=%r normalized=%r", when_str, clean_when)
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
    logging.debug("Logging initialized. Log file: %s", log_file)


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
    logging.debug("Successfully opened spreadsheet: %s", sh.title)

    try:
        ws = sh.worksheet(WORKSHEET_NAME)
        logging.debug("Found worksheet: %s", WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        logging.info("Creating new worksheet: %s", WORKSHEET_NAME)
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=20)

    if not ws.get_all_values():
        ws.append_row(
            DEFAULT_HEADERS,
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

        logging.debug("=== Available Mail Folders ===")
        for folder in folders:
            name = folder.get("displayName", "Unknown")
            unread = folder.get("unreadItemCount", 0)
            total = folder.get("totalItemCount", 0)
            folder_id = folder.get("id", "")
            logging.debug("  Folder %s: %s unread / %s total (ID: %s...)", name, unread, total, folder_id[:20])

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

    logging.debug("Total unread messages found (before sender filter): %d", len(msgs))

    def sender_addr(m: Dict[str, Any]) -> str:
        return (m.get("from", {}) or {}).get("emailAddress", {}).get("address", "") or ""

    for i, m in enumerate(msgs, 1):
        sender = sender_addr(m)
        subject = m.get("subject", "")
        logging.debug("  #%d From=%s | Subject=%s", i, sender, subject)

    if SENDER_EMAILS:
        msgs = [m for m in msgs if sender_addr(m).lower() in SENDER_EMAILS]
        logging.debug("Found %d unread message(s) from configured sender list", len(msgs))
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
        logging.debug(
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
        course_title = appointment["what"] or "Appointment"
        
        # Extract location name (before the address if it contains one)
        location = appointment["where"] or ""
        location_display = location.split(",")[0] if location else "See details"
        
        # Format title as "Name: Course (Location)"
        subject = f"{person_name}: {course_title} ({location_display})"

        # Build event body with formatted information
        body_content = ""
        
        # Add datetime display
        try:
            from datetime import datetime
            start_dt = datetime.fromisoformat(start_datetime)
            formatted_date = start_dt.strftime("%B %d, %Y %I:%M%p %Z").replace(" 0", " ")
            body_content += f"{formatted_date}\n"
        except:
            body_content += f"{appointment['when']}\n"
        
        body_content += "Calendar: CPR Lifeline\n"
        
        # Add name, phone, email
        if person_name:
            body_content += f"Name: {person_name}\n"
        if appointment["phone"]:
            body_content += f"Phone: {appointment['phone']}\n"
        if lead_email:
            body_content += f"Email: {lead_email}\n"
        
        # Add price information
        if appointment["price"]:
            body_content += f"Price: {appointment['price']}\n"
        if appointment["paid_online"]:
            body_content += f"Paid Online: {appointment['paid_online']}\n"
        
        # Add location section
        if location:
            body_content += f"\nLocation\n============\n{location}\n"
        
        # Add address section
        if appointment["street_address_1"]:
            body_content += f"\nAddress\n============\n"
            body_content += f"Street Address Line 1\n{appointment['street_address_1']}\n"
            if appointment["street_address_2"]:
                body_content += f"\nStreet Address Line 2\n{appointment['street_address_2']}\n"
            if appointment["city"]:
                body_content += f"\nCity\n{appointment['city']}\n"
            if appointment["state"]:
                body_content += f"\nState\n{appointment['state']}\n"
            if appointment["zip"]:
                body_content += f"\nZIP\n{appointment['zip']}\n"
        
        # Add cancellation/rescheduling info
        body_content += f"\nCancellation/Rescheduling info\n============\nI have read and agree to the terms above: yes\n"

        event_body = {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body_content
            },
            "start": {
                "dateTime": start_datetime,
                "timeZone": "America/Chicago"
            },
            "end": {
                "dateTime": end_datetime,
                "timeZone": "America/Chicago"
            },
            "location": {
                "displayName": location if location else "See details"
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


# --------------------------------------------------------------------
# Main Processing Logic
# --------------------------------------------------------------------

def main():
    """
    Main processing function - one complete cycle of checking and processing emails.
    """
    if PROVIDER != "outlook":
        raise RuntimeError("EMAIL_PROVIDER must be 'outlook' (this script is Outlook-only).")

    logging.debug("Starting Outlook(Graph) -> Sheets processing...")

    ws = get_worksheet()
    sheet_headers = ws.row_values(1)
    if not sheet_headers:
        sheet_headers = DEFAULT_HEADERS
    logging.debug("Using worksheet headers for mapping: %s", sheet_headers)

    removed_rows = cleanup_corrupt_rows(ws, sheet_headers)
    if removed_rows:
        logging.info("Removed %d previously corrupted row(s) from worksheet.", removed_rows)

    maybe_roll_batch_window(sheet_headers)                                                                                            # Ensure the current CSV batch exists before processing any unread emails

    token = authenticate()
    if not token:
        raise RuntimeError("Authentication failed: no access token returned.")

    try:
        user_url = f"{GRAPH_BASE}/me"
        user_data = graph_get(token, user_url, params={"$select": "mail,userPrincipalName,displayName"})
        user_email = user_data.get("mail") or user_data.get("userPrincipalName", "Unknown")
        user_name = user_data.get("displayName", "")
        logging.debug("Authenticated user: %s (%s)", user_name, user_email)
        print(f"✓ Logged in as: {user_email}")
    except Exception as e:
        logging.warning("Could not fetch user profile: %s", e)

    msgs = fetch_unread_messages(token, limit=50)
    logging.debug("Found %d unread messages", len(msgs))

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
        received_dt = msg.get("receivedDateTime") or ""

        body_text = get_message_body(token, msg_id) if msg_id else ""
        if not body_text:
            body_text = msg.get("bodyPreview") or ""

        fields = _sanitize_fields(extract_fields(body_text))
        logging.debug("Extracted fields from msg %s: %s", msg_id, fields)
        logging.debug("Raw email body (first 500 chars): %s", body_text[:500] if body_text else "(empty)")
        non_empty_fields = {k: v for k, v in fields.items() if v}
        logging.debug("Non-empty extracted fields: %s", non_empty_fields)
        appointment = extract_appointment_fields(body_text)

        # Process all emails including Acuity appointment emails for RQI sheet data extraction
        if not (fields.get("FirstName") or "").strip() and not (fields.get("LastName") or "").strip():
            appointment_name = (appointment.get("for_name") or "").strip()
            # If appointment extraction didn't get the name, try direct extraction from email text
            if not appointment_name:
                appointment_name = extract_labeled_field(body_text, "For")
            if appointment_name:
                parts = appointment_name.split(maxsplit=1)
                fields["FirstName"] = parts[0]
                if len(parts) > 1:
                    fields["LastName"] = parts[1]
                logging.debug("Applied name fallback from appointment field for msg %s: %s", msg_id, appointment_name)

        # LocationName always comes from appointment "What" text.
        # Example: "Online BLS ... (CPR Lifeline, Nashville, Film House)" -> "Film House"
        appointment_what = (appointment.get("what") or "").strip()
        # If appointment extraction didn't get What, try direct extraction from email text
        if not appointment_what:
            appointment_what = extract_labeled_field(body_text, "What")
        if appointment_what:
            location_candidate = ""
            group_course = ""

            # Derive course level from "What" text.
            # Example: "Online BLS with Skills Check (...)" -> "BLS"
            course_match = re.search(r"\bonline\s+(.+?)(?:\s+with\b|\s*\(|$)", appointment_what, re.IGNORECASE)
            if course_match:
                course_raw = course_match.group(1).strip()
                if course_raw:
                    # Keep concise, stable token for Group label (first token, usually BLS/ACLS/PALS)
                    group_course = re.sub(r"[^A-Za-z0-9+/\- ]", "", course_raw).strip().split()[0] if course_raw.split() else ""

            trailing_paren_match = re.search(r"\(([^()]*)\)\s*$", appointment_what)
            if trailing_paren_match:
                inside_parens = trailing_paren_match.group(1).strip()
                if "," in inside_parens:
                    segments = [seg.strip() for seg in inside_parens.split(",") if seg.strip()]
                    if segments:
                        location_candidate = segments[-1]

            if not location_candidate and "," in appointment_what:
                segments = [seg.strip() for seg in appointment_what.split(",") if seg.strip()]
                if segments:
                    location_candidate = segments[-1]

            if location_candidate:
                fields["LocationName"] = location_candidate
                logging.debug(
                    "Set LocationName from appointment What field for msg %s: %s",
                    msg_id,
                    location_candidate,
                )

            if group_course:
                fields["Group"] = f"HeartCode {group_course} Online - 2025"
                logging.debug(
                    "Set Group from appointment What field for msg %s: %s",
                    msg_id,
                    fields["Group"],
                )

        # Ensure Status is populated for rows appended from processed emails.
        if not (fields.get("Status") or "").strip():
            fields["Status"] = "Active"
            logging.debug("Set default Status=Active for msg %s", msg_id)

        try:
            persist_email_snapshot_to_env(
                fields=fields,
                appointment=appointment,
                subject=subject,
                sender=sender,
                received_dt=received_dt,
                body_text=body_text,
            )
        except Exception as e:
            logging.warning("Failed to persist extracted email snapshot to .env: %s", e)

        full_name = " ".join(filter(None, [
            fields.get("FirstName", ""),
            fields.get("MiddleName", ""),
            fields.get("LastName", "")
        ])).strip()

        row = build_row_from_headers(fields, sheet_headers)

        try:
            ws.append_row(row, value_input_option="RAW")
            logging.info("Appended row to sheet for message subject: %s", subject)
            dashboard_event(f"[RQI] added email '{subject}' to Google Sheets")                                                          # Mini dashboard event for successful RQI sheet write

            append_row_to_current_csv(row, sheet_headers)                                                                             # Append the same processed lead row into the active CSV batch for SFTP upload
            logging.info("Appended row to current CSV batch for message subject: %s", subject)
            dashboard_event(f"[RQI] added email '{subject}' to the current CSV batch")                                                  # Mini dashboard event for successful CSV batch write
        except Exception as e:
            logging.error("Failed to append row to sheet: %s", e)
            print(f"✗ Failed to append row / subject: {subject} / from: {sender}")
            continue

        trigger_email = (fields.get("Email") or "").strip()
        trigger_first_name = (fields.get("FirstName") or "").strip()
        trigger_last_name = (fields.get("LastName") or "").strip()
        if trigger_email or (trigger_first_name and trigger_last_name):
            registration_date = extract_mmddyyyy_for_aha_date(
                appointment_when=appointment.get("when", ""),
                fallback=fields.get("HireDate", ""),
            )
            try:
                updated = update_aha_registration_status(
                    trigger_email,
                    registration_date=registration_date,
                    first_name=trigger_first_name,
                    last_name=trigger_last_name,
                )
                if updated:
                    logging.info(
                        "Updated AHA registration row (No->Yes when applicable), date=%s for email=%s name=%s %s",
                        registration_date,
                        trigger_email,
                        trigger_first_name,
                        trigger_last_name,
                    )
                else:
                    logging.debug(
                        "AHA registration update found no matching No->Yes change for email=%s name=%s %s",
                        trigger_email,
                        trigger_first_name,
                        trigger_last_name,
                    )
            except Exception as e:
                logging.error(
                    "Failed to update AHA registration status for email=%s name=%s %s: %s",
                    trigger_email,
                    trigger_first_name,
                    trigger_last_name,
                    e,
                )
        else:
            logging.info("Skipping AHA registration update because no email/name could be extracted for subject: %s", subject)

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


# --------------------------------------------------------------------
# Run Forever
# --------------------------------------------------------------------

def run_forever(interval=INTERVAL, pause_all_event=None, pause_email_event=None):
    setup_logging()

    while True:
        if pause_all_event is not None:
            pause_all_event.wait()                                                                                                  # Block when user pauses all automation

        if pause_email_event is not None:
            pause_email_event.wait()                                                                                                # Block when user pauses only email_to_sheets

        try:
            maybe_roll_batch_window(DEFAULT_HEADERS)                                                                                # Auto-close/upload previous batch and create new batch when upload window rolls over
            main()
        except Exception:
            logging.exception("Email to sheets error")

        time.sleep(int(interval))                                                                                                   # Wait before next check cycle


# --------------------------------------------------------------------
# Script Entry Point
# --------------------------------------------------------------------

if __name__ == "__main__":
    setup_logging()

    try:
        generate_csv_now()                                                                                                          # Ensure a current CSV batch exists when running the file directly for testing
        main()
    except KeyboardInterrupt:
        logging.info("Stopped by user")
    except Exception:
        logging.exception("Error in main...")
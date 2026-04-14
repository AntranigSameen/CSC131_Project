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
from Proper_MS.utils import resource_path, update_aha_registration_status

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

    if not _get_sftp_remote_path():
        missing_items.append("Remote File Path")                                                                                      # Required so uploads know where to land on the SFTP server

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
    Accepts multiple label aliases such as "FirstName" and "First Name".
    """
    expected = {_compact_label(label) for label in labels if label}
    for normalized_label, value in _iter_labeled_lines(text):
        if normalized_label in expected and value:
            return value
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
    )

    if not fields["Email"]:
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

    logging.info("Starting Outlook(Graph) -> Sheets processing...")

    ws = get_worksheet()
    sheet_headers = ws.row_values(1)
    if not sheet_headers:
        sheet_headers = DEFAULT_HEADERS
    logging.info("Using worksheet headers for mapping: %s", sheet_headers)

    maybe_roll_batch_window(sheet_headers)                                                                                            # Ensure the current CSV batch exists before processing any unread emails

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
        appointment = extract_appointment_fields(body_text)

        full_name = " ".join(filter(None, [
            fields.get("FirstName", ""),
            fields.get("MiddleName", ""),
            fields.get("LastName", "")
        ])).strip()

        row = build_row_from_headers(fields, sheet_headers)

        try:
            ws.append_row(row, value_input_option="RAW")
            logging.info("Appended row to sheet for message subject: %s", subject)

            append_row_to_current_csv(row, sheet_headers)                                                                             # Append the same processed lead row into the active CSV batch for SFTP upload
            logging.info("Appended row to current CSV batch for message subject: %s", subject)
        except Exception as e:
            logging.error("Failed to append row to sheet: %s", e)
            print(f"✗ Failed to append row / subject: {subject} / from: {sender}")
            continue

        trigger_email = (fields.get("Email") or "").strip()
        if trigger_email and payment_completed(appointment.get("paid_online", "")):
            try:
                updated = update_aha_registration_status(trigger_email)
                if updated:
                    logging.info("Marked Acuity Registration as Yes for %s from the current payment email", trigger_email)
                else:
                    logging.info("No matching AHA row found for payment email %s", trigger_email)
            except Exception as e:
                logging.error("Failed to update AHA registration status for %s: %s", trigger_email, e)

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
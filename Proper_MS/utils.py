#==========
# IMPORTS
#==========

import sys
import os
import shutil
from dotenv import load_dotenv


_AHA_GS_CLIENT = None
_AHA_GS_SPREADSHEET = None
_AHA_GS_WORKSHEETS = {}

#=======
# LOGIC
#=======

# ===============
# Base Directory
# ===============

# Returns the base dir. Project Folder when through python and folder with EXE when running EXE
def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)

    return os.path.dirname(os.path.abspath(__file__))

# ================================
# Resource Path (for PyInstaller)
# ================================

# Get absolute path to resources. Works in development and packaged app
def resource_path(relative_path):
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = base_dir()

    return os.path.join(base_path, relative_path)

# ======================
# Logs Dir and ENV Load
# ======================

def logs_dir():
    path = os.path.join(base_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path

def env_file():
    external_env = os.path.join(base_dir(), ".env")
    if os.path.exists(external_env):
        return external_env
    return resource_path(".env")

def writable_env_file():
    return os.path.join(base_dir(), ".env")

def ensure_external_env():
    target = writable_env_file()
    if not os.path.exists(target):
        bundled = resource_path(".env")
        if os.path.exists(bundled):
            shutil.copyfile(bundled, target)
    return target

def load_settings():
    load_dotenv(env_file(), override=True)

    return {
        "CLIENT_ID": os.getenv("CLIENT_ID", ""),
        "TENANT_ID": os.getenv("TENANT_ID", ""),
        "AUTHORITY": os.getenv("AUTHORITY", ""),
        "SCOPES": os.getenv("SCOPES", ""),
        "CACHE_FILE": os.getenv("CACHE_FILE", ""),
        "AHA_URL": os.getenv("AHA_URL", ""),
        "AHA_USERNAME": os.getenv("AHA_USERNAME", ""),
        "AHA_PASSWORD": os.getenv("AHA_PASSWORD", ""),
        "EMAIL_PROVIDER": os.getenv("EMAIL_PROVIDER", ""),
        "SENDER_EMAIL": os.getenv("SENDER_EMAIL", ""),
        "SENDER_EMAIL_RQI": os.getenv("SENDER_EMAIL_RQI", ""),
        "KEYWORD_NAME": os.getenv("KEYWORD_NAME", ""),
        "INTERVAL": int(os.getenv("INTERVAL", "10")),
        "SPREADSHEET_ID": os.getenv("SPREADSHEET_ID", ""),
        "WORKSHEET_NAME": os.getenv("WORKSHEET_NAME", ""),
        "SERVICE_ACCOUNT_RQI_JSON": os.getenv("SERVICE_ACCOUNT_RQI_JSON", ""),
        "GOOGLE_SHEET_URL": os.getenv("GOOGLE_SHEET_URL", ""),
        "SERVICE_ACCOUNT_AHA_JSON": os.getenv("SERVICE_ACCOUNT_AHA_JSON", ""),
        "ORG_NAME": os.getenv("ORG_NAME", ""),
        "IS_HEADLESS": os.getenv("IS_HEADLESS", "1").lower() in ("1", "true", "yes"),
    }

# =========
# Log File
# =========

def log_file():
    return os.path.join(logs_dir(), "app.log")


def _get_aha_sheet_url():
    load_dotenv(env_file(), override=True)
    return os.getenv("GOOGLE_SHEET_URL", "").strip()


def _get_aha_service_account_path():
    load_dotenv(env_file(), override=True)
    return resource_path(os.getenv("SERVICE_ACCOUNT_AHA_JSON", "google_sheet_api_key.json"))


def _get_aha_registration_worksheet_name():
    load_dotenv(env_file(), override=True)
    return os.getenv("AHA_REGISTRATION_WORKSHEET", "").strip()


def _normalize_header(value):
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _find_aha_registration_worksheet(spreadsheet):
    configured_name = _get_aha_registration_worksheet_name()
    if configured_name:
        try:
            return spreadsheet.worksheet(configured_name)
        except Exception:
            pass

    for ws in spreadsheet.worksheets():
        try:
            headers = ws.row_values(1)
        except Exception:
            continue

        normalized = {_normalize_header(h) for h in headers}
        has_email = "email" in normalized
        has_acuity = "acuityregistration" in normalized
        has_aha = "aharegistration" in normalized

        if has_email and has_acuity and has_aha:
            return ws

    return spreadsheet.sheet1


def _get_aha_gsheet_worksheet(worksheet_name=None):
    global _AHA_GS_CLIENT, _AHA_GS_SPREADSHEET, _AHA_GS_WORKSHEETS

    try:
        import gspread
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError("Missing dependency 'gspread'. Install with: pip install gspread google-auth") from e

    sheet_url = _get_aha_sheet_url()
    if not sheet_url:
        raise RuntimeError("Missing GOOGLE_SHEET_URL for AHA registration updates.")

    key_path = _get_aha_service_account_path()

    if _AHA_GS_CLIENT is None:
        _AHA_GS_CLIENT = gspread.service_account(filename=key_path)

    if _AHA_GS_SPREADSHEET is None:
        _AHA_GS_SPREADSHEET = _AHA_GS_CLIENT.open_by_url(sheet_url)

    cache_key = (worksheet_name or "").strip() or "__aha_registration__"
    if cache_key in _AHA_GS_WORKSHEETS:
        return _AHA_GS_WORKSHEETS[cache_key]

    if worksheet_name:
        worksheet = _AHA_GS_SPREADSHEET.worksheet(worksheet_name)
    else:
        worksheet = _find_aha_registration_worksheet(_AHA_GS_SPREADSHEET)

    _AHA_GS_WORKSHEETS[cache_key] = worksheet
    return worksheet


def update_aha_registration_status(email, worksheet_name=None, reminder_sent_date=None):
    ws = _get_aha_gsheet_worksheet(worksheet_name)

    email_norm = (email or "").strip().lower()
    if not email_norm:
        return False

    headers = ws.row_values(1)
    header_index = {_normalize_header(h): idx + 1 for idx, h in enumerate(headers)}

    email_col = header_index.get("email", 1)
    acuity_col = header_index.get("acuityregistration", 7)
    aha_col = header_index.get("aharegistration", 8)
    reminder_col = header_index.get("reminderemail", 9)

    all_values = ws.get_all_values()
    for row_idx, row in enumerate(all_values, start=1):
        if row_idx == 1:
            continue

        if not row:
            continue

        row_email = (row[email_col - 1] if len(row) >= email_col else "").strip().lower()
        if row_email != email_norm:
            continue

        ws.update_cell(row_idx, acuity_col, "Yes", value_input_option="RAW")
        ws.update_cell(row_idx, aha_col, "Yes", value_input_option="RAW")
        ws.update_cell(row_idx, reminder_col, (reminder_sent_date or "").strip(), value_input_option="RAW")
        return True

    return False
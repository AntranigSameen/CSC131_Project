import os
import sys
import re
import logging
from dotenv import load_dotenv

"""Acuity-to-AHA registration sync helpers.

This module updates only the "Acuity Registration/Regristration" flag on the
AHA registration sheet after an RQI row is successfully appended.
"""

_AHA_GS_CLIENT = None
_AHA_GS_SPREADSHEET = None
_AHA_GS_WORKSHEETS = {}


def _base_dir():
    """Return runtime base directory for script and PyInstaller exe modes."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _resource_path(relative_path):
    """Resolve resource paths for both dev and bundled execution."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = _base_dir()
    return os.path.join(base_path, relative_path)


def _env_file():
    """Prefer external .env, then fall back to bundled .env."""
    external_env = os.path.join(_base_dir(), ".env")
    if os.path.exists(external_env):
        return external_env
    return _resource_path(".env")


def _get_aha_sheet_url():
    load_dotenv(_env_file(), override=True)
    return os.getenv("GOOGLE_SHEET_URL", "").strip()


def _get_aha_service_account_path():
    load_dotenv(_env_file(), override=True)
    return _resource_path(os.getenv("SERVICE_ACCOUNT_AHA_JSON", "google_sheet_api_key.json"))


def _get_aha_registration_worksheet_name():
    load_dotenv(_env_file(), override=True)
    return os.getenv("AHA_REGISTRATION_WORKSHEET", "").strip()


def _normalize_header(value):
    """Normalize headers to alphanumeric lowercase for tolerant matching."""
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _normalize_person_name(value):
    """Normalize person name spacing/casing while preserving word boundaries."""
    return " ".join(part for part in re.sub(r"\s+", " ", (value or "").strip()).lower().split(" ") if part)


def _normalize_name_token(value):
    """Normalize a single name token for strict equality comparisons."""
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _first_last_from_full_name(value):
    """Extract first and last token from a full-name cell."""
    parts = [p for p in _normalize_person_name(value).split(" ") if p]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    if len(parts) == 1:
        return parts[0], ""
    return "", ""


def _update_cell_raw(ws, row_idx, col_idx, value):
    """Write cell value as RAW while handling older gspread signatures."""
    try:
        ws.update_cell(row_idx, col_idx, value, value_input_option="RAW")
    except TypeError as e:
        if "value_input_option" not in str(e):
            raise
        ws.update_cell(row_idx, col_idx, value)


def _find_aha_registration_worksheet(spreadsheet):
    """Find target worksheet by configured name, then title/header heuristics."""
    configured_name = _get_aha_registration_worksheet_name()
    if configured_name:
        try:
            return spreadsheet.worksheet(configured_name)
        except Exception:
            pass

    # Prefer a worksheet whose title clearly indicates the AHA registration tab.
    for ws in spreadsheet.worksheets():
        title_norm = _normalize_header(ws.title)
        if "aha" in title_norm and "registration" in title_norm:
            return ws

    for ws in spreadsheet.worksheets():
        try:
            headers = ws.row_values(1)
        except Exception:
            continue

        normalized = {_normalize_header(h) for h in headers}
        has_email = any(k in normalized for k in ("email", "emailaddress"))
        has_acuity = any(k in normalized for k in ("acuityregistration", "acuityregristration"))
        has_aha = any(k in normalized for k in ("aharegistration", "aharegristration"))

        # Some sheets only track Acuity registration without a separate AHA registration column.
        if has_email and has_acuity:
            return ws

        # Secondary match for sheets that can be matched by name but don't have email header variants.
        if has_acuity and has_aha:
            return ws

    return spreadsheet.sheet1


def _get_aha_gsheet_worksheet(worksheet_name=None):
    """Return cached worksheet handle for the AHA registration sheet."""
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
        # Authenticate once and reuse client across update calls.
        _AHA_GS_CLIENT = gspread.service_account(filename=key_path)

    if _AHA_GS_SPREADSHEET is None:
        # Open spreadsheet once to avoid repeated API setup overhead.
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


def update_aha_registration_status(
    email,
    worksheet_name=None,
    reminder_sent_date=None,
    registration_date=None,
    first_name=None,
    last_name=None,
):
    """
    After RQI row append, find matching person in AHA sheet and flip only
    Acuity Registration/Regristration from No -> Yes.
    Matching is name-only (first + last). Email is intentionally ignored.
    """
    ws = _get_aha_gsheet_worksheet(worksheet_name)
    logging.info("AHA sync using worksheet: %s", ws.title)

    input_first = _normalize_name_token(first_name)
    input_last = _normalize_name_token(last_name)
    if not input_first or not input_last:
        logging.info("AHA sync skipped: missing required first/last input name")
        return False

    headers = ws.row_values(1)
    header_index = {_normalize_header(h): idx + 1 for idx, h in enumerate(headers)}

    def _first_present(*keys, default_idx):
        for key in keys:
            idx = header_index.get(key)
            if idx:
                return idx
        return default_idx

    acuity_col = _first_present("acuityregistration", "acuityregristration", default_idx=7)
    first_name_col = _first_present(
        "firstname",
        "first",
        "studentfirstname",
        "studentfirst",
        "fname",
        default_idx=0,
    )
    last_name_col = _first_present(
        "lastname",
        "last",
        "studentlastname",
        "studentlast",
        "lname",
        default_idx=0,
    )
    full_name_col = _first_present(
        "name",
        "fullname",
        "studentname",
        "nameofstudent",
        default_idx=0,
    )

    all_values = ws.get_all_values()
    for row_idx, row in enumerate(all_values, start=1):
        if row_idx == 1 or not row:
            continue

        row_first = (row[first_name_col - 1] if first_name_col > 0 and len(row) >= first_name_col else "").strip()
        row_last = (row[last_name_col - 1] if last_name_col > 0 and len(row) >= last_name_col else "").strip()
        row_full = (row[full_name_col - 1] if full_name_col > 0 and len(row) >= full_name_col else "").strip()

        if row_first or row_last:
            # Prefer explicit first/last columns when present.
            row_first_norm = _normalize_name_token(row_first)
            row_last_norm = _normalize_name_token(row_last)
        else:
            # Fall back to parsing first/last from a single full-name cell.
            full_first, full_last = _first_last_from_full_name(row_full)
            row_first_norm = _normalize_name_token(full_first)
            row_last_norm = _normalize_name_token(full_last)

        if not (row_first_norm == input_first and row_last_norm == input_last):
            continue

        current_acuity = (row[acuity_col - 1] if len(row) >= acuity_col else "").strip().lower()
        logging.info(
            "AHA sync matched row=%s name=%s %s current_acuity=%r",
            row_idx,
            input_first,
            input_last,
            current_acuity,
        )
        if current_acuity == "no":
            # Only this column is updated; all other columns are left untouched.
            _update_cell_raw(ws, row_idx, acuity_col, "Yes")
            logging.info("AHA sync flipped row %s Acuity Regristration from No to Yes", row_idx)
            return True

        logging.info("AHA sync found match but no flip needed on row %s", row_idx)
        return False

    logging.info("AHA sync found no matching row for name=%s %s", input_first, input_last)
    return False

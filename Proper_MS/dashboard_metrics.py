# ========
# IMPORTS
# ========

import json
import os
import re
from datetime import date
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from utils import base_dir, resource_path

# ==================
# DASHBOARD METRICS
# ==================

def _metrics_path():
    return Path(base_dir()) / "dashboard_metrics.json"                                                                                # Persistent dashboard metric file beside runtime files


def _today_key():
    return date.today().isoformat()                                                                                                   # YYYY-MM-DD key for daily dashboard counters


def _default_metrics():
    return {
        "date": _today_key(),
        "registered_today": 0,
        "paid_today": 0,
    }                                                                                                                                 # Safe default counter state


def load_dashboard_metrics():
    path = _metrics_path()

    if not path.exists():
        metrics = _default_metrics()
        save_dashboard_metrics(metrics)
        return metrics

    try:
        metrics = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        metrics = _default_metrics()
        save_dashboard_metrics(metrics)
        return metrics

    if metrics.get("date") != _today_key():
        metrics = _default_metrics()                                                                                                  # Reset daily counters automatically on a new day
        save_dashboard_metrics(metrics)

    return metrics


def save_dashboard_metrics(metrics):
    path = _metrics_path()
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")                                                                  # Save readable JSON metrics file


def increment_registered_today(amount=1):
    metrics = load_dashboard_metrics()
    metrics["registered_today"] = int(metrics.get("registered_today", 0)) + amount
    save_dashboard_metrics(metrics)


def increment_paid_today(amount=1):
    metrics = load_dashboard_metrics()
    metrics["paid_today"] = int(metrics.get("paid_today", 0)) + amount
    save_dashboard_metrics(metrics)

def _extract_google_sheet_id(sheet_url_or_id):
    value = (sheet_url_or_id or "").strip()

    if not value:
        return ""

    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
    if match:
        return match.group(1)

    return value                                                                                                                      # Allow raw spreadsheet ID too


def _count_non_header_rows(sheet_id, service_account_json, worksheet_name=None):
    if not sheet_id or not service_account_json:
        return 0                                                                                                                      # Missing config should not crash dashboard

    try:
        json_path = resource_path(Path(service_account_json).name)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(json_path, scopes=scopes)
        client = gspread.authorize(creds)

        spreadsheet = client.open_by_key(sheet_id)

        if worksheet_name:
            worksheet = spreadsheet.worksheet(worksheet_name)
        else:
            worksheet = spreadsheet.get_worksheet(0)                                                                                  # AHA uses first worksheet safely

        rows = worksheet.get_all_values()

        if len(rows) <= 1:
            return 0                                                                                                                  # Header-only or empty sheet

        return len(rows) - 1                                                                                                          # Exclude header row

    except Exception:
        return 0                                                                                                                      # Dashboard should never crash if Sheets lookup fails


def get_registered_total():
    aha_sheet_id = _extract_google_sheet_id(os.getenv("GOOGLE_SHEET_URL", ""))                                                        # AHA sheet URL or ID from GUI settings
    aha_service_json = os.getenv("SERVICE_ACCOUNT_AHA_JSON", "service_account.json")                                                  # AHA service account file
    return _count_non_header_rows(aha_sheet_id, aha_service_json)                                                                     # Count AHA sheet rows excluding header


def get_paid_total():
    rqi_sheet_id = os.getenv("SPREADSHEET_ID", "")                                                                                    # RQI Google Sheet ID from GUI settings
    rqi_worksheet = os.getenv("WORKSHEET_NAME", "Leads")                                                                              # RQI worksheet tab
    rqi_service_json = os.getenv("SERVICE_ACCOUNT_RQI_JSON", "service_account.json")                                                  # RQI service account file
    return _count_non_header_rows(rqi_sheet_id, rqi_service_json, rqi_worksheet)                                                      # Count RQI sheet rows excluding header

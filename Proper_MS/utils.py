#==========
# IMPORTS
#==========

import sys
import os
import shutil
from dotenv import load_dotenv

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
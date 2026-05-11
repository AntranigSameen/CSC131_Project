#==========
# IMPORTS
#==========

import logging
import msal
import os
from dotenv import load_dotenv
from utils import app_data_dir

# ===========================
# Load environment variables
# ===========================

#load_dotenv()

CLIENT_ID = (os.getenv("CLIENT_ID") or "").strip()                                                                                    # Azure app registration client ID
TENANT_ID = (os.getenv("TENANT_ID") or "").strip()                                                                                    # Microsoft Entra tenant ID for organization account
AUTHORITY = (os.getenv("AUTHORITY") or "").strip()                                                                                    # Microsoft login authority URL
SCOPES_RAW = (os.getenv("SCOPES") or "").strip()                                                                                      # Comma-separated Microsoft Graph delegated scopes
CACHE_FILE = os.path.expandvars(
    (os.getenv("CACHE_FILE") or os.path.join(app_data_dir(), "token_cache.json")).strip()
)                                                                                                                                     # MSAL token cache file

#====================================
# Check loaded environment variables
#====================================

if not CLIENT_ID:
    raise ValueError("CLIENT_ID not found in environment variables")

if not AUTHORITY and TENANT_ID:
    AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"                                                                      # Build organization authority from tenant ID when AUTHORITY is not explicitly set

if not SCOPES_RAW:
    raise ValueError("SCOPES not found in environment variables")

SCOPES = [scope.strip() for scope in SCOPES_RAW.split(",")]

#=================
# Authentication
#=================

def authenticate():
    # Load token cache from file if it exists
    cache = msal.SerializableTokenCache()
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cache.deserialize(f.read())

    app = msal.PublicClientApplication(client_id=CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    accounts = app.get_accounts()
    if accounts:
        # Attempt silent token acquisition
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
    else:
        result = None

    if not result:
        logging.info("Launching Microsoft Login Window...")                                                                           # Log the launch for outlook login

        result = app.acquire_token_interactive(scopes=SCOPES)

    if cache.has_state_changed:
        cache_dir = os.path.dirname(CACHE_FILE)

        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)                                                                                     # Ensure token cache folder exists before writing

        with open(CACHE_FILE, "w") as f:
            f.write(cache.serialize())
    
    if "access_token" in result:
        logging.debug("Outlook Authentication successful.")                                                                           # Log successful authentication
        return result["access_token"]

    logging.error("Authentication failed: %s", result)                                                                                # Log the error description for debugging
    return None
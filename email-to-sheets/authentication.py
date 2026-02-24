#==========
# IMPORTS
#==========

import logging
import msal
import os
from dotenv import load_dotenv

# ===========================
# Load environment variables
# ===========================

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
AUTHORITY = os.getenv("AUTHORITY", "https://login.microsoftonline.com/consumers")
SCOPES_RAW = os.getenv("SCOPES")
CACHE_FILE = os.getenv("CACHE_FILE", "token_cache.json")                 # Cache file for MSAL tokens (makes it a single sign-on experience)

#====================================
# Check loaded environment variables
#====================================

if not CLIENT_ID:
    raise ValueError("CLIENT_ID not found in environment variables")

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
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            print("Failed to create device flow:", flow)
            logging.info("Failed to create device flow. Check your client ID and authority.")       # Log the failure reason for debugging
            raise Exception("Failed to create device flow.")
        print(flow["message"])
        logging.info("Device flow initiated. User must authenticate.")                              # Log that the device flow has started
        result = app.acquire_token_by_device_flow(flow)

    if cache.has_state_changed:
        with open(CACHE_FILE, "w") as f:
            f.write(cache.serialize())
    
    if result and "access_token" in result:
        logging.info("Authentication successful.")                                                  # Log successful authentication
        return result["access_token"]

    logging.error("Authentication failed: %s", result)                     # Log the error description for debugging
    return None
    
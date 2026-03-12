#==========
# IMPORTS
#==========

import os
import requests
import logging
from dotenv import load_dotenv

# ===========================
# Load environment variables
# ===========================

#load_dotenv()
SENDER_EMAIL = os.getenv("SENDER_EMAIL")

if not SENDER_EMAIL:
    logging.error("SENDER_EMAIL not found in environment variables")       # Log the missing variable for debugging
    raise ValueError("SENDER_EMAIL not found in environment variables")

#===========================
# Pulling email data
#===========================

def get_from_email(access_token, keyword):
    headers = { "Authorization": f"Bearer {access_token}" }


    url = f"https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages" f"?$filter=from/emailAddress/address eq '{SENDER_EMAIL}' and isRead eq false"     # Filter for unread emails from the specified sender

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        emails = response.json().get("value", [])

        # Sort emails by receivedDateTime (newest first)
        emails_sorted = sorted(emails, key=lambda x: x.get("receivedDateTime", ""), reverse=True)

        return emails_sorted

    else:
        logging.error("Failed to fetch %s: %s", keyword, response.text)       # Log the error response for debugging
        print(f"Failed to fetch {keyword}.")
        return []

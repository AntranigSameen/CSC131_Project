#=========
# IMPORTS
#=========

import logging
import requests

#=====================
# Mark Emails as Read
#=====================

def mark_emails_seen(token, emails):
    headers = { "Authorization": f"Bearer {token}", "Content-Type": "application/json" }

    for email in emails:
        try:
            email_id =email.get("id")
            if not email_id:
                logging.info("No new emails found")                                                         # Log if there are no new emails to mark as read
                continue

            url = f"https://graph.microsoft.com/v1.0/me/messages/{email_id}"
            body = { "isRead": True }

            response = requests.patch(url, json=body, headers=headers)
            if response.status_code == 200:
                logging.info("Marked email as read: Subject=%s", email.get("subject", "No Subject"))        # Log successful marking of email as read
            else:
                logging.error("Failed to mark email as seen: Subject='%s', Status=%s, Response=%s", email.get("subject", "No Subject"), response.status_code, response.text)       # Log failure reason for debugging
        
        except Exception as e:
            logging.error("Error marking email as seen: %s", e)                                             # Log any exceptions that occur during the API call
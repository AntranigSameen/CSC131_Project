#==========
# IMPORTS
#==========

import os
import time
import logging
import re

from authentication import authenticate
from name_date_pull import get_from_email
from parser import parse_name, parse_date
from dotenv import load_dotenv

# ===========================
# Load environment variables
# ===========================

load_dotenv()
KEYWORD_NAME = os.getenv("KEYWORD_NAME")
INTERVAL = int(os.getenv("INTERVAL", "10"))       # Default to 10 seconds if not set

# =============================
# Set up Logging with Log File
# =============================

logging.basicConfig(filename="completeApp.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==========
# Date Regex
# ==========

DATE_REGEX = re.compile(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b')   # Matches DD/MM/YYYY, MM/DD/YYYY, DD/MM/YY, MM/DD/YY

# ==========
# MAIN LOOP
# ==========

def main():
    logging.info("Starting email data pull service...")                                             # Log the start of the service

    # Authenticate and get access token ONE TIME
    token = authenticate()
    if not token:
        logging.error("Exiting application due to authentication failure. No Access Token.")       # Log the exit reason for debugging
        return
    logging.info("Authentication successful. Token acquired.")

    while True:
        logging.info("Pulling email data...")                                                      # Log each data pull attempt

        try:
            # Pull names from emails
            emails = get_from_email(token, KEYWORD_NAME)
            name_parsed = parse_name(emails, KEYWORD_NAME)
            if name_parsed:
                for entry in name_parsed:
                    logging.info("Extracted Name - Subject: %s, Value: %s", entry["Subject"], entry["Value"])
            else:
                logging.info("No names found in this cycle.")

            # Pull dates from emails
            emails_all = get_from_email(token, "")        # Fetch all emails
            date_parsed = parse_date(emails_all)

            if date_parsed:
                for entry in date_parsed:
                    logging.info("Extracted Date - Subject: %s, Value: %s", entry["Subject"], entry["Value"])
            else:
                logging.info("No dates found in this cycle.")

        except Exception as e:
            logging.exception("Error during email pull/parsing cycle: %s", e)

        logging.info("Data pull complete. Waiting %d seconds for next cycle...", INTERVAL)                      # Log the completion of the cycle
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

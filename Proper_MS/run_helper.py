#==========
# IMPORTS
#==========
import os
import logging

from name_date_pull import get_from_email
from read_emails import mark_emails_seen
from store_data import store_data
from parser import parse_name, parse_date
from dotenv import load_dotenv

# ===========================
# Load environment variables
# ===========================

load_dotenv()
KEYWORD_NAME = os.getenv("KEYWORD_NAME")

# =================
# RUNS MAIN HELPER
# =================

# Pulls Emails, Filters Unread Emails, Parses Name and Date, Logs, Stores in a txt

def run_cycle(token):
            emails = get_from_email(token, KEYWORD_NAME)                                                         # Pull emails and filter for new/unread ones

            ret_name = None
            ret_date = None

            if not emails:
                logging.info("No new emails found in this cycle.")                                               # Log if there are no new emails to process

            else:
                name_parsed = parse_name(emails, KEYWORD_NAME)                                                   # Parse names from emails
                if name_parsed:
                    for entry in name_parsed:
                        logging.info("Extracted Name - Subject: %s, Value: %s", entry["Subject"], entry["Name"])
                else:
                    logging.info("No names found in this cycle.")

                date_parsed = parse_date(emails)                                                                 # Parse dates from emails
                if date_parsed:
                    for entry in date_parsed:
                        logging.info("Extracted Date - Subject: %s, Value: %s", entry["Subject"], entry["Date"])
                else:
                    logging.info("No dates found in this cycle.")

                if name_parsed and date_parsed:
                    store_data(name_parsed, date_parsed)                                                         # Store extracted data in text file
                    ret_name = name_parsed[0]["Name"]                                                            # Get the first name value for return
                    ret_date = date_parsed[0]["Date"]                                                            # Get the first date value for return
                    logging.info("Data stored successfully for %d entries.", len(name_parsed))                   # Log the number of entries stored

                # Mark processed emails as read
                mark_emails_seen(token, emails)

                emails.clear()                                                                                   # Clear the list of processed emails to avoid reprocessing in the next cycle
                if ret_name and ret_date:
                     return f"{ret_name},{ret_date}"                                                             # Return parsed data for Sherri separated by a comma
                else:
                    return None                                                                                  # Return None if parsing was unsuccessful
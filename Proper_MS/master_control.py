#==========
# IMPORTS
#==========

import os
import time
import logging

from setup_login import aha_login_check
from outlook_authentication import authenticate
from run_helper import run_cycle
from run_automation import run_demo
from dotenv import load_dotenv

load_dotenv()

INTERVAL = int(os.getenv("INTERVAL", "10"))                                                 # Default to 10 seconds if not set

# =============================
# Set up Logging with Log File
# =============================

logging.basicConfig(filename="app.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

#===============
# THE BEGINNING
#===============

def main():
    logging.info("Starting the Master Control Script...")                                   # Log the start of the master control script

    aha_login_check()                                                                       # check if the user has logged in to AHA, if not, open a browser window for them to log in
    logging.info("AHA login check complete.")                                               # Log the completion of AHA login check

    token = authenticate()                                                                  # authenticate with Outlook and return the authentication token
    if not token:
        logging.error("Authentication failure. No Access Token.")                           # Failed to get token. Log the exit reason for debugging
        return
    logging.info("Authentication successful. Outlook Token acquired.")                      # Log successful Outlook authentication

    # Run the main cycle of parsing emails and automation. log Errors.
    while True:
        result = None
        try:
            result = run_cycle(token)                                                       # Run the email parsing
        except Exception as e:
            logging.exception("Error during email parsing cycle: %s", e)                    # Log any exceptions that occur during the email parsing cycle

        if result:
            logging.info("Email parsed successfully. Result: %s", result)                   # Log the successful completion of the email parsing cycle with the result
            try:
                run_demo(headless=False)                                                    # Run the main automation loop
            except Exception as e:
                logging.exception("Error during automation cycle: %s", e)                   # Log any exceptions that occur during the automation cycle
        
        if not result:
            logging.info("No new emails to process in this cycle.")                         # Log if there were no new emails to process
    
        logging.info("Cycle complete. Waiting %d seconds for next cycle...", INTERVAL)      # Log the completion of the cycle and the wait time until the next cycle
        time.sleep(INTERVAL)                                                                # Wait for the specified interval before starting the next cycle


#================
# ENTRY POINT
#================

if __name__ == "__main__":
    main()
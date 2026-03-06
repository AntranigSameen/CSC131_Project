#==========
# IMPORTS
#==========

import os
import time
import logging

from outlook_authentication import authenticate
from run_helper import run_cycle
from dotenv import load_dotenv

# ===========================
# Load environment variables
# ===========================

load_dotenv()
KEYWORD_NAME = os.getenv("KEYWORD_NAME")
INTERVAL = int(os.getenv("INTERVAL", "10"))                                                                     # Default to 10 seconds if not set

# =============================
# Set up Logging with Log File
# =============================

logging.basicConfig(filename="Log Name Date Initial.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==========
# MAIN LOOP
# ==========

def main():
    logging.info("Starting email data pull service...")                                                         # Log the start of the service

    # Authenticate and get access token ONE TIME
    token = authenticate()
    if not token:
        logging.error("Exiting application due to authentication failure. No Access Token.")                    # Log the exit reason for debugging
        return
    logging.info("Authentication successful. Token acquired.")

    while True:
        logging.info("Pulling email data...")                                                                   # Log each data pull attempt
        print("running...")                                                                                     # Indicate the cycle is running in the console TESTING

        try:
            run_cycle(token)                                                                                    # Run the main cycle of pulling, parsing, and storing data

        except Exception as e:
            logging.exception("Error during email pull/parsing cycle: %s", e)

        logging.info("Data pull complete. Waiting %d seconds for next cycle...", INTERVAL)                      # Log the completion of the cycle
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

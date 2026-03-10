#==========
# IMPORTS
#==========

import os
import time
import logging
import threading

from pystray import Icon, MenuItem as item, Menu
from PIL import Image

from gui import open_settings

from setup_login import aha_login_check
from outlook_authentication import authenticate
from run_helper import run_cycle
from run_automation import run_demo
from utils import resource_path

from dotenv import load_dotenv

#============================
# Load Environment Variables
#============================

load_dotenv()

INTERVAL = int(os.getenv("INTERVAL", "10"))                                                 # Default to 10 seconds if not set

# =============================
# Set up Logging with Log File
# =============================

os.makedirs("logs", exist_ok=True)
logging.basicConfig(filename="logs/app.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

#===================
# AUTOMATION LOGIC
#===================

def automation_loop():
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
        load_dotenv(override=True)                                                          # Reload env variables in case user edited them
        interval = int(os.getenv("INTERVAL", "10"))

        result = None
        try:
            result = run_cycle(token)                                                       # Run the email parsing
        except Exception as e:
            logging.exception("Error during email parsing cycle: %s", e)                    # Log any exceptions that occur during the email parsing cycle

        if result and str(result).strip():
            logging.info("Email parsed successfully. Result: %s", result)                   # Log the successful completion of the email parsing cycle with the result
            try:
                name, date = result.split(",")
                run_demo(name=name, date=date, headless=False)                              # Run the main automation loop
            except Exception as e:
                logging.exception("Error during automation cycle: %s", e)                   # Log any exceptions that occur during the automation cycle
        
        else:
            logging.info("No new emails to process in this cycle.")                         # Log if there were no new emails to process
    
        logging.info("Cycle complete. Waiting %d seconds for next cycle...", interval)      # Log the completion of the cycle and the wait time until the next cycle
        time.sleep(interval)                                                                # Wait for the specified interval before starting the next cycle

#===========
# TRAY ICON
#===========

# Stop the tray icon
def on_quit(icon, item):
    icon.stop()
    os._exit(0)

# Start GUI
def on_settings(icon, item):
    threading.Thread(target=open_settings, daemon=True).start()

# Start the tray icon
def start_tray():
    image = Image.open(resource_path("icon.png")).convert("RGBA").resize((64, 64))
    menu = Menu(item("Settings", on_settings), item("Quit", on_quit))
    icon = Icon("Automation", image, "Complete Automation", menu)
    icon.run_detached()

#================
# ENTRY POINT
#================

if __name__ == "__main__":
    logging.info("Starting Tray App in daemon thread")
    threading.Thread(target=start_tray, daemon=True).start()                                     # Start tray in a daemon thread so it does not block automation

    logging.info("Starting Automation Loop in main thread")
    automation_loop()                                                                            # Run automation in main thread to avoid browser windows closing immediately
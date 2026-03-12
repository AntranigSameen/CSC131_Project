#==========
# IMPORTS
#==========

import os
import sys
import time
import logging
import threading
import subprocess

from pystray import Icon, MenuItem as item, Menu
from PIL import Image

from gui import open_settings

from setup_login import aha_login_check
from outlook_authentication import authenticate
from run_helper import run_cycle
from run_automation import run_demo
from utils import resource_path, log_file, base_dir

from dotenv import load_dotenv

#============================
# Load Environment Variables
#============================

load_dotenv(resource_path(".env"))

INTERVAL = int(os.getenv("INTERVAL", "10"))                                                 # Default to 10 seconds if not set
#IS_HEADLESS = bool(os.getenv("IS_HEADLESS", False))

# =============================
# Set up Logging with Log File
# =============================

logging.basicConfig(filename=log_file(), level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# =======================================
# Set up Global Variable and Pause Event
# =======================================

automation_paused = False
pause_event = threading.Event()
pause_event.set()                                                                           # start unpaused

#=============
# STATUS READ
#=============

# Stores automation status so GUI can read
def set_status(status):
    status_file = os.path.join(base_dir, "automation_status.txt")

    with open(status_file, "w") as f:
        f.write(status)

#===================
# AUTOMATION SCRIPT
#===================

def automation_loop():
    logging.info("Starting the Automation Script...")                                       # Log the start of the master control script
    set_status("RUNNING")                                                                   # Set status for program

    aha_login_check()                                                                       # check if the user has logged in to AHA, if not, open a browser window for them to log in
    logging.info("AHA login check complete.")                                               # Log the completion of AHA login check

    token = authenticate()                                                                  # authenticate with Outlook and return the authentication token
    if not token:
        logging.error("Authentication failure. No Access Token.")                           # Failed to get token. Log the exit reason for debugging
        return
    logging.info("Authentication successful. Outlook Token acquired.")                      # Log successful Outlook authentication

    # Run the main cycle of parsing emails and automation. log Errors.
    while True:
        pause_event.wait()                                                                  # Pauses here when automation paused

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
    logging.info("Exiting Application through System Tray Menu")
    icon.stop()
    os._exit(0)

# Start GUI into settings
def on_settings(icon, item):
    logging.info("Settings GUI Opened through System Tray Menu")
    threading.Thread(target=open_settings, daemon=True).start()

# Opens logs for the app
def on_open_logs(icon, item):
    log_path = os.path.join(base_dir(), "logs", "app.log")

    if os.path.exists(log_path):
        subprocess.Popen(["notepad", log_path])
    else:
        logging.error("Log file not found: %s", log_path)

# Pause/Resume Function for Automation
def on_pause_resume(icon, item):
    global automation_paused

    if automation_paused:
        automation_paused = False
        pause_event.set()
        logging.info("Automation Resumed")
        icon.notify("Automation Resumed")
        set_status("RUNNING")                                                                   # Set status for program
    else:
        automation_paused = True
        pause_event.clear()
        logging.info("Automation Paused")
        icon.notify("Automation Paused")
        set_status("PAUSED")                                                                    # Set status for program

# Tracks what to show to user based on automation state
def pause_menu_text(item):
    return "Resume Automation" if automation_paused else "Pause Automation"

# Start the tray icon
def start_tray():
    image = Image.open(resource_path("icon.png")).convert("RGBA").resize((64, 64))
    menu = Menu(item("Settings", on_settings), item("Open App Logs", on_open_logs), item(pause_menu_text, on_pause_resume), item("Quit", on_quit))
    icon = Icon("Automation", image, "Complete Automation", menu)
    icon.run_detached()

#=============
# ENTRY POINT
#=============

if __name__ == "__main__":
    logging.info("Starting Tray App in daemon thread")
    threading.Thread(target=start_tray, daemon=True).start()                                     # Start tray in a daemon thread so it does not block automation

    logging.info("Starting Automation Loop in main thread")
    automation_loop()                                                                            # Run automation in main thread to avoid browser windows closing immediately
#=========
# IMPORTS
#=========

import os
import time
import logging
import threading
import certifi
from queue import Queue

from pathlib import Path
from dotenv import load_dotenv

from utils import resource_path, log_file, base_dir, load_settings, env_file, ensure_external_env

"""PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))"""

#============================
# Load Environment Variables
#============================

os.environ["SSL_CERT_FILE"] = certifi.where()                                                                                        # Use certifi certificate bundle for HTTPS requests
ensure_external_env()                                                                                                                # Make sure the writable external .env file exists
load_dotenv(dotenv_path=env_file(), override=True)                                                                                   # Load .env variables from writable env file

INTERVAL = int(os.getenv("INTERVAL", "10"))                                                                                          # Default to 10 seconds if not set

#==============
# MORE IMPORTS
#==============

from gui import open_settings
from setup_login import aha_login_check
from outlook_authentication import authenticate
from run_helper import run_cycle
from run_automation import run_demo

from RQI_EmailSheets.email_to_sheets import run_forever as email_to_sheets_worker

# =============================
# Set up Logging with Log File
# =============================

logging.basicConfig(
    filename=log_file(),                                                                                                             # Write logs to the shared application log file
    level=logging.INFO,                                                                                                              # Log INFO level and above
    format="%(asctime)s - %(levelname)s - %(message)s"                                                                               # Standard log message format
)

# ===========================================
# Set up Global Variable, Pause Event, Queue
# ===========================================

automation_paused = False                                                                                                            # Tracks whether automation is currently paused
pause_event = threading.Event()                                                                                                      # Thread event used to pause/resume the automation loop
pause_event.set()                                                                                                                    # Start unpaused

automation_queue = Queue(maxsize=5)                                                                                                  # Queue to process automation tasks

def is_automation_paused():
    return automation_paused                                                                                                         # Return current pause state for GUI/tray button text

def set_pause_state(paused: bool, icon=None):
    global automation_paused
    automation_paused = paused                                                                                                       # Update shared pause flag

    if paused:
        pause_event.clear()                                                                                                          # Block automation loop until resumed
        set_status("PAUSED")                                                                                                         # Write paused status for GUI
        logging.info("Automation Paused")

    else:
        pause_event.set()                                                                                                            # Allow automation loop to continue
        set_status("RUNNING")                                                                                                        # Write running status for GUI
        logging.info("Automation Resumed")

def toggle_pause(icon=None):
    set_pause_state(not automation_paused, icon=icon)                                                                                # Flip between paused and running states


def quit_application(icon=None):
    logging.info("Exiting Application")
    os._exit(0)                                                                                                                      # Immediately terminate entire program

def set_queue_status(count):
    queue_file = os.path.join(base_dir(), "queue_status.txt")                                                                        # File read by GUI to show current queue size
    with open(queue_file, "w", encoding="utf-8") as f:
        f.write(str(count))                                                                                                          # Save queue count as plain text

#===================
# STATUS READ/WRITE
#===================

def set_status(status):
    status_file = os.path.join(base_dir(), "automation_status.txt")                                                                  # File read by GUI to show RUNNING/PAUSED
    with open(status_file, "w") as f:
        f.write(status)                                                                                                              # Save current automation state

#========================
# EMAIL TO SHEETS THREAD
#========================

def start_email_to_sheets():
    thread = threading.Thread(target=email_to_sheets_worker, daemon=True)                                                            # Run email-to-sheets in background daemon thread
    thread.start()                                                                                                                   # Start continuous email-to-sheets worker

#===================
# AUTOMATION WORKER
#===================

# Worker thread that continuously consumes tasks from the queue.
def automation_worker():
    while True:                                                                                                                      # Keep processing queued automation jobs forever
        name, date = automation_queue.get()                                                                                          # Wait for next queued name/date task
        logging.info("Worker starting automation task: %s, %s", name, date)
        try:
            settings = load_settings()                                                                                               # Reload current settings before each task
            run_demo(name=name, date=date, headless=settings["IS_HEADLESS"])                                                         # Run browser automation for queued task
        except Exception as e:
            logging.exception("Error in automation_worker for %s, %s: %s", name, date, e)
        finally:
            automation_queue.task_done()                                                                                             # Mark queued task as finished
            set_queue_status(automation_queue.qsize())                                                                               # Update GUI queue count file
            logging.info("Worker completed automation task: %s, %s", name, date)

#===================
# AUTOMATION SCRIPT
#===================

def automation_loop():
    logging.info("Starting the Automation Script...")                                                                                # Log the start of the master control script
    set_status("RUNNING")                                                                                                            # Set status for program

    aha_auth_file = Path(base_dir()) / "aha_auth.json"                                                                               # Checks for AHA log in file
    if not aha_auth_file.exists():
        aha_login_check()  # user will manually log in once                                                                          # Run AHA log in manually if no file
        logging.info("AHA login completed and state saved.")                                                                         # Logs the login
    else:
        logging.info("Using existing AHA login state: %s", aha_auth_file)                                                            # Logs whether file was used

    token = authenticate()                                                                                                           # authenticate with Outlook and return token
    if not token:
        logging.error("Authentication failure. No Access Token.")                                                                    # Stop automation loop if Outlook auth fails
        return
    logging.info("Authentication successful. Outlook Token acquired.")

    # Start the automation worker thread (non-daemon for safe shutdown)
    threading.Thread(target=automation_worker, daemon=False).start()                                                                 # Start queue worker that handles browser jobs

    set_queue_status(automation_queue.qsize())                                                                                       # Initialize queue status file for GUI

    # Main cycle: check emails and queue automation tasks
    while True:
        pause_event.wait()                                                                                                           # Pause when automation paused

        settings = load_settings()                                                                                                   # Reload ENV file for settings changes
        interval = settings["INTERVAL"]                                                                                              # Pull latest interval from settings

        result = None                                                                                                                # Default result in case cycle fails
        try:
            result = run_cycle(token)                                                                                                # Run email parsing
        except Exception as e:
            logging.exception("Error during email parsing cycle: %s", e)

        if result and str(result).strip():
            logging.info("Email parsed successfully. Result: %s", result)
            try:
                name, date = result.split(",")                                                                                       # Split parser result into automation inputs
                if automation_queue.full():                                                                                          # Add to queue for worker
                    logging.warning("Automation queue full. Skipping task: %s, %s", name, date)
                else:
                    logging.info("Queuing automation task: %s, %s (queue size: %d)", name, date, automation_queue.qsize())
                    automation_queue.put((name, date))                                                                               # Add task to queue for worker thread
                    set_queue_status(automation_queue.qsize())                                                                       # Update visible queue count
            except Exception as e:
                logging.exception("Error queuing automation cycle: %s", e)
        else:
            logging.info("No new emails to process in this cycle.")                                                                  # Nothing valid returned from run_cycle

        logging.info("Cycle complete. Waiting %d seconds for next cycle...", interval)
        time.sleep(interval)                                                                                                         # Wait before next email parsing cycle

#=================
# GUI WINDOW OPEN
#=================

def open_settings_window():
    logging.info("Opening settings window")
    open_settings(on_pause_resume=toggle_pause, on_quit=quit_application, get_pause_state=is_automation_paused,)                     # Launch main GUI and pass control callbacks

# ==================
# BACKGROUND STARTUP
# ==================

def start_background_services():
    logging.info("Starting RQI Email to Sheets Searches")
    start_email_to_sheets()                                                                                                          # Email-to-sheets in daemon thread

    logging.info("Starting Automation Loop in Daemon Thread")
    threading.Thread(target=automation_loop, daemon=True).start()                                                                    # Main loop

#=============
# ENTRY POINT
#=============

if __name__ == "__main__":
    start_background_services()                                                                                                      # Start background threads first
    logging.info("Opening Settings GUI on startup")
    open_settings_window()                                                                                                           # GUI in Main Thread
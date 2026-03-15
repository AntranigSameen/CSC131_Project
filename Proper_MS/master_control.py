#=========
# IMPORTS
#=========

import os
import sys
import time
import logging
import threading
import subprocess
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

os.environ["SSL_CERT_FILE"] = certifi.where()
ensure_external_env()
load_dotenv(dotenv_path=env_file(), override=True)

INTERVAL = int(os.getenv("INTERVAL", "10"))                                                                                            # Default to 10 seconds if not set

#==============
# MORE IMPORTS
#==============

from pystray import Icon, MenuItem as item, Menu
from PIL import Image

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
    filename=log_file(),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ===========================================
# Set up Global Variable, Pause Event, Queue
# ===========================================

automation_paused = False
pause_event = threading.Event()
pause_event.set()                                                                                                                      # Start unpaused

automation_queue = Queue(maxsize=5)                                                                                                             # Queue to process automation tasks

#============= 
# STATUS READ
#=============

def set_status(status):
    status_file = os.path.join(base_dir(), "automation_status.txt")
    with open(status_file, "w") as f:
        f.write(status)

#========================
# EMAIL TO SHEETS THREAD
#========================

def start_email_to_sheets():
    thread = threading.Thread(target=email_to_sheets_worker, daemon=True)
    thread.start()

#===================
# AUTOMATION WORKER
#===================

# Worker thread that continuously consumes tasks from the queue.
def automation_worker():
    while True:
        name, date = automation_queue.get()
        logging.info("Worker starting automation task: %s, %s", name, date)
        try:
            settings = load_settings()
            run_demo(name=name, date=date, headless=settings["IS_HEADLESS"])
        except Exception as e:
            logging.exception("Error in automation_worker for %s, %s: %s", name, date, e)
        finally:
            automation_queue.task_done()
            logging.info("Worker completed automation task: %s, %s", name, date)

#===================
# AUTOMATION SCRIPT
#===================

def automation_loop():
    logging.info("Starting the Automation Script...")                                                                                  # Log the start of the master control script
    set_status("RUNNING")                                                                                                              # Set status for program

    aha_auth_file = Path(base_dir()) / "aha_auth.json"                                                                                 # Checks for AHA log in file
    if not aha_auth_file.exists():
        aha_login_check()  # user will manually log in once                                                                            # Run AHA log in manually if no file
        logging.info("AHA login completed and state saved.")                                                                           # Logs the login
    else:
        logging.info("Using existing AHA login state: %s", aha_auth_file)                                                              # Logs whether file was used

    token = authenticate()                                                                                                             # authenticate with Outlook and return token
    if not token:
        logging.error("Authentication failure. No Access Token.")
        return
    logging.info("Authentication successful. Outlook Token acquired.")

    # Start the automation worker thread (non-daemon for safe shutdown)
    threading.Thread(target=automation_worker, daemon=False).start()

    # Main cycle: check emails and queue automation tasks
    while True:
        pause_event.wait()                                                                                                             # Pause when automation paused

        settings = load_settings()                                                                                                     # Reload ENV file for settings changes
        interval = settings["INTERVAL"]

        result = None
        try:
            result = run_cycle(token)                                                                                                  # Run email parsing
        except Exception as e:
            logging.exception("Error during email parsing cycle: %s", e)

        if result and str(result).strip():
            logging.info("Email parsed successfully. Result: %s", result)
            try:
                name, date = result.split(",")
                if automation_queue.full():                                                                                            # Add to queue for worker
                    logging.warning("Automation queue full. Skipping task: %s, %s", name, date)
                else:
                    logging.info("Queuing automation task: %s, %s (queue size: %d)", name, date, automation_queue.qsize())
                    automation_queue.put((name, date))
            except Exception as e:
                logging.exception("Error queuing automation cycle: %s", e)
        else:
            logging.info("No new emails to process in this cycle.")

        logging.info("Cycle complete. Waiting %d seconds for next cycle...", interval)
        time.sleep(interval)

#===========
# TRAY ICON
#===========

def on_quit(icon, item):
    logging.info("Exiting Application through System Tray Menu")
    icon.stop()
    os._exit(0)

def on_settings(icon, item):
    logging.info("Settings GUI Opened through System Tray Menu")
    threading.Thread(target=open_settings, daemon=True).start()

def on_open_logs(icon, item):
    log_path = os.path.join(base_dir(), "logs", "app.log")
    if os.path.exists(log_path):
        subprocess.Popen(["notepad", log_path])
    else:
        logging.error("Log file not found: %s", log_path)

def on_pause_resume(icon, item):
    global automation_paused
    if automation_paused:
        automation_paused = False
        pause_event.set()
        logging.info("Automation Resumed")
        icon.notify("Automation Resumed")
        set_status("RUNNING")
    else:
        automation_paused = True
        pause_event.clear()
        logging.info("Automation Paused")
        icon.notify("Automation Paused")
        set_status("PAUSED")

def pause_menu_text(item):
    return "Resume Automation" if automation_paused else "Pause Automation"

def start_tray():
    image = Image.open(resource_path("icon.png")).convert("RGBA").resize((64, 64))
    menu = Menu(
        item("Settings", on_settings),
        item("Open App Logs", on_open_logs),
        item(pause_menu_text, on_pause_resume),
        item("Quit", on_quit)
    )
    icon = Icon("Automation", image, "Complete Automation", menu)
    icon.run_detached()

#=============
# ENTRY POINT
#=============

if __name__ == "__main__":
    logging.info("Starting RQI Email to Sheets Searches")
    start_email_to_sheets()                                                                                                            # Email-to-sheets in daemon thread

    logging.info("Starting Tray App in Daemon Thread")
    threading.Thread(target=start_tray, daemon=True).start()                                                                           # Tray in daemon thread

    logging.info("Starting Automation Loop in Main Thread")
    automation_loop()                                                                                                                  # Main loop
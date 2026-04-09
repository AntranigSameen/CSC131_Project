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

INTERVAL = int(os.getenv("INTERVAL") or "10")                                                                                          # Default to 10 seconds if not set

#==============
# MORE IMPORTS
#==============

from gui import open_settings, prompt_for_aha_credentials
from setup_login import aha_login_check
from outlook_authentication import authenticate
from run_helper import run_cycle
from run_automation import run_demo

from RQI_EmailSheets.email_to_sheets import (run_forever as email_to_sheets_worker,
                                             generate_csv_now, upload_latest_csv_now, refresh_upload_window,
                                             get_current_batch_status, validate_sftp_settings,)

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

pause_all_event = threading.Event()                                                                                                  # Master switch for all background services
pause_automation_loop_event = threading.Event()                                                                                      # Controls only the main automation loop
pause_email_to_sheets_event = threading.Event()                                                                                      # Controls only the email_to_sheets worker

pause_all_event.set()                                                                                                                # App starts in running state
pause_automation_loop_event.set()                                                                                                    # Main automation loop starts enabled
pause_email_to_sheets_event.set()                                                                                                    # Email-to-sheets worker starts enabled

automation_queue = Queue(maxsize=5)                                                                                                  # Queue to process automation tasks

background_services_started = False                                                                                                  # Prevent startup code from launching duplicate background threads

def aha_credentials_exist():
    settings = load_settings()                                                                                                       # Load latest .env values before checking AHA credentials
    return bool(settings["AHA_USERNAME"].strip()) and bool(settings["AHA_PASSWORD"].strip())                                         # Only True when both username and password exist


def aha_session_exists():
    aha_auth_file = Path(base_dir()) / "aha_auth.json"                                                                               # Saved Playwright AHA login state file
    return aha_auth_file.exists()                                                                                                    # True when session file already exists


def bootstrap_after_gui(window):
    global background_services_started

    if background_services_started:
        return                                                                                                                       # Prevent bootstrap from running more than once

    if not aha_session_exists() and not aha_credentials_exist():
        logging.info("No saved AHA session or AHA credentials found. Prompting user from GUI.")
        credentials_saved = prompt_for_aha_credentials(window)

        if not credentials_saved:
            logging.warning("User cancelled AHA credential prompt. Background services not started.")
            return                                                                                                                   # Leave GUI open, but do not start automation yet

    if not aha_session_exists():
        logging.info("No saved AHA session found. Running automated AHA login.")
        aha_login_check()                                                                                                            # Use saved env credentials to log in and save aha_auth.json
        logging.info("AHA login completed and state saved.")
    else:
        logging.info("Using existing AHA login state.")

    start_background_services()                                                                                                      # Start automation only after AHA setup is ready
    background_services_started = True                                                                                               # Mark startup as complete so it does not run twice

# ======================
# PAUSE STATE HELPERS
# ======================

def is_automation_loop_paused():
    return not pause_automation_loop_event.is_set()                                                                                  # True only when the main automation loop is paused


def is_email_to_sheets_paused():
    return not pause_email_to_sheets_event.is_set()                                                                                  # True only when email_to_sheets worker is paused


def is_all_paused():
    return not pause_all_event.is_set()                                                                                              # True only when the master "pause all" switch is active


def get_pause_states():
    return {
        "all": is_all_paused(),                                                                                                      # Master pause state
        "automation_loop": is_automation_loop_paused(),                                                                              # Main automation loop pause state
        "email_to_sheets": is_email_to_sheets_paused(),                                                                              # Email-to-sheets pause state
    }

# ======================
# PAUSE / RESUME ACTIONS
# ======================

def refresh_combined_pause_state():
    automation_paused = is_automation_loop_paused()                                                                                  # True when AHA automation loop is paused
    email_paused = is_email_to_sheets_paused()                                                                                       # True when RQI email parsing is paused

    if automation_paused and email_paused:
        pause_all_event.clear()                                                                                                      # Treat both individual pauses together as "all automation paused"
        set_status("PAUSED_ALL")                                                                                                     # Show combined paused state in GUI
        logging.warning("All automation paused")

    elif automation_paused:
        pause_all_event.set()                                                                                                        # Global pause is not active when only one service is paused
        set_status("PAUSED_AUTOMATION_LOOP")                                                                                         # Show AHA-only paused state in GUI
        logging.warning("AHA automation paused")

    elif email_paused:
        pause_all_event.set()                                                                                                        # Global pause is not active when only one service is paused
        set_status("PAUSED_EMAIL_TO_SHEETS")                                                                                         # Show RQI-only paused state in GUI
        logging.warning("RQI email parsing paused")

    else:
        pause_all_event.set()                                                                                                        # No pause states remain, so all services may run
        set_status("RUNNING")                                                                                                        # Return GUI to running state
        logging.warning("All automation Running")

def pause_all_automation():
    pause_all_event.clear()                                                                                                          # Stop all controlled background services
    pause_automation_loop_event.clear()                                                                                              # Pause AHA automation
    pause_email_to_sheets_event.clear()                                                                                              # Pause RQI email parsing
    set_status("PAUSED_ALL")                                                                                                         # Write status for GUI
    logging.warning("All automation paused")


def resume_all_automation():
    pause_all_event.set()                                                                                                            # Re-enable all controlled background services
    pause_automation_loop_event.set()                                                                                                # Resume AHA automation
    pause_email_to_sheets_event.set()                                                                                                # Resume RQI email parsing
    set_status("RUNNING")                                                                                                            # Write status for GUI
    logging.warning("All automation resumed")


def toggle_pause_all():
    if is_all_paused():
        resume_all_automation()                                                                                                      # Resume everything if currently fully paused
    else:
        pause_all_automation()                                                                                                       # Pause everything if currently running


def pause_automation_loop():
    pause_automation_loop_event.clear()                                                                                              # Pause only the main automation loop
    refresh_combined_pause_state()                                                                                                   # Recalculate whether state is AHA paused or fully paused
    set_status("PAUSED_AUTOMATION_LOOP")
    logging.warning("AHA automation paused")


def resume_automation_loop():
    pause_automation_loop_event.set()                                                                                                # Resume only the main automation loop
    refresh_combined_pause_state()                                                                                                   # Recalculate whether state is running, RQI paused, or still fully paused
    logging.warning("AHA automation resumed")


def toggle_pause_automation_loop():
    if is_automation_loop_paused():
        resume_automation_loop()                                                                                                     # Resume only the main automation loop
    else:
        pause_automation_loop()                                                                                                      # Pause only the main automation loop


def pause_email_to_sheets():
    pause_email_to_sheets_event.clear()                                                                                              # Pause only the email_to_sheets worker
    refresh_combined_pause_state()                                                                                                   # Recalculate whether state is RQI paused or fully paused
    logging.warning("RQI email parsing paused")


def resume_email_to_sheets():
    pause_email_to_sheets_event.set()                                                                                                # Resume only the email_to_sheets worker
    refresh_combined_pause_state()                                                                                                   # Recalculate whether state is running, AHA paused, or still fully paused
    logging.warning("RQI email parsing resumed")


def toggle_pause_email_to_sheets():
    if is_email_to_sheets_paused():
        resume_email_to_sheets()                                                                                                     # Resume only email-to-sheets
    else:
        pause_email_to_sheets()                                                                                                      # Pause only email-to-sheets

# ===========================
# END PAUSE / RESUME ACTIONS
# ===========================

# =======================
# RQI CSV / SFTP ACTIONS
# =======================

def trigger_rqi_csv_generation():
    try:
        csv_path = generate_csv_now()                                                                                                # Create the current CSV batch immediately on demand
        logging.info("Manual CSV generation completed: %s", csv_path)
        return str(csv_path)                                                                                                         # Return created CSV path so GUI can show success message
    except Exception as e:
        logging.exception("Manual CSV generation failed: %s", e)
        raise                                                                                                                        # Re-raise so GUI can show the real error message


def trigger_rqi_sftp_upload():
    try:
        remote_path = upload_latest_csv_now()                                                                                        # Upload the most recent CSV batch immediately on demand
        logging.info("Manual SFTP upload completed: %s", remote_path)
        return remote_path                                                                                                           # Return remote upload destination so GUI can show success message
    except Exception as e:
        logging.exception("Manual SFTP upload failed: %s", e)
        raise                                                                                                                        # Re-raise so GUI can show the real error message


def trigger_rqi_upload_window_refresh():
    try:
        csv_path = refresh_upload_window()                                                                                           # Start a brand-new upload window immediately and create its CSV batch
        logging.info("Manual upload window refresh completed: %s", csv_path)
        return str(csv_path)                                                                                                         # Return new CSV path so GUI can show success message
    except Exception as e:
        logging.exception("Manual upload window refresh failed: %s", e)
        raise                                                                                                                        # Re-raise so GUI can show the real error message

def get_rqi_csv_sftp_status():
    try:
        return get_current_batch_status()                                                                                            # Return live batch-window countdown, current CSV path, last upload info, and last upload error for GUI display
    except Exception as e:
        logging.exception("Failed to get RQI CSV / SFTP status: %s", e)
        return {
            "batch_start": "",
            "batch_end": "",
            "seconds_remaining": 0,
            "current_csv_path": "",
            "latest_csv_path": "",
            "last_uploaded_local_path": "",
            "last_uploaded_remote_path": "",
            "last_upload_time": "",
            "last_upload_error": str(e),
        }                                                                                                                            # Return safe fallback status so GUI can stay alive even if backend status lookup fails


def get_missing_sftp_fields():
    try:
        return validate_sftp_settings()                                                                                              # Return a list of human-readable missing SFTP settings so GUI can validate before upload
    except Exception as e:
        logging.exception("Failed to validate SFTP settings: %s", e)
        return [str(e)]                                                                                                              # Return backend validation error as one message so GUI can show it cleanly

# ===========================
# END RQI CSV / SFTP ACTIONS
# ===========================

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
    thread = threading.Thread(target=email_to_sheets_worker,
                              kwargs={"pause_all_event": pause_all_event,
                                      "pause_email_event": pause_email_to_sheets_event,},
                                      daemon=True,)                                                                                  # Run email-to-sheets in background daemon thread with pause controls
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
        pause_all_event.wait()                                                                                                       # Block here when user pauses all automation
        pause_automation_loop_event.wait()                                                                                           # Block here when user pauses only the main automation loop

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
    open_settings(on_toggle_pause_all=toggle_pause_all,                                                                              # Main GUI/tray action for pausing all automation
        on_toggle_pause_email=toggle_pause_email_to_sheets,                                                                          # GUI action for pausing email_to_sheets only
        on_toggle_pause_automation_loop=toggle_pause_automation_loop,                                                                # GUI action for pausing main automation loop only
        on_generate_rqi_csv=trigger_rqi_csv_generation,                                                                              # GUI action for manual CSV batch generation
        on_upload_rqi_csv=trigger_rqi_sftp_upload,                                                                                   # GUI action for manual SFTP upload of latest CSV batch
        on_refresh_rqi_upload_window=trigger_rqi_upload_window_refresh,                                                              # GUI action for starting a brand-new upload window immediately
        get_rqi_csv_sftp_status=get_rqi_csv_sftp_status,                                                                             # GUI status callback for live batch window countdown and last upload info
        get_missing_sftp_fields=get_missing_sftp_fields,                                                                             # GUI validation callback for missing SFTP settings before upload
        on_quit=quit_application,
        get_pause_states=get_pause_states,
        on_ready=bootstrap_after_gui,)

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
    logging.info("Opening Settings GUI on startup")
    open_settings_window()                                                                                                           # GUI in Main Thread
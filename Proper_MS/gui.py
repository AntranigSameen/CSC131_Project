#==========
# IMPORTS
#==========

import os
import sys
import subprocess
import ttkbootstrap as tb
import logging

from pathlib import Path
from utils import env_file, writable_env_file, base_dir, log_file
from tkinter import messagebox
from dotenv import set_key, load_dotenv

#============================
# Load Environment Variables
#============================

CONFIG_FILE = writable_env_file()
load_dotenv(CONFIG_FILE)

RESTART_REQUIRED = {
    "IS_HEADLESS",
    "CLIENT_ID",
    "TENANT_ID",
    "AUTHORITY",
    "SCOPES",
    "CACHE_FILE",
    "SERVICE_ACCOUNT_RQI_JSON",
    "SERVICE_ACCOUNT_AHA_JSON",
    "AHA_USERNAME",
    "AHA_PASSWORD"
}

#===============
# Save Settings
#===============

# SAVE EDITED VARIABLES IN ENV
def save_settings(entries, restart=False):
    restart_needed = False

    for key, var in entries.items():
        new_value = var.get()
        old_value = os.getenv(key, "")

        if new_value != old_value and key in RESTART_REQUIRED:
            restart_needed = True

        set_key(CONFIG_FILE, key, new_value)

    logging.info("Settings saved successfully")

    from dotenv import load_dotenv
    load_dotenv(CONFIG_FILE, override=True)

    logging.info("New Settings Saved and Loaded")

    if restart:
        restart_application()

    else:
        if restart_needed:
            messagebox.showwarning(
                "Restart Required",
                "Some changes require restarting the automation to take effect."
            )
        else:
            messagebox.showinfo("Saved", "Settings saved successfully!")

#=================
# Restart Program
#=================

def restart_application():
    logging.info("Restarting application")

    exe_path = os.path.abspath(sys.executable)
    subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
    os._exit(0)

#=================
# Sign Out of AHA
#=================

# Deletes the saved AHA login state so the next run requires manual login.
def sign_out():
    aha_auth_file = Path(base_dir()) / "aha_auth.json"
    if aha_auth_file.exists():
        aha_auth_file.unlink()                                                                                                  # Delete the file
        logging.info("User signed out: deleted AHA login state")
        tb.messagebox.showinfo("Signed Out", "AHA login state cleared. You will need to sign in next time.")
    else:
        logging.info("Sign out requested, but aha_auth.json does not exist")
        tb.messagebox.showinfo("Info", "No existing AHA login state to delete.")

#=============
# Scrollable
#=============

# Container that scrolls
class ScrollableFrame(tb.Frame):

    def __init__(self, container):
        super().__init__(container)
        canvas = tb.Canvas(self)
        scrollbar = tb.Scrollbar(self, orient="vertical", command=canvas.yview)

        self.scrollable_frame = tb.Frame(canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

#=========
# BUTTONS
#=========
def buttons(root, entries):
    button_frame = tb.Frame(root)
    button_frame.pack(pady=10)

    # Save Button 
    tb.Button(button_frame, text="Save", bootstyle="success", command=lambda: save_settings(entries, restart=False)).pack(side="left", padx=10)

    # Restart Button
    tb.Button(button_frame, text="Restart", bootstyle="danger", command=restart_application).pack(side="left", padx=10)

    # Sign Out of AHA Button
    tb.Button(button_frame, text="Sign Out of AHA", bootstyle="warning", command=sign_out).pack(side="left", padx=10)

#==============
# Settings GUI
#==============

# CREATES A WINDOW
def open_settings():
    root = tb.Window(themename="darkly")                                                                                        # Theme
    root.title("Automation Machine")                                                                                            # Title
    root.geometry("1280x720")                                                                                                   # Window Size

    notebook = tb.Notebook(root)                                                                                                # Create TABS
    notebook.pack(fill="both", expand=True, padx=15, pady=15)

    entries = {}

    #========
    # STATUS
    #========
    
    status_var = tb.StringVar(value="Checking status...")

    status_frame = tb.Frame(root)
    status_frame.pack(fill="x", pady=10)

    tb.Label(status_frame, text= "Automation Status:", font=("Segoe UI", 8, "bold")).pack(side="left", padx=10)

    status_label = tb.Label(status_frame, textvariable=status_var, bootstyle="success")
    status_label.pack(side="left")

    #===============
    # UPDATE STATUS
    #===============

    def update_status():

        status_file = os.path.join(base_dir(), "automation_status.txt")

        if os.path.exists(status_file):

            with open(status_file, "r") as f:
                status = f.read().strip()

            if status == "RUNNING":
                status_var.set("Running 🟢")
                status_label.configure(bootstyle="success")

            elif status == "PAUSED":
                status_var.set("Paused 🟡")
                status_label.configure(bootstyle="warning")

        else:
            status_var.set("Unknown ⚪")

        root.after(2000, update_status)

    update_status()                                                                                                         # Start updating the process

    #===============
    # AHA LOGIN TAB
    #===============

    login_tab = ScrollableFrame(notebook)
    notebook.add(login_tab, text="AHA Login")                                                                               # New tab for credentials

    login_status_var = tb.StringVar(value="Checking login state...")

    status_frame = tb.Frame(login_tab.scrollable_frame)
    status_frame.pack(fill="x", pady=10)

    tb.Label(status_frame, text="AHA Login Status:", font=("Segoe UI", 10, "bold")).pack(side="left", padx=10)
    tb.Label(status_frame, textvariable=login_status_var, bootstyle="info").pack(side="left")

    login_variables = {
        "AHA Username": "AHA_USERNAME",
        "AHA Password": "AHA_PASSWORD"
    }

    for label, env_var in login_variables.items():
        frame = tb.Frame(login_tab.scrollable_frame)
        frame.pack(fill="x", padx=10, pady=6)

        tb.Label(frame, text=label, width=28).pack(side="left")
        value = tb.StringVar(value=os.getenv(env_var, ""))

        # Mask password field
        show_char = "*" if "Password" in label else None
        entry = tb.Entry(frame, textvariable=value, width=50, show=show_char)
        entry.pack(side="left", fill="x", expand=True)

        entries[env_var] = value

    #====================
    # AHA Login Status
    #====================
    def update_login_status():
        """
        Updates the login status label based on whether aha_auth.json exists.
        """
        aha_auth_file = Path(base_dir()) / "aha_auth.json"
        if aha_auth_file.exists():
            login_status_var.set("Signed In ✅")
        else:
            login_status_var.set("Not Signed In ⚪")
        # Refresh every 2 seconds
        root.after(2000, update_login_status)

    update_login_status()  # Start the dynamic status updater

    #============
    # EMAIL TAB
    #============

    email_tab = ScrollableFrame(notebook)
    notebook.add(email_tab, text="Email Settings")
    email_variables= {"Sender Email Address": "SENDER_EMAIL",
                      "Keyword Before Name": "KEYWORD_NAME",
                       "Automation Interval (seconds)": "INTERVAL"}                                                             # Variables in this tab
    
    for label, env_var in email_variables.items():
        frame = tb.Frame(email_tab.scrollable_frame)
        frame.pack(fill="x", padx=10, pady=6)

        tb.Label(frame, text=label, width=28).pack(side="left")
        value = tb.StringVar(value=os.getenv(env_var, ""))

        entry = tb.Entry(frame, textvariable=value, width=50)
        entry.pack(side="left", fill="x", expand=True)

        entries[env_var] = value

    #============
    # GOOGLE TAB
    #============

    google_tab = ScrollableFrame(notebook)
    notebook.add(google_tab, text="Sheets Settings")
    google_variables = {"RQI Service Account File": "SERVICE_ACCOUNT_RQI_JSON",
                        "AHA Service Account File": "SERVICE_ACCOUNT_AHA_JSON",
                        "AHA Google Sheet URL": "GOOGLE_SHEET_URL",
                        "RQI Google Sheet ID": "SPREADSHEET_ID"}

    for label, env_var in google_variables.items():
        frame = tb.Frame(google_tab.scrollable_frame)
        frame.pack(fill="x", padx=10, pady=6)

        tb.Label(frame, text=label, width=28).pack(side="left")
        value = tb.StringVar(value=os.getenv(env_var, ""))

        entry = tb.Entry(frame, textvariable=value, width=50)
        entry.pack(side="left", fill="x", expand=True)

        entries[env_var] = value

    #====================
    # AUTHENTICATION TAB
    #====================

    auth_tab = ScrollableFrame(notebook)
    notebook.add(auth_tab, text="Authentication Settings")
    auth_variables = {"Azure Client ID": "CLIENT_ID","Azure Tenant ID": "TENANT_ID",
                      "Highest Credential Access": "AUTHORITY", "App Permissions": "SCOPES",
                      "Cache File": "CACHE_FILE"}

    for label, env_var in auth_variables.items():
        frame = tb.Frame(auth_tab.scrollable_frame)
        frame.pack(fill="x", padx=10, pady=6)

        tb.Label(frame, text=label, width=28).pack(side="left")
        value = tb.StringVar(value=os.getenv(env_var, ""))

        entry = tb.Entry(frame, textvariable=value, width=50)
        entry.pack(side="left", fill="x", expand=True)

        entries[env_var] = value
    
    #============
    # OTHER TAB
    #============

    other_tab = ScrollableFrame(notebook)
    notebook.add(other_tab, text="Other Settings")
    other_variables = {"Orgnatizaiton Name": "ORG_NAME",
                        "Run Headless": "IS_HEADLESS"}

    for label, env_var in other_variables.items():
        frame = tb.Frame(other_tab.scrollable_frame)
        frame.pack(fill="x", padx=10, pady=6)

        tb.Label(frame, text=label, width=28).pack(side="left")
        value = tb.StringVar(value=os.getenv(env_var, ""))

        entry = tb.Entry(frame, textvariable=value, width=50)
        entry.pack(side="left", fill="x", expand=True)

        entries[env_var] = value

    #=========
    # LOG TAB
    #=========

    log_tab = tb.Frame(notebook)
    notebook.add(log_tab, text="System Logs")

    log_text = tb.Text(log_tab, height=30)
    log_text.pack(fill="both", expand=True, padx=10, pady=10)
    
    def update_logs():
        current_log_file = log_file()
        if os.path.exists(current_log_file):
            with open(current_log_file, "r", encoding="utf-8") as f:
                content = f.read()

            log_text.delete("1.0", "end")
            log_text.insert("end", content)
            log_text.see("end")

        root.after(3000, update_logs)

    update_logs()

    buttons(root, entries)

    root.mainloop()

#######################################
# FOR TESTING ONLY
#######################################
if __name__ == "__main__":
    open_settings()

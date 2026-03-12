#==========
# IMPORTS
#==========

import os
import tkinter as tk
import ttkbootstrap as tb
import logging

from utils import resource_path
from tkinter import messagebox
from dotenv import set_key, load_dotenv

#============================
# Load Environment Variables
#============================

CONFIG_FILE = resource_path(".env")
load_dotenv(CONFIG_FILE)

#===============
# Save Settings
#===============

# SAVE EDITED VARIABLES IN ENV
def save_settings(entries):
    for key, var in entries.items():
        set_key(CONFIG_FILE, key, var.get())
    logging.info("Settings saved successfully")                                                                                 # Logs when changes are saved
    messagebox.showinfo("Saved", "Settings saved successfully!")

    from dotenv import load_dotenv
    load_dotenv(CONFIG_FILE, override=True)

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

        status_file = resource_path("automation_status.txt")

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

    #============
    # EMAIL TAB
    #============

    email_tab = ScrollableFrame(notebook)
    notebook.add(email_tab, text="Email Settings")

    container = email_tab.scrollable_frame
    #tb.Label(container, text="Emails From AHA", font=("Segoe UI", 12, "bold"))

    email_variables= {"Sender Email Address": "SENDER_EMAIL",
                      "Keyword Before Name": "KEYWORD_NAME",
                       "Automation Interval (seconds)": "INTERVAL"}                                                             # Variables in this tab
    
    for label, env_var in email_variables.items():
        frame = tb.Frame(container)
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
    google_variables = {"Service Account File": "SERVICE_ACCOUNT_JSON",
                        "Google Sheet URL": "GOOGLE_SHEET_URL"}

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

    #=========
    # LOG TAB
    #=========

    log_tab = tb.Frame(notebook)
    notebook.add(log_tab, text="System Logs")

    log_text = tb.Text(log_tab, height=30)
    log_text.pack(fill="both", expand=True, padx=10, pady=10)
    
    def update_logs():
        log_file = os.path.join(resource_path("."), "logs", "app.log")
        if os.path.exists(log_file):

            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()

            log_text.delete("1.0", "end")
            log_text.insert("end", content)

            log_text.see("end")

        root.after(3000, update_logs)

    #=========
    # BUTTONS
    #=========

    button_frame = tb.Frame(root)
    button_frame.pack(pady=10)

    # Save Button
    tb.Button(button_frame, text="Save & Restart", bootstyle="success", command=lambda: save_settings(entries)).pack(side="left", padx=10)

    root.mainloop()

#######################################
# FOR TESTING ONLY
#######################################
if __name__ == "__main__":
    open_settings()

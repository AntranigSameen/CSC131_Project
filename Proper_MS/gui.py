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
from tkinter import messagebox, scrolledtext
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

#==============
# STATUS CARDS
#==============

def make_status_card(parent, title, value_var, bootstyle="dark"):
    outer = tb.Frame(parent, bootstyle=bootstyle, padding=1)
    outer.pack(side="left", fill="x", expand=True, padx=6, pady=4)

    card = tb.Frame(outer, bootstyle=bootstyle, padding=(14, 10))
    card.pack(fill="both", expand=True)

    title_label = tb.Label(card, text=title, font=("Lato", 8, "bold"), bootstyle=f"{bootstyle}-inverse")
    title_label.pack(anchor="w")
    value_label = tb.Label(card, textvariable=value_var, font=("Lato", 12, "bold"), bootstyle=f"{bootstyle}-inverse")
    value_label.pack(anchor="w", pady=(3, 0))

    return {"outer": outer, "card": card, "title": title_label, "value": value_label,}


#=========
# BUTTONS
#=========

def buttons(root, entries, on_pause_resume=None, on_quit=None, get_pause_state=None):
    toolbar = tb.Frame(root, padding=(20, 6, 20, 10))
    toolbar.pack(fill="x")
    left_toolbar = tb.Frame(toolbar)
    left_toolbar.pack(side="left")
    right_toolbar = tb.Frame(toolbar)
    right_toolbar.pack(side="right")

    def pause_resume_clicked():
        if on_pause_resume:
            on_pause_resume()
            update_pause_button()
        else:
            messagebox.showinfo("Info", "Pause/Resume control is not available.")

    def quit_clicked():
        if messagebox.askyesno("Quit", "Are you sure you want to quit the application?"):
            if on_quit:
                on_quit()
            else:
                os._exit(0)

    pause_text = tb.StringVar(value="Pause Automation")

    def update_pause_button():
        if get_pause_state and get_pause_state():
            pause_text.set("Resume Automation")
        else:
            pause_text.set("Pause Automation")

    # Save Button
    tb.Button(left_toolbar, text="Save Settings", bootstyle="success, outline", command=lambda: save_settings(entries, restart=False), width=16,).pack(side="left", padx=5)

    # Pause/Resume Button
    tb.Button(right_toolbar, textvariable=pause_text, bootstyle="warning, outline", command=pause_resume_clicked, width=18,).pack(side="left", padx=5)

    # Restart Button
    tb.Button(right_toolbar, text="Restart App", bootstyle="danger, outline", command=restart_application, width=14,).pack(side="left", padx=5)

    # Sign Out Button for AHA
    tb.Button(left_toolbar, text="Sign Out of AHA", bootstyle="info, outline", command=sign_out, width=16,).pack(side="left", padx=5)

    # Quit Button
    tb.Button(right_toolbar, text="Quit", bootstyle="danger, outline", command=quit_clicked, width=10,).pack(side="right", padx=5)

    update_pause_button()
    return update_pause_button

#==============
# Settings GUI
#==============

# CREATES A WINDOW
def open_settings(on_pause_resume=None, on_quit=None, get_pause_state=None, on_ready=None):
    root = tb.Window(themename="darkly")                                                                                    # Theme
    if on_ready:                                                                                                            # For pulling window to front
        on_ready(root)

    root.title("Automation Machine")                                                                                        # Title
    root.geometry("1360x820")                                                                                               # Size
    root.minsize(1120, 700)                                                                                                 # Mini Size

    def handle_window_close():
        root.withdraw()

    root.protocol("WM_DELETE_WINDOW", handle_window_close)

    entries = {}

    header = tb.Frame(root, padding=(22, 18, 22, 6))
    header.pack(fill="x")

    tb.Label(header, text="Automation Control Center", font=("Lato", 23, "bold")).pack(anchor="w")
    #tb.Label(header, text="Manage automation, monitor status, update settings, and review logs.", font=("Lato", 10)).pack(anchor="w", pady=(3, 0))

    #========
    # STATUS
    #========
    
    status_var = tb.StringVar(value="Checking status...")
    login_status_var = tb.StringVar(value="Checking login state...")
    mode_var = tb.StringVar(value=f"Headless: {os.getenv('IS_HEADLESS', '')}")
    interval_var = tb.StringVar(value=f"Interval: {os.getenv('INTERVAL', '')} sec")
    queue_var = tb.StringVar(value="Queue: 0 tasks")

    cards = tb.Frame(root, padding=(16, 2, 16, 4))
    cards.pack(fill="x")

    automation_card = make_status_card(cards, "Automation", status_var, "dark")
    #make_status_card(cards, "AHA Login", login_status_var, "dark")
    browser_card = make_status_card(cards, "Browser", mode_var, "dark")
    interval_card = make_status_card(cards, "Interval", interval_var, "dark")
    queue_card = make_status_card(cards, "Queue", queue_var, "dark")

    update_pause_button = buttons(root, entries, on_pause_resume=on_pause_resume, on_quit=on_quit, get_pause_state=get_pause_state,)

    content = tb.Frame(root, padding=(14, 4, 14, 14))
    content.pack(fill="both", expand=True)

    notebook = tb.Notebook(content)
    notebook.pack(fill="both", expand=True, padx=15, pady=10)

    #===============
    # UPDATE STATUS
    #===============

    def update_status():
        status_file = os.path.join(base_dir(), "automation_status.txt")

        if os.path.exists(status_file):
            try:
                with open(status_file, "r", encoding="utf-8") as f:
                    raw_status = f.read().strip().upper()
            except Exception:
                raw_status = "UNKNOWN"
        else:
            raw_status = "UNKNOWN"

        if raw_status == "RUNNING":
            status_var.set("Running")
            automation_card["value"].configure(foreground="#00bc8c")
            quick_status_label.configure(foreground="#00bc8c")

        elif raw_status == "PAUSED":
            status_var.set("Paused")
            automation_card["value"].configure(foreground="#f39c12")
            quick_status_label.configure(foreground="#f39c12")

        else:
            status_var.set("Unknown")
            automation_card["value"].configure(foreground="#e64e30")
            quick_status_label.configure(foreground="#e64e30")

        current_headless = os.getenv("IS_HEADLESS", "")
        if str(current_headless).strip().lower() in ("1", "true", "yes"):
            mode_var.set("▣ Headless")
            browser_card["value"].configure(foreground="#00bc8c")
            quick_mode_label.configure(foreground="#00bc8c")
        else:
            mode_var.set("🌐 Visible Browser")
            browser_card["value"].configure(foreground="#5dade2")
            quick_mode_label.configure(foreground="#5dade2")

        interval_text = os.getenv("INTERVAL", "")
        interval_var.set(f"⏱️ {os.getenv('INTERVAL', '')} sec")
        interval_card["value"].configure(foreground="#f39c12")

        queue_count_int = 0
        queue_file = os.path.join(base_dir(), "queue_status.txt")
        if os.path.exists(queue_file):
            try:
                with open(queue_file, "r", encoding="utf-8") as f:
                    queue_count_int = int(f.read().strip())
                queue_var.set(f"📋 {queue_count_int} task(s)")
            except Exception:
                queue_var.set("📋 ? task(s)")
                queue_card["value"].configure(foreground="#e64e30")
                quick_queue_label.configure(foreground="#e64e30")
            else:
                if queue_count_int == 0:
                    queue_color = "#00bc8c"
                elif 1 <= queue_count_int <= 3:
                    queue_color = "#f39c12"
                else:
                    queue_color = "#e64e30"

                queue_card["value"].configure(foreground=queue_color)
                quick_queue_label.configure(foreground=queue_color)
        else:
            queue_var.set("📋 0 tasks")
            queue_card["value"].configure(foreground="#00bc8c")
            quick_queue_label.configure(foreground="#00bc8c")

        if update_pause_button:
            update_pause_button()

        root.after(2000, update_status)

    #==============
    # OVERVIEW TAB
    #==============
    
    overview_tab = ScrollableFrame(notebook)
    notebook.add(overview_tab, text="Overview")

    summary_box = tb.Labelframe(overview_tab.scrollable_frame, text="Application Overview", padding=18)
    summary_box.pack(fill="x", padx=12, pady=(12, 8))

    tb.Label(summary_box, text="Use this window to manage automation settings, monitor live status, review logs, and control the automation process.",
             wraplength=1000, justify="left", font=("Lato", 10),).pack(anchor="w")

    tb.Label(summary_box, text="Use Save Settings for configuration updates. Use Pause Automation to temporarily stop cycles without closing the app.",
             wraplength=1000, justify="left", font=("Lato", 10),).pack(anchor="w", pady=(10, 0))
    
    quick_box = tb.Labelframe(overview_tab.scrollable_frame, text="Quick Status", padding=18)
    quick_box.pack(fill="x", padx=12, pady=(0, 12))

    quick_status_label = tb.Label(quick_box, textvariable=status_var, font=("Lato", 12, "bold"))
    quick_status_label.pack(anchor="w", pady=(0, 6))

    quick_login_label = tb.Label(quick_box, textvariable=login_status_var, font=("Lato", 11))
    quick_login_label.pack(anchor="w", pady=(0, 4))

    quick_mode_label = tb.Label(quick_box, textvariable=mode_var, font=("Lato", 11))
    quick_mode_label.pack(anchor="w", pady=(0, 4))

    quick_queue_label = tb.Label(quick_box, textvariable=queue_var, font=("Lato", 11))
    quick_queue_label.pack(anchor="w")

    update_status()                                                                                                         # Calls this AFTER Labels are created

    #===============
    # AHA LOGIN TAB
    #===============

    login_tab = ScrollableFrame(notebook)
    notebook.add(login_tab, text="AHA Login")                                                                               # New tab for credentials

    login_status_var = tb.StringVar(value="Checking login state...")

    status_frame = tb.Frame(login_tab.scrollable_frame)
    status_frame.pack(fill="x", pady=10)

    tb.Label(status_frame, text="AHA Login Status:", font=("Lato", 10, "bold")).pack(side="left", padx=10)
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
        #Updates the login status label based on whether aha_auth.json exists.
        
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
    notebook.add(email_tab, text="Email")
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
    notebook.add(google_tab, text="Sheets")
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
    notebook.add(auth_tab, text="Authentication")
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
    notebook.add(other_tab, text="General")
    other_variables = {"Organization Name": "ORG_NAME",
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

    log_container = tb.Frame(log_tab, padding=10)
    log_container.pack(fill="both", expand=True)

    tb.Label(log_container, text="Live Application Logs", font=("Lato", 11, "bold")).pack(anchor="w", pady=(0, 8))

    log_text = scrolledtext.ScrolledText(log_container, height=30, wrap="none", font=("Consolas", 10), relief="flat", borderwidth=0)
    log_text.pack(fill="both", expand=True)

    def update_logs():
        current_log_file = log_file()
        if os.path.exists(current_log_file):
            with open(current_log_file, "r", encoding="utf-8") as f:
                content = f.read()

            log_text.config(state="normal")
            log_text.delete("1.0", "end")
            log_text.insert("end", content)
            log_text.see("end")
            log_text.config(state="disabled")

        root.after(3000, update_logs)

    update_logs()

    root.mainloop()

#######################################
# FOR TESTING ONLY
#######################################
if __name__ == "__main__":
    open_settings()

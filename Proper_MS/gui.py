#==========
# IMPORTS
#==========

import os
import tkinter as tk
from tkinter import messagebox
from utils import resource_path
from dotenv import set_key, load_dotenv

#============================
# Load Environment Variables
#============================

CONFIG_FILE = resource_path(".env")
load_dotenv(CONFIG_FILE)

#=============
# All Methods
#=============

# SAVE EDITED VARIABLES IN ENV
def save_settings(entries):
    for key, var in entries.items():
        set_key(CONFIG_FILE, key, var.get())
    messagebox.showinfo("Saved", "Settings saved successfully!")

    from dotenv import load_dotenv
    load_dotenv(CONFIG_FILE, override=True)

# CREATES A WINDOW WITH THE FIELDS TO INTERACT WITH
def open_settings():
    root = tk.Tk()
    root.attributes("-topmost", True)                                                                                           # Keep window on top
    root.title("Settings")
    root.geometry("1280x720")

    entries = {}

    editable_variables= ['CLIENT_ID', 'TENANT_ID', 'AUTHORITY', 'SCOPES', 'CACHE_FILE', 'SENDER_EMAIL',                         # All Editable Variables
                         'KEYWORD_NAME', 'INTERVAL', 'SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_URL', 'ORG_NAME']
    
    for var in editable_variables:
        tk.Label(root, text=var).pack(anchor="w", padx=10)
        var_val = tk.StringVar()
        var_val.set(os.getenv(var, ""))
        entry = tk.Entry(root, textvariable=var_val, width=50)
        entry.pack(padx=10, pady=2)
        entries[var] = var_val

    # Save Button
    tk.Button(root, text="Save & Restart", command=lambda: save_settings(entries)).pack(pady=5)

    root.mainloop()
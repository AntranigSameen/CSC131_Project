#==========
# IMPORTS
#==========

import sys
import os

#=======
# LOGIC
#=======

# ===============
# Base Directory
# ===============

# Returns the base dir. Project Folder when through python and folder with EXE when running EXE
def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)

    return os.path.dirname(os.path.abspath(__file__))

# ================================
# Resource Path (for PyInstaller)
# ================================

# Get absolute path to resources. Works in development and packaged app
def resource_path(relative_path):
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = base_dir()

    return os.path.join(base_path, relative_path)

# ===============
# Logs Directory
# ===============

def logs_dir():
    path = os.path.join(base_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path

# =========
# Log File
# =========

def log_file():
    return os.path.join(logs_dir(), "app.log")
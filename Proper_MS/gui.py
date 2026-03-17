# ==========
# IMPORTS
# ==========

import os
import sys
import subprocess
import logging
from pathlib import Path

from dotenv import set_key, load_dotenv
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QGuiApplication, QTextCursor, QTextCharFormat, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QTabWidget,
                               QScrollArea, QLineEdit, QMessageBox, QPlainTextEdit, QFormLayout, QSystemTrayIcon, QMenu, QDialog, QDialogButtonBox,)

from utils import writable_env_file, base_dir, log_file, resource_path

# ============================
# LOAD ENVIRONMENT VARIABLES
# ============================

CONFIG_FILE = writable_env_file()                                                                                                     # Writable .env file used by GUI settings
load_dotenv(CONFIG_FILE)                                                                                                              # Load current .env values into environment

RESTART_REQUIRED = {                                                                                                                  # Settings that require restart after change
    "IS_HEADLESS",                                                                                                                    #
    "CLIENT_ID",                                                                                                                      #
    "TENANT_ID",                                                                                                                      #
    "AUTHORITY",                                                                                                                      #
    "SCOPES",                                                                                                                         #
    "CACHE_FILE",                                                                                                                     #
    "SERVICE_ACCOUNT_RQI_JSON",                                                                                                       #
    "SERVICE_ACCOUNT_AHA_JSON",                                                                                                       #
    "AHA_USERNAME",                                                                                                                   #
    "AHA_PASSWORD",                                                                                                                   #
}                                                                                                                                     # Settings that require restart after change


# ===============
# SAVE SETTINGS
# ===============

def save_settings(entries, restart=False):
    restart_needed = False                                                                                                            # Track whether any changed setting needs restart

    for key, widget in entries.items():
        new_value = widget.text()                                                                                                     # Value currently entered in GUI
        old_value = os.getenv(key, "")                                                                                                # Existing loaded env value

        if new_value != old_value and key in RESTART_REQUIRED:
            restart_needed = True                                                                                                     # Flag restart warning if important setting changed

        set_key(CONFIG_FILE, key, new_value)                                                                                          # Write updated setting into writable .env file

    load_dotenv(CONFIG_FILE, override=True)                                                                                           # Reload .env values into current process
    logging.info("Settings saved successfully")

    if restart:
        restart_application()                                                                                                         # Fully restart app if requested
    else:
        if restart_needed:
            QMessageBox.warning(
                None,
                "Restart Required",
                "Some changes require restarting the automation to take effect.",
            )
        else:
            QMessageBox.information(None, "Saved", "Settings saved successfully!")                                                    # Normal success popup


# =================
# RESTART PROGRAM
# =================

def restart_application():
    logging.info("Restarting application")
    exe_path = os.path.abspath(sys.executable)                                                                                        # Current executable path (pyinstaller exe or python)
    subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))                                                                       # Launch fresh copy of application
    os._exit(0)                                                                                                                       # Exit current process immediately


# =================
# SIGN OUT OF AHA
# =================

def sign_out():
    aha_auth_file = Path(base_dir()) / "aha_auth.json"                                                                                # Saved AHA authentication state file
    if aha_auth_file.exists():
        aha_auth_file.unlink()                                                                                                        # Delete saved login state so user must sign in again
        logging.info("User signed out: deleted AHA login state")
        QMessageBox.information(None, "Signed Out", "AHA login state cleared. You will need to sign in next time.",)

    else:
        QMessageBox.information(None, "Info", "No existing AHA login state to delete.",)

# ==========================
# FIRST RUN AHA CREDENTIALS
# ==========================

class AhaCredentialsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("AHA Login Required")
        self.setModal(True)
        self.resize(420, 190)                                                                                                         # Dialog size for first-run credential prompt

        layout = QVBoxLayout(self)

        info = QLabel("Enter your AHA username and password.\n"
                      "These will be saved to your .env file and used for future AHA logins.")
        
        info.setWordWrap(True)                                                                                                        # Allow explanatory text to wrap cleanly
        layout.addWidget(info)

        form = QFormLayout()

        self.username_edit = QLineEdit(os.getenv("AHA_USERNAME", ""))                                                                 # Pre-fill with existing username if present
        self.password_edit = QLineEdit(os.getenv("AHA_PASSWORD", ""))                                                                 # Pre-fill with existing password if present
        self.password_edit.setEchoMode(QLineEdit.Password)                                                                            # Hide password characters while typing

        form.addRow("AHA Username", self.username_edit)
        form.addRow("AHA Password", self.password_edit)

        layout.addLayout(form)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)                                           # Save or cancel buttons for first-run prompt
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def get_values(self):
        return self.username_edit.text().strip(), self.password_edit.text().strip()                                                   # Return cleaned username/password values


def save_single_setting(key, value):
    set_key(CONFIG_FILE, key, value)                                                                                                  # Save one key/value pair into writable .env file
    load_dotenv(CONFIG_FILE, override=True)                                                                                           # Reload current process environment after saving


def prompt_for_aha_credentials(parent=None):
    dialog = AhaCredentialsDialog(parent)                                                                                             # Create modal first-run AHA credential dialog

    while True:
        result = dialog.exec()

        if result != QDialog.Accepted:
            return False                                                                                                              # User cancelled prompt, so do not start automation

        username, password = dialog.get_values()

        if not username or not password:
            QMessageBox.warning(parent, "Missing Information", "Both AHA username and password are required.")
            continue                                                                                                                  # Keep prompting until both values are entered

        save_single_setting("AHA_USERNAME", username)                                                                                 # Save username to writable .env file
        save_single_setting("AHA_PASSWORD", password)                                                                                 # Save password to writable .env file
        logging.info("AHA credentials saved from first-run GUI prompt")
        return True                                                                                                                   # Credentials successfully saved

# ==============
# STATUS CARD
# ==============

class StatusCard(QFrame):
    def __init__(self, title: str, value: str = ""):
        super().__init__()
        self.setObjectName("StatusCard")                                                                                              # Used by stylesheet for card styling

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)                                                                                     # Inner padding for card content
        layout.setSpacing(4)                                                                                                          # Small spacing between title and value

        self.title_label = QLabel(title)
        self.title_label.setObjectName("StatusCardTitle")                                                                             # Used by stylesheet for title style

        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatusCardValue")                                                                             # Used by stylesheet for main value style

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, text: str):
        self.value_label.setText(text)                                                                                                # Update card value text

    def set_color(self, color: str):
        self.value_label.setStyleSheet(f"color: {color}; font-weight: 700;")                                                          # Update card value color


# ===================
# SCROLLABLE PAGE
# ===================

class ScrollablePage(QWidget):
    def __init__(self, child_widget: QWidget):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)                                                                                         # Remove extra outer margins

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)                                                                                               # Allow page to resize with window
        scroll.setWidget(child_widget)                                                                                                # Put actual page inside scroll area

        layout.addWidget(scroll)

# =================
# SYSTEM TRAY ICON
# =================

class AppTrayIcon(QSystemTrayIcon):
    def __init__(self, window, on_pause_resume=None, on_quit=None, get_pause_state=None):
        icon_path = resource_path("icon.png")                                                                                         # Path to tray icon image
        super().__init__(QIcon(icon_path), window)

        self.window = window                                                                                                          # Reference to main settings window
        self.on_pause_resume = on_pause_resume                                                                                        # Pause/resume callback from master_control
        self.on_quit = on_quit                                                                                                        # Quit callback from master_control
        self.get_pause_state = get_pause_state                                                                                        # Function used to decide button/menu text

        self.menu = QMenu()                                                                                                           # Tray right-click context menu

        self.settings_action = QAction("Settings", self)
        self.settings_action.triggered.connect(self.show_settings)                                                                    # Open main settings window
        self.menu.addAction(self.settings_action)

        self.logs_action = QAction("Open App Logs", self)
        self.logs_action.triggered.connect(self.open_logs)                                                                            # Open log file in notepad
        self.menu.addAction(self.logs_action)

        self.pause_action = QAction(self.pause_menu_text(), self)
        self.pause_action.triggered.connect(self.pause_resume_clicked)                                                                # Pause or resume automation
        self.menu.addAction(self.pause_action)

        self.menu.addSeparator()                                                                                                      # Visual separator before quit item

        self.quit_action = QAction("Quit", self)
        self.quit_action.triggered.connect(self.quit_clicked)                                                                         # Quit the whole application
        self.menu.addAction(self.quit_action)

        self.setContextMenu(self.menu)                                                                                                # Attach context menu to tray icon
        self.setToolTip("Complete Automation")                                                                                        # Tooltip shown on hover
        self.activated.connect(self.on_activated)                                                                                     # Left-click behavior for tray icon

    def pause_menu_text(self):
        if self.get_pause_state and self.get_pause_state():
            return "Resume Automation"                                                                                                # Show resume when currently paused
        return "Pause Automation"                                                                                                     # Show pause when currently running

    def refresh_pause_text(self):
        self.pause_action.setText(self.pause_menu_text())                                                                             # Refresh tray menu text after state change

    def show_settings(self):
        self.window.show()                                                                                                            # Show settings window if hidden
        self.window.raise_()                                                                                                          # Bring window to front
        self.window.activateWindow()                                                                                                  # Focus the window

    def open_logs(self):
        log_path = log_file()                                                                                                         # Shared application log file path
        if os.path.exists(log_path):
            subprocess.Popen(["notepad", log_path])                                                                                   # Open logs in Notepad on Windows
        else:
            logging.error("Log file not found: %s", log_path)

    def pause_resume_clicked(self):
        if self.on_pause_resume:
            self.on_pause_resume()                                                                                                    # Trigger pause/resume callback
        self.refresh_pause_text()                                                                                                     # Update tray menu label immediately

    def quit_clicked(self):
        if self.on_quit:
            self.on_quit()                                                                                                            # Use shared quit callback if available
        else:
            os._exit(0)                                                                                                               # Fallback immediate exit

    def on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_settings()                                                                                                      # Left-click tray icon opens settings window

# ==================
# MAIN WINDOW
# ==================

class SettingsWindow(QMainWindow):
    def __init__(self, on_pause_resume=None, on_quit=None, get_pause_state=None, on_ready=None):
        super().__init__()

        self.setWindowIcon(QIcon(resource_path("icon.png")))                                                                          # Set window icon in title bar/taskbar
        self.on_pause_resume = on_pause_resume                                                                                        # Callback for pause button
        self.on_quit = on_quit                                                                                                        # Callback for quit button
        self.get_pause_state = get_pause_state                                                                                        # Callback for current pause state
        self.entries = {}                                                                                                             # Stores all editable env QLineEdit widgets

        self.setWindowTitle("Automation Machine")
        self.resize(1360, 820)                                                                                                        # Default window size
        self.setMinimumSize(1120, 700)                                                                                                # Prevent window from getting too small

        self._log_position = 0                                                                                                        # Current file read position for incremental log loading
        self._log_initialized = False                                                                                                 # Tracks whether log viewer has been fully loaded once

        self._build_ui()                                                                                                              # Create all GUI widgets and layouts
        self._start_timers()                                                                                                          # Start automatic status/login/log refresh timers
    
    # ==================
    # TRAY NOTIFICATION
    # ==================

    def notify_tray(self, title: str, message: str):
        global _qt_tray
        if _qt_tray is not None:
            _qt_tray.showMessage(title, message, QSystemTrayIcon.Information, 3000)                                                   # Show temporary tray notification popup

    # ==========
    # BUILD UI
    # ==========

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)                                                                                                # Main central widget for window

        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)                                                                                       # Outer padding around whole interface
        root.setSpacing(10)                                                                                                           # Vertical spacing between major sections

        header = QVBoxLayout()
        title = QLabel("Automation Control Center")
        title.setObjectName("MainTitle")                                                                                              # Used by stylesheet for title formatting
        header.addWidget(title)
        root.addLayout(header)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)                                                                                                      # Space between top status cards

        self.automation_card = StatusCard("Automation", "Checking status...")                                                         # Shows running/paused state
        self.browser_card = StatusCard("Browser", "")                                                                                 # Shows headless vs visible browser
        self.interval_card = StatusCard("Interval", "")                                                                               # Shows current cycle interval
        self.queue_card = StatusCard("Queue", "")                                                                                     # Shows automation queue size

        cards_row.addWidget(self.automation_card)
        cards_row.addWidget(self.browser_card)
        cards_row.addWidget(self.interval_card)
        cards_row.addWidget(self.queue_card)

        root.addLayout(cards_row)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)                                                                                                         # Space between control buttons

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setObjectName("SaveButton")                                                                                     # Used by stylesheet for save button color

        self.pause_btn = QPushButton("Pause Automation")
        self.pause_btn.setObjectName("PauseButton")                                                                                   # Used by stylesheet for pause button color

        self.restart_btn = QPushButton("Restart App")
        self.restart_btn.setObjectName("RestartButton")                                                                               # Used by stylesheet for restart button color

        self.signout_btn = QPushButton("Sign Out of AHA")
        self.signout_btn.setObjectName("SignOutButton")                                                                               # Used by stylesheet for sign-out button color

        self.quit_btn = QPushButton("Quit")
        self.quit_btn.setObjectName("QuitButton")                                                                                     # Used by stylesheet for quit button color

        self.save_btn.clicked.connect(lambda: save_settings(self.entries, restart=False))                                             # Save .env changes without restarting
        self.pause_btn.clicked.connect(self._pause_resume_clicked)                                                                    # Pause/resume automation
        self.restart_btn.clicked.connect(restart_application)                                                                         # Restart whole app
        self.signout_btn.clicked.connect(sign_out)                                                                                    # Clear saved AHA login state
        self.quit_btn.clicked.connect(self._quit_clicked)                                                                             # Confirm and quit app

        toolbar.addWidget(self.save_btn)
        toolbar.addStretch(1)                                                                                                         # Push remaining buttons to the right
        toolbar.addWidget(self.pause_btn)
        toolbar.addWidget(self.restart_btn)
        toolbar.addWidget(self.signout_btn)
        toolbar.addWidget(self.quit_btn)

        root.addLayout(toolbar)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)                                                                                                  # Main tab area fills remaining window space

        self._build_overview_tab()                                                                                                    # Dashboard tab
        self._build_aha_tab()                                                                                                         # AHA credential tab
        self._build_email_tab()                                                                                                       # Email settings tab
        self._build_sheets_tab()                                                                                                      # Google Sheets settings tab
        self._build_auth_tab()                                                                                                        # Microsoft auth settings tab
        self._build_general_tab()                                                                                                     # General app settings tab
        self._build_logs_tab()                                                                                                        # Live log viewer tab

        self._apply_styles()                                                                                                          # Apply full application stylesheet

    # ==============
    # TAB BUILDERS
    # ==============

    def _build_overview_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.quick_status = QLabel("Checking status...")                                                                              # Quick automation status line
        self.quick_login = QLabel("Checking login state...")                                                                          # Quick AHA login status line
        self.quick_mode = QLabel("")                                                                                                  # Quick browser mode line
        self.quick_queue = QLabel("")                                                                                                 # Quick queue count line

        layout.addWidget(QLabel("Application Overview"))
        layout.addWidget(QLabel("Use this window to manage automation settings, monitor live status, review logs, and control the automation process."))
        layout.addSpacing(12)
        layout.addWidget(QLabel("Quick Status"))
        layout.addWidget(self.quick_status)
        layout.addWidget(self.quick_login)
        layout.addWidget(self.quick_mode)
        layout.addWidget(self.quick_queue)
        layout.addStretch(1)                                                                                                          # Push content upward

        self.tabs.addTab(ScrollablePage(page), "Overview")                                                                            # Add overview tab to tab widget

    def _build_aha_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        self.aha_login_label = QLabel("Checking login state...")                                                                      # Live label showing signed in/out state
        form.addRow("AHA Login Status:", self.aha_login_label)

        aha_user = QLineEdit(os.getenv("AHA_USERNAME", ""))                                                                           # Populate username from .env
        aha_pass = QLineEdit(os.getenv("AHA_PASSWORD", ""))                                                                           # Populate password from .env
        aha_pass.setEchoMode(QLineEdit.Password)                                                                                      # Hide password characters in GUI

        self.entries["AHA_USERNAME"] = aha_user                                                                                       # Save widget reference for later .env writeback
        self.entries["AHA_PASSWORD"] = aha_pass                                                                                       # Save widget reference for later .env writeback

        form.addRow("AHA Username", aha_user)
        form.addRow("AHA Password", aha_pass)

        self.tabs.addTab(ScrollablePage(page), "AHA Login")

    def _build_email_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        fields = {
            "SENDER_EMAIL": "Sender Email Address",
            "KEYWORD_NAME": "Keyword Before Name",
            "INTERVAL": "Automation Interval (seconds)",
        }                                                                                                                             # All editable email-related env fields

        for key, label in fields.items():
            edit = QLineEdit(os.getenv(key, ""))                                                                                      # Pre-fill each field from current .env
            self.entries[key] = edit                                                                                                  # Store widget by env variable name
            form.addRow(label, edit)

        self.tabs.addTab(ScrollablePage(page), "Email")

    def _build_sheets_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        fields = {
            "SERVICE_ACCOUNT_RQI_JSON": "RQI Service Account File",
            "SERVICE_ACCOUNT_AHA_JSON": "AHA Service Account File",
            "GOOGLE_SHEET_URL": "AHA Google Sheet URL",
            "SPREADSHEET_ID": "RQI Google Sheet ID",
        }                                                                                                                             # Google Sheets related env fields

        for key, label in fields.items():
            edit = QLineEdit(os.getenv(key, ""))                                                                                      # Pre-fill each field from current .env
            self.entries[key] = edit                                                                                                  # Store widget by env variable name
            form.addRow(label, edit)

        self.tabs.addTab(ScrollablePage(page), "Sheets")

    def _build_auth_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        fields = {                                                                                                                    # Microsoft authentication env fields
            "CLIENT_ID": "Azure Client ID",                                                                                           #
            "TENANT_ID": "Azure Tenant ID",                                                                                           #
            "AUTHORITY": "Highest Credential Access",                                                                                 #
            "SCOPES": "App Permissions",                                                                                              #
            "CACHE_FILE": "Cache File",                                                                                               #
        }                                                                                                                             # Microsoft authentication env fields

        for key, label in fields.items():
            edit = QLineEdit(os.getenv(key, ""))                                                                                      # Pre-fill each field from current .env
            self.entries[key] = edit                                                                                                  # Store widget by env variable name
            form.addRow(label, edit)

        self.tabs.addTab(ScrollablePage(page), "Authentication")

    def _build_general_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        fields = {
            "ORG_NAME": "Organization Name",
            "IS_HEADLESS": "Run Headless",
        }                                                                                                                             # General application env fields

        for key, label in fields.items():
            edit = QLineEdit(os.getenv(key, ""))                                                                                      # Pre-fill each field from current .env
            self.entries[key] = edit                                                                                                  # Store widget by env variable name
            form.addRow(label, edit)

        self.tabs.addTab(ScrollablePage(page), "General")

    def _build_logs_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Live Application Logs")
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)                                                                                               # Prevent editing log viewer contents
        self.log_text.setLineWrapMode(QPlainTextEdit.NoWrap)                                                                          # Preserve original log line formatting

        layout.addWidget(title)
        layout.addWidget(self.log_text)

        self.tabs.addTab(page, "System Logs")

    # =================
    # UI INTERACTIONS
    # =================

    def _pause_resume_clicked(self):
        global _qt_tray

        if self.on_pause_resume:
            self.on_pause_resume()                                                                                                    # Call shared pause/resume handler
        self._update_pause_button()                                                                                                   # Refresh button text after state change

        if _qt_tray is not None:
            _qt_tray.refresh_pause_text()                                                                                             # Keep tray text synced with button text

    def _quit_clicked(self):
        result = QMessageBox.question(
            self,
            "Quit",
            "Are you sure you want to quit the application?",
        )                                                                                                                             # Ask user to confirm quit action
        if result == QMessageBox.Yes:
            if self.on_quit:
                self.on_quit()                                                                                                        # Use shared quit callback
            else:
                os._exit(0)                                                                                                           # Fallback immediate exit

    def closeEvent(self, event):
        self.hide()                                                                                                                   # Hide window instead of fully closing app
        event.ignore()                                                                                                                # Keep app alive in system tray

    # ===============
    # UI REFRESHERS
    # ===============

    def _start_timers(self):
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._update_status)                                                                        # Refresh status cards and labels
        self.status_timer.start(2000)                                                                                                 # Every 2 seconds

        self.login_timer = QTimer(self)
        self.login_timer.timeout.connect(self._update_login_status)                                                                   # Refresh AHA sign-in state
        self.login_timer.start(2000)                                                                                                  # Every 2 seconds

        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self._update_logs)                                                                             # Refresh live log viewer
        self.log_timer.start(3000)                                                                                                    # Every 3 seconds

        self._update_status()                                                                                                         # Initial status refresh on startup
        self._update_login_status()                                                                                                   # Initial login refresh on startup
        self._update_logs()                                                                                                           # Initial log refresh on startup

    def _update_pause_button(self):
        global _qt_tray

        if self.get_pause_state and self.get_pause_state():
            self.pause_btn.setText("Resume Automation")                                                                               # Button text when currently paused
        else:
            self.pause_btn.setText("Pause Automation")                                                                                # Button text when currently running
        
        if _qt_tray is not None:
            _qt_tray.refresh_pause_text()                                                                                             # Keep tray menu text synced

    def _update_status(self):
        status_file = os.path.join(base_dir(), "automation_status.txt")                                                               # Status file written by master_control

        if os.path.exists(status_file):
            try:
                with open(status_file, "r", encoding="utf-8") as f:
                    raw_status = f.read().strip().upper()                                                                             # Normalize file text to uppercase
            except Exception:
                raw_status = "UNKNOWN"                                                                                                # Fall back if file read fails
        else:
            raw_status = "UNKNOWN"                                                                                                    # Fall back if status file missing

        if raw_status == "RUNNING":
            self.automation_card.set_value("Running")
            self.automation_card.set_color("#00bc8c")
            self.quick_status.setText("Running")
            self.quick_status.setStyleSheet("color: #00bc8c; font-weight: 700;")
        elif raw_status == "PAUSED":
            self.automation_card.set_value("Paused")
            self.automation_card.set_color("#f39c12")
            self.quick_status.setText("Paused")
            self.quick_status.setStyleSheet("color: #f39c12; font-weight: 700;")
        else:
            self.automation_card.set_value("Unknown")
            self.automation_card.set_color("#e64e30")
            self.quick_status.setText("Unknown")
            self.quick_status.setStyleSheet("color: #e64e30; font-weight: 700;")

        current_headless = os.getenv("IS_HEADLESS", "")                                                                               # Read current browser visibility setting
        if str(current_headless).strip().lower() in ("1", "true", "yes"):
            self.browser_card.set_value("Headless")
            self.browser_card.set_color("#5dade2")
            self.quick_mode.setText("Headless")
            self.quick_mode.setStyleSheet("color: #5dade2;")
        else:
            self.browser_card.set_value("Visible Browser")
            self.browser_card.set_color("#00bc8c")
            self.quick_mode.setText("Visible Browser")
            self.quick_mode.setStyleSheet("color: #00bc8c;")

        interval_text = os.getenv("INTERVAL", "")                                                                                     # Show current automation interval from env
        self.interval_card.set_value(f"{interval_text} sec")
        self.interval_card.set_color("#f39c12")

        queue_file = os.path.join(base_dir(), "queue_status.txt")                                                                     # Queue status file written by master_control
        if os.path.exists(queue_file):
            try:
                with open(queue_file, "r", encoding="utf-8") as f:
                    queue_count_int = int(f.read().strip())                                                                           # Parse queue count as integer
            except Exception:
                queue_count_int = -1                                                                                                  # Use -1 if file content is invalid
        else:
            queue_count_int = 0                                                                                                       # Default to zero when no file exists yet

        if queue_count_int < 0:
            self.queue_card.set_value("? task(s)")
            self.queue_card.set_color("#e64e30")
            self.quick_queue.setText("? task(s)")
            self.quick_queue.setStyleSheet("color: #e64e30;")
        else:
            self.queue_card.set_value(f"{queue_count_int} task(s)")
            self.quick_queue.setText(f"{queue_count_int} task(s)")

            if queue_count_int == 0:
                queue_color = "#00bc8c"                                                                                              # Green when queue empty
            elif 1 <= queue_count_int <= 3:
                queue_color = "#f39c12"                                                                                              # Orange when queue has a few tasks
            else:
                queue_color = "#e64e30"                                                                                              # Red when queue is getting large

            self.queue_card.set_color(queue_color)
            self.quick_queue.setStyleSheet(f"color: {queue_color};")

        self._update_pause_button()                                                                                                   # Keep pause button label synced with real state

    def _update_login_status(self):
        aha_auth_file = Path(base_dir()) / "aha_auth.json"                                                                            # Saved AHA auth state file
        if aha_auth_file.exists():
            text = "Signed In"
            color = "#00bc8c"
        else:
            text = "Not Signed In"
            color = "#adb5bd"

        self.aha_login_label.setText(text)                                                                                            # Update label on AHA tab
        self.aha_login_label.setStyleSheet(f"color: {color}; font-weight: 700;")
        self.quick_login.setText(text)                                                                                                # Update quick label on overview tab
        self.quick_login.setStyleSheet(f"color: {color};")

    # ===================
    # LOG VIEWER HELPERS
    # ===================

    def _is_log_near_bottom(self):
        scrollbar = self.log_text.verticalScrollBar()
        return scrollbar.value() >= scrollbar.maximum() - 20                                                                          # Treat near-bottom as auto-scroll zone

    def _append_log_line(self, line: str):
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)                                                                                          # Append all new logs to end of viewer

        fmt = QTextCharFormat()

        upper_line = line.upper()                                                                                                     # Normalize once for easier keyword checks

        if " - ERROR - " in upper_line or "ERROR:" in upper_line:                                                                     # Color for Error Logs
            fmt.setForeground(QColor("#e64e30"))

        elif " - WARNING - " in upper_line or "WARNING:" in upper_line:                                                               # Color for Warning Logs
            fmt.setForeground(QColor("#f39c12"))

        elif " - INFO - " in upper_line or "INFO:" in upper_line:                                                                     # Color for Info Logs
            fmt.setForeground(QColor("#5dade2"))

        else:                                                                                                                         # Color for Logs (default)
            fmt.setForeground(QColor("#d7dce2"))

        cursor.insertText(line, fmt)                                                                                                  # Insert line using selected color format

    def _append_log_text(self, text: str):
        if not text:
            return                                                                                                                    # Nothing to append

        lines = text.splitlines(keepends=True)                                                                                        # Preserve original line endings
        for line in lines:
            self._append_log_line(line)                                                                                               # Append each line with color formatting

    def _update_logs(self):
        current_log_file = log_file()                                                                                                 # Current live application log path

        if not os.path.exists(current_log_file):
            return                                                                                                                    # Do nothing if log file does not exist yet

        try:
            current_size = os.path.getsize(current_log_file)                                                                          # File size used to detect truncation/reset

            # If log file was truncated or recreated, reset viewer state
            if current_size < self._log_position:
                self._log_position = 0                                                                                                # Start reading from top again
                self._log_initialized = False                                                                                         # Force full reload on next read
                self.log_text.clear()                                                                                                 # Clear old displayed logs

            was_near_bottom = self._is_log_near_bottom()                                                                              # Decide whether to auto-scroll after append

            with open(current_log_file, "r", encoding="utf-8", errors="replace") as f:
                # First load: read entire file once
                if not self._log_initialized:
                    content = f.read()                                                                                                # Read complete log file on first load
                    self.log_text.clear()
                    self._append_log_text(content)
                    self._log_position = f.tell()                                                                                     # Save current end position
                    self._log_initialized = True                                                                                      # Mark log viewer as initialized

                    scrollbar = self.log_text.verticalScrollBar()
                    scrollbar.setValue(scrollbar.maximum())                                                                           # Scroll to bottom after initial full load

                else:
                    # Subsequent loads: append only new content
                    f.seek(self._log_position)                                                                                        # Jump to last-read position
                    new_text = f.read()                                                                                               # Read only newly added log text

                    if new_text:
                        self._append_log_text(new_text)

                        if was_near_bottom:
                            scrollbar = self.log_text.verticalScrollBar()
                            scrollbar.setValue(scrollbar.maximum())                                                                   # Keep following logs if user was already near bottom

                    self._log_position = f.tell()                                                                                     # Save updated read position

        except Exception as e:
            logging.exception("Error updating log viewer: %s", e)

    # =======
    # STYLES
    # =======

    def _apply_styles(self):                                                                                                          # Main dark theme stylesheet for the entire GUI
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1f22;
            }
            QLabel#MainTitle {
                color: white;
                font-size: 24px;
                font-weight: 700;
            }
            QFrame#StatusCard {
                background-color: #2b2d31;
                border: 1px solid #3b3d42;
                border-radius: 16px;
                padding: 6px;
            }
            QLabel#StatusCardTitle {
                color: #bfc5d2;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#StatusCardValue {
                color: white;
                font-size: 18px;
                font-weight: 700;
            }
            QTabWidget::pane {
                border: 1px solid #3b3d42;
                border-radius: 12px;
                background: #2b2d31;
            }
            QTabBar::tab {
                background: #2b2d31;
                color: #d7dce2;
                padding: 10px 16px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #3b82f6;
                color: white;
            }
            QPushButton {
                color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 16px;
                font-weight: 600;
                min-height: 18px;
            }

            QPushButton#SaveButton {background-color: #00bc8c;}
            QPushButton#SaveButton:hover {background-color: #17d7a0;}

            QPushButton#PauseButton {background-color: #f39c12;}
            QPushButton#PauseButton:hover {background-color: #ffb347;}

            QPushButton#RestartButton {background-color: #e67e22;}
            QPushButton#RestartButton:hover {background-color: #f39c12;}

            QPushButton#SignOutButton {background-color: #3498db;}
            QPushButton#SignOutButton:hover {background-color: #5dade2;}

            QPushButton#QuitButton {background-color: #e64e30;}
            QPushButton#QuitButton:hover {background-color: #ff6b57;}
            
            QPushButton:hover {background-color: #3b82f6;}
            
            QLineEdit {
                background-color: #1f2125;
                color: white;
                border: 1px solid #3b3d42;
                border-radius: 10px;
                padding: 8px;
            }
            QPlainTextEdit {
                background-color: #1f2125;
                color: #d7dce2;
                border: 1px solid #3b3d42;
                border-radius: 10px;
                padding: 8px;
                font-family: Consolas;
                font-size: 10pt;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

# ==========
# WINDOW ENTRY
# ==========

_qt_app = None                                                                                                                        # Shared QApplication instance
_qt_window = None                                                                                                                     # Shared main settings window instance
_qt_tray = None                                                                                                                       # Shared system tray icon instance

def open_settings(on_pause_resume=None, on_quit=None, get_pause_state=None, on_ready=None):
    global _qt_app, _qt_window, _qt_tray

    # Enable high DPI scaling
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)                              # Improve scaling on high DPI displays

    app = QApplication.instance()
    if app is None:
        _qt_app = QApplication(sys.argv)                                                                                              # Create QApplication only once
        app = _qt_app

        app.setApplicationName("Automation Machine")                                                                                  # App Name
        app.setOrganizationName("Sentient Grok")                                                                                      # App Creator Name
        app.setApplicationDisplayName("Automation Machine")                                                                           # App Display Name

        # Set global application icon
        icon_path = resource_path("icon.png")
        app.setWindowIcon(QIcon(icon_path))                                                                                           # Taskbar/application icon

    if _qt_window is None:
        _qt_window = SettingsWindow(on_pause_resume=on_pause_resume, on_quit=on_quit, get_pause_state=get_pause_state, on_ready=on_ready,)  # Create main window once

    if _qt_tray is None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            _qt_tray = AppTrayIcon(_qt_window, on_pause_resume=on_pause_resume, on_quit=on_quit, get_pause_state=get_pause_state,)    # Create tray icon once
            _qt_tray.show()                                                                                                           # Show tray icon in system tray

        else:
            logging.warning("System tray is not available on this system.")

    _qt_window.show()                                                                                                                 # Show main settings window
    _qt_window.raise_()                                                                                                               # Bring window to front
    _qt_window.activateWindow()                                                                                                       # Focus main window

    if on_ready:
        QTimer.singleShot(0, lambda: on_ready(_qt_window))                                                                            # Run startup bootstrap only after GUI event loop begins

    if _qt_app is not None:
        _qt_app.exec()                                                                                                                # Start Qt event loop when app was created here


# =============
# FOR TESTING
# =============

if __name__ == "__main__":
    open_settings()                                                                                                                   # Run GUI directly for standalone testing
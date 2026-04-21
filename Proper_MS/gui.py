# ==========
# IMPORTS
# ==========

import os
import sys
import subprocess
import logging
from pathlib import Path

from dotenv import set_key, load_dotenv
from PySide6.QtCore import Qt, QTimer, QSize, QRect, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QIcon, QGuiApplication, QTextCursor, QTextCharFormat, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QStackedWidget,
                               QScrollArea, QLineEdit, QMessageBox, QPlainTextEdit, QFormLayout, QSystemTrayIcon, QMenu, QDialog, QDialogButtonBox,
                               QToolButton, QSizePolicy, QGraphicsDropShadowEffect, QGridLayout, QFileDialog, QSpinBox, QSlider,)

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
    "SENDER_EMAIL",                                                                                                                   #
    "SENDER_EMAIL_RQI",                                                                                                               #
    "RQI_CSV_BATCH_MINUTES"                                                                                                           #
}                                                                                                                                     # Settings that require restart after change


# ===============
# SAVE SETTINGS
# ===============

def save_settings(entries, restart=False):
    restart_needed = False                                                                                                            # Track whether any changed setting needs restart

    for key, widget in entries.items():
        # Handle both QLineEdit (text()) and QSpinBox (value())
        if isinstance(widget, QSpinBox):
            new_value = str(widget.value())
        else:
            new_value = widget.text()                                                                                                 # Value currently entered in GUI
        
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
        layout.setContentsMargins(10, 8, 10, 8)                                                                                       # Inner padding for card content
        layout.setSpacing(2)                                                                                                          # Small spacing between title and value

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
    def __init__(self, window, on_toggle_pause_all=None, on_quit=None, get_pause_states=None):
        icon_path = resource_path("icon.png")                                                                                         # Path to tray icon image
        super().__init__(QIcon(icon_path), window)

        self.window = window                                                                                                          # Reference to main settings window
        self.on_toggle_pause_all = on_toggle_pause_all                                                                                # Pause/resume callback from master_control
        self.on_quit = on_quit                                                                                                        # Quit callback from master_control
        self.get_pause_states = get_pause_states                                                                                      # Function used to decide button/menu text

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
        pause_states = self.get_pause_states() if self.get_pause_states else {
            "all": False,
            "automation_loop": False,
            "email_to_sheets": False,
        }

        if pause_states["all"]:
            return "Resume All Automation"                                                                                            # Show resume when all automation is paused

        return "Pause All Automation"                                                                                                 # Show pause when all automation is running

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
        if self.on_toggle_pause_all:
            self.on_toggle_pause_all()                                                                                                # Trigger pause/resume callback
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
    def __init__(self, on_toggle_pause_all=None, on_toggle_pause_email=None,
                 on_toggle_pause_automation_loop=None, on_generate_rqi_csv=None,
                 on_upload_rqi_csv=None, on_refresh_rqi_upload_window=None,
                 get_rqi_csv_sftp_status=None, get_missing_sftp_fields=None,
                 on_quit=None, get_pause_states=None, on_ready=None,):
        super().__init__()

        self.setWindowIcon(QIcon(resource_path("icon.png")))                                                                          # Set window icon in title bar/taskbar

        self.on_toggle_pause_all = on_toggle_pause_all                                                                                # Callback for pausing/resuming all automation
        self.on_toggle_pause_email = on_toggle_pause_email                                                                            # Callback for pausing/resuming email_to_sheets
        self.on_toggle_pause_automation_loop = on_toggle_pause_automation_loop                                                        # Callback for pausing/resuming the main automation loop
        self.on_generate_rqi_csv = on_generate_rqi_csv                                                                                # Callback for manually generating the current RQI CSV batch
        self.on_upload_rqi_csv = on_upload_rqi_csv                                                                                    # Callback for manually uploading the latest RQI CSV batch to SFTP
        self.on_refresh_rqi_upload_window = on_refresh_rqi_upload_window                                                              # Callback for starting a brand-new RQI upload window immediately
        self.get_rqi_csv_sftp_status = get_rqi_csv_sftp_status                                                                        # Callback returning live CSV batch window status, last upload info, and upload errors
        self.get_missing_sftp_fields = get_missing_sftp_fields                                                                        # Callback returning missing SFTP settings before manual upload
        self.get_pause_states = get_pause_states                                                                                      # Callback returning all current pause states
        self.on_quit = on_quit                                                                                                        # Callback for quit button
        self.entries = {}                                                                                                             # Stores all editable env QLineEdit widgets

        self.selected_pause_target = "all"                                                                                            # Tracks which pause action the main split button should execute

        self.setWindowTitle("Automation Machine")
        self.resize(1360, 820)                                                                                                        # Default window size
        self.setMinimumSize(1120, 700)                                                                                                # Prevent window from getting too small

        self._log_position = 0                                                                                                        # Current file read position for incremental log loading
        self._log_initialized = False                                                                                                 # Tracks whether log viewer has been fully loaded once

        self._build_ui()                                                                                                              # Create all GUI widgets and layouts
        self._start_timers()                                                                                                          # Start automatic status/login/log refresh timers
    
    # ==================
    # BUTTON ANIMATIONS
    # ==================

    def _animate_button_press(self, button):
        start_rect = button.geometry()                                                                                                # Current button position and size

        pressed_rect = start_rect.adjusted(0, 2, 0, 2)                                                                                # Slightly shift button downward to simulate press

        anim = QPropertyAnimation(button, b"geometry")                                                                                # Animate the button geometry (position/size)
        anim.setDuration(60)                                                                                                          # Very fast animation for responsive feel
        anim.setStartValue(start_rect)                                                                                                # Start from normal position
        anim.setEndValue(pressed_rect)                                                                                                # End at "pressed down" position
        anim.setEasingCurve(QEasingCurve.OutQuad)                                                                                     # Smooth easing for natural motion

        def bounce_back():
            anim_back = QPropertyAnimation(button, b"geometry")                                                                       # Reverse animation to return to original position
            anim_back.setDuration(80)                                                                                                 # Match forward animation speed
            anim_back.setStartValue(pressed_rect)                                                                                     # Start from pressed position
            anim_back.setEndValue(start_rect)                                                                                         # Return to original position
            anim_back.setEasingCurve(QEasingCurve.OutQuad)                                                                            # Smooth easing on release
            anim_back.start()

            button._anim_back = anim_back                                                                                             # Store reference to prevent garbage collection

        anim.finished.connect(bounce_back)                                                                                            # When press animation finishes, bounce back
        anim.start()

        button._anim = anim                                                                                                           # Store reference to prevent garbage collection

    # ==================
    # TRAY NOTIFICATION
    # ==================

    def notify_tray(self, title: str, message: str):
        global _qt_tray
        if _qt_tray is not None:
            _qt_tray.showMessage(title, message, QSystemTrayIcon.Information, 3000)                                                   # Show temporary tray notification popup

    # ==============
    # SIDEBAR SETUP
    # ==============

    def _set_sidebar_page(self, index):
        self.page_stack.setCurrentIndex(index)                                                                                        # Show the selected page in the main content area

        for i, button in enumerate(self.sidebar_buttons):
            is_active = (i == index)
            button.setChecked(is_active)                                                                                              # Highlight only the currently selected sidebar button

            if is_active:
                glow = QGraphicsDropShadowEffect(self)
                glow.setBlurRadius(18)                                                                                                # Soft active glow around selected sidebar button
                glow.setOffset(0, 0)
                button.setGraphicsEffect(glow)
            else:
                button.setGraphicsEffect(None)                                                                                        # Remove glow from non-active buttons

        self._move_sidebar_indicator(index)                                                                                           # Move selected sidebar pill to the active button

    def _add_sidebar_page(self, page_widget, tooltip_text, icon_text):
        page_index = self.page_stack.addWidget(page_widget)                                                                           # Add page to stacked content area

        button = QToolButton()
        button.setObjectName("SidebarButton")
        button.setText(icon_text)                                                                                                     # Use emoji/icon text inside circular sidebar button
        button.setToolTip(tooltip_text)                                                                                               # Show page name when user hovers over icon
        button.setCheckable(True)                                                                                                     # Allow active/selected button styling
        button.setFixedSize(44, 44)                                                                                                   # Make sidebar button circular
        button.setIconSize(QSize(18, 18))                                                                                             # Keep icon/text visually centered
        button.clicked.connect(lambda checked=False, idx=page_index: self._set_sidebar_page(idx))                                     # Switch stacked page when icon is clicked

        self.sidebar_buttons.append(button)                                                                                           # Store sidebar buttons so selected state can be updated
        self.sidebar_layout.addWidget(button)                                                                                         # Add circular icon button to left sidebar

    def _toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed                                                                           # Flip between expanded and collapsed sidebar states

        if self.sidebar_collapsed:
            self.sidebar_frame.setFixedWidth(22)                                                                                      # Collapse sidebar down to a very thin rail
            self.collapse_button.setText("»")                                                                                         # Show expand arrow while collapsed
            self.collapse_button.setToolTip("Expand Sidebar")

            for button in self.sidebar_buttons:
                button.hide()                                                                                                         # Hide all sidebar page buttons when collapsed

            self.sidebar_indicator.hide()                                                                                             # Hide active page indicator when sidebar is collapsed

            self.collapse_button.setFixedSize(16, 48)                                                                                 # Tall narrow expand button for collapsed state
            self.collapse_button.setStyleSheet("")                                                                                    # Let normal stylesheet apply cleanly

        else:
            self.sidebar_frame.setFixedWidth(68)                                                                                      # Restore normal sidebar width when expanded
            self.collapse_button.setText("«")                                                                                         # Show collapse arrow while expanded
            self.collapse_button.setToolTip("Collapse Sidebar")

            self.collapse_button.setFixedSize(44, 28)                                                                                 # Restore top toggle button size

            for button in self.sidebar_buttons:
                button.show()                                                                                                         # Show sidebar page buttons again when expanded
                button.setFixedSize(44, 44)                                                                                           # Restore small circular button size
                button.setStyleSheet("font-size: 18px;")                                                                              # Restore normal emoji size

            self.sidebar_indicator.show()                                                                                             # Show active page indicator again
            self._move_sidebar_indicator(self.page_stack.currentIndex())                                                              # Re-align active page indicator after expanding

    def _move_sidebar_indicator(self, index):
        if not self.sidebar_buttons:
            return                                                                                                                    # Nothing to move if no sidebar buttons exist yet

        if index < 0 or index >= len(self.sidebar_buttons):
            return                                                                                                                    # Ignore invalid page index

        button = self.sidebar_buttons[index]
        button_y = button.y()                                                                                                         # Vertical position of selected sidebar button
        button_h = button.height()                                                                                                    # Height of selected sidebar button

        pill_height = max(24, button_h - 10)                                                                                          # Make selected pill slightly smaller than the button
        pill_y = button_y + (button_h - pill_height) // 2                                                                             # Center pill vertically beside selected button

        self.sidebar_indicator.setGeometry(4, pill_y, 4, pill_height)                                                                 # Move left-side selection pill to active button


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._move_sidebar_indicator(self.page_stack.currentIndex())                                                                  # Keep selected pill aligned when window is resized

    # ==========
    # BUILD UI
    # ==========

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)                                                                                                # Main central widget for window

        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)                                                                                       # Outer padding around whole interface
        root.setSpacing(10)                                                                                                           # Vertical spacing between major sections

        # ==============
        # Card Creation
        # ==============

        self.automation_card = StatusCard("Automation", "Checking status...")                                                         # Shows running/paused state
        self.browser_card = StatusCard("Browser", "")                                                                                 # Shows headless vs visible browser
        self.interval_card = StatusCard("Interval", "")                                                                               # Shows current cycle interval
        self.queue_card = StatusCard("Queue", "")                                                                                     # Shows automation queue size

        for card in [self.automation_card, self.browser_card, self.interval_card, self.queue_card]:
            card.setMinimumWidth(160)                                                                                                 # Keep dashboard cards compact
            card.setMaximumWidth(200)                                                                                                 # Prevent cards from stretching too wide
            card.setFixedHeight(78)                                                                                                   # Force all four cards to the same height so the 2x2 grid is predictable

        # ======================
        # Top Left Status Cards
        # ======================

        cards_grid = QGridLayout()
        cards_grid.setContentsMargins(0, 0, 0, 0)                                                                                     # Keep top-left card block tight
        cards_grid.setHorizontalSpacing(10)                                                                                           # Space between left/right cards
        cards_grid.setVerticalSpacing(10)                                                                                             # Space between top/bottom cards

        cards_grid.addWidget(self.automation_card, 0, 0)                                                                              # Top-left status card
        cards_grid.addWidget(self.browser_card, 0, 1)                                                                                 # Top-right status card
        cards_grid.addWidget(self.interval_card, 1, 0)                                                                                # Bottom-left status card
        cards_grid.addWidget(self.queue_card, 1, 1)                                                                                   # Bottom-right status card

        left_top_panel = QWidget()
        left_top_layout = QVBoxLayout(left_top_panel)
        left_top_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)                                                            # Keep card grid tightly sized
        left_top_panel.setFixedHeight(166)                                                                                            # Match the visual height of the mini log panel
        left_top_layout.setContentsMargins(0, 0, 0, 0)
        left_top_layout.setSpacing(10)
        left_top_layout.addLayout(cards_grid)                                                                                         # Compact 2x2 grid of mini cards

        # ===============================
        # Top Right Mini Live Log Viewer
        # ===============================

        mini_logs_panel = QFrame()
        mini_logs_panel.setObjectName("MiniLogsPanel")                                                                                # Styled compact log viewer panel for top-right area
        mini_logs_panel.setFixedHeight(166)                                                                                           # Set Live Logs panel to match height of cards grid

        mini_logs_layout = QVBoxLayout(mini_logs_panel)
        mini_logs_layout.setContentsMargins(10, 8, 10, 8)                                                                             # Compact inner padding so log box fits cleanly inside the fixed-height panel
        mini_logs_layout.setSpacing(4)

        mini_logs_title = QLabel("Live Logs")
        mini_logs_title.setObjectName("MiniLogsTitle")                                                                                # Small heading above top-right log preview

        self.mini_log_text = QPlainTextEdit()
        self.mini_log_text.setObjectName("MiniLogText")                                                                               # Separate styling hook for compact top log viewer
        self.mini_log_text.setReadOnly(True)                                                                                          # Prevent editing the compact log preview
        self.mini_log_text.setLineWrapMode(QPlainTextEdit.NoWrap)                                                                     # Preserve original log line formatting
        self.mini_log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)                                                # Fill available space inside panel
        self.mini_log_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)                                                        # Hide horizontal scrollbar in compact preview
        self.mini_log_text.setPlaceholderText("Recent log lines will appear here...")

        mini_logs_layout.addWidget(mini_logs_title)
        mini_logs_layout.addWidget(self.mini_log_text)

        # =========================
        # Top dashboard row
        # =========================

        top_dashboard_row = QHBoxLayout()
        top_dashboard_row.setContentsMargins(0, 0, 0, 0)
        top_dashboard_row.setSpacing(14)

        top_dashboard_row.addWidget(left_top_panel, 0)                                                                                # Top-left compact status card block
        top_dashboard_row.addWidget(mini_logs_panel, 1)                                                                               # Top-right mini live log viewer takes remaining width
        mini_logs_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)                                                       # Prevent vertical stretching of log panel

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setObjectName("SaveButton")                                                                                     # Used by stylesheet for save button

        self.restart_btn = QPushButton("Restart App")
        self.restart_btn.setObjectName("RestartButton")                                                                               # Used by stylesheet for restart button
        self.restart_btn.setFixedHeight(26)

        self.quit_btn = QPushButton("Quit")
        self.quit_btn.setObjectName("QuitButton")                                                                                     # Used by stylesheet for quit button
        self.quit_btn.setFixedHeight(26)

        self.signout_btn = QPushButton("Sign Out of AHA")
        self.signout_btn.setObjectName("SignOutButton")                                                                               # Used by stylesheet for sign-out button
        self.signout_btn.setFixedHeight(28)                                                                                           # Set the AHA sign-out button height
        self.signout_btn.setMinimumWidth(110)                                                                                         # Keep button compact without shrinking text too aggressively
        self.signout_btn.setMaximumWidth(130)                                                                                         # Prevent button from stretching too wide

        self.aha_required_label = QLabel("AHA login required")
        self.aha_required_label.setObjectName("AHARequiredLabel")                                                                     # Red warning label shown when no AHA login exists
        self.aha_required_label.hide()                                                                                                # Hidden by default until login check says it is needed

        # =========================
        # Top-right AHA Status Row
        # =========================

        aha_row = QHBoxLayout()
        aha_row.setContentsMargins(0, 0, 0, 0)
        aha_row.setSpacing(6)

        aha_row.addStretch(1)                                                                                                         # Push AHA controls toward the right side
        aha_row.addWidget(self.signout_btn, 0, Qt.AlignVCenter)                                                                       # Standalone AHA sign-out button, centered vertically
        aha_row.addWidget(self.aha_required_label, 0, Qt.AlignVCenter)                                                                # Red warning text appears when AHA login is missing, aligned with button


        self.pause_btn = QPushButton("Pause All")
        self.pause_btn.setObjectName("PauseButton")                                                                                   # Main quick-action button for pausing/resuming all automation
        self.pause_btn.setFixedHeight(24)
        self.pause_btn.setMinimumWidth(112)

        self.pause_menu_btn = QToolButton()
        self.pause_menu_btn.setFixedWidth(24)                                                                                         # Narrow arrow button
        self.pause_menu_btn.setFixedHeight(24)
        self.pause_menu_btn.setStyleSheet("padding: 0px; margin: 0px;")
        self.pause_menu_btn.setObjectName("PauseMenuButton")                                                                          # Small dropdown arrow button next to Pause All
        self.pause_menu_btn.setText("☰")
        self.pause_menu_btn.setPopupMode(QToolButton.InstantPopup)                                                                    # Open menu immediately on click

        self.pause_menu = QMenu(self)

        self.pause_all_action = QAction("Pause All Automation", self)
        self.pause_all_action.triggered.connect(lambda: self._select_pause_target("all"))                                             # Select Pause All for the main split button

        self.pause_email_action = QAction("Pause RQI Email Parsing", self)
        self.pause_email_action.triggered.connect(lambda: self._select_pause_target("email"))                                         # Select RQI Email Parsing for the main split button

        self.pause_loop_action = QAction("Pause AHA Automation", self)
        self.pause_loop_action.triggered.connect(lambda: self._select_pause_target("automation_loop"))                                # Select AHA Automation for the main split button

        self.pause_menu.addAction(self.pause_all_action)
        self.pause_menu.addAction(self.pause_email_action)
        self.pause_menu.addAction(self.pause_loop_action)

        self.pause_menu_btn.setMenu(self.pause_menu)


        self.save_btn.clicked.connect(lambda: self._animate_button_press(self.save_btn))                                              # Animate press before save
        self.save_btn.clicked.connect(lambda: save_settings(self.entries, restart=False))                                             # Save .env changes without restarting
        self.pause_btn.clicked.connect(lambda: self._animate_button_press(self.pause_btn))                                            # Animate press before pause
        self.pause_btn.clicked.connect(self._run_selected_pause_action)                                                               # Main button acts as quick toggle for Pause All
        self.restart_btn.clicked.connect(lambda: self._animate_button_press(self.restart_btn))                                        # Animate press before restart
        self.restart_btn.clicked.connect(restart_application)                                                                         # Restart whole app
        self.signout_btn.clicked.connect(lambda: self._animate_button_press(self.signout_btn))                                        # Animate press before sign out
        self.signout_btn.clicked.connect(sign_out)                                                                                    # Clear saved AHA login state
        self.quit_btn.clicked.connect(lambda: self._animate_button_press(self.quit_btn))                                              # Animate press before quit
        self.quit_btn.clicked.connect(self._quit_clicked)                                                                             # Confirm and quit app

        # =========================
        # Main action buttons row
        # =========================

        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(4)
        controls_row.addStretch(1)                                                                                                    # Keep restart/quit aligned away from Save
        controls_row.addWidget(self.restart_btn)                                                                                      # Restart the whole application
        controls_row.addWidget(self.quit_btn)                                                                                         # Quit the application

        pause_control = QWidget()
        pause_control_layout = QHBoxLayout(pause_control)
        pause_control_layout.setContentsMargins(0, 0, 0, 0)
        pause_control_layout.setSpacing(0)                                                                                            # Keep button and dropdown arrow tightly joined

        pause_control_layout.addWidget(self.pause_btn)
        pause_control_layout.addWidget(self.pause_menu_btn)

        mini_logs_layout.addWidget(pause_control, 0, Qt.AlignRight)                                                                   # Pause All control under the mini logs on the right side

        root.addLayout(aha_row)                                                                                                       # Separate AHA sign-out + warning near top
        root.addLayout(top_dashboard_row)                                                                                             # Top-left cards + top-right mini logs
        root.addLayout(controls_row)                                                                                                  # Save / Restart / Quit row

        content_row = QHBoxLayout()
        content_row.setSpacing(6)                                                                                                     # Tight spacing between sidebar and main content

        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("SidebarFrame")                                                                              # Styled container for left-side circular navigation buttons
        self.sidebar_frame.setFixedWidth(68)                                                                                          # Thin sidebar width for compact icon rail
        self.sidebar_collapsed = False                                                                                                # Track whether sidebar is collapsed

        self.sidebar_layout = QVBoxLayout(self.sidebar_frame)
        self.sidebar_layout.setContentsMargins(10, 10, 10, 10)
        self.sidebar_layout.setSpacing(10)                                                                                            # Tight spacing between smaller circular buttons
        self.sidebar_layout.setAlignment(Qt.AlignTop)

        self.collapse_button = QToolButton()
        self.collapse_button.setObjectName("SidebarCollapseButton")
        self.collapse_button.setText("«")                                                                                             # Collapse arrow shown at top of sidebar
        self.collapse_button.setToolTip("Collapse Sidebar")
        self.collapse_button.setFixedSize(44, 28)
        self.collapse_button.clicked.connect(self._toggle_sidebar)                                                                    # Collapse or expand left sidebar when clicked
        self.sidebar_layout.addWidget(self.collapse_button, alignment=Qt.AlignTop | Qt.AlignHCenter)                                  # Keep collapse/expand button pinned at the top of the sidebar

        self.sidebar_indicator = QFrame(self.sidebar_frame)
        self.sidebar_indicator.setObjectName("SidebarIndicator")                                                                      # Vertical pill showing which page is currently selected
        self.sidebar_indicator.setGeometry(QRect(4, 60, 4, 24))
        self.sidebar_indicator.raise_()

        self.sidebar_buttons = []                                                                                                     # Keep references so selected sidebar button can be highlighted

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("ContentStack")                                                                                 # Main right-side content area that replaces QTabWidget

        self.right_content_panel = QWidget()
        self.right_content_layout = QVBoxLayout(self.right_content_panel)
        self.right_content_layout.setContentsMargins(0, 0, 0, 0)
        self.right_content_layout.setSpacing(10)                                                                                      # Space between tab content area and centered Save button

        self.right_content_layout.addWidget(self.page_stack, 1)                                                                       # Main tab content takes all remaining vertical space

        save_footer_row = QHBoxLayout()
        save_footer_row.setContentsMargins(0, 0, 0, 0)
        save_footer_row.addStretch(1)                                                                                                 # Center the Save button at the bottom of the tab area
        save_footer_row.addWidget(self.save_btn)                                                                                      # Shared Save Settings button shown inside all tabs
        save_footer_row.addStretch(1)

        self.right_content_layout.addLayout(save_footer_row)                                                                          # Add centered Save button under the page stack

        content_row.addWidget(self.sidebar_frame)
        content_row.addWidget(self.right_content_panel, 1)                                                                            # Right-side panel now contains both page stack and bottom Save button

        root.addLayout(content_row, 1)

        self._build_csv_sftp_tab()                                                                                                    # RQI CSV & SFTP page
        self._build_aha_tab()                                                                                                         # AHA credentials page
        self._build_email_tab()                                                                                                       # Email settings page
        self._build_sheets_tab()                                                                                                      # Google Sheets settings page
        self._build_auth_tab()                                                                                                        # Microsoft authentication settings page
        self._build_general_tab()                                                                                                     # General settings page
        self._build_logs_tab()                                                                                                        # Live logs page

        if self.sidebar_buttons:
            self._set_sidebar_page(0)                                                                                                 # Start on the RQI CSV & SFTP page when GUI opens
            QTimer.singleShot(0, lambda: self._move_sidebar_indicator(0))                                                             # Reposition selected pill after layout finishes

        self._apply_styles()                                                                                                          # Apply full application stylesheet

    # ==============
    # TAB BUILDERS
    # ==============

    # ===================
    # RQI CSV & SFTP TAB
    # ===================

    def _build_csv_sftp_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)                                                                                                         # Comfortable spacing between sections in the renamed RQI export dashboard

        title = QLabel("RQI CSV / SFTP")
        title.setObjectName("SectionTitle")                                                                                           # Main heading for RQI export controls shown only on this tab

        subtitle = QLabel(
            "Manage the RQI CSV export folder, time-window batching, and manual SFTP actions from this page."
        )
        subtitle.setWordWrap(True)                                                                                                    # Allow explanatory text to wrap naturally inside the content area
        subtitle.setObjectName("SectionSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        export_form = QFormLayout()
        export_form.setLabelAlignment(Qt.AlignLeft)
        export_form.setFormAlignment(Qt.AlignTop)
        export_form.setSpacing(10)                                                                                                    # Keep form rows readable without taking too much vertical space

        # =========================
        # Quick live status labels
        # =========================

        self.quick_status = QLabel("Checking status...")                                                                              # Quick automation status line used by existing refresh logic
        self.quick_login = QLabel("Checking login state...")                                                                          # Quick AHA login status line used by existing refresh logic
        self.quick_mode = QLabel("")                                                                                                  # Quick browser mode line used by existing refresh logic
        self.quick_queue = QLabel("")                                                                                                 # Quick queue count line used by existing refresh logic

        self.quick_status.hide()                                                                                                      # Do not show automation status inside the RQI CSV / SFTP tab
        self.quick_login.hide()                                                                                                       # Do not show AHA login inside the RQI CSV / SFTP tab
        self.quick_mode.hide()                                                                                                        # Do not show browser mode inside the RQI CSV / SFTP tab
        self.quick_queue.hide()                                                                                                       # Do not show queue count inside the RQI CSV / SFTP tab

        # ====================
        # CSV export settings
        # ====================

        export_dir_row = QWidget()
        export_dir_layout = QHBoxLayout(export_dir_row)
        export_dir_layout.setContentsMargins(0, 0, 0, 0)
        export_dir_layout.setSpacing(8)

        export_dir_edit = QLineEdit(os.getenv("RQI_CSV_EXPORT_DIR", ""))                                                             # Root folder where time-window CSV subfolders will be created
        self.entries["RQI_CSV_EXPORT_DIR"] = export_dir_edit                                                                          # Save widget reference so Save Settings writes it into the shared .env file

        browse_export_dir_btn = QPushButton("Browse")
        browse_export_dir_btn.setObjectName("BrowseButton")                                                                          # Small helper button for choosing export folder from file dialog
        browse_export_dir_btn.clicked.connect(lambda: self._animate_button_press(browse_export_dir_btn))                             # Animate press before folder chooser opens
        browse_export_dir_btn.clicked.connect(self._browse_rqi_export_dir)                                                           # Open folder chooser and write result into export path field

        export_dir_layout.addWidget(export_dir_edit, 1)
        export_dir_layout.addWidget(browse_export_dir_btn)

        export_form.addRow("CSV Export Folder", export_dir_row)

        csv_filename_edit = QLineEdit(os.getenv("RQI_CSV_FILENAME", "rqi_export.csv"))                                               # Fixed file name used inside each date/time upload-window folder
        self.entries["RQI_CSV_FILENAME"] = csv_filename_edit
        export_form.addRow("CSV File Name", csv_filename_edit)

        batch_minutes_edit = QLineEdit(os.getenv("RQI_CSV_BATCH_MINUTES", "15"))                                                     # Number of minutes per automatic CSV batch window
        self.entries["RQI_CSV_BATCH_MINUTES"] = batch_minutes_edit
        export_form.addRow("Batch Minutes", batch_minutes_edit)

        layout.addLayout(export_form)

        layout.addSpacing(6)

        # =========================
        # SFTP connection settings
        # =========================

        sftp_title = QLabel("SFTP Settings")
        sftp_title.setObjectName("SectionSubtitle")                                                                                   # Secondary heading for remote upload settings
        layout.addWidget(sftp_title)

        sftp_form = QFormLayout()
        sftp_form.setLabelAlignment(Qt.AlignLeft)
        sftp_form.setFormAlignment(Qt.AlignTop)
        sftp_form.setSpacing(10)

        sftp_fields = {
            "RQI_SFTP_HOST": "Host Name",
            "RQI_SFTP_PORT": "Port",
            "RQI_SFTP_USERNAME": "Username",
            "RQI_SFTP_REMOTE_PATH": "Remote File Path",
            "RQI_SFTP_FILE_NAME": "Remote File Name",
            "RQI_SFTP_FILE_TYPE": "Remote File Type",
        }                                                                                                                             # Non-password SFTP settings shown as normal line edits

        for key, label in sftp_fields.items():
            edit = QLineEdit(os.getenv(key, ""))
            self.entries[key] = edit                                                                                                  # Save widget reference so Save Settings writes it into the shared .env file
            sftp_form.addRow(label, edit)

        sftp_password_edit = QLineEdit(os.getenv("RQI_SFTP_PASSWORD", ""))
        sftp_password_edit.setEchoMode(QLineEdit.Password)                                                                            # Hide SFTP password in the GUI the same way AHA password is hidden
        self.entries["RQI_SFTP_PASSWORD"] = sftp_password_edit
        sftp_form.addRow("Password", sftp_password_edit)

        layout.addLayout(sftp_form)
        layout.addSpacing(8)

        # =======================
        # Live CSV / SFTP status
        # =======================

        csv_status_title = QLabel("Live CSV / Upload Status")
        csv_status_title.setObjectName("SectionSubtitle")                                                                             # Secondary heading for current batch window and upload status information
        layout.addWidget(csv_status_title)

        csv_status_form = QFormLayout()
        csv_status_form.setLabelAlignment(Qt.AlignLeft)
        csv_status_form.setFormAlignment(Qt.AlignTop)
        csv_status_form.setSpacing(10)

        self.rqi_batch_window_label = QLabel("Loading...")                                                                            # Shows current active batch window start and end time
        self.rqi_batch_countdown_label = QLabel("Loading...")                                                                         # Shows live countdown until current batch window ends
        self.rqi_current_csv_label = QLabel("Loading...")                                                                             # Shows currently active CSV batch file path
        self.rqi_last_uploaded_local_label = QLabel("None yet")                                                                       # Shows most recent local CSV file that was uploaded successfully
        self.rqi_last_uploaded_remote_label = QLabel("None yet")                                                                      # Shows most recent remote SFTP destination used successfully
        self.rqi_last_upload_time_label = QLabel("None yet")                                                                          # Shows timestamp of most recent successful upload
        self.rqi_last_upload_error_label = QLabel("")                                                                                 # Shows most recent upload error for debugging/feedback when upload fails

        for status_label in [
            self.rqi_batch_window_label,
            self.rqi_batch_countdown_label,
            self.rqi_current_csv_label,
            self.rqi_last_uploaded_local_label,
            self.rqi_last_uploaded_remote_label,
            self.rqi_last_upload_time_label,
            self.rqi_last_upload_error_label,
        ]:
            status_label.setWordWrap(True)                                                                                            # Allow long file paths and error messages to wrap cleanly inside the tab

        csv_status_form.addRow("Current Batch Window", self.rqi_batch_window_label)
        csv_status_form.addRow("Time Remaining", self.rqi_batch_countdown_label)
        csv_status_form.addRow("Current CSV File", self.rqi_current_csv_label)
        csv_status_form.addRow("Last Uploaded Local File", self.rqi_last_uploaded_local_label)
        csv_status_form.addRow("Last Uploaded Remote Path", self.rqi_last_uploaded_remote_label)
        csv_status_form.addRow("Last Upload Time", self.rqi_last_upload_time_label)
        csv_status_form.addRow("Last Upload Error", self.rqi_last_upload_error_label)

        layout.addLayout(csv_status_form)
        layout.addSpacing(10)

        # ======================
        # Manual action buttons
        # ======================

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        self.generate_rqi_csv_btn = QPushButton("Generate CSV Now")
        self.generate_rqi_csv_btn.setObjectName("ActionButton")                                                                       # Manual action button shown only on the csv_sftp tab
        self.generate_rqi_csv_btn.clicked.connect(lambda: self._animate_button_press(self.generate_rqi_csv_btn))                      # Animate press before manual CSV generation
        self.generate_rqi_csv_btn.clicked.connect(self._generate_rqi_csv_clicked)                                                     # Trigger backend CSV generation callback

        self.upload_rqi_csv_btn = QPushButton("Upload to SFTP Now")
        self.upload_rqi_csv_btn.setObjectName("ActionButton")                                                                         # Manual action button shown only on the csv_sftp tab
        self.upload_rqi_csv_btn.clicked.connect(lambda: self._animate_button_press(self.upload_rqi_csv_btn))                          # Animate press before manual upload
        self.upload_rqi_csv_btn.clicked.connect(self._upload_rqi_csv_clicked)                                                         # Trigger backend SFTP upload callback

        self.refresh_rqi_window_btn = QPushButton("Refresh Upload Window")
        self.refresh_rqi_window_btn.setObjectName("ActionButton")                                                                     # Manual action button shown only on the csv_sftp tab
        self.refresh_rqi_window_btn.clicked.connect(lambda: self._animate_button_press(self.refresh_rqi_window_btn))                  # Animate press before refreshing the upload window
        self.refresh_rqi_window_btn.clicked.connect(self._refresh_rqi_upload_window_clicked)                                          # Trigger backend upload-window refresh callback

        action_row.addWidget(self.generate_rqi_csv_btn)
        action_row.addWidget(self.upload_rqi_csv_btn)
        action_row.addWidget(self.refresh_rqi_window_btn)
        action_row.addStretch(1)                                                                                                      # Keep manual action buttons aligned neatly on the left

        layout.addLayout(action_row)
        layout.addStretch(1)                                                                                                          # Push all RQI export controls upward inside the page

        self._add_sidebar_page(ScrollablePage(page), "RQI CSV / SFTP", "🏠")                                                         # Add sidebar page for RQI CSV & SFTP tab

    # ==============
    # AHA LOGIN TAB
    # ==============

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

        self._add_sidebar_page(ScrollablePage(page), "AHA Login", "🔐")                                                               # Add AHA login page to sidebar navigation

    # ================
    # EMAIL LOGIN TAB
    # ================

    def _build_email_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        fields = {
            "SENDER_EMAIL": "Sender Email Address",
            "KEYWORD_NAME": "Keyword Before Name",
            "INTERVAL": "Automation Interval (seconds)",

            "SENDER_EMAIL_RQI": "Sender Email for RQI Parsing",
        }                                                                                                                             # All editable email-related env fields

        for key, label in fields.items():
            edit = QLineEdit(os.getenv(key, ""))                                                                                      # Pre-fill each field from current .env
            self.entries[key] = edit                                                                                                  # Store widget by env variable name
            form.addRow(label, edit)

        self._add_sidebar_page(ScrollablePage(page), "Email", "📧")                                                                  # Add Email settings page to sidebar navigation

    # ==================
    # GOOGLE SHEETS TAB
    # ==================

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

        # Reminder cadence for non-registered Acuity users (x days)
        not_registered_days = QSpinBox()
        not_registered_days.setMinimum(1)
        not_registered_days.setMaximum(3650)
        not_registered_days.setValue(int(os.getenv("ACUITY_NOT_REGISTERED_REMINDER_DAYS", os.getenv("REMINDER_EMAIL_DAYS", "7"))))
        self.entries["ACUITY_NOT_REGISTERED_REMINDER_DAYS"] = not_registered_days
        form.addRow("Not Registered Reminder (Days)", not_registered_days)

        # Reminder cadence for registered Acuity users (y years)
        registered_years = QSpinBox()
        registered_years.setMinimum(1)
        registered_years.setMaximum(25)
        registered_years.setValue(int(os.getenv("ACUITY_REGISTERED_REMINDER_YEARS", "1")))
        self.entries["ACUITY_REGISTERED_REMINDER_YEARS"] = registered_years
        form.addRow("Registered Reminder (Years)", registered_years)

        self._add_sidebar_page(ScrollablePage(page), "Sheets", "📄")                                                                 # Add Sheets page to sidebar navigation

    # =============================
    # MICROSOFT AUTHENTICATION TAB
    # =============================

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

        self._add_sidebar_page(ScrollablePage(page), "Authentication", "🪪")                                                         # Add Authentication page to sidebar navigation

    # ============
    # GENERAL TAB
    # ============

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

        self._add_sidebar_page(ScrollablePage(page), "General", "⚙️")                                                                # Add General settings page to sidebar navigation

    # =========
    # lOGS TAB
    # =========

    def _build_logs_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Live Application Logs")
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)                                                                                               # Prevent editing log viewer contents
        self.log_text.setLineWrapMode(QPlainTextEdit.NoWrap)                                                                          # Preserve original log line formatting

        layout.addWidget(title)
        layout.addWidget(self.log_text)

        self._add_sidebar_page(page, "System Logs", "🧾")                                                                            # Add live log viewer page to sidebar navigation

    # =================
    # UI INTERACTIONS
    # =================

    def _browse_rqi_export_dir(self):
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Select RQI CSV Export Folder",
            self.entries.get("RQI_CSV_EXPORT_DIR").text().strip() if self.entries.get("RQI_CSV_EXPORT_DIR") else "",
        )                                                                                                                             # Let user choose the root folder where time-window CSV batch folders should be created

        if selected_dir and "RQI_CSV_EXPORT_DIR" in self.entries:
            self.entries["RQI_CSV_EXPORT_DIR"].setText(selected_dir)                                                                  # Write selected export folder into the csv_sftp tab field

    def _generate_rqi_csv_clicked(self):
        if not self.on_generate_rqi_csv:
            QMessageBox.warning(self, "Unavailable", "Generate CSV action is not connected.")                                         # Guard against missing backend callback
            return

        try:
            csv_path = self.on_generate_rqi_csv()                                                                                     # Ask backend to create the current RQI CSV batch immediately
            QMessageBox.information(self, "CSV Generated", f"CSV created successfully:\n{csv_path}")
            self._update_rqi_csv_sftp_status()                                                                                        # Refresh visible batch window and CSV file information immediately after generation
        except Exception as e:
            QMessageBox.critical(self, "CSV Generation Failed", str(e))                                                               # Show real backend error when manual generation fails

    def _upload_rqi_csv_clicked(self):
        if not self.on_upload_rqi_csv:
            QMessageBox.warning(self, "Unavailable", "Upload to SFTP action is not connected.")                                       # Guard against missing backend callback
            return

        missing_fields = self.get_missing_sftp_fields() if self.get_missing_sftp_fields else []                                       # Ask backend which required SFTP settings are still missing
        if missing_fields:
            QMessageBox.warning(
                self,
                "Missing SFTP Settings",
                "Fill in these SFTP settings before uploading:\n\n- " + "\n- ".join(missing_fields),
            )                                                                                                                         # Block manual upload and show exactly which SFTP fields still need values
            return

        try:
            remote_path = self.on_upload_rqi_csv()                                                                                    # Ask backend to upload the latest CSV batch immediately
            QMessageBox.information(self, "Upload Complete", f"CSV uploaded successfully:\n{remote_path}")
            self._update_rqi_csv_sftp_status()                                                                                        # Refresh visible last-upload information immediately after successful upload
        except Exception as e:
            QMessageBox.critical(self, "SFTP Upload Failed", str(e))                                                                  # Show real backend error when manual upload fails
            self._update_rqi_csv_sftp_status()                                                                                        # Refresh visible upload-error information immediately after failed upload

    def _refresh_rqi_upload_window_clicked(self):
        if not self.on_refresh_rqi_upload_window:
            QMessageBox.warning(self, "Unavailable", "Refresh upload window action is not connected.")                                # Guard against missing backend callback
            return

        try:
            csv_path = self.on_refresh_rqi_upload_window()                                                                            # Ask backend to close current batch and start a brand-new upload window immediately
            QMessageBox.information(self, "Upload Window Refreshed", f"New upload window started:\n{csv_path}")
            self._update_rqi_csv_sftp_status()                                                                                        # Refresh visible batch window and upload information immediately after refresh
        except Exception as e:
            QMessageBox.critical(self, "Refresh Upload Window Failed", str(e))                                                        # Show real backend error when upload window refresh fails
            self._update_rqi_csv_sftp_status()                                                                                        # Refresh visible upload-error information immediately after failed refresh

    def _select_pause_target(self, target):
        self.selected_pause_target = target                                                                                           # Remember which pause action the dropdown selected
        self._update_pause_controls()                                                                                                 # Refresh main button text to match selected pause target

    def _run_selected_pause_action(self):
        if self.selected_pause_target == "all":
            self._toggle_pause_all_clicked()                                                                                          # Run Pause/Resume All through existing callback

        elif self.selected_pause_target == "email":
            self._toggle_pause_email_clicked()                                                                                        # Run Pause/Resume RQI Email Parsing through existing callback

        elif self.selected_pause_target == "automation_loop":
            self._toggle_pause_automation_loop_clicked()                                                                              # Run Pause/Resume AHA Automation through existing callback

    def _toggle_pause_all_clicked(self):
        if self.on_toggle_pause_all:
            self.on_toggle_pause_all()                                                                                                # Pause or resume all automation through shared callback
        self._update_pause_controls()                                                                                                 # Refresh visible button/menu text after state change

    def _toggle_pause_email_clicked(self):
        if self.on_toggle_pause_email:
            self.on_toggle_pause_email()                                                                                              # Pause or resume only email_to_sheets
        self._update_pause_controls()                                                                                                 # Refresh visible button/menu text after state change

    def _toggle_pause_automation_loop_clicked(self):
        if self.on_toggle_pause_automation_loop:
            self.on_toggle_pause_automation_loop()                                                                                    # Pause or resume only the main automation loop
        self._update_pause_controls()                                                                                                 # Refresh visible button/menu text after state change

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

    def _update_rqi_csv_sftp_status(self):
        if not self.get_rqi_csv_sftp_status:
            return                                                                                                                    # No backend status callback available, so nothing to refresh

        try:
            status = self.get_rqi_csv_sftp_status()                                                                                   # Pull current batch window, countdown, and last upload info from backend
        except Exception as e:
            logging.exception("Failed to refresh RQI CSV / SFTP status: %s", e)
            return                                                                                                                    # Leave existing labels untouched if backend status lookup fails unexpectedly

        batch_start = status.get("batch_start", "")
        batch_end = status.get("batch_end", "")
        seconds_remaining = int(status.get("seconds_remaining", 0) or 0)

        minutes_remaining = seconds_remaining // 60                                                                                   # Whole minutes remaining in current batch window
        seconds_remainder = seconds_remaining % 60                                                                                    # Remaining seconds after full minutes are removed

        self.rqi_batch_window_label.setText(f"{batch_start}  →  {batch_end}" if batch_start and batch_end else "Unavailable")
        self.rqi_batch_countdown_label.setText(f"{minutes_remaining:02d}:{seconds_remainder:02d}")                                    # Live countdown until automatic batch rollover

        current_csv_path = status.get("current_csv_path") or status.get("latest_csv_path") or ""
        self.rqi_current_csv_label.setText(current_csv_path if current_csv_path else "No CSV created yet")

        last_uploaded_local = status.get("last_uploaded_local_path", "")
        self.rqi_last_uploaded_local_label.setText(last_uploaded_local if last_uploaded_local else "None yet")

        last_uploaded_remote = status.get("last_uploaded_remote_path", "")
        self.rqi_last_uploaded_remote_label.setText(last_uploaded_remote if last_uploaded_remote else "None yet")

        last_upload_time = status.get("last_upload_time", "")
        self.rqi_last_upload_time_label.setText(last_upload_time if last_upload_time else "None yet")

        last_upload_error = status.get("last_upload_error", "")
        self.rqi_last_upload_error_label.setText(last_upload_error if last_upload_error else "None")

        if last_upload_error:
            self.rqi_last_upload_error_label.setStyleSheet("color: #e64e30; font-weight: 700;")                                       # Show upload errors in red so failed SFTP attempts are obvious
        else:
            self.rqi_last_upload_error_label.setStyleSheet("color: #00bc8c;")                                                         # Show healthy state when no upload error is present

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

        self.rqi_status_timer = QTimer(self)
        self.rqi_status_timer.timeout.connect(self._update_rqi_csv_sftp_status)                                                       # Refresh current batch window countdown and last upload information
        self.rqi_status_timer.start(1000)                                                                                             # Every 1 second so countdown feels live and responsive

        self._update_status()                                                                                                         # Initial status refresh on startup
        self._update_login_status()                                                                                                   # Initial login refresh on startup
        self._update_logs()                                                                                                           # Initial log refresh on startup
        self._update_rqi_csv_sftp_status()                                                                                            # Initial CSV batch window / upload status refresh on startup
        self._update_pause_controls()                                                                                                 # Initial pause button/menu refresh on startup

    def _update_pause_controls(self):
        pause_states = self.get_pause_states() if self.get_pause_states else {
            "all": False,
            "automation_loop": False,
            "email_to_sheets": False,
        }

        if pause_states["all"]:
            self.pause_all_action.setText("Resume All Automation")                                                                    # Menu text when everything is paused
        else:
            self.pause_all_action.setText("Pause All Automation")                                                                     # Menu text when everything is running

        if pause_states["email_to_sheets"]:
            self.pause_email_action.setText("Resume RQI Email Parsing")                                                               # Menu text when RQI email parsing is paused
        else:
            self.pause_email_action.setText("Pause RQI Email Parsing")                                                                # Menu text when RQI email parsing is running

        if pause_states["automation_loop"]:
            self.pause_loop_action.setText("Resume AHA Automation")                                                                   # Menu text when AHA automation is paused
        else:
            self.pause_loop_action.setText("Pause AHA Automation")                                                                    # Menu text when AHA automation is running

        if self.selected_pause_target == "all":
            if pause_states["all"]:
                self.pause_btn.setText("Resume All")                                                                                  # Main button follows selected target and current state
            else:
                self.pause_btn.setText("Pause All")

        elif self.selected_pause_target == "email":
            if pause_states["email_to_sheets"]:
                self.pause_btn.setText("Resume RQI")
            else:
                self.pause_btn.setText("Pause RQI")

        elif self.selected_pause_target == "automation_loop":
            if pause_states["automation_loop"]:
                self.pause_btn.setText("Resume AHA")
            else:
                self.pause_btn.setText("Pause AHA")

        global _qt_tray
        if _qt_tray is not None:
            _qt_tray.refresh_pause_text()                                                                                             # Keep tray text synced with current pause state

    def _update_status(self):
        status_file = os.path.join(base_dir(), "automation_status.txt")                                                               # Status file written by master_control
        self._update_pause_controls()                                                                                                 # Keep pause controls synced with real runtime state

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

        elif raw_status == "PAUSED_ALL":
            self.automation_card.set_value("All Automation Paused")
            self.automation_card.set_color("#e64e30")
            self.quick_status.setText("All Automation Paused")
            self.quick_status.setStyleSheet("color: #e64e30; font-weight: 700;")

        elif raw_status == "PAUSED_AUTOMATION_LOOP":
            self.automation_card.set_value("AHA Automation Paused")
            self.automation_card.set_color("#e64e30")
            self.quick_status.setText("AHA Automation Paused")
            self.quick_status.setStyleSheet("color: #e64e30; font-weight: 700;")

        elif raw_status == "PAUSED_EMAIL_TO_SHEETS":
            self.automation_card.set_value("RQI Email Parsing Paused")
            self.automation_card.set_color("#e64e30")
            self.quick_status.setText("RQI Email Parsing Paused")
            self.quick_status.setStyleSheet("color: #e64e30; font-weight: 700;")
        else:
            self.automation_card.set_value("Unknown")
            self.automation_card.set_color("#e64e30")
            self.quick_status.setText("Unknown")
            self.quick_status.setStyleSheet("color: #e64e30; font-weight: 700;")

        current_headless = os.getenv("IS_HEADLESS", "")                                                                               # Read current browser visibility setting
        if str(current_headless).strip().lower() in ("1", "true", "yes"):
            self.browser_card.set_value("Headless")
            self.browser_card.set_color("#00bc8c")
            self.quick_mode.setText("Headless")
            self.quick_mode.setStyleSheet("color: #00bc8c;")
        else:
            self.browser_card.set_value("Visible Browser")
            self.browser_card.set_color("#f39c12")
            self.quick_mode.setText("Visible Browser")
            self.quick_mode.setStyleSheet("color: #f39c12;")

        interval_text = os.getenv("INTERVAL", "")                                                                                     # Show current automation interval from env
        self.interval_card.set_value(f"{interval_text} sec")
        self.interval_card.set_color("#00bc8c")

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

        self._update_pause_controls()                                                                                                 # Keep pause button label synced with real state

    def _update_login_status(self):
        aha_auth_file = Path(base_dir()) / "aha_auth.json"                                                                            # Saved AHA auth state file
        if aha_auth_file.exists():
            text = "Signed In"
            color = "#00bc8c"
            aha_required = False                                                                                                      # No warning needed when AHA login exists
        else:
            text = "Not Signed In"
            color = "#e64e30"
            aha_required = True                                                                                                       # Show warning when no AHA login exists

        self.aha_login_label.setText(text)                                                                                            # Update label on AHA tab
        self.aha_login_label.setStyleSheet(f"color: {color}; font-weight: 700;")

        self.quick_login.setText(text)                                                                                                # Update quick label on csv_sftp tab
        self.quick_login.setStyleSheet(f"color: {color};")

        if aha_required:
            self.aha_required_label.show()                                                                                            # Show red warning near Sign Out button when login is missing
        else:
            self.aha_required_label.hide()                                                                                            # Hide warning when AHA login is present

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

    def _append_mini_log_line(self, line: str):
        cursor = self.mini_log_text.textCursor()
        cursor.movePosition(QTextCursor.End)                                                                                          # Append all new mini logs to end of compact viewer

        fmt = QTextCharFormat()

        upper_line = line.upper()                                                                                                     # Normalize once for easier keyword checks

        if " - ERROR - " in upper_line or "ERROR:" in upper_line:
            fmt.setForeground(QColor("#e64e30"))                                                                                    # Red for error lines in compact log viewer

        elif " - WARNING - " in upper_line or "WARNING:" in upper_line:
            fmt.setForeground(QColor("#f39c12"))                                                                                    # Orange for warning lines in compact log viewer

        elif " - INFO - " in upper_line or "INFO:" in upper_line:
            fmt.setForeground(QColor("#5dade2"))                                                                                    # Blue for info lines in compact log viewer

        else:
            fmt.setForeground(QColor("#d7dce2"))                                                                                    # Default light text for all other log lines

        cursor.insertText(line, fmt)                                                                                                  # Insert compact log line with color formatting

    def _append_log_text(self, text: str):
        if not text:
            return                                                                                                                    # Nothing to append

        lines = text.splitlines(keepends=True)                                                                                        # Preserve original line endings
        for line in lines:
            self._append_log_line(line)                                                                                               # Append each line with color formatting

    def _append_mini_log_text(self, text: str):
        if not text:
            return                                                                                                                    # Nothing to append into compact log viewer

        lines = text.splitlines(keepends=True)                                                                                        # Preserve original line endings
        for line in lines:
            self._append_mini_log_line(line)                                                                                          # Append each compact log line with color formatting

    def _update_mini_logs(self):
        current_log_file = log_file()                                                                                                 # Current live application log path

        if not os.path.exists(current_log_file):
            self.mini_log_text.clear()                                                                                                # Clear compact viewer when no log file exists
            return

        try:
            with open(current_log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()                                                                                                 # Read all lines so we can show only the newest ones

            recent_lines = lines[-8:]                                                                                                 # Show only the last few log lines in compact viewer

            self.mini_log_text.clear()                                                                                                # Rebuild compact log viewer fresh on each refresh
            self._append_mini_log_text("".join(recent_lines))                                                                         # Insert recent lines with INFO/WARNING/ERROR colors

            scrollbar = self.mini_log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())                                                                                   # Keep compact viewer pinned to newest lines

        except Exception as e:
            logging.exception("Error updating mini log viewer: %s", e)

    def _update_logs(self):
        current_log_file = log_file()                                                                                                 # Current live application log path

        if not os.path.exists(current_log_file):
            if hasattr(self, "mini_log_text"):
                self.mini_log_text.clear()                                                                                            # Clear compact log viewer if no log file exists yet
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

        self._update_mini_logs()

    # =======
    # STYLES
    # =======

    def _apply_styles(self):                                                                                                          # Main dark theme stylesheet for the entire GUI
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1f22;
            }
            QFrame#StatusCard {
                background-color: #2b2d31;
                border: 1px solid #3b3d42;
                border-radius: 14px;
                padding: 2px;                                                                                                         /* Smaller visual footprint for compact dashboard cards */
            }
            QLabel#StatusCardTitle {
                color: #bfc5d2;
                font-size: 10px;                                                                                                      /* Smaller title text for compact cards */
                font-weight: 600;
            }
            QLabel#StatusCardValue {
                color: white;
                font-size: 14px;                                                                                                      /* Smaller value text so 2x2 grid fits comfortably */
                font-weight: 700;
            }
            QFrame#SidebarFrame {
                background-color: #20242c;
                border: 1px solid #323844;
                border-radius: 14px;
            }
            QFrame#SidebarIndicator {
                background-color: #00bc8c;
                border-radius: 2px;                                                                                                   /* Thin rounded vertical pill for active page */
            }
            QStackedWidget#ContentStack {
                background-color: #2b2d31;
                border: 1px solid #3b3d42;
                border-radius: 16px;
            }
            QToolButton#SidebarCollapseButton {
                background-color: #1b1d21;
                color: #d7dce2;
                border: 1px solid #3b3d42;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 0px;
            }
            QToolButton#SidebarCollapseButton:hover {
                background-color: #31343a;
                border: 1px solid #5dade2;
            }
            QToolButton#SidebarButton {
                background-color: #1b1d21;
                color: white;
                border: 1px solid #353840;
                border-radius: 22px;                                                                                                  /* Half of 44px to make perfect circle */
                font-size: 18px;
                font-weight: 600;
                padding: 0px;
            }
            QToolButton#SidebarButton:hover {
                background-color: #2f6feb;
                border: 1px solid #7fb3ff;
            }
            QToolButton#SidebarButton:checked {
                background-color: #00bc8c;
                border: 1px solid #5ff0bf;
            }
            QToolButton#SidebarButton:checked:hover {
                background-color: #11c995;
                border: 1px solid #7ff7d0;
            }
            QToolTip {
                background-color: #111317;
                color: white;
                border: 1px solid #3b3d42;
                padding: 6px 10px;
            }
            QPushButton {
                color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 16px;
                font-weight: 600;
                min-height: 8px;
            }
            QPushButton#RestartButton, QPushButton#QuitButton {
                padding: 4px 12px;
                min-height: 0px;
            }

            QPushButton#SaveButton {
                background-color: #00bc8c;
                padding: 8px 18px;                                                                                                    /* Slightly wider bottom-centered save button */
                min-width: 150px;                                                                                                     /* Gives bottom save button a more intentional centered look */
            }
            QPushButton#SaveButton:hover {
                background-color: #17d7a0;
            }

            QPushButton#PauseButton {
                background-color: #f4a51c;                                                                                            /* Main pause button color */
                color: white;
                border: none;
                border-top-left-radius: 10px;                                                                                         /* Round only left side */
                border-bottom-left-radius: 10px;
                border-top-right-radius: 0px;                                                                                         /* No rounding where it joins dropdown */
                border-bottom-right-radius: 0px;
                padding: 0 10px;
                font-weight: 600;
            }
            QPushButton#PauseButton:hover {background-color: #ffb52e;}
                           
            QPushButton#PauseButton:pressed {
                background-color: #de9210;                                                                                            /* Pressed state */
            }

            QToolButton#PauseMenuButton {
                background-color: #f4a51c;
                color: white;
                border: none;
                border-left: 1px solid rgba(255, 255, 255, 0.18);                                                                     /* Small divider between main and dropdown areas */
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 10px;
                border-bottom-right-radius: 10px;
                padding: 0px;
                margin: 0px;
            }
            QToolButton#PauseMenuButton:hover {
                background-color: #ffb52e;                                                                                            /* Match hover */
            }
            QToolButton#PauseMenuButton:pressed {
                background-color: #de9210;                                                                                            /* Match pressed */
            }          
            QToolButton#PauseMenuButton::menu-indicator {
                image: none;                                                                                                          /* Hide Qt's default dropdown arrow */
                width: 0px;                                                                                                           /* Remove reserved arrow space */
            }

            QPushButton#RestartButton {background-color: #e67e22;}
            QPushButton#RestartButton:hover {background-color: #f39c12;}

            QPushButton#SignOutButton {
                background-color: #3498db;
                padding: 6px 12px;                                                                                                    /* Smaller AHA button so the top-right row takes less height */
                min-height: 0px;
                border-radius: 10px;
                font-size: 11px;                                                                                                      /* Match smaller button height */
                font-weight: 600;
            }
            QPushButton#SignOutButton:hover {background-color: #5dade2;}

            QPushButton#QuitButton {background-color: #e64e30;}
            QPushButton#QuitButton:hover {background-color: #ff6b57;}
            
            QPushButton:hover {background-color: #3b82f6;}
    
            QLabel#SectionTitle {
                color: white;
                font-size: 18px;
                font-weight: 700;
            }

            QLabel#SectionSubtitle {
                color: #bfc5d2;
                font-size: 12px;
                font-weight: 600;
            }

            QPushButton#BrowseButton {
                background-color: #3498db;
                padding: 6px 12px;
                min-width: 80px;
            }
            QPushButton#BrowseButton:hover {
                background-color: #5dade2;
            }

            QPushButton#ActionButton {
                background-color: #5865f2;
                padding: 8px 14px;
                min-width: 150px;
            }
            QPushButton#ActionButton:hover {
                background-color: #6f7cff;
            }               

            QFrame#MiniLogsPanel {
                background-color: #2b2d31;
                border: 1px solid #3b3d42;
                border-radius: 14px;
                min-height: 166px;
                max-height: 166px;
            }

            QLabel#MiniLogsTitle {
                color: white;
                font-size: 12px;
                font-weight: 700;
            }

            QLabel#AHARequiredLabel {
                color: #ff5f56;                                                                                                       /* Red warning text when AHA login is missing */
                font-size: 11px;
                font-weight: 700;
            }
            
            QLineEdit {
                background-color: #1f2125;
                color: white;
                border: 1px solid #3b3d42;
                border-radius: 10px;
                padding: 8px;
            }
            QPlainTextEdit {
                background-color: #1b1d21;
                color: #d7dce2;
                border: 1px solid #3b3d42;
                border-radius: 10px;
                padding: 6px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 11px;
            }
            QPlainTextEdit#MiniLogText {
                background-color: #151821;                                                                                            /* Slightly darker compact log panel */
                border: 1px solid #343842;
                border-radius: 10px;
                padding: 5px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 10px;                                                                                                      /* Smaller font for dashboard-style compact logs */
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

def open_settings(on_toggle_pause_all=None, on_toggle_pause_email=None, on_toggle_pause_automation_loop=None,
                  on_generate_rqi_csv=None, on_upload_rqi_csv=None, on_refresh_rqi_upload_window=None,
                  get_rqi_csv_sftp_status=None, get_missing_sftp_fields=None,
                  on_quit=None, get_pause_states=None, on_ready=None,):
    
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
        _qt_window = SettingsWindow(on_toggle_pause_all=on_toggle_pause_all,                                                          # Main window Pause All button
            on_toggle_pause_email=on_toggle_pause_email,                                                                              # Main window menu item for email_to_sheets
            on_toggle_pause_automation_loop=on_toggle_pause_automation_loop,                                                          # Main window menu item for automation loop
            on_generate_rqi_csv=on_generate_rqi_csv,                                                                                  # RQI CSV & SFTP tab button for manual CSV batch generation
            on_upload_rqi_csv=on_upload_rqi_csv,                                                                                      # RQI CSV & SFTP tab button for manual SFTP upload
            on_refresh_rqi_upload_window=on_refresh_rqi_upload_window,                                                                # RQI CSV & SFTP tab button for starting a brand-new upload window immediately
            get_rqi_csv_sftp_status=get_rqi_csv_sftp_status,                                                                          # RQI CSV & SFTP tab status callback for live batch window and last upload info
            get_missing_sftp_fields=get_missing_sftp_fields,                                                                          # RQI CSV & SFTP tab validation callback for missing SFTP settings
            on_quit=on_quit, get_pause_states=get_pause_states, on_ready=on_ready,)                                                   # Create main window once

    if _qt_tray is None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            _qt_tray = AppTrayIcon(_qt_window, on_toggle_pause_all=on_toggle_pause_all, on_quit=on_quit,
                                   get_pause_states=get_pause_states,)                                                                # Create tray icon once
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
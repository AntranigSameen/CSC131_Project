# ==========
# IMPORTS
# ==========

import os
import sys
import json
import subprocess
import logging
from pathlib import Path

from dotenv import set_key, load_dotenv
from PySide6.QtCore import Qt, QTimer, QSize, QRect, QRectF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QIcon, QGuiApplication, QTextCursor, QTextCharFormat, QColor, QPainter, QPen, QFont, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QStackedWidget,
                               QScrollArea, QLineEdit, QMessageBox, QPlainTextEdit, QFormLayout, QSystemTrayIcon, QMenu, QDialog, QDialogButtonBox,
                               QToolButton, QSizePolicy, QGraphicsDropShadowEffect, QGridLayout, QFileDialog, QSpinBox, QListWidget, QComboBox, QTextEdit, QCheckBox, QTabWidget,)

from utils import writable_env_file, base_dir, log_file, resource_path
from location_keys import (
    load_location_keys,
    upsert_location_key,
    remove_location_key,
    get_location_keys_file_path,
)
from location_email_tracker import (
    load_tracker_entries,
    get_tracker_file_path,
    clear_tracker_file,
)
from location_email_templates import (
    get_location_templates_file_path,
    ensure_location_templates_file,
    ensure_location_template_entry,
    remove_location_template_entry,
)

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
    "ACUITY_NOT_REGISTERED_REMINDER_DAYS"                                                                                             #
    "ACUITY_REGISTERED_REMINDER_YEARS"                                                                                                #
}                                                                                                                                     # Settings that require restart after change

# =====================
# REMINDER TEMPLATES
# =====================

TEMPLATE_DIR = Path(base_dir()) / "email_templates"                                                                                   # Folder that stores editable reminder email body template files
NOT_REGISTERED_TEMPLATE_FILE = TEMPLATE_DIR / "acuity_not_registered_email_body.txt"                                                  # Template file for non-registered Acuity users
REGISTERED_TEMPLATE_FILE = TEMPLATE_DIR / "acuity_registered_email_body.txt"                                                          # Template file for registered Acuity users


def ensure_template_files():
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)                                                                                   # Create template folder if it does not exist yet

    if not NOT_REGISTERED_TEMPLATE_FILE.exists():
        NOT_REGISTERED_TEMPLATE_FILE.write_text("", encoding="utf-8")                                                                 # Create empty non-registered email template file on first run

    if not REGISTERED_TEMPLATE_FILE.exists():
        REGISTERED_TEMPLATE_FILE.write_text("", encoding="utf-8")                                                                     # Create empty registered email template file on first run


def read_template_file(path: Path) -> str:
    ensure_template_files()                                                                                                           # Make sure template directory and files exist before reading
    return path.read_text(encoding="utf-8")                                                                                           # Return full template body text from file


def write_template_file(path: Path, content: str):
    ensure_template_files()                                                                                                           # Make sure template directory exists before writing
    path.write_text(content, encoding="utf-8")                                                                                        # Save full multi-line reminder email template body to file

# ===============
# SAVE SETTINGS
# ===============

def save_settings(entries, restart=False):
    restart_needed = False                                                                                                            # Track whether any changed setting needs restart

    ensure_template_files()                                                                                                           # Make sure reminder template files exist before saving editor content

    for key, widget in entries.items():
        if key == "ACUITY_NOT_REGISTERED_EMAIL_BODY_TEMPLATE":
            new_value = widget.toPlainText()                                                                                          # Read full multi-line body text for non-registered reminder email template
            old_value = read_template_file(NOT_REGISTERED_TEMPLATE_FILE)

            if new_value != old_value:
                write_template_file(NOT_REGISTERED_TEMPLATE_FILE, new_value)                                                          # Save non-registered reminder email body into template file
            continue                                                                                                                  # Skip .env write because this setting lives in a template file

        if key == "ACUITY_REGISTERED_EMAIL_BODY_TEMPLATE":
            new_value = widget.toPlainText()                                                                                          # Read full multi-line body text for registered reminder email template
            old_value = read_template_file(REGISTERED_TEMPLATE_FILE)

            if new_value != old_value:
                write_template_file(REGISTERED_TEMPLATE_FILE, new_value)                                                              # Save registered reminder email body into template file
            continue                                                                                                                  # Skip .env write because this setting lives in a template file

        if key == "LOCATION_EMAIL_TEMPLATES_JSON_EDITOR":
            new_value = widget.toPlainText()
            try:
                parsed = json.loads(new_value or "{}")
                pretty = json.dumps(parsed, indent=2)
            except Exception as e:
                QMessageBox.critical(None, "Invalid Template JSON", f"Could not save location templates:\n{e}")
                continue

            template_path = ensure_location_templates_file()
            Path(template_path).write_text(pretty + "\n", encoding="utf-8")
            continue

        # Handle both QLineEdit (text()) and QSpinBox (value())
        if isinstance(widget, QSpinBox):
            new_value = str(widget.value())                                                                                           # Numeric widgets save their integer value
        elif isinstance(widget, QCheckBox):
            new_value = "True" if widget.isChecked() else "False"                                                                     # Checkboxes save as "True"/"False" strings   
        else:
            new_value = widget.text()                                                                                                 # Standard single-line fields save their text normally

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

# ===================
# PILL SWITCH TOGGLE
# ===================

class PillSwitch(QCheckBox):
    def __init__(self, left_icon="🌙", right_icon="☀️", parent=None):
        super().__init__(parent)
        self.left_icon = left_icon                                                                                                    # Icon shown on left side of switch
        self.right_icon = right_icon                                                                                                  # Icon shown on right side of switch
        self.setCursor(Qt.PointingHandCursor)                                                                                         # Make the switch feel clickable
        self.setFixedSize(60, 30)                                                                                                     # Fixed pill size for icon toggle

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)                                                                                  # Smooth rounded pill and knob

        checked = self.isChecked()

        bg_color = QColor("#00bc8c") if checked else QColor("#2b2f36")                                                            # Accent color when enabled, dark gray when disabled
        border_color = QColor("#00bc8c") if checked else QColor("#555b66")
        knob_color = QColor("#ffffff")

        pill_rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(bg_color)
        painter.drawRoundedRect(pill_rect, 14, 14)                                                                                    # Draw rounded switch background

        knob_size = 24
        knob_x = self.width() - knob_size - 4 if checked else 4
        knob_y = (self.height() - knob_size) / 2
        knob_rect = QRectF(knob_x, knob_y, knob_size, knob_size)

        painter.setPen(Qt.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(knob_rect)                                                                                                # Draw centered sliding knob

        painter.setFont(QFont("Segoe UI Emoji", 9))

        left_rect = QRectF(4, 0, 24, self.height())
        right_rect = QRectF(self.width() - 28, 0, 24, self.height())

        painter.setPen(QColor("#f4c542"))
        painter.drawText(left_rect, Qt.AlignCenter, self.left_icon)                                                                   # Center left icon inside left side

        painter.setPen(QColor("#f4c542"))
        painter.drawText(right_rect, Qt.AlignCenter, self.right_icon)                                                                 # Center right icon inside right side

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

# ============
# MAIN WINDOW
# ============

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

    def _add_soft_shadow(self, widget, blur=18, y_offset=3):
        shadow = QGraphicsDropShadowEffect(self)                                                                                      # Soft visual depth effect for important panels/cards
        shadow.setBlurRadius(blur)                                                                                                    # Higher blur makes the shadow softer
        shadow.setOffset(0, y_offset)                                                                                                 # Slight downward shadow feels natural
        shadow.setColor(QColor(15, 23, 42, 35))                                                                                       # Very subtle slate shadow for light mode
        widget.setGraphicsEffect(shadow)                                                                                              # Apply shadow to target widget

    def _add_button_shadow(self, button):
        if button.objectName() == "ActionButton":
            return                                                                                                                    # Keep RQI action buttons visually identical between light and dark mode
        shadow = QGraphicsDropShadowEffect(self)                                                                                      # Soft depth effect for light-mode buttons
        shadow.setBlurRadius(22)                                                                                                      # Softer than panel shadows
        shadow.setOffset(0, 3)                                                                                                        # Small downward offset feels natural for buttons
        shadow.setColor(QColor(15, 23, 42, 55))                                                                                       # Very subtle shadow so buttons do not look heavy
        button.setGraphicsEffect(shadow)                                                                                              # Apply shadow to button

    def _refresh_button_shadows(self):
        buttons = [
            getattr(self, "save_button", None),
            getattr(self, "pause_button", None),
            getattr(self, "restart_button", None),
            getattr(self, "quit_button", None),
        ]                                                                                                                            # Main persistent application buttons

        for button in buttons:
            if button is None:
                continue                                                                                                              # Skip buttons that do not exist yet

            if self.light_mode_enabled:
                self._add_button_shadow(button)                                                                                       # Enable shadows in light mode
            else:
                button.setGraphicsEffect(None)                                                                                        # Remove shadows in dark mode

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

    def _emoji_icon(self, emoji):
        pixmap = QPixmap(24, 24)                                                                                                      # Create pixmap for emoji-based sidebar icon
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        font = QFont()
        font.setPointSize(14)
        painter.setFont(font)

        painter.drawText(pixmap.rect(), Qt.AlignCenter, emoji)                                                                       # Draw emoji centered into icon pixmap
        painter.end()

        return QIcon(pixmap)

    def _set_sidebar_page(self, index):
        self.page_stack.setCurrentIndex(index)                                                                                        # Show the selected page in the main content area

        for item in self.sidebar_buttons:
            is_active = item["page_index"] == index                                                                                   # Check whether this sidebar item is selected

            for button in (item["expanded"], item["collapsed"]):
                button.setChecked(is_active)                                                                                          # Highlight both expanded/collapsed versions of selected page

                if is_active:
                    glow = QGraphicsDropShadowEffect(self)
                    glow.setBlurRadius(18)                                                                                            # Soft active glow around selected sidebar button
                    glow.setOffset(0, 0)
                    button.setGraphicsEffect(glow)
                else:
                    button.setGraphicsEffect(None)                                                                                    # Remove glow from non-active buttons

        self._move_sidebar_indicator(index)                                                                                           # Move selected sidebar pill to the active button

    def _add_sidebar_page(self, page_widget, tooltip_text, icon_text):
        page_index = self.page_stack.addWidget(page_widget)                                                                           # Add page to stacked content area

        expanded_button = QPushButton()                                                                                               # QPushButton aligns expanded sidebar text better than QToolButton
        expanded_button.sidebar_icon_text = icon_text                                                                                 # Store icon for expanded/collapsed sidebar states
        expanded_button.sidebar_label_text = tooltip_text                                                                             # Store label for expanded sidebar state
        expanded_button.sidebar_page_index = page_index                                                                               # Store page index for active-page tracking
        expanded_button.setObjectName("SidebarButton")                                                                                # Stylesheet hook for expanded sidebar button
        expanded_button.setText(f"{icon_text}  {tooltip_text}")                                                                       # Expanded sidebar shows icon plus page name
        expanded_button.setToolTip(tooltip_text)                                                                                      # Show page name when hovering over sidebar item
        expanded_button.setCheckable(True)                                                                                            # Allow active/selected styling
        expanded_button.setFixedSize(203, 37)                                                                                         # Slim expanded sidebar row size
        expanded_button.clicked.connect(lambda checked=False, idx=page_index: self._set_sidebar_page(idx))                            # Switch stacked page when clicked

        collapsed_button = QToolButton()                                                                                              # QToolButton keeps collapsed icon-only tiles clean and centered
        collapsed_button.sidebar_icon_text = icon_text                                                                                # Store icon for collapsed sidebar state
        collapsed_button.sidebar_label_text = tooltip_text                                                                            # Store label for tooltip/reference
        collapsed_button.sidebar_page_index = page_index                                                                              # Store page index for active-page tracking
        collapsed_button.setObjectName("CollapsedSidebarButton")                                                                      # Stylesheet hook for collapsed sidebar button
        collapsed_button.setText(icon_text)                                                                                           # Collapsed sidebar shows icon only
        collapsed_button.setToolTip(tooltip_text)                                                                                     # Show page name when hovering over collapsed icon
        collapsed_button.setCheckable(True)                                                                                           # Allow active/selected styling
        collapsed_button.setFixedSize(50, 50)                                                                                         # Square collapsed icon tile size
        collapsed_button.setToolButtonStyle(Qt.ToolButtonTextOnly)                                                                    # Keep emoji icon centered as text
        collapsed_button.clicked.connect(lambda checked=False, idx=page_index: self._set_sidebar_page(idx))                           # Switch stacked page when clicked
        collapsed_button.hide()                                                                                                       # Hide collapsed button because sidebar starts expanded

        sidebar_item = {
            "page_index": page_index,
            "expanded": expanded_button,
            "collapsed": collapsed_button,
        }                                                                                                                             # Store both sidebar buttons as one logical sidebar item

        self.sidebar_buttons.append(sidebar_item)                                                                                     # Store sidebar item so selected/collapsed state can be updated
        self.sidebar_layout.addWidget(expanded_button)                                                                                # Add expanded button to sidebar layout
        self.sidebar_layout.addWidget(collapsed_button)                                                                               # Add collapsed button to sidebar layout

    def _toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed                                                                           # Flip between expanded and collapsed sidebar states
        self._refresh_sidebar_visual_state()                                                                                          # Apply correct sidebar sizing and labels for current state

    def _refresh_sidebar_visual_state(self):
        if not hasattr(self, "sidebar_buttons"):
            return                                                                                                                    # Sidebar has not been created yet

        if self.sidebar_collapsed:
            self.sidebar_frame.setFixedWidth(72)                                                                                      # Collapsed sidebar width for square icon tiles
            self.collapse_button.setText("»")                                                                                         # Show expand arrow while collapsed
            self.collapse_button.setToolTip("Expand Sidebar")
            self.collapse_button.setFixedSize(50, 28)

            for item in self.sidebar_buttons:
                item["expanded"].hide()                                                                                               # Hide expanded text button while sidebar is collapsed

                collapsed_button = item["collapsed"]
                collapsed_button.show()                                                                                               # Show collapsed icon-only button
                collapsed_button.setFixedSize(50, 50)                                                                                 # Keep collapsed icon tile square
                collapsed_button.setMinimumSize(50, 50)                                                                               # Prevent stylesheet/layout from shrinking icon tile
                collapsed_button.setMaximumSize(50, 50)                                                                               # Prevent stylesheet/layout from stretching icon tile

        else:
            self.sidebar_frame.setFixedWidth(225)                                                                                     # Expanded sidebar width for icon plus tab names
            self.collapse_button.setText("Collapse")                                                                                  # Show collapse while expanded
            self.collapse_button.setToolTip("Collapse Sidebar")
            self.collapse_button.setFixedSize(188, 28)

            for item in self.sidebar_buttons:
                item["collapsed"].hide()                                                                                              # Hide collapsed icon-only button while sidebar is expanded

                expanded_button = item["expanded"]
                expanded_button.show()                                                                                                # Show expanded icon plus label button
                expanded_button.setFixedSize(203, 37)                                                                                 # Keep expanded row slim
                expanded_button.setMinimumSize(203, 37)                                                                               # Prevent light/dark stylesheet from resizing row
                expanded_button.setMaximumSize(203, 37)                                                                               # Prevent light/dark stylesheet from resizing row

        self.sidebar_indicator.show()                                                                                                 # Keep selected page indicator visible
        self._move_sidebar_indicator(self.page_stack.currentIndex())                                                                  # Re-align indicator after sidebar size changes

    def _move_sidebar_indicator(self, index):
        if not self.sidebar_buttons:
            return                                                                                                                    # Nothing to move if no sidebar buttons exist yet

        active_item = None                                                                                                            # Track selected sidebar item

        for item in self.sidebar_buttons:
            if item["page_index"] == index:
                active_item = item                                                                                                    # Found active sidebar item
                break

        if active_item is None:
            return                                                                                                                    # Ignore invalid page index

        button = active_item["collapsed"] if self.sidebar_collapsed else active_item["expanded"]                                      # Use visible button for indicator position

        button_y = button.y()                                                                                                         # Vertical position of selected sidebar button
        button_h = button.height()                                                                                                    # Height of selected sidebar button

        pill_height = max(24, button_h - 10)                                                                                          # Make selected pill slightly smaller than the button
        pill_y = button_y + (button_h - pill_height) // 2                                                                             # Center pill vertically beside selected button

        self.sidebar_indicator.setGeometry(5, pill_y, 4, pill_height)                                                                 # Move left-side selection pill to active button


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
        self._add_soft_shadow(mini_logs_panel)                                                                                        # Add subtle depth to top live-log panel
        mini_logs_panel.setFixedHeight(166)                                                                                           # Set Live Logs panel to match height of cards grid
        mini_logs_panel.setMaximumHeight(166)                                                                                         # Keep mini live logs same height in light and dark mode
        mini_logs_panel.setMinimumHeight(166)                                                                                         # Prevent stylesheet/layout changes from making mini logs taller

        mini_logs_layout = QVBoxLayout(mini_logs_panel)
        mini_logs_layout.setContentsMargins(10, 8, 10, 8)                                                                             # Compact inner padding so log box fits cleanly inside the fixed-height panel
        mini_logs_layout.setSpacing(4)

        mini_logs_title = QLabel("Live Logs")
        mini_logs_title.setObjectName("MiniLogsTitle")                                                                                # Small heading above top-right log preview

        self.mini_log_text = QPlainTextEdit()
        self.mini_log_text.setObjectName("MiniLogText")                                                                               # Separate styling hook for compact top log viewer
        self.mini_log_text.setReadOnly(True)                                                                                          # Prevent editing the compact log preview
        self.mini_log_text.setLineWrapMode(QPlainTextEdit.WidgetWidth)                                                                # Wrap friendly activity feed lines inside compact mini viewer
        self.mini_log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)                                                # Fill available space inside panel
        self.mini_log_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)                                                        # Hide horizontal scrollbar in compact preview
        self.mini_log_text.setPlaceholderText("Recent log lines will appear here...")
        self.mini_log_text.setMaximumHeight(100)                                                                                      # Keep compact mini log text area from growing in light mode

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

        self._add_button_shadow(self.save_btn)                                                                                        # Add subtle light-mode depth to Save button

        self.restart_btn = QPushButton("Restart App")
        self.restart_btn.setObjectName("RestartButton")                                                                               # Used by stylesheet for restart button
        self.restart_btn.setFixedHeight(32)

        self._add_button_shadow(self.restart_btn)                                                                                     # Add subtle depth to Restart button

        self.quit_btn = QPushButton("Quit")
        self.quit_btn.setObjectName("QuitButton")                                                                                     # Used by stylesheet for quit button
        self.quit_btn.setFixedHeight(32)
    
        self._add_button_shadow(self.quit_btn)                                                                                        # Add subtle depth to Quit button

        self.aha_required_label = QLabel("AHA login required")
        self.aha_required_label.setObjectName("AHARequiredLabel")                                                                     # Red warning label shown when no AHA login exists
        self.aha_required_label.hide()                                                                                                # Hidden by default until login check says it is needed

        # ===========================
        # Top-right Theme Toggle Row
        # ===========================

        top_tools_row = QHBoxLayout()
        top_tools_row.setContentsMargins(0, 0, 0, 0)
        top_tools_row.setSpacing(8)

        self.theme_toggle = PillSwitch("🌙", "☀️")                                                                                   # Custom sun/moon switch for toggling between dark and light mode
        self.theme_toggle.setObjectName("ThemeToggle")                                                                                # Custom sun/moon switch for toggling between light and dark mode

        current_theme = os.getenv("APP_THEME", "dark").strip().lower()
        self.is_light_mode = current_theme == "light"                                                                                 # Track current GUI theme
        self.theme_toggle.setChecked(self.is_light_mode)                                                                              # Checked means light mode

        self.theme_label = QLabel("Light" if self.is_light_mode else "Dark")
        self.theme_label.setObjectName("ThemeToggleText")                                                                             # Text beside theme toggle showing active theme

        self.theme_toggle.stateChanged.connect(self._toggle_theme_mode)                                                               # Change theme immediately when toggle is clicked

        top_tools_row.addStretch(1)                                                                                                   # Push theme toggle to the top-right corner
        top_tools_row.addWidget(self.theme_toggle, 0, Qt.AlignVCenter)                                                                # Single custom toggle already contains moon and sun icons
        top_tools_row.addWidget(self.theme_label, 0, Qt.AlignVCenter)                                                                 # Active theme text


        self.pause_btn = QPushButton("Pause All")
        self.pause_btn.setObjectName("PauseButton")                                                                                   # Main quick-action button for pausing/resuming all automation
        self.pause_btn.setFixedHeight(24)
        self.pause_btn.setMinimumWidth(112)

        self._add_button_shadow(self.pause_btn)                                                                                       # Add subtle depth to Pause button

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

        root.addLayout(top_tools_row)                                                                                                 # Separate theme toggle
        root.addLayout(top_dashboard_row)                                                                                             # Top-left cards + top-right mini logs
        root.addLayout(controls_row)                                                                                                  # Save / Restart / Quit row

        content_row = QHBoxLayout()
        content_row.setSpacing(6)                                                                                                     # Tight spacing between sidebar and main content

        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("SidebarFrame")                                                                              # Styled container for left-side circular navigation buttons
        self._add_soft_shadow(self.sidebar_frame)                                                                                     # Add subtle depth to sidebar container
        self.sidebar_frame.setFixedWidth(225)                                                                                         # Thin sidebar width for compact icon rail
        self.sidebar_collapsed = False                                                                                                # Track whether sidebar is collapsed

        self.sidebar_layout = QVBoxLayout(self.sidebar_frame)
        self.sidebar_layout.setContentsMargins(8, 10, 8, 10)
        self.sidebar_layout.setSpacing(10)                                                                                            # Tight spacing between smaller circular buttons
        self.sidebar_layout.setAlignment(Qt.AlignTop)

        self.collapse_button = QToolButton()
        self.collapse_button.setObjectName("SidebarCollapseButton")
        self.collapse_button.setText("«")                                                                                             # Collapse arrow shown at top of sidebar
        self.collapse_button.setToolTip("Collapse Sidebar")
        self.collapse_button.setFixedSize(188, 28)
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
        self._build_credentials_tab()                                                                                                 # Credential management page
        self._build_reminders_tab()                                                                                                   # Combined Reminder Emails and Manual Emailer page
        self._build_locations_tab()                                                                                                   # Combined Locations page with keys, templates, and tracker subtabs
        self._build_logs_tab()                                                                                                        # Live logs page

        if self.sidebar_buttons:
            self._set_sidebar_page(0)                                                                                                 # Start on the RQI CSV & SFTP page when GUI opens
            QTimer.singleShot(0, lambda: self._move_sidebar_indicator(0))                                                             # Reposition selected pill after layout finishes

        self._apply_styles()                                                                                                          # Apply full application stylesheet
        self._refresh_sidebar_visual_state()                                                                                          # Make initial sidebar sizing consistent with selected theme

    # ====================
    # THEME TOGGLE BUTTON
    # ====================

    def _toggle_theme_mode(self):
        self.is_light_mode = self.theme_toggle.isChecked()                                                                            # Checked means light mode

        theme_value = "light" if self.is_light_mode else "dark"
        set_key(CONFIG_FILE, "APP_THEME", theme_value)                                                                                # Save selected theme into .env immediately
        load_dotenv(CONFIG_FILE, override=True)                                                                                       # Reload current process environment after saving theme

        self.theme_label.setText("Light" if self.is_light_mode else "Dark")                                                           # Update visible theme text

        self._apply_styles()                                                                                                          # Re-apply stylesheet using selected theme
        self._refresh_sidebar_visual_state()                                                                                          # Re-apply sidebar size/state after theme stylesheet changes
        self._refresh_button_shadows()                                                                                                # Enable/disable button shadows depending on active theme


    # ==============
    # TAB BUILDERS
    # ==============

    # ==================
    # RQI EXPORT MANAGER
    # ==================

    def _make_export_status_card(self, title, value_label):
        card = QFrame()
        card.setObjectName("ExportStatusCard")                                                                                        # Styled card for RQI export status values
        card.setMaximumHeight(74)                                                                                                     # Keep status cards compact so manual action buttons remain visible

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(3)

        title_label = QLabel(title)
        title_label.setObjectName("ExportStatusTitle")                                                                                # Smaller label shown above the live value

        value_label.setObjectName("ExportStatusValue")                                                                                # Larger wrapped status value
        value_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch(1)

        return card
    
    def _make_export_action_bar(self):
        action_widget = QWidget()
        action_widget.setObjectName("ExportActionBar")                                                                                # Manual action bar shown inside each RQI Export Manager inner tab

        action_row = QHBoxLayout(action_widget)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        generate_btn = QPushButton("Generate CSV Now")
        generate_btn.setObjectName("ActionButton")                                                                                    # Manual CSV generation button
        generate_btn.clicked.connect(lambda: self._animate_button_press(generate_btn))                                                # Animate press before manual CSV generation
        generate_btn.clicked.connect(self._generate_rqi_csv_clicked)                                                                  # Trigger backend CSV generation callback
        self._add_button_shadow(generate_btn)                                                                                         # Add subtle depth to action button

        upload_btn = QPushButton("Upload to SFTP Now")
        upload_btn.setObjectName("ActionButton")                                                                                      # Manual SFTP upload button
        upload_btn.clicked.connect(lambda: self._animate_button_press(upload_btn))                                                    # Animate press before manual upload
        upload_btn.clicked.connect(self._upload_rqi_csv_clicked)                                                                      # Trigger backend SFTP upload callback
        self._add_button_shadow(upload_btn)                                                                                           # Add subtle depth to action button

        refresh_btn = QPushButton("Refresh Upload Window")
        refresh_btn.setObjectName("ActionButton")                                                                                     # Manual upload-window refresh button
        refresh_btn.clicked.connect(lambda: self._animate_button_press(refresh_btn))                                                  # Animate press before refreshing the upload window
        refresh_btn.clicked.connect(self._refresh_rqi_upload_window_clicked)                                                          # Trigger backend upload-window refresh callback
        self._add_button_shadow(refresh_btn)                                                                                          # Add subtle depth to action button

        action_row.addStretch(1)                                                                                                      # Center the action buttons inside the current inner tab
        action_row.addWidget(generate_btn)
        action_row.addWidget(upload_btn)
        action_row.addWidget(refresh_btn)
        action_row.addStretch(1)                                                                                                      # Center the action buttons inside the current inner tab

        return action_widget

    def _build_csv_sftp_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)                                                                                                         # Space between heading and internal horizontal tabs

        title = QLabel("RQI Export Manager")
        title.setObjectName("SectionTitle")                                                                                           # Humanized page heading for RQI CSV batching and SFTP uploads

        subtitle = QLabel("Monitor RQI export activity, manage CSV batching, configure SFTP uploads, and run manual export actions.")
        subtitle.setObjectName("SectionSubtitle")                                                                                     # Short explanation for this combined RQI export page
        subtitle.setWordWrap(True)

        export_tabs = QTabWidget()
        export_tabs.setObjectName("SettingsInnerTabs")                                                                                # Horizontal tabs inside the RQI Export Manager page

        # =========================
        # Hidden quick status labels
        # =========================

        self.quick_status = QLabel("Checking status...")                                                                              # Hidden label used by existing _update_status logic
        self.quick_login = QLabel("Checking login state...")                                                                          # Hidden label used by existing _update_login_status logic
        self.quick_mode = QLabel("")                                                                                                  # Hidden label used by existing _update_status logic
        self.quick_queue = QLabel("")                                                                                                 # Hidden label used by existing _update_status logic

        self.quick_status.hide()                                                                                                      # Keep old quick-status backend compatibility without showing clutter
        self.quick_login.hide()                                                                                                       # Keep old quick-login backend compatibility without showing clutter
        self.quick_mode.hide()                                                                                                        # Keep old browser-mode backend compatibility without showing clutter
        self.quick_queue.hide()                                                                                                       # Keep old queue backend compatibility without showing clutter

        # ===========
        # STATUS TAB
        # ===========

        status_page = QWidget()
        status_layout = QVBoxLayout(status_page)
        status_layout.setSpacing(14)

        status_cards_grid = QGridLayout()
        status_cards_grid.setHorizontalSpacing(12)
        status_cards_grid.setVerticalSpacing(12)

        self.rqi_batch_window_label = QLabel("Loading...")                                                                            # Shows current active batch window start and end time
        self.rqi_batch_countdown_label = QLabel("Loading...")                                                                         # Shows live countdown until current batch window ends
        self.rqi_current_csv_label = QLabel("Loading...")                                                                             # Shows currently active CSV batch file path
        self.rqi_last_uploaded_local_label = QLabel("None yet")                                                                       # Shows most recent local CSV file uploaded successfully
        self.rqi_last_uploaded_remote_label = QLabel("None yet")                                                                      # Shows most recent remote SFTP destination used successfully
        self.rqi_last_upload_time_label = QLabel("None yet")                                                                          # Shows timestamp of most recent successful upload
        self.rqi_last_upload_error_label = QLabel("None")                                                                             # Shows most recent upload error

        status_cards = [
            self._make_export_status_card("Current Batch Window", self.rqi_batch_window_label),
            self._make_export_status_card("Time Remaining", self.rqi_batch_countdown_label),
            self._make_export_status_card("Current CSV File", self.rqi_current_csv_label),
            self._make_export_status_card("Last Uploaded Local File", self.rqi_last_uploaded_local_label),
            self._make_export_status_card("Last Uploaded Remote Path", self.rqi_last_uploaded_remote_label),
            self._make_export_status_card("Last Upload Time", self.rqi_last_upload_time_label),
            self._make_export_status_card("Last Upload Error", self.rqi_last_upload_error_label),
        ]                                                                                                                             # Status cards make the live information easier to scan than a long form

        for index, card in enumerate(status_cards):
            row = index // 2
            col = index % 2
            status_cards_grid.addWidget(card, row, col)                                                                               # Arrange status cards into a clean 2-column grid

        status_layout.addLayout(status_cards_grid)
        status_layout.addStretch(1)
        status_layout.addWidget(self._make_export_action_bar(), 0, Qt.AlignHCenter)                                                   # Manual actions stay inside the Status tab box
        status_layout.addSpacing(14)                                                                                                  # Extra space at the bottom of the status tab for visual balance

        export_tabs.addTab(status_page, "Status")                                                                                     # First horizontal tab shows live status

        # =================
        # CSV SETTINGS TAB
        # =================

        csv_page = QWidget()
        csv_layout = QVBoxLayout(csv_page)
        csv_layout.setSpacing(12)

        csv_form = QFormLayout()
        csv_form.setLabelAlignment(Qt.AlignLeft)
        csv_form.setFormAlignment(Qt.AlignTop)
        csv_form.setSpacing(10)

        export_dir_row = QWidget()
        export_dir_layout = QHBoxLayout(export_dir_row)
        export_dir_layout.setContentsMargins(0, 0, 0, 0)
        export_dir_layout.setSpacing(8)

        export_dir_edit = QLineEdit(os.getenv("RQI_CSV_EXPORT_DIR", ""))                                                              # Root folder where time-window CSV subfolders will be created
        self.entries["RQI_CSV_EXPORT_DIR"] = export_dir_edit                                                                          # Save widget reference so Save Settings writes it into the shared .env file

        browse_export_dir_btn = QPushButton("Browse")
        browse_export_dir_btn.setObjectName("BrowseButton")                                                                           # Small helper button for choosing export folder from file dialog
        browse_export_dir_btn.clicked.connect(lambda: self._animate_button_press(browse_export_dir_btn))                              # Animate press before folder chooser opens
        browse_export_dir_btn.clicked.connect(self._browse_rqi_export_dir)                                                            # Open folder chooser and write result into export path field

        export_dir_layout.addWidget(export_dir_edit, 1)
        export_dir_layout.addWidget(browse_export_dir_btn)

        csv_form.addRow("CSV Export Folder", export_dir_row)

        csv_filename_edit = QLineEdit(os.getenv("RQI_CSV_FILENAME", "rqi_export.csv"))                                                # Fixed file name used inside each date/time upload-window folder
        self.entries["RQI_CSV_FILENAME"] = csv_filename_edit
        csv_form.addRow("CSV File Name", csv_filename_edit)

        batch_minutes_edit = QLineEdit(os.getenv("RQI_CSV_BATCH_MINUTES", "15"))                                                      # Number of minutes per automatic CSV batch window
        self.entries["RQI_CSV_BATCH_MINUTES"] = batch_minutes_edit
        csv_form.addRow("Batch Minutes", batch_minutes_edit)

        csv_layout.addLayout(csv_form)
        csv_layout.addStretch(1)
        csv_layout.addWidget(self._make_export_action_bar())                                                                          # Manual actions stay visible inside CSV Settings tab

        export_tabs.addTab(csv_page, "CSV Settings")                                                                                  # CSV folder/name/window settings

        # ==================
        # SFTP SETTINGS TAB
        # ==================

        sftp_page = QWidget()
        sftp_layout = QVBoxLayout(sftp_page)
        sftp_layout.setSpacing(12)

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
        sftp_password_edit.setEchoMode(QLineEdit.Password)                                                                            # Hide SFTP password in the GUI
        self.entries["RQI_SFTP_PASSWORD"] = sftp_password_edit
        sftp_form.addRow("Password", sftp_password_edit)

        sftp_layout.addLayout(sftp_form)
        sftp_layout.addStretch(1)
        sftp_layout.addWidget(self._make_export_action_bar())                                                                         # Manual actions stay visible inside SFTP Settings tab

        export_tabs.addTab(sftp_page, "SFTP Settings")                                                                                # SFTP server credentials and remote file settings

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(export_tabs, 1)

        self._add_sidebar_page(ScrollablePage(page), "RQI Export Manager", "🏠")                                                      # Add sidebar page for RQI export manager

    # ================
    # CREDENTIALS TAB
    # ================

    def _build_credentials_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)                                                                                                         # Comfortable spacing between credential management controls and instructions

        title = QLabel("Credential Management")
        title.setObjectName("SectionTitle")                                                                                           # Main heading for credential management page

        subtitle = QLabel("Manage AHA Login, Email Parsing Settings, and Browser Mode")
        subtitle.setObjectName("SectionSubtitle")                                                                                     # Explanatory text under the main heading to guide users on what belongs in this page
        subtitle.setWordWrap(True)                                                                                                    # Allow explanatory text to wrap naturally inside the content area

        settings_tabs = QTabWidget()                                                                                                  # Use tabs to separate different types of credentials while keeping them all in one place
        settings_tabs.setObjectName("SettingsInnerTabs")                                                                              # Container for AHA Login, Email Parsing, and Browser Mode settings subtabs
        
        # ==============
        # AHA inner tab
        # ==============

        aha_page = QWidget()
        aha_form = QFormLayout(aha_page)
        aha_form.setSpacing(10)

        self.aha_login_label = QLabel("Checking login state...")                                                                      # Live label showing signed in/out state
        aha_form.addRow("AHA Login Status:", self.aha_login_label)

        aha_user = QLineEdit(os.getenv("AHA_USERNAME", ""))                                                                           # Populate username from .env
        aha_pass = QLineEdit(os.getenv("AHA_PASSWORD", ""))                                                                           # Populate password from .env
        aha_pass.setEchoMode(QLineEdit.Password)                                                                                      # Hide password characters in GUI

        self.entries["AHA_USERNAME"] = aha_user                                                                                       # Save widget reference for later .env writeback
        self.entries["AHA_PASSWORD"] = aha_pass                                                                                       # Save widget reference for later .env writeback

        aha_form.addRow("AHA Username", aha_user)
        aha_form.addRow("AHA Password", aha_pass)

        self.headless_toggle = PillSwitch("", "")                                                                                     # Visible/headless browser toggle shown inside AHA Login tab

        current_headless = os.getenv("IS_HEADLESS", "True").strip().lower()
        self.headless_toggle.setChecked(current_headless in ("1", "true", "yes", "on"))                                               # Load existing headless value from .env

        self.headless_toggle_label = QLabel()
        self.headless_toggle_label.setObjectName("HeadlessToggleLabel")                                                               # Text label beside the toggle showing current browser mode

        self.entries["IS_HEADLESS"] = self.headless_toggle                                                                            # Save toggle value back into .env as True/False

        headless_row = QWidget()
        headless_row_layout = QHBoxLayout(headless_row)
        headless_row_layout.setContentsMargins(0, 0, 0, 0)
        headless_row_layout.setSpacing(10)
        headless_row_layout.addWidget(self.headless_toggle)
        headless_row_layout.addWidget(self.headless_toggle_label)
        headless_row_layout.addStretch(1)

        self.headless_toggle.stateChanged.connect(self._update_headless_toggle_label)                                                 # Update descriptive label when toggle changes
        self._update_headless_toggle_label()                                                                                          # Initial label update on page creation

        aha_form.addRow("Browser Mode", headless_row)

        aha_signout_widget = QWidget()
        aha_signout_row = QHBoxLayout(aha_signout_widget)
        aha_signout_row.setContentsMargins(0, 6, 0, 0)                                                                                # Keep Sign Out button aligned to the true left edge of the AHA tab
        aha_signout_row.setSpacing(8)

        self.signout_btn = QPushButton("Sign Out of AHA")
        self.signout_btn.setObjectName("SignOutButton")                                                                               # AHA sign-out button now lives inside the AHA Login settings tab
        self.signout_btn.setFixedHeight(30)
        self.signout_btn.setMaximumWidth(150)
        self.signout_btn.clicked.connect(lambda: self._animate_button_press(self.signout_btn))                                        # Animate press before sign out
        self.signout_btn.clicked.connect(sign_out)                                                                                    # Clear saved AHA login state

        aha_signout_row.addWidget(self.signout_btn, 0, Qt.AlignLeft)                                                                  # Align button to the left edge
        aha_signout_row.addStretch(1)

        aha_form.addRow(aha_signout_widget)                                                                                           # Full-width form row with no label-column indentation

        settings_tabs.addTab(aha_page, "AHA Login")                                                                                   # Add AHA settings as horizontal inner tab

        # ================
        # Email inner tab
        # ================

        email_page = QWidget()
        email_form = QFormLayout(email_page)
        email_form.setSpacing(10)

        email_fields = {
            "SENDER_EMAIL": "Sender Email Address",
            "KEYWORD_NAME": "Keyword Before Name",
            "INTERVAL": "Automation Interval (seconds)",
            "SENDER_EMAIL_RQI": "Sender Email for RQI Parsing",
        }                                                                                                                             # Email and parsing related env fields

        for key, label in email_fields.items():
            edit = QLineEdit(os.getenv(key, ""))                                                                                      # Pre-fill each field from current .env
            self.entries[key] = edit                                                                                                  # Store widget by env variable name
            email_form.addRow(label, edit)

        settings_tabs.addTab(email_page, "Email")                                                                                     # Add Email settings as horizontal inner tab

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(settings_tabs, 1)

        self._add_sidebar_page(ScrollablePage(page), "Credentials Management", "🔐")                                                  # One sidebar button for AHA, Email, and Browser Mode

    # ==============
    # REMINDERS TAB
    # ==============

    def _build_reminders_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)                                                                                                         # Comfortable spacing between heading and reminder subtabs

        title = QLabel("Reminders")
        title.setObjectName("SectionTitle")                                                                                           # Main heading for all reminder-related tools

        subtitle = QLabel("Manage automatic reminder email templates and send manual reminder emails.")
        subtitle.setObjectName("SectionSubtitle")                                                                                     # Short explanation for the combined reminders page
        subtitle.setWordWrap(True)

        reminder_tabs = QTabWidget()
        reminder_tabs.setObjectName("SettingsInnerTabs")                                                                              # Horizontal tabs inside the Reminders sidebar page
        reminder_tabs.setMinimumHeight(0)                                                                                             # Prevent Reminders inner tab widget from pushing into the top controls
        reminder_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)                                                       # Let inner tab pages scroll instead of making the whole page too tall

        reminder_email_page = self._make_reminder_emails_page()                                                                       # Automatic reminder email settings/template editor
        manual_email_page = self._make_manual_emailer_page()                                                                          # Manual email sending tools

        reminder_email_scroll = ScrollablePage(reminder_email_page)                                                                   # Reminder Emails tab gets its own scroll area
        reminder_email_scroll.setMinimumHeight(0)                                                                                     # Prevent inner scroll page from forcing the whole app taller
        reminder_email_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)                                               # Allow tab content to shrink instead of clipping top buttons

        manual_email_scroll = ScrollablePage(manual_email_page)                                                                       # Manual Emailer tab gets its own scroll area
        manual_email_scroll.setMinimumHeight(0)                                                                                       # Prevent inner scroll page from forcing the whole app taller
        manual_email_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)                                                 # Allow tab content to scroll instead of expanding the main window

        reminder_tabs.addTab(reminder_email_scroll, "Reminder Emails")                                                                # First horizontal tab for automated reminder templates
        reminder_tabs.addTab(manual_email_scroll, "Manual Emailer")                                                                   # Second horizontal tab for manual sending

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(reminder_tabs, 1)

        self._add_sidebar_page(page, "Reminders", "⏰")                                                                               # One sidebar button for all reminder tools

    def _make_reminder_emails_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)                                                                                                         # Comfortable spacing between reminder timing controls and email body editors
        layout.setAlignment(Qt.AlignTop)                                                                                              # Keep Reminder Emails controls stacked at the top instead of spreading vertically

        form = QFormLayout()
        form.setSpacing(10)

        # Reminder cadence for non-registered Acuity users (x days)
        not_registered_days = QSpinBox()
        not_registered_days.setMinimum(1)
        not_registered_days.setMaximum(3650)
        not_registered_days.setValue(int(os.getenv("ACUITY_NOT_REGISTERED_REMINDER_DAYS", os.getenv("REMINDER_EMAIL_DAYS", "7"))))
        self.entries["ACUITY_NOT_REGISTERED_REMINDER_DAYS"] = not_registered_days                                                     # Save reminder timing for non-registered Acuity users into .env
        form.addRow("Reminder For Acuity Not Registered Yet (Days)", not_registered_days)

        # Reminder cadence for registered Acuity users (y years)
        registered_years = QSpinBox()
        registered_years.setMinimum(1)
        registered_years.setMaximum(25)
        registered_years.setValue(int(os.getenv("ACUITY_REGISTERED_REMINDER_YEARS", "1")))
        self.entries["ACUITY_REGISTERED_REMINDER_YEARS"] = registered_years                                                           # Save reminder timing for registered Acuity users into .env
        form.addRow("Reminder For Acuity Registered Users (Years)", registered_years)

        layout.addLayout(form)

        ensure_template_files()                                                                                                       # Make sure template files exist before loading them into the editors

        # =======================================
        # Reminder email body for non-registered users
        # =======================================

        not_registered_body_title = QLabel("Non-Registered User Email Body")
        not_registered_body_title.setObjectName("SectionSubtitle")                                                                    # Section heading above the non-registered reminder email body editor

        self.not_registered_email_body_edit = QPlainTextEdit()
        self.not_registered_email_body_edit.setPlaceholderText("Type the email body for non-registered users here...")                # Guide the user on what belongs in this editor
        self.not_registered_email_body_edit.setPlainText(read_template_file(NOT_REGISTERED_TEMPLATE_FILE))                            # Load saved non-registered reminder email template from text file
        self.not_registered_email_body_edit.setFixedHeight(120)                                                                       # Clean compact default editor height for reminder templates
        self.not_registered_email_body_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)                                   # Prevent vertical layout from stretching this editor        
        self.entries["ACUITY_NOT_REGISTERED_EMAIL_BODY_TEMPLATE"] = self.not_registered_email_body_edit                               # Save editor through template-file logic in save_settings()

        layout.addWidget(not_registered_body_title)
        layout.addWidget(self.not_registered_email_body_edit)

        # =======================================
        # Reminder email body for registered users
        # =======================================

        registered_body_title = QLabel("Registered User Email Body")
        registered_body_title.setObjectName("SectionSubtitle")                                                                        # Section heading above the registered reminder email body editor

        self.registered_email_body_edit = QPlainTextEdit()
        self.registered_email_body_edit.setPlaceholderText("Type the email body for registered users here...")                        # Guide the user on what belongs in this editor
        self.registered_email_body_edit.setPlainText(read_template_file(REGISTERED_TEMPLATE_FILE))                                    # Load saved registered reminder email template from text file
        self.registered_email_body_edit.setFixedHeight(120)                                                                           # Clean compact default editor height for reminder templates
        self.registered_email_body_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)                                       # Prevent vertical layout from stretching this editor        
        self.entries["ACUITY_REGISTERED_EMAIL_BODY_TEMPLATE"] = self.registered_email_body_edit                                       # Save editor through template-file logic in save_settings()

        layout.addWidget(registered_body_title)
        layout.addWidget(self.registered_email_body_edit)
        self.registered_email_body_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)                                       # Prevent editor row from vertically stretching and creating huge empty gaps

        return page                                                                                                                   # Return page so it can be placed inside the Reminders horizontal tab

    def _make_manual_emailer_page(self):
        from manual_email_handler import get_available_locations
        
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)                                                                                              # Keep reminder controls stacked at the top instead of spreading vertically

        title = QLabel("Manual Email Sender")
        title.setObjectName("SectionTitle")

        subtitle = QLabel(
            "Send individual emails manually while preventing duplicate auto-emailer sends. "
            "Sent emails are tracked automatically to prevent the auto-emailer from sending to the same person."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("SectionSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        # === Single Email Form ===
        form = QFormLayout()
        form.setSpacing(10)

        self.manual_email_input = QLineEdit()
        self.manual_email_input.setPlaceholderText("recipient@example.com")
        form.addRow("Email Address*", self.manual_email_input)

        self.manual_location_combo = QComboBox()
        self.manual_location_combo.setEditable(True)
        self.manual_location_combo.setPlaceholderText("Select or type location...")
        form.addRow("Location*", self.manual_location_combo)

        self.manual_first_name_input = QLineEdit()
        self.manual_first_name_input.setPlaceholderText("John (optional, for personalization)")
        form.addRow("First Name", self.manual_first_name_input)

        self.manual_last_name_input = QLineEdit()
        self.manual_last_name_input.setPlaceholderText("Doe (optional, for personalization)")
        form.addRow("Last Name", self.manual_last_name_input)

        self.manual_cycle_marker_input = QLineEdit()
        self.manual_cycle_marker_input.setPlaceholderText("01/15/2026 (optional, for tracking)")
        form.addRow("Cycle Marker/Date", self.manual_cycle_marker_input)

        layout.addLayout(form)

        # === Custom Subject/Body (Optional) ===
        custom_section = QLabel("Custom Email Content (Optional - leave blank to use template)")
        custom_section.setObjectName("SectionSubtitle")
        layout.addWidget(custom_section)

        self.manual_subject_input = QLineEdit()
        self.manual_subject_input.setPlaceholderText("Leave blank to use location template...")
        layout.addWidget(QLabel("Custom Subject:"))
        layout.addWidget(self.manual_subject_input)

        self.manual_body_input = QTextEdit()
        self.manual_body_input.setPlaceholderText("Leave blank to use location template...")
        self.manual_body_input.setMaximumHeight(120)
        layout.addWidget(QLabel("Custom Body:"))
        layout.addWidget(self.manual_body_input)

        # === Update Sheet Option ===
        self.manual_update_sheet_checkbox = QCheckBox("Update 'Reminder Email' column in sheet after sending")
        self.manual_update_sheet_checkbox.setChecked(True)
        layout.addWidget(self.manual_update_sheet_checkbox)

        # === Action Buttons ===
        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.manual_preview_btn = QPushButton("Preview Email")
        self.manual_preview_btn.setObjectName("ActionButton")                                                                         # Match RQI Export Manager action button styling
        self.manual_preview_btn.clicked.connect(self._preview_manual_email)
        button_row.addWidget(self.manual_preview_btn)

        self.manual_send_btn = QPushButton("Send Email")
        self.manual_send_btn.clicked.connect(self._send_manual_email)
        self.manual_send_btn.setObjectName("ActionButton")
        button_row.addWidget(self.manual_send_btn)

        self.manual_refresh_locations_btn = QPushButton("Refresh Locations")
        self.manual_refresh_locations_btn.setObjectName("ActionButton")                                                               # Match RQI Export Manager action button styling
        self.manual_refresh_locations_btn.clicked.connect(self._refresh_manual_location_combo)
        button_row.addWidget(self.manual_refresh_locations_btn)

        layout.addLayout(button_row)

        # === Batch Upload Section ===
        batch_section = QLabel("Batch Send (CSV File)")
        batch_section.setObjectName("SectionSubtitle")
        layout.addWidget(batch_section)

        batch_info = QLabel("CSV format: Email,Location,FirstName,LastName,CycleMarker")
        batch_info.setWordWrap(True)
        layout.addWidget(batch_info)

        batch_row = QHBoxLayout()
        self.manual_csv_path_label = QLabel("No file selected")
        batch_row.addWidget(self.manual_csv_path_label, 1)

        self.manual_browse_csv_btn = QPushButton("Browse...")
        self.manual_browse_csv_btn.setObjectName("ActionButton")
        self.manual_browse_csv_btn.clicked.connect(self._browse_manual_csv)
        batch_row.addWidget(self.manual_browse_csv_btn)

        self.manual_send_batch_btn = QPushButton("Send Batch")
        self.manual_send_batch_btn.setObjectName("ActionButton")
        self.manual_send_batch_btn.clicked.connect(self._send_manual_batch)
        self.manual_send_batch_btn.setEnabled(False)
        batch_row.addWidget(self.manual_send_batch_btn)

        layout.addLayout(batch_row)

        # === Status Log ===
        log_label = QLabel("Send Log:")
        log_label.setObjectName("SectionSubtitle")
        layout.addWidget(log_label)

        self.manual_send_log = QPlainTextEdit()
        self.manual_send_log.setReadOnly(True)
        self.manual_send_log.setMaximumHeight(150)
        self.manual_send_log.setPlaceholderText("Email send status will appear here...")
        layout.addWidget(self.manual_send_log)

        self._refresh_manual_location_combo()                                                                                         # Refresh location dropdown only after manual_send_log exists

        layout.addStretch(1)

        return page                                                                                                                   # Return page so it can be placed inside the Reminders horizontal tab

    def _refresh_manual_location_combo(self):
        """Refresh the location dropdown with current location keys."""
        from manual_email_handler import get_available_locations
        
        try:
            self.manual_location_combo.clear()
            locations = get_available_locations()
            
            for location in locations:
                self.manual_location_combo.addItem(location)
                
            self._log_to_manual_send("✓ Locations refreshed")
        except Exception as e:
            self._log_to_manual_send(f"✗ Failed to refresh locations: {e}")

    def _browse_manual_csv(self):
        """Browse for a CSV file for batch sending."""
        csv_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV File for Batch Email Send",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if csv_path:
            self.manual_csv_path_label.setText(csv_path)
            self.manual_send_batch_btn.setEnabled(True)
            self._log_to_manual_send(f"✓ Selected: {csv_path}")

    def _log_to_manual_send(self, message: str):
        """Add a message to the manual send log."""
        if not hasattr(self, "manual_send_log"):                                                                                       # Avoid crashing if logging happens before the log widget is created
            logging.debug("Manual Emailer: %s", message)
            return

        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.manual_send_log.appendPlainText(f"[{timestamp}] {message}")

    def _preview_manual_email(self):
        """Preview the email that would be sent."""
        from manual_email_handler import compose_email_content
        
        try:
            email = self.manual_email_input.text().strip()
            location = self.manual_location_combo.currentText().strip()
            first_name = self.manual_first_name_input.text().strip()
            last_name = self.manual_last_name_input.text().strip()
            custom_subject = self.manual_subject_input.text().strip()
            custom_body = self.manual_body_input.toPlainText().strip()

            if not email or "@" not in email:
                QMessageBox.warning(self, "Invalid Email", "Please enter a valid email address.")
                return

            if not location:
                QMessageBox.warning(self, "Missing Location", "Please select or enter a location.")
                return

            subject, body, error = compose_email_content(
                email, location, first_name, last_name, custom_subject, custom_body
            )
            
            if error:
                QMessageBox.warning(self, "Composition Error", error)
                return

            preview_text = (
                f"TO: {email}\n"
                f"LOCATION: {location}\n"
                f"SUBJECT: {subject}\n"
                f"\n{'-' * 60}\n\n"
                f"{body}"
            )

            preview_dialog = QDialog(self)
            preview_dialog.setWindowTitle("Email Preview")
            preview_dialog.resize(600, 400)
            
            preview_layout = QVBoxLayout(preview_dialog)
            preview_text_widget = QPlainTextEdit()
            preview_text_widget.setPlainText(preview_text)
            preview_text_widget.setReadOnly(True)
            preview_layout.addWidget(preview_text_widget)
            
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(preview_dialog.accept)
            preview_layout.addWidget(close_btn)
            
            preview_dialog.exec()

        except Exception as e:
            QMessageBox.critical(self, "Preview Failed", f"Could not preview email:\n{e}")
            self._log_to_manual_send(f"✗ Preview failed: {e}")

    def _send_manual_email(self):
        """Send a single manual email."""
        from manual_email_handler import (
            send_single_manual_email,
            check_if_already_sent,
            update_reminder_email_column,
        )
        
        try:
            email = self.manual_email_input.text().strip()
            location = self.manual_location_combo.currentText().strip()
            first_name = self.manual_first_name_input.text().strip()
            last_name = self.manual_last_name_input.text().strip()
            cycle_marker = self.manual_cycle_marker_input.text().strip()
            custom_subject = self.manual_subject_input.text().strip()
            custom_body = self.manual_body_input.toPlainText().strip()
            update_sheet = self.manual_update_sheet_checkbox.isChecked()

            if not email or "@" not in email:
                QMessageBox.warning(self, "Invalid Email", "Please enter a valid email address.")
                return

            if not location:
                QMessageBox.warning(self, "Missing Location", "Please select or enter a location.")
                return

            self._log_to_manual_send(f"Sending to {email}...")
            
            # Check if already sent
            already_sent, _ = check_if_already_sent(email, location, cycle_marker)
            force_send = False
            
            if already_sent:
                reply = QMessageBox.question(
                    self,
                    "Already Sent",
                    f"Email to {email} for location '{location}' was already sent.\n\nSend anyway?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    self._log_to_manual_send(f"✗ Cancelled (already sent): {email}")
                    return
                force_send = True

            # Send email
            result = send_single_manual_email(
                email, location, first_name, last_name, cycle_marker,
                custom_subject, custom_body, force_send
            )
            
            if result.success:
                self._log_to_manual_send(f"✓ {result.message}")

                # Update sheet if requested
                if update_sheet:
                    success, message = update_reminder_email_column(email)
                    if success:
                        self._log_to_manual_send(f"✓ {message}")
                    else:
                        self._log_to_manual_send(f"⚠ {message}")

                QMessageBox.information(self, "Success", result.message)
                
                # Clear form
                self.manual_email_input.clear()
                self.manual_first_name_input.clear()
                self.manual_last_name_input.clear()
                self.manual_cycle_marker_input.clear()
                self.manual_subject_input.clear()
                self.manual_body_input.clear()
            else:
                self._log_to_manual_send(f"✗ {result.message}")
                QMessageBox.critical(self, "Send Failed", result.message)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to send email:\n{e}")
            self._log_to_manual_send(f"✗ Error: {e}")

    def _send_manual_batch(self):
        """Send batch emails from CSV file."""
        from manual_email_handler import send_batch_from_csv, update_reminder_email_column
        
        csv_path = self.manual_csv_path_label.text()
        if csv_path == "No file selected":
            return

        try:
            update_sheet = self.manual_update_sheet_checkbox.isChecked()
            
            self._log_to_manual_send(f"=== Starting batch send from {csv_path} ===")
            
            stats = send_batch_from_csv(csv_path, update_sheet)
            
            self._log_to_manual_send(
                f"=== Batch complete: {stats['success']} sent, "
                f"{stats['failed']} failed, {stats['skipped']} skipped ==="
            )
            
            QMessageBox.information(
                self,
                "Batch Complete",
                f"Batch send complete:\n"
                f"{stats['success']} sent\n"
                f"{stats['failed']} failed\n"
                f"{stats['skipped']} skipped"
            )

        except Exception as e:
            QMessageBox.critical(self, "Batch Failed", f"Batch send failed:\n{e}")
            self._log_to_manual_send(f"✗ Batch error: {e}")

    # =============
    # LOCATIONS TAB
    # =============

    def _build_locations_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)                                                                                                         # Comfortable spacing between heading and location subtabs

        title = QLabel("Locations")
        title.setObjectName("SectionTitle")                                                                                           # Main heading for all location-related tools

        subtitle = QLabel("Manage location keys, location email templates, and sent-email tracking.")
        subtitle.setObjectName("SectionSubtitle")                                                                                     # Short explanation for the combined Locations page
        subtitle.setWordWrap(True)

        location_tabs = QTabWidget()
        location_tabs.setObjectName("SettingsInnerTabs")                                                                              # Horizontal tabs inside the Locations sidebar page
        location_tabs.setMinimumHeight(0)                                                                                              # Prevent location subtabs from forcing the app layout taller
        location_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)                                                       # Let inner pages scroll instead of stretching the whole GUI

        keys_page = self._make_location_keys_page()                                                                                   # Location key mapping editor
        templates_page = self._make_location_templates_page()                                                                         # Location email template editor
        tracker_page = self._make_location_tracker_page()                                                                             # Location email tracker audit page

        keys_scroll = ScrollablePage(keys_page)                                                                                       # Location Keys tab gets its own scrolling
        keys_scroll.setMinimumHeight(0)
        keys_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)

        templates_scroll = ScrollablePage(templates_page)                                                                             # Location Templates tab gets its own scrolling
        templates_scroll.setMinimumHeight(0)
        templates_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)

        tracker_scroll = ScrollablePage(tracker_page)                                                                                 # Location Tracker tab gets its own scrolling
        tracker_scroll.setMinimumHeight(0)
        tracker_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)

        location_tabs.addTab(keys_scroll, "Location Keys")                                                                            # First horizontal tab for location key mappings
        location_tabs.addTab(templates_scroll, "Location Templates")                                                                  # Second horizontal tab for template JSON/editor
        location_tabs.addTab(tracker_scroll, "Location Tracker")                                                                      # Third horizontal tab for sent-email tracking

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(location_tabs, 1)

        self._add_sidebar_page(page, "Locations", "📌")                                                                               # One sidebar button for all location tools

    # ===================
    # LOCATION KEYS PAGE
    # ===================

    def _make_location_keys_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        title = QLabel("Location Keys")
        title.setObjectName("SectionTitle")

        subtitle = QLabel(
            "Manage the key-to-location list used by automation. "
            "Entries are saved in a plain text file and can be added or removed here."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("SectionSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setSpacing(10)

        self.location_key_edit = QLineEdit()
        self.location_key_edit.setPlaceholderText("Location key (example: SAC_MAIN)")
        form.addRow("Key", self.location_key_edit)

        self.location_name_edit = QLineEdit()
        self.location_name_edit.setPlaceholderText("Location name (example: Sacramento Main Campus)")
        form.addRow("Location", self.location_name_edit)

        layout.addLayout(form)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        self.add_location_key_btn = QPushButton("Add / Update")
        self.add_location_key_btn.setObjectName("ActionButton")
        self.add_location_key_btn.clicked.connect(lambda: self._animate_button_press(self.add_location_key_btn))
        self.add_location_key_btn.clicked.connect(self._add_location_key_clicked)

        self.remove_location_key_btn = QPushButton("Remove")
        self.remove_location_key_btn.setObjectName("ActionButton")
        self.remove_location_key_btn.clicked.connect(lambda: self._animate_button_press(self.remove_location_key_btn))
        self.remove_location_key_btn.clicked.connect(self._remove_location_key_clicked)

        self.refresh_location_keys_btn = QPushButton("Refresh")
        self.refresh_location_keys_btn.setObjectName("ActionButton")
        self.refresh_location_keys_btn.clicked.connect(lambda: self._animate_button_press(self.refresh_location_keys_btn))
        self.refresh_location_keys_btn.clicked.connect(self._refresh_location_keys_list)

        action_row.addWidget(self.add_location_key_btn)
        action_row.addWidget(self.remove_location_key_btn)
        action_row.addWidget(self.refresh_location_keys_btn)
        action_row.addStretch(1)

        layout.addLayout(action_row)

        self.location_keys_list = QListWidget()
        self.location_keys_list.itemSelectionChanged.connect(self._sync_location_selection_to_inputs)
        layout.addWidget(self.location_keys_list, 1)

        self.location_store_path_label = QLabel("")
        self.location_store_path_label.setWordWrap(True)
        layout.addWidget(self.location_store_path_label)

        self._refresh_location_keys_list()
        
        return page

    def _refresh_location_keys_list(self):
        pairs = load_location_keys()
        self.location_keys_list.clear()

        for key in sorted(pairs.keys(), key=lambda value: value.lower()):
            self.location_keys_list.addItem(f"{key} | {pairs[key]}")

        self.location_store_path_label.setText(f"Storage file: {get_location_keys_file_path()}")

    def _sync_location_selection_to_inputs(self):
        selected_items = self.location_keys_list.selectedItems()
        if not selected_items:
            return

        text = selected_items[0].text()
        if "|" not in text:
            return

        key, location = text.split("|", 1)
        self.location_key_edit.setText(key.strip())
        self.location_name_edit.setText(location.strip())

    def _add_location_key_clicked(self):
        key = self.location_key_edit.text().strip()
        location = self.location_name_edit.text().strip()

        if not key or not location:
            QMessageBox.warning(self, "Missing Value", "Both key and location are required.")
            return

        try:
            upsert_location_key(key, location)
            template_created = ensure_location_template_entry(key, location)
            self._refresh_location_keys_list()
            self._reload_location_templates_editor_from_disk()
            message = f"Location key saved: {key}"
            if template_created:
                message += "\n\nA matching location email template entry was also created."
            QMessageBox.information(self, "Saved", message)
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))

    def _remove_location_key_clicked(self):
        key = self.location_key_edit.text().strip()
        if not key:
            selected_items = self.location_keys_list.selectedItems()
            if selected_items and "|" in selected_items[0].text():
                key = selected_items[0].text().split("|", 1)[0].strip()

        if not key:
            QMessageBox.warning(self, "Missing Key", "Enter or select a key to remove.")
            return

        try:
            removed = remove_location_key(key)
            if not removed:
                QMessageBox.information(self, "Not Found", f"Location key not found: {key}")
                return

            remove_location_template_entry(key)
            self._refresh_location_keys_list()
            self._reload_location_templates_editor_from_disk()
            self.location_key_edit.clear()
            self.location_name_edit.clear()
            QMessageBox.information(self, "Removed", f"Location key removed: {key}")
        except Exception as e:
            QMessageBox.critical(self, "Remove Failed", str(e))

    def _reload_location_templates_editor_from_disk(self):
        if not hasattr(self, "location_templates_editor"):
            return

        template_path = get_location_templates_file_path()
        try:
            self.location_templates_editor.setPlainText(Path(template_path).read_text(encoding="utf-8"))
        except Exception:
            self.location_templates_editor.setPlainText("{}")

        self._refresh_location_template_key_list()

    def _parse_location_templates_editor_json(self, show_error: bool = False):
        if not hasattr(self, "location_templates_editor"):
            return None

        raw = self.location_templates_editor.toPlainText().strip() or "{}"
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("Template JSON must be an object.")
            return parsed
        except Exception as e:
            if show_error:
                QMessageBox.critical(self, "Invalid Template JSON", f"Could not parse location templates:\n{e}")
            return None

    def _refresh_location_template_key_list(self, preferred_key: str = ""):
        if not hasattr(self, "location_template_keys_list"):
            return

        parsed = self._parse_location_templates_editor_json(show_error=False)
        if parsed is None:
            return

        by_key = parsed.get("by_key") if isinstance(parsed.get("by_key"), dict) else {}
        # Keep insertion order so newly added locations appear at the bottom.
        keys = list(by_key.keys())

        self.location_template_keys_list.clear()
        for key in keys:
            self.location_template_keys_list.addItem(key)

        target = (preferred_key or self.location_template_key_edit.text() or "").strip()
        if not target and keys:
            target = keys[0]

        if target:
            for idx in range(self.location_template_keys_list.count()):
                item = self.location_template_keys_list.item(idx)
                if (item.text() or "").strip() == target:
                    self.location_template_keys_list.setCurrentRow(idx)
                    break

    def _sync_template_selection_to_inputs(self):
        if not hasattr(self, "location_template_keys_list"):
            return

        selected_items = self.location_template_keys_list.selectedItems()
        if not selected_items:
            return

        key = selected_items[0].text().strip()
        self.location_template_key_edit.setText(key)

        parsed = self._parse_location_templates_editor_json(show_error=False)
        if parsed is None:
            return

        by_key = parsed.get("by_key") if isinstance(parsed.get("by_key"), dict) else {}
        entry = by_key.get(key) if isinstance(by_key.get(key), dict) else {}

        self.location_template_subject_edit.setText((entry.get("subject") or "").strip())
        self.location_template_body_edit.setPlainText(entry.get("body") or "")

    def _save_template_entry_from_inputs(self):
        parsed = self._parse_location_templates_editor_json(show_error=True)
        if parsed is None:
            return

        key = (self.location_template_key_edit.text() or "").strip()
        if not key:
            QMessageBox.warning(self, "Missing Template Key", "Enter or select a template key.")
            return

        subject = self.location_template_subject_edit.text().strip()
        body = self.location_template_body_edit.toPlainText()

        if not isinstance(parsed.get("default"), dict):
            parsed["default"] = {}
        if not isinstance(parsed.get("by_key"), dict):
            parsed["by_key"] = {}
        if not isinstance(parsed.get("by_location"), dict):
            parsed["by_location"] = {}

        parsed["by_key"][key] = {
            "subject": subject,
            "body": body,
        }

        self.location_templates_editor.setPlainText(json.dumps(parsed, indent=2) + "\n")
        self._refresh_location_template_key_list(preferred_key=key)
        QMessageBox.information(self, "Template Saved", f"Template entry saved for key: {key}")

    def _format_location_templates_json(self):
        parsed = self._parse_location_templates_editor_json(show_error=True)
        if parsed is None:
            return

        self.location_templates_editor.setPlainText(json.dumps(parsed, indent=2) + "\n")
        self._refresh_location_template_key_list()

    # ========================
    # LOCATION TEMPLATES PAGE
    # ========================

    def _make_location_templates_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        title = QLabel("Location Email Templates")
        title.setObjectName("SectionTitle")

        subtitle = QLabel(
            "Store per-location email formats in JSON. "
            "Selection order is by_key, then by_location, then default."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("SectionSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        ensure_location_templates_file()
        template_path = get_location_templates_file_path()

        self.location_templates_path_label = QLabel(f"Template file: {template_path}")
        self.location_templates_path_label.setWordWrap(True)
        layout.addWidget(self.location_templates_path_label)

        structured_hint = QLabel(
            "Use the fields below to edit one location at a time. "
            "This updates the JSON automatically so users do not need to hand-edit JSON."
        )
        structured_hint.setWordWrap(True)
        structured_hint.setObjectName("SectionSubtitle")
        layout.addWidget(structured_hint)

        new_location_hint = QLabel(
            "New locations appear at the bottom of the list below."
        )
        new_location_hint.setWordWrap(True)
        new_location_hint.setObjectName("SectionSubtitle")
        layout.addWidget(new_location_hint)

        self.location_template_keys_list = QListWidget()
        self.location_template_keys_list.setMinimumHeight(120)
        self.location_template_keys_list.itemSelectionChanged.connect(self._sync_template_selection_to_inputs)
        layout.addWidget(self.location_template_keys_list)

        template_form = QFormLayout()
        template_form.setSpacing(8)

        self.location_template_key_edit = QLineEdit()
        self.location_template_key_edit.setPlaceholderText("Template key (example: TN Film)")
        template_form.addRow("Key", self.location_template_key_edit)

        self.location_template_subject_edit = QLineEdit()
        self.location_template_subject_edit.setPlaceholderText("Email subject")
        template_form.addRow("Subject", self.location_template_subject_edit)

        self.location_template_body_edit = QPlainTextEdit()
        self.location_template_body_edit.setMinimumHeight(180)
        self.location_template_body_edit.setPlaceholderText("Email body for the selected location key")
        template_form.addRow("Body", self.location_template_body_edit)

        layout.addLayout(template_form)

        template_actions = QHBoxLayout()
        template_actions.setContentsMargins(0, 0, 0, 0)
        template_actions.setSpacing(8)

        self.template_entry_save_btn = QPushButton("Save Selected Entry")
        self.template_entry_save_btn.setObjectName("ActionButton")
        self.template_entry_save_btn.clicked.connect(lambda: self._animate_button_press(self.template_entry_save_btn))
        self.template_entry_save_btn.clicked.connect(self._save_template_entry_from_inputs)

        self.template_json_format_btn = QPushButton("Format JSON")
        self.template_json_format_btn.setObjectName("ActionButton")
        self.template_json_format_btn.clicked.connect(lambda: self._animate_button_press(self.template_json_format_btn))
        self.template_json_format_btn.clicked.connect(self._format_location_templates_json)

        template_actions.addWidget(self.template_entry_save_btn)
        template_actions.addWidget(self.template_json_format_btn)
        template_actions.addStretch(1)
        layout.addLayout(template_actions)

        self.location_templates_editor = QPlainTextEdit()
        self.location_templates_editor.setMinimumHeight(320)
        self.location_templates_editor.setPlaceholderText(
            '{\n  "default": {"subject": "...", "body": "..."},\n  "by_key": {},\n  "by_location": {}\n}'
        )

        try:
            self.location_templates_editor.setPlainText(Path(template_path).read_text(encoding="utf-8"))
        except Exception:
            self.location_templates_editor.setPlainText("{}")

        self._refresh_location_template_key_list()

        self.entries["LOCATION_EMAIL_TEMPLATES_JSON_EDITOR"] = self.location_templates_editor
        layout.addWidget(self.location_templates_editor, 1)

        layout.addStretch(1)
        
        return page                                                                                                                   # Return page so it can be placed inside the Locations horizontal tab

    # ======================
    # LOCATION TRACKER PAGE
    # ======================

    def _make_location_tracker_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        title = QLabel("Location Email Tracker")
        title.setObjectName("SectionTitle")

        subtitle = QLabel(
            "Audit one-time location email sends without writing tracking data into the RQI sheet. "
            "Tracker rows store timestamp and hashed identifiers."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("SectionSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        self.refresh_location_tracker_btn = QPushButton("Refresh")
        self.refresh_location_tracker_btn.setObjectName("ActionButton")
        self.refresh_location_tracker_btn.clicked.connect(lambda: self._animate_button_press(self.refresh_location_tracker_btn))
        self.refresh_location_tracker_btn.clicked.connect(self._refresh_location_tracker_list)

        self.clear_location_tracker_btn = QPushButton("Clear Tracker")
        self.clear_location_tracker_btn.setObjectName("ActionButton")
        self.clear_location_tracker_btn.clicked.connect(lambda: self._animate_button_press(self.clear_location_tracker_btn))
        self.clear_location_tracker_btn.clicked.connect(self._clear_location_tracker_clicked)

        action_row.addWidget(self.refresh_location_tracker_btn)
        action_row.addWidget(self.clear_location_tracker_btn)
        action_row.addStretch(1)

        layout.addLayout(action_row)

        self.location_tracker_list = QListWidget()
        layout.addWidget(self.location_tracker_list, 1)

        self.location_tracker_path_label = QLabel("")
        self.location_tracker_path_label.setWordWrap(True)
        layout.addWidget(self.location_tracker_path_label)

        self._refresh_location_tracker_list()
        
        return page                                                                                                                   # Return page so it can be placed inside the Locations horizontal tab

    def _refresh_location_tracker_list(self):
        entries = load_tracker_entries()
        self.location_tracker_list.clear()

        if not entries:
            self.location_tracker_list.addItem("No tracker entries yet.")
        else:
            for timestamp, hash_value in entries:
                if timestamp:
                    self.location_tracker_list.addItem(f"{timestamp} | {hash_value}")
                else:
                    self.location_tracker_list.addItem(f"(legacy) | {hash_value}")

        self.location_tracker_path_label.setText(f"Tracker file: {get_tracker_file_path()}")

    def _clear_location_tracker_clicked(self):
        result = QMessageBox.question(
            self,
            "Clear Tracker",
            "Clear all location email tracker entries?",
        )
        if result != QMessageBox.Yes:
            return

        try:
            clear_tracker_file()
            self._refresh_location_tracker_list()
            QMessageBox.information(self, "Tracker Cleared", "Location email tracker entries were cleared.")
        except Exception as e:
            QMessageBox.critical(self, "Clear Failed", str(e))

    # =========
    # lOGS TAB
    # =========

    def _build_logs_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Live Application Logs")
        title.setObjectName("SectionTitle")                                                                                           # Main heading for logs tab

        subtitle = QLabel("Switch between separated logs for the full app, RQI, AHA, SFTP, and errors.")
        subtitle.setObjectName("SectionSubtitle")                                                                                     # Short explanation for the horizontal log tabs
        subtitle.setWordWrap(True)

        self.log_tabs = QTabWidget()
        self.log_tabs.setObjectName("LogTabs")                                                                                        # Horizontal tabs for switching between log files
        self.log_tabs.currentChanged.connect(self._reset_selected_log_view)                                                           # Reload selected log from the beginning when switching tabs

        self.log_viewers = {}                                                                                                         # Stores QPlainTextEdit widgets by log category
        self.log_positions = {}                                                                                                       # Stores file read positions by log category

        log_tabs = {
            "All Logs": "app.log",
            "RQI": "logs/rqi.log",
            "AHA": "logs/aha.log",
            "SFTP": "logs/sftp.log",
            "Errors": "logs/errors.log",
        }                                                                                                                             # Log tab label mapped to relative log file path

        for tab_name, relative_path in log_tabs.items():
            viewer = QPlainTextEdit()
            viewer.setReadOnly(True)                                                                                                  # Prevent editing log file contents from GUI
            viewer.setLineWrapMode(QPlainTextEdit.NoWrap)                                                                             # Keep logs aligned like normal log files
            viewer.setPlaceholderText(f"{tab_name} log entries will appear here...")

            self.log_viewers[tab_name] = viewer                                                                                       # Save viewer so refresh logic can update the selected tab
            self.log_positions[tab_name] = 0                                                                                          # Start reading each log from beginning on first load

            self.log_tabs.addTab(viewer, tab_name)                                                                                    # Add horizontal clickable tab for this log category

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.log_tabs, 1)

        self._add_sidebar_page(page, "System Logs", "🧾")                                                                             # Add live log viewer page to sidebar navigation

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

        self.mini_log_timer = QTimer(self)
        self.mini_log_timer.timeout.connect(self._update_mini_logs)                                                                   # Refresh the cleaned mini activity feed
        self.mini_log_timer.start(3000)                                                                                               # Update every 3 seconds

        self.rqi_status_timer = QTimer(self)
        self.rqi_status_timer.timeout.connect(self._update_rqi_csv_sftp_status)                                                       # Refresh current batch window countdown and last upload information
        self.rqi_status_timer.start(1000)                                                                                             # Every 1 second so countdown feels live and responsive

        self._update_status()                                                                                                         # Initial status refresh on startup
        self._update_login_status()                                                                                                   # Initial login refresh on startup
        self._update_logs()                                                                                                           # Initial log refresh on startup
        self._update_rqi_csv_sftp_status()                                                                                            # Initial CSV batch window / upload status refresh on startup
        self._update_mini_logs()                                                                                                      # Initial mini activity feed refresh on startup
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

    def _update_headless_toggle_label(self):
        if not hasattr(self, "headless_toggle"):
            return                                                                                                                    # Headless toggle has not been created yet

        if self.headless_toggle.isChecked():
            self.headless_toggle_label.setText("Headless Browser")
            self.headless_toggle_label.setStyleSheet("color: #00bc8c; font-weight: 700;")                                             # Green text when browser runs hidden
        else:
            self.headless_toggle_label.setText("Visible Browser")
            self.headless_toggle_label.setStyleSheet("color: #f39c12; font-weight: 700;")                                             # Orange text when browser window is visible

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

    def _append_colored_log_line(self, viewer, line):
        cursor = viewer.textCursor()
        cursor.movePosition(QTextCursor.End)                                                                                          # Move cursor to the bottom before adding the new line

        fmt = QTextCharFormat()
        lower_line = line.lower()                                                                                                     # Lowercase copy makes category matching easier

        if "error" in lower_line or "failed" in lower_line or "exception" in lower_line or "traceback" in lower_line or "⚠" in line:
            fmt.setForeground(QColor("#e64e30"))                                                                                    # Red for errors, failures, exceptions, and warnings

        elif "[rqi]" in lower_line or "rqi" in lower_line or "appended row to sheet" in lower_line or "appended row to csv" in lower_line:
            fmt.setForeground(QColor("#3498db"))                                                                                    # Blue for RQI activity

        elif "[sftp]" in lower_line or "sftp" in lower_line or "csv uploaded" in lower_line or "uploaded csv to sftp" in lower_line:
            fmt.setForeground(QColor("#00bc8c"))                                                                                    # Green for SFTP upload activity

        elif "[aha]" in lower_line or "aha" in lower_line or "automation task" in lower_line or "worker starting" in lower_line or "worker completed" in lower_line:
            fmt.setForeground(QColor("#f39c12"))                                                                                    # Orange/yellow for AHA automation activity

        elif "[app]" in lower_line or "opening settings" in lower_line or "application started" in lower_line or "exiting application" in lower_line:
            fmt.setForeground(QColor("#d8dee9"))                                                                                    # Light gray for app/general activity

        else:
            fmt.setForeground(QColor("#d8dee9"))                                                                                    # Default light gray for general messages

        cursor.insertText(line + "\n", fmt)                                                                                           # Add the line using the selected color
        viewer.setTextCursor(cursor)                                                                                                  # Apply cursor back to the viewer

    def _update_mini_logs(self):
        log_path = log_file()                                                                                                         # Read from main app log for the mini dashboard feed

        if not os.path.exists(log_path):
            self.mini_log_text.setPlainText("Waiting for activity...")                                                                # Friendly empty state before log file exists
            return

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-250:]                                                                                          # Read only recent log lines so mini viewer stays fast

            friendly_lines = []

            for line in lines:
                clean_line = self._format_mini_log_line(line)                                                                         # Convert raw technical log line into dashboard-friendly text
                if clean_line:
                    friendly_lines.append(clean_line)

            friendly_lines = friendly_lines[-7:]                                                                                      # Show only the last few meaningful events

            self.mini_log_text.clear()                                                                                                # Clear old mini feed before rewriting color-coded activity lines

            if friendly_lines:
                for friendly_line in friendly_lines:
                    self._append_colored_log_line(self.mini_log_text, friendly_line)                                                  # Add each dashboard event using category-based color
            else:
                self.mini_log_text.setPlainText("No recent important activity.")                                                      # Friendly message when only noisy logs exist

            self.mini_log_text.moveCursor(QTextCursor.End)                                                                            # Keep newest activity visible

        except Exception as e:
            self.mini_log_text.setPlainText(f"Could not read activity feed:\n{e}")                                                    # Show readable error instead of crashing GUI

    def _get_selected_log_path(self):
        if not hasattr(self, "log_tabs"):
            return log_file()                                                                                                         # Fallback to main app log before log tabs exist

        current_tab = self.log_tabs.tabText(self.log_tabs.currentIndex())                                                             # Get selected horizontal log tab name

        log_paths = {
            "All Logs": log_file(),
            "RQI": os.path.join(base_dir(), "logs", "rqi.log"),
            "AHA": os.path.join(base_dir(), "logs", "aha.log"),
            "SFTP": os.path.join(base_dir(), "logs", "sftp.log"),
            "Errors": os.path.join(base_dir(), "logs", "errors.log"),
        }                                                                                                                             # Runtime paths for each separated log file

        return log_paths.get(current_tab, log_file())                                                                                 # Default to main app log if selected tab is unknown

    def _reset_selected_log_view(self):
        if not hasattr(self, "log_tabs"):
            return                                                                                                                    # Log tabs not created yet

        current_tab = self.log_tabs.tabText(self.log_tabs.currentIndex())                                                             # Selected horizontal log tab
        self.log_positions[current_tab] = 0                                                                                           # Force selected tab to reload from the beginning

        if current_tab in self.log_viewers:
            self.log_viewers[current_tab].clear()                                                                                     # Clear old text before loading selected log file

        self._update_logs()                                                                                                           # Immediately populate newly selected log tab

    def _format_mini_log_line(self, line):
        if "DASHBOARD:" not in line and "ERROR" not in line:
            return None                                                                                                               # Mini viewer only shows intentional dashboard events and errors

        try:
            time_part = line.split(" - ", 1)[0].split(" ")[1][:8]                                                                     # Extract HH:MM:SS from timestamp
            message = line.split(" - ", 2)[2].strip()                                                                                 # Extract log message
        except Exception:
            return None                                                                                                               # Ignore malformed lines safely

        if "DASHBOARD:" in message:
            clean_message = message.split("DASHBOARD:", 1)[1].strip()                                                                 # Remove dashboard prefix for cleaner GUI display
            return f"{time_part}  •  {clean_message}"

        return f"{time_part}  •  ⚠ {message}"                                                                                        # Always show errors in mini viewer

    def _update_logs(self):
        if not hasattr(self, "log_tabs"):
            return                                                                                                                    # Log tabs not ready yet

        current_tab = self.log_tabs.tabText(self.log_tabs.currentIndex())                                                             # Selected log category
        viewer = self.log_viewers.get(current_tab)

        if viewer is None:
            return                                                                                                                    # No viewer exists for selected tab

        selected_log_path = self._get_selected_log_path()                                                                             # Get file path for selected log category

        if not os.path.exists(selected_log_path):
            viewer.setPlainText("No log file found yet.")                                                                             # Show friendly message if selected log has not been created
            self.log_positions[current_tab] = 0
            return

        try:
            with open(selected_log_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self.log_positions.get(current_tab, 0))                                                                        # Continue reading from last position for this tab
                new_text = f.read()                                                                                                   # Read only newly added log text
                self.log_positions[current_tab] = f.tell()                                                                            # Save new read position for this tab

            if new_text:
                viewer.moveCursor(QTextCursor.End)                                                                                    # Append new text at the end
                
                for line in new_text.splitlines():
                    self._append_colored_log_line(viewer, line)                                                                       # Add full log lines with category/error colors
                
                viewer.moveCursor(QTextCursor.End)                                                                                    # Auto-scroll selected log tab to newest entry

        except Exception as e:
            viewer.setPlainText(f"Could not read log file:\n{e}")                                                                     # Show readable error instead of crashing GUI

    # =======
    # STYLES
    # =======

    def _apply_styles(self):                                                                                                          # Main dark theme stylesheet for the entire GUI
        
        if getattr(self, "is_light_mode", False):
            self._apply_light_styles()                                                                                                # Apply light theme stylesheet
            return
        self._apply_dark_styles()                                                                                                     # Apply dark theme stylesheet

    def _apply_dark_styles(self):
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
            QFrame#ExportStatusCard {
                background-color: #252a33;
                border: 1px solid #343b48;
                border-radius: 12px;
            }

            QLabel#ExportStatusTitle {
                color: #aeb7c4;
                font-size: 12px;
                font-weight: 600;
                background-color: transparent;
            }

            QLabel#ExportStatusValue {
                color: #f3f6fb;
                font-size: 14px;
                font-weight: 700;
                background-color: transparent;
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
            QLabel#HeadlessToggleLabel {
                font-size: 13px;
                font-weight: 700;
            }
            QCheckBox#HeadlessToggle {
                spacing: 8px;
            }                           
            QFrame#SidebarFrame {
                background-color: #1f242d;
                border: 1px solid #333842;
                border-radius: 12px;
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
            QPushButton#SidebarButton {
                background-color: transparent;
                color: #d8dee9;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                padding-left: 14px;
                padding-right: 8px;
                text-align: left;
            }

            QPushButton#SidebarButton:hover {
                background-color: #252b33;
                color: white;
            }

            QPushButton#SidebarButton:checked {
                background-color: #00bc8c;
                color: white;
                font-weight: 600;
                border: none;
                border-radius: 8px;
            }
            QToolButton#CollapsedSidebarButton {
                background-color: transparent;
                color: #d8dee9;
                border: none;
                border-radius: 0px;
                font-size: 20px;
                font-weight: 600;
                padding: 0px;
            }

            QToolButton#CollapsedSidebarButton:hover {
                background-color: rgba(255, 255, 255, 18);
                border: none;
            }

            QToolButton#CollapsedSidebarButton:checked {
                background-color: #00bc8c;
                color: white;
                border: none;
                border-radius: 0px;
            }
            QToolTip {
                background-color: #111317;
                color: white;
                border: 1px solid #3b3d42;
                padding: 6px 10px;
            }
            
            QPushButton#ActionButton:disabled {
                background-color: #6b7280;
                color: #d1d5db;
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
                color: white;
                min-width: 170px;
                padding: 7px 14px;
                border-radius: 10px;
                font-weight: 700;
            }
            QPushButton#SaveButton:hover {
                background-color: #17d7a0;
                padding-top: 6px;
                padding-bottom: 8px;
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
                font-weight: 700;
            }
                           
            QPushButton#PauseButton:hover {
                background-color: #ffb52e;
                padding-top: 6px;
                padding-bottom: 8px;
            }
                           
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

            QPushButton#RestartButton {
                background-color: #e67e22;
                color: white;
                padding: 7px 14px;
                border-radius: 10px;
                font-weight: 700;
            }
            QPushButton#RestartButton:hover {
                background-color: #f39c12;
                padding-top: 6px;
                padding-bottom: 8px;
                }

            QPushButton#SignOutButton {
                background-color: #3498db;
                padding: 6px 12px;                                                                                                    /* Smaller AHA button so the top-right row takes less height */
                min-height: 0px;
                border-radius: 10px;
                font-size: 11px;                                                                                                      /* Match smaller button height */
                font-weight: 600;
            }
            QPushButton#SignOutButton:hover {
                background-color: #5dade2;
                padding-top: 6px;
                padding-bottom: 8px;
            }

            QPushButton#QuitButton {
                background-color: #e64e30;
                color: white;
                padding: 7px 14px;
                border-radius: 10px;
                font-weight: 700;
            }
            QPushButton#QuitButton:hover {
                background-color: #ff6b57;
                padding-top: 6px;
                padding-bottom: 8px;
            }
            
            QPushButton:hover {
                background-color: #3b82f6;
                padding-top: 6px;
                padding-bottom: 8px;
            }
    
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
            
            QTabWidget::pane {
                border: 1px solid #333842;
                border-radius: 10px;
                background-color: #1b1c1f;
                margin-top: 6px;
            }

            QTabBar::tab {
                background-color: #25272c;
                color: white;
                padding: 8px 16px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
            }

            QTabBar::tab:selected {
                background-color: #00bc8c;
                color: white;
                font-weight: 700;
            }

            QTabBar::tab:hover {
                background-color: #3498db;
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
                padding-top: 6px;
                padding-bottom: 8px;
            }               

            QFrame#MiniLogsPanel {
                background-color: #2b2d31;
                border: 1px solid #3b3d42;
                border-radius: 12px;
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
            
            QSpinBox {
                background-color: #1f2125;
                color: white;
                border: 1px solid #3b3d42;
                border-radius: 10px;
                padding: 8px;                                                                                                         /* Match QLineEdit internal spacing */
                min-height: 18px;
                selection-background-color: #3b82f6;
            }

            QSpinBox:hover {
                border: 1px solid #4b5563;                                                                                            /* Slight hover highlight like other inputs */
            }

            QSpinBox:focus {
                border: 1px solid #3b82f6;                                                                                            /* Blue focus border to match active text fields */
            }

            QSpinBox::up-button,
            QSpinBox::down-button {
                width: 0px;
                border: none;
                background: transparent;
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
                background-color: #11141c;
                color: white;
                border: 1px solid #333842;
                border-radius: 10px;
                padding: 6px;
                min-height: 84px;
                max-height: 100px;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)
    
    def _apply_light_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f7fb;
                color: #111827;
            }

            QWidget {
                background-color: #f5f7fb;
                color: #111827;
                font-family: Segoe UI;
                font-size: 12px;
            }

            QFrame#StatusCard,
            QStackedWidget#ContentStack,
            QFrame#ExportStatusCard {
                background-color: #ffffff;
                border: 1px solid #d5dce8;
                border-radius: 12px;
            }
            QFrame#MiniLogsPanel {
                background-color: #ffffff;
                border: 1px solid #d5dce8;
                border-radius: 12px;
                min-height: 166px;
                max-height: 166px;
            }

            QFrame#SidebarFrame {
                background-color: #ffffff;
                border: 1px solid #d5dce8;
                border-radius: 12px;
            }
                           
            QLabel {
                background-color: transparent;                                                                                        /* Prevent labels from showing unwanted gray background boxes in light mode */
            }

            QLabel#SectionTitle {
                color: #111827;
                font-size: 20px;
                font-weight: 800;
            }

            QLabel#SectionSubtitle {
                color: #4b5563;
                font-size: 12px;
            }

            QLabel#StatusCardTitle,
            QLabel#ExportStatusTitle,
            QLabel#MiniLogsTitle {
                color: #374151;
                font-size: 12px;
                font-weight: 600;
                background-color: transparent;
            }

            QLabel#StatusCardValue,
            QLabel#ExportStatusValue {
                color: #111827;
                font-size: 14px;
                font-weight: 700;
                background-color: transparent;
            }

            QLineEdit,
            QPlainTextEdit,
            QTextEdit,
            QComboBox,
            QSpinBox {
                background-color: #ffffff;
                color: #111827;
                border: 1px solid #d1d8e3;
                border-radius: 8px;
                padding: 7px;
                selection-background-color: #3498db;
            }
                           
            QLineEdit:hover,
            QPlainTextEdit:hover,
            QTextEdit:hover,
            QComboBox:hover,
            QSpinBox:hover {
                border: 1px solid #b8c2d1;
            }

            QLineEdit:focus,
            QPlainTextEdit:focus,
            QTextEdit:focus,
            QComboBox:focus,
            QSpinBox:focus {
                border: 1px solid #3498db;
                background-color: #fbfdff;
            }

            QPlainTextEdit#MiniLogText {
                background-color: #ffffff;
                color: #111827;
                border: 1px solid #c8d0dc;
                border-radius: 10px;
                padding: 6px;
                min-height: 84px;
                max-height: 100px;
            }

            QPushButton#ActionButton:disabled {
                background-color: #6b7280;
                color: #d1d5db;
            }
                           
            QPushButton {
                background-color: #3498db;
                color: white;
                border: 1 px solid transparent;
                border-radius: 10px;
                padding: 7px 14px;
                font-weight: 700;
            }

            QPushButton:hover {
                padding-top: 6px;
                padding-bottom: 8px;           
                background-color: #2d89c8;
            }
            
            QPushButton:pressed {
                background-color: #2477ad;
            }
                           
            QPushButton#SaveButton {
                background-color: #00bc8c;
                color: white;
                min-width: 170px;
            }
                           
            QPushButton#SaveButton:hover {
                background-color: #00a77d;
                padding-top: 6px;
                padding-bottom: 8px;
            }

            QPushButton#PauseButton {
                background-color: #f39c12;
                color: white;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
            }

            QPushButton#PauseButton:hover {
                background-color: #db8b0f;
                padding-top: 6px;
                padding-bottom: 8px;
            }

            QPushButton#PauseButton:pressed {
                background-color: #c77b0c;
            }
                           
            QToolButton#PauseMenuButton {
                background-color: #f39c12;
                color: white;
                border: none;
                border-left: 1px solid rgba(255,255,255,80);
                border-top-right-radius: 10px;
                border-bottom-right-radius: 10px;
            }

            QToolButton#PauseMenuButton:hover {
                background-color: #db8b0f;
                border-left: 1px solid rgba(255,255,255,120);                                                                          /* Match Pause button hover */
            }

            QToolButton#PauseMenuButton:pressed {
                background-color: #c77b0c;
            }
                           
            QPushButton#QuitButton {
                background-color: #e64e30;
                color: white;
            }

            QPushButton#QuitButton:hover {
                background-color: #cf4328;
                padding-top: 6px;
                padding-bottom: 8px;
            }
                           
            QPushButton#RestartButton {
                background-color: #f39c12;
                color: white;
            }

            QPushButton#RestartButton:hover {
                background-color: #db8b0f;
                padding-top: 6px;
                padding-bottom: 8px;
            }
                           
            QPushButton#SignOutButton {
                background-color: #3498db;
                color: white;
            }

            QPushButton#SignOutButton:hover {
                background-color: #2d89c8;
                padding-top: 6px;
                padding-bottom: 8px;
            }
                           
            QPushButton#ActionButton {
                background-color: #5865f2;
                color: white;
                min-width: 160px;
                min-height: 18px;
                padding: 7px 14px;
                border-radius: 10px;
                font-weight: 600;
                border: none;
            }

            QPushButton#ActionButton:hover {
                background-color: #4752c4;
            }

            QPushButton#ActionButton:pressed {
                background-color: #3c45aa;
            }
                           
            QPushButton#SidebarButton {
                background-color: transparent;
                color: #1f2937;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 400;
                padding-left: 14px;
                padding-right: 8px;
                text-align: left;
            }

            QPushButton#SidebarButton:hover {
                background-color: #eef3f8;
                color: #111827;
            }

            QPushButton#SidebarButton:checked {
                background-color: #00bc8c;
                color: white;
                font-weight: 600;
                border: none;
                border-radius: 8px;
            }
            QToolButton#CollapsedSidebarButton {
                background-color: transparent;
                color: #1f2937;
                border: none;
                border-radius: 0px;
                font-size: 20px;
                font-weight: 600;
                padding: 0px;
            }

            QToolButton#CollapsedSidebarButton:hover {
                background-color: #737270;
                border: none;
            }

            QToolButton#CollapsedSidebarButton:checked {
                background-color: #00bc8c;
                color: white;
                border: none;
                border-radius: 0px;
            }
            QFrame#SidebarIndicator {
                background-color: #00bc8c;
                border-radius: 2px;
            }

            QToolButton#SidebarCollapseButton {
                background-color: #ffffff;
                color: #111827;
                border: 1px solid #d5dce8;
                border-radius: 8px;
            }

            QTabWidget::pane {
                border: 1px solid #d5dce8;
                border-radius: 10px;
                background-color: #ffffff;
                margin-top: 6px;
            }

            QTabBar::tab {
                background-color: #eef2f7;
                color: #111827;
                padding: 8px 16px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
            }

            QTabBar::tab:selected {
                background-color: #00bc8c;
                color: white;
                font-weight: 700;
            }

            QTabBar::tab:hover {
                background-color: #dbeafe;
            }

            QLabel#AHARequiredLabel {
                color: #e64e30;
                font-weight: 800;
            }

            QLabel#ThemeToggleText,
            QLabel#HeadlessToggleLabel {
                color: #111827;
                font-weight: 700;
                background-color: transparent;
            }

            QScrollArea {
                border: none;
                background-color: transparent;
            }

            QScrollArea > QWidget > QWidget {
                background-color: #f5f7fb;
            }
            QScrollBar:vertical {
                background-color: transparent;
                width: 10px;
                margin: 2px;
            }

            QScrollBar::handle:vertical {
                background-color: #cbd5e1;
                border-radius: 5px;
                min-height: 28px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: #94a3b8;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
                border: none;
            }

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: none;
            }

            QScrollBar:horizontal {
                background-color: transparent;
                height: 10px;
                margin: 2px;
            }

            QScrollBar::handle:horizontal {
                background-color: #cbd5e1;
                border-radius: 5px;
                min-width: 28px;
            }

            QScrollBar::handle:horizontal:hover {
                background-color: #94a3b8;
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0px;
                background: none;
                border: none;
            }

            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: none;
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
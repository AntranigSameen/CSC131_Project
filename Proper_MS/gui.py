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
                               QScrollArea, QLineEdit, QMessageBox, QPlainTextEdit, QFormLayout, QSystemTrayIcon, QMenu,)

from utils import writable_env_file, base_dir, log_file, resource_path

# ============================
# LOAD ENVIRONMENT VARIABLES
# ============================

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
    "AHA_PASSWORD",
}


# ===============
# SAVE SETTINGS
# ===============

def save_settings(entries, restart=False):
    restart_needed = False

    for key, widget in entries.items():
        new_value = widget.text()
        old_value = os.getenv(key, "")

        if new_value != old_value and key in RESTART_REQUIRED:
            restart_needed = True

        set_key(CONFIG_FILE, key, new_value)

    load_dotenv(CONFIG_FILE, override=True)
    logging.info("Settings saved successfully")

    if restart:
        restart_application()
    else:
        if restart_needed:
            QMessageBox.warning(
                None,
                "Restart Required",
                "Some changes require restarting the automation to take effect.",
            )
        else:
            QMessageBox.information(None, "Saved", "Settings saved successfully!")


# =================
# RESTART PROGRAM
# =================

def restart_application():
    logging.info("Restarting application")
    exe_path = os.path.abspath(sys.executable)
    subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
    os._exit(0)


# =================
# SIGN OUT OF AHA
# =================

def sign_out():
    aha_auth_file = Path(base_dir()) / "aha_auth.json"
    if aha_auth_file.exists():
        aha_auth_file.unlink()
        logging.info("User signed out: deleted AHA login state")
        QMessageBox.information(
            None,
            "Signed Out",
            "AHA login state cleared. You will need to sign in next time.",
        )
    else:
        QMessageBox.information(
            None,
            "Info",
            "No existing AHA login state to delete.",
        )


# ==============
# STATUS CARD
# ==============

class StatusCard(QFrame):
    def __init__(self, title: str, value: str = ""):
        super().__init__()
        self.setObjectName("StatusCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("StatusCardTitle")

        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatusCardValue")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, text: str):
        self.value_label.setText(text)

    def set_color(self, color: str):
        self.value_label.setStyleSheet(f"color: {color}; font-weight: 700;")


# ===================
# SCROLLABLE PAGE
# ===================

class ScrollablePage(QWidget):
    def __init__(self, child_widget: QWidget):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(child_widget)

        layout.addWidget(scroll)

# =================
# SYSTEM TRAY ICON
# =================

class AppTrayIcon(QSystemTrayIcon):
    def __init__(self, window, on_pause_resume=None, on_quit=None, get_pause_state=None):
        icon_path = resource_path("icon.png")
        super().__init__(QIcon(icon_path), window)

        self.window = window
        self.on_pause_resume = on_pause_resume
        self.on_quit = on_quit
        self.get_pause_state = get_pause_state

        self.menu = QMenu()

        self.settings_action = QAction("Settings", self)
        self.settings_action.triggered.connect(self.show_settings)
        self.menu.addAction(self.settings_action)

        self.logs_action = QAction("Open App Logs", self)
        self.logs_action.triggered.connect(self.open_logs)
        self.menu.addAction(self.logs_action)

        self.pause_action = QAction(self.pause_menu_text(), self)
        self.pause_action.triggered.connect(self.pause_resume_clicked)
        self.menu.addAction(self.pause_action)

        self.menu.addSeparator()

        self.quit_action = QAction("Quit", self)
        self.quit_action.triggered.connect(self.quit_clicked)
        self.menu.addAction(self.quit_action)

        self.setContextMenu(self.menu)
        self.setToolTip("Complete Automation")
        self.activated.connect(self.on_activated)

    def pause_menu_text(self):
        if self.get_pause_state and self.get_pause_state():
            return "Resume Automation"
        return "Pause Automation"

    def refresh_pause_text(self):
        self.pause_action.setText(self.pause_menu_text())

    def show_settings(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def open_logs(self):
        log_path = log_file()
        if os.path.exists(log_path):
            subprocess.Popen(["notepad", log_path])
        else:
            logging.error("Log file not found: %s", log_path)

    def pause_resume_clicked(self):
        if self.on_pause_resume:
            self.on_pause_resume()
        self.refresh_pause_text()

    def quit_clicked(self):
        if self.on_quit:
            self.on_quit()
        else:
            os._exit(0)

    def on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_settings()

# ==================
# MAIN WINDOW
# ==================

class SettingsWindow(QMainWindow):
    def __init__(self, on_pause_resume=None, on_quit=None, get_pause_state=None, on_ready=None):
        super().__init__()

        self.setWindowIcon(QIcon(resource_path("icon.png")))
        self.on_pause_resume = on_pause_resume
        self.on_quit = on_quit
        self.get_pause_state = get_pause_state
        self.entries = {}

        self.setWindowTitle("Automation Machine")
        self.resize(1360, 820)
        self.setMinimumSize(1120, 700)

        self._log_position = 0
        self._log_initialized = False

        self._build_ui()
        self._start_timers()

        if on_ready:
            on_ready(self)
    
    # ==================
    # TRAY NOTIFICATION
    # ==================

    def notify_tray(self, title: str, message: str):
        global _qt_tray
        if _qt_tray is not None:
            _qt_tray.showMessage(title, message, QSystemTrayIcon.Information, 3000)

    # ==========
    # BUILD UI
    # ==========

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        header = QVBoxLayout()
        title = QLabel("Automation Control Center")
        title.setObjectName("MainTitle")
        header.addWidget(title)
        root.addLayout(header)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)

        self.automation_card = StatusCard("Automation", "Checking status...")
        self.browser_card = StatusCard("Browser", "")
        self.interval_card = StatusCard("Interval", "")
        self.queue_card = StatusCard("Queue", "")

        cards_row.addWidget(self.automation_card)
        cards_row.addWidget(self.browser_card)
        cards_row.addWidget(self.interval_card)
        cards_row.addWidget(self.queue_card)

        root.addLayout(cards_row)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.save_btn = QPushButton("Save Settings")
        self.pause_btn = QPushButton("Pause Automation")
        self.restart_btn = QPushButton("Restart App")
        self.signout_btn = QPushButton("Sign Out of AHA")
        self.quit_btn = QPushButton("Quit")

        self.save_btn.clicked.connect(lambda: save_settings(self.entries, restart=False))
        self.pause_btn.clicked.connect(self._pause_resume_clicked)
        self.restart_btn.clicked.connect(restart_application)
        self.signout_btn.clicked.connect(sign_out)
        self.quit_btn.clicked.connect(self._quit_clicked)

        toolbar.addWidget(self.save_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self.pause_btn)
        toolbar.addWidget(self.restart_btn)
        toolbar.addWidget(self.signout_btn)
        toolbar.addWidget(self.quit_btn)

        root.addLayout(toolbar)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self._build_overview_tab()
        self._build_aha_tab()
        self._build_email_tab()
        self._build_sheets_tab()
        self._build_auth_tab()
        self._build_general_tab()
        self._build_logs_tab()

        self._apply_styles()

    # ==============
    # TAB BUILDERS
    # ==============

    def _build_overview_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.quick_status = QLabel("Checking status...")
        self.quick_login = QLabel("Checking login state...")
        self.quick_mode = QLabel("")
        self.quick_queue = QLabel("")

        layout.addWidget(QLabel("Application Overview"))
        layout.addWidget(QLabel("Use this window to manage automation settings, monitor live status, review logs, and control the automation process."))
        layout.addSpacing(12)
        layout.addWidget(QLabel("Quick Status"))
        layout.addWidget(self.quick_status)
        layout.addWidget(self.quick_login)
        layout.addWidget(self.quick_mode)
        layout.addWidget(self.quick_queue)
        layout.addStretch(1)

        self.tabs.addTab(ScrollablePage(page), "Overview")

    def _build_aha_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        self.aha_login_label = QLabel("Checking login state...")
        form.addRow("AHA Login Status:", self.aha_login_label)

        aha_user = QLineEdit(os.getenv("AHA_USERNAME", ""))
        aha_pass = QLineEdit(os.getenv("AHA_PASSWORD", ""))
        aha_pass.setEchoMode(QLineEdit.Password)

        self.entries["AHA_USERNAME"] = aha_user
        self.entries["AHA_PASSWORD"] = aha_pass

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
        }

        for key, label in fields.items():
            edit = QLineEdit(os.getenv(key, ""))
            self.entries[key] = edit
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
        }

        for key, label in fields.items():
            edit = QLineEdit(os.getenv(key, ""))
            self.entries[key] = edit
            form.addRow(label, edit)

        self.tabs.addTab(ScrollablePage(page), "Sheets")

    def _build_auth_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        fields = {
            "CLIENT_ID": "Azure Client ID",
            "TENANT_ID": "Azure Tenant ID",
            "AUTHORITY": "Highest Credential Access",
            "SCOPES": "App Permissions",
            "CACHE_FILE": "Cache File",
        }

        for key, label in fields.items():
            edit = QLineEdit(os.getenv(key, ""))
            self.entries[key] = edit
            form.addRow(label, edit)

        self.tabs.addTab(ScrollablePage(page), "Authentication")

    def _build_general_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        fields = {
            "ORG_NAME": "Organization Name",
            "IS_HEADLESS": "Run Headless",
        }

        for key, label in fields.items():
            edit = QLineEdit(os.getenv(key, ""))
            self.entries[key] = edit
            form.addRow(label, edit)

        self.tabs.addTab(ScrollablePage(page), "General")

    def _build_logs_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Live Application Logs")
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QPlainTextEdit.NoWrap)

        layout.addWidget(title)
        layout.addWidget(self.log_text)

        self.tabs.addTab(page, "System Logs")

    # =================
    # UI INTERACTIONS
    # =================

    def _pause_resume_clicked(self):
        global _qt_tray

        if self.on_pause_resume:
            self.on_pause_resume()
        self._update_pause_button()

        if _qt_tray is not None:
            _qt_tray.refresh_pause_text()

    def _quit_clicked(self):
        result = QMessageBox.question(
            self,
            "Quit",
            "Are you sure you want to quit the application?",
        )
        if result == QMessageBox.Yes:
            if self.on_quit:
                self.on_quit()
            else:
                os._exit(0)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    # ===============
    # UI REFRESHERS
    # ===============

    def _start_timers(self):
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(2000)

        self.login_timer = QTimer(self)
        self.login_timer.timeout.connect(self._update_login_status)
        self.login_timer.start(2000)

        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self._update_logs)
        self.log_timer.start(3000)

        self._update_status()
        self._update_login_status()
        self._update_logs()

    def _update_pause_button(self):
        global _qt_tray

        if self.get_pause_state and self.get_pause_state():
            self.pause_btn.setText("Resume Automation")
        else:
            self.pause_btn.setText("Pause Automation")
        
        if _qt_tray is not None:
            _qt_tray.refresh_pause_text()

    def _update_status(self):
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

        current_headless = os.getenv("IS_HEADLESS", "")
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

        interval_text = os.getenv("INTERVAL", "")
        self.interval_card.set_value(f"{interval_text} sec")
        self.interval_card.set_color("#f39c12")

        queue_file = os.path.join(base_dir(), "queue_status.txt")
        if os.path.exists(queue_file):
            try:
                with open(queue_file, "r", encoding="utf-8") as f:
                    queue_count_int = int(f.read().strip())
            except Exception:
                queue_count_int = -1
        else:
            queue_count_int = 0

        if queue_count_int < 0:
            self.queue_card.set_value("? task(s)")
            self.queue_card.set_color("#e64e30")
            self.quick_queue.setText("? task(s)")
            self.quick_queue.setStyleSheet("color: #e64e30;")
        else:
            self.queue_card.set_value(f"{queue_count_int} task(s)")
            self.quick_queue.setText(f"{queue_count_int} task(s)")

            if queue_count_int == 0:
                queue_color = "#00bc8c"
            elif 1 <= queue_count_int <= 3:
                queue_color = "#f39c12"
            else:
                queue_color = "#e64e30"

            self.queue_card.set_color(queue_color)
            self.quick_queue.setStyleSheet(f"color: {queue_color};")

        self._update_pause_button()

    def _update_login_status(self):
        aha_auth_file = Path(base_dir()) / "aha_auth.json"
        if aha_auth_file.exists():
            text = "Signed In"
            color = "#00bc8c"
        else:
            text = "Not Signed In"
            color = "#adb5bd"

        self.aha_login_label.setText(text)
        self.aha_login_label.setStyleSheet(f"color: {color}; font-weight: 700;")
        self.quick_login.setText(text)
        self.quick_login.setStyleSheet(f"color: {color};")

    # ===================
    # LOG VIEWER HELPERS
    # ===================

    def _is_log_near_bottom(self):
        scrollbar = self.log_text.verticalScrollBar()
        return scrollbar.value() >= scrollbar.maximum() - 20

    def _append_log_line(self, line: str):
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()

        upper_line = line.upper()

        if " - ERROR - " in upper_line or "ERROR:" in upper_line:                                                                                   # Color for Error Logs
            fmt.setForeground(QColor("#e64e30"))

        elif " - WARNING - " in upper_line or "WARNING:" in upper_line:                                                                             # Color for Warning Logs
            fmt.setForeground(QColor("#f39c12"))

        elif " - INFO - " in upper_line or "INFO:" in upper_line:                                                                                   # Color for Info Logs
            fmt.setForeground(QColor("#5dade2"))

        else:                                                                                                                                       # Color for Logs (default)
            fmt.setForeground(QColor("#d7dce2"))

        cursor.insertText(line, fmt)

    def _append_log_text(self, text: str):
        if not text:
            return

        lines = text.splitlines(keepends=True)
        for line in lines:
            self._append_log_line(line)

    def _update_logs(self):
        current_log_file = log_file()

        if not os.path.exists(current_log_file):
            return

        try:
            current_size = os.path.getsize(current_log_file)

            # If log file was truncated or recreated, reset viewer state
            if current_size < self._log_position:
                self._log_position = 0
                self._log_initialized = False
                self.log_text.clear()

            was_near_bottom = self._is_log_near_bottom()

            with open(current_log_file, "r", encoding="utf-8") as f:
                # First load: read entire file once
                if not self._log_initialized:
                    content = f.read()
                    self.log_text.clear()
                    self._append_log_text(content)
                    self._log_position = f.tell()
                    self._log_initialized = True

                    scrollbar = self.log_text.verticalScrollBar()
                    scrollbar.setValue(scrollbar.maximum())

                else:
                    # Subsequent loads: append only new content
                    f.seek(self._log_position)
                    new_text = f.read()

                    if new_text:
                        self._append_log_text(new_text)

                        if was_near_bottom:
                            scrollbar = self.log_text.verticalScrollBar()
                            scrollbar.setValue(scrollbar.maximum())

                    self._log_position = f.tell()

        except Exception as e:
            logging.exception("Error updating log viewer: %s", e)

    # =======
    # STYLES
    # =======

    def _apply_styles(self):
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
                background-color: #2f6fed;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #3b82f6;
            }
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

_qt_app = None
_qt_window = None
_qt_tray = None

def open_settings(on_pause_resume=None, on_quit=None, get_pause_state=None, on_ready=None):
    global _qt_app, _qt_window, _qt_tray

    # Enable high DPI scaling
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication.instance()
    if app is None:
        _qt_app = QApplication(sys.argv)
        app = _qt_app

        app.setApplicationName("Automation Machine")                                                                                                # App Name
        app.setOrganizationName("Sentient Grok")                                                                                                    # App Creator Name
        app.setApplicationDisplayName("Automation Machine")                                                                                         # App Display Name

        # Set global application icon
        icon_path = resource_path("icon.png")
        app.setWindowIcon(QIcon(icon_path))

    if _qt_window is None:
        _qt_window = SettingsWindow(on_pause_resume=on_pause_resume, on_quit=on_quit, get_pause_state=get_pause_state, on_ready=on_ready,)

    if _qt_tray is None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            _qt_tray = AppTrayIcon(_qt_window, on_pause_resume=on_pause_resume, on_quit=on_quit, get_pause_state=get_pause_state,)
            _qt_tray.show()

        else:
            logging.warning("System tray is not available on this system.")

    _qt_window.show()
    _qt_window.raise_()
    _qt_window.activateWindow()

    if on_ready:
        on_ready(_qt_window)

    if _qt_app is not None:
        _qt_app.exec()


# =============
# FOR TESTING
# =============

if __name__ == "__main__":
    open_settings()
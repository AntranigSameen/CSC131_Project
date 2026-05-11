# ==========
# IMPORTS
# ==========

import logging
from pathlib import Path

from utils import app_data_dir


# =====================
# SPLIT LOGGING SETUP
# =====================

_SPLIT_LOGGING_INSTALLED = False                                                                                                      # Prevent duplicate handlers when setup is called more than once

def _logs_dir():
    path = Path(app_data_dir()) / "logs"                                                                                              # Store separated logs in a dedicated logs folder beside app runtime files
    path.mkdir(parents=True, exist_ok=True)                                                                                           # Create logs folder if it does not exist yet
    for file_name in ["rqi.log", "aha.log", "sftp.log", "errors.log"]:
        (path / file_name).touch(exist_ok=True)                                                                                       # Ensure each separated log file exists
    return path


def _write_line(file_name, line):
    log_path = _logs_dir() / file_name                                                                                                # Full path for selected separated log file
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")                                                                                                          # Append formatted log line to selected separated log file


class SplitLogHandler(logging.Handler):
    def emit(self, record):
        try:
            message = record.getMessage()
            formatted = self.format(record)                                                                                           # Preserve timestamp + level formatting

            lower_message = message.lower()

            # =========================
            # CLASSIFY MESSAGE TYPES
            # =========================

            is_sftp = (
                "sftp" in lower_message
                or "uploaded csv to sftp" in lower_message
                or "opened sftp connection" in lower_message
                or "sftp session closed" in lower_message
            )                                                                                                                         # Detect SFTP upload + connection logs FIRST

            is_rqi = (
                "rqi" in lower_message
                or "email to sheets" in lower_message
                or "appended row to csv batch" in lower_message
                or "appended row to current csv batch" in lower_message
                or "appended row to sheet" in lower_message
                or "worksheet: leads" in lower_message
            )                                                                                                                         # Detect RQI parsing, sheet updates, CSV batching

            is_aha = (
                "aha" in lower_message
                or "automation task" in lower_message
                or "automation script" in lower_message
                or "worker starting automation task" in lower_message
                or "worker completed automation task" in lower_message
                or "queuing automation task" in lower_message
            )                                                                                                                         # Detect AHA login + automation loop activity

            # =========================
            # ROUTING RULES
            # =========================

            if record.levelno >= logging.ERROR:
                _write_line("errors.log", formatted)                                                                                  # Always capture errors globally

            if is_sftp:
                _write_line("sftp.log", formatted)                                                                                    # SFTP logs go ONLY here

            elif is_rqi:
                _write_line("rqi.log", formatted)                                                                                     # RQI logs go ONLY here (unless they were SFTP)

            if is_aha:
                _write_line("aha.log", formatted)                                                                                     # AHA logs can coexist with others

        except Exception:
            pass                                                                                                                      # Never let logging crash the app


def setup_split_logging():
    global _SPLIT_LOGGING_INSTALLED

    if _SPLIT_LOGGING_INSTALLED:
        return                                                                                                                        # Avoid installing duplicate split handlers

    handler = SplitLogHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))                                               # Match current app.log format

    logging.getLogger().addHandler(handler)                                                                                           # Attach split handler to root logger so existing logging.info calls still work
    _SPLIT_LOGGING_INSTALLED = True
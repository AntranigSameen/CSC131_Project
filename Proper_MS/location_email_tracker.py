import os
from datetime import datetime
from typing import List, Tuple

from utils import base_dir


def get_tracker_file_path() -> str:
    configured = (os.getenv("LOCATION_EMAIL_TRACKER_FILE") or "").strip()
    if configured:
        return configured
    return os.path.join(base_dir(), "location_email_tracker.txt")


def load_tracker_entries() -> List[Tuple[str, str]]:
    """Return tracker rows as (timestamp, hash) tuples."""
    path = get_tracker_file_path()
    if not os.path.exists(path):
        return []

    entries: List[Tuple[str, str]] = []
    with open(path, "r", encoding="utf-8") as file_obj:
        for raw_line in file_obj:
            line = (raw_line or "").strip()
            if not line or line.startswith("#"):
                continue

            if "|" in line:
                timestamp, hash_value = line.split("|", 1)
                timestamp = timestamp.strip()
                hash_value = hash_value.strip()
                if hash_value:
                    entries.append((timestamp, hash_value))
            else:
                # Backward-compatible support for old hash-only lines.
                entries.append(("", line))

    return entries


def load_tracker_hashes() -> set[str]:
    return {hash_value for _, hash_value in load_tracker_entries() if hash_value}


def append_tracker_hash(hash_value: str) -> None:
    clean_hash = (hash_value or "").strip()
    if not clean_hash:
        return

    path = get_tracker_file_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", encoding="utf-8") as file_obj:
        file_obj.write(f"{timestamp}|{clean_hash}\n")


def clear_tracker_file() -> None:
    path = get_tracker_file_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file_obj:
        file_obj.write("# timestamp|sha256_hash\n")

import os
from typing import Dict

from utils import app_data_dir, resource_path


LOCATION_KEYS_FILE = os.path.join(app_data_dir(), "location_keys.txt")


def ensure_location_keys_file() -> str:
    if os.path.exists(LOCATION_KEYS_FILE):
        return LOCATION_KEYS_FILE

    directory = os.path.dirname(LOCATION_KEYS_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)

    bundled = resource_path("location_keys.txt")
    if os.path.exists(bundled):
        with open(bundled, "r", encoding="utf-8") as source_obj, open(LOCATION_KEYS_FILE, "w", encoding="utf-8") as target_obj:
            target_obj.write(source_obj.read())
        return LOCATION_KEYS_FILE

    with open(LOCATION_KEYS_FILE, "w", encoding="utf-8") as file_obj:
        file_obj.write("# key|location\n")

    return LOCATION_KEYS_FILE


def get_location_keys_file_path() -> str:
    return ensure_location_keys_file()


def load_location_keys() -> Dict[str, str]:
    """Load key|location pairs from text file."""
    path = ensure_location_keys_file()

    pairs: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as file_obj:
        for raw_line in file_obj:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                continue

            key, location = line.split("|", 1)
            key = key.strip()
            location = location.strip()
            if not key or not location:
                continue
            pairs[key] = location

    return pairs


def save_location_keys(pairs: Dict[str, str]) -> None:
    """Persist key|location pairs in deterministic sorted order."""
    path = ensure_location_keys_file()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file_obj:
        file_obj.write("# key|location\n")
        for key in sorted(pairs.keys(), key=lambda value: value.lower()):
            file_obj.write(f"{key}|{pairs[key]}\n")


def upsert_location_key(key: str, location: str) -> None:
    clean_key = (key or "").strip()
    clean_location = (location or "").strip()
    if not clean_key or not clean_location:
        raise ValueError("Both key and location are required.")

    pairs = load_location_keys()
    pairs[clean_key] = clean_location
    save_location_keys(pairs)


def remove_location_key(key: str) -> bool:
    clean_key = (key or "").strip()
    if not clean_key:
        return False

    pairs = load_location_keys()
    if clean_key not in pairs:
        return False

    del pairs[clean_key]
    save_location_keys(pairs)
    return True

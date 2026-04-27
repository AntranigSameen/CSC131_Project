import json
import os
from typing import Dict, Any

from utils import base_dir, resource_path


DEFAULT_TEMPLATE_CONFIG: Dict[str, Any] = {
    "default": {
        "subject": "AHA Update - {location}",
        "body": (
            "Hello {first_name},\n\n"
            "This is your AHA update for {location}.\n"
            "Please review the required steps for your location and complete any pending items.\n\n"
            "If you have questions, reply to this email."
        ),
    },
    "by_key": {},
    "by_location": {},
}


def _default_location_subject(location_name: str) -> str:
    clean_location = (location_name or "").strip() or "Location"
    return f"{clean_location} AHA Instructions"


def _default_location_body(location_name: str) -> str:
    clean_location = (location_name or "").strip() or "your location"
    return (
        "Hello,\n\n"
        f"Thank you for registering with CPR Lifeline at our [ADDRESS], {clean_location} location for your upcoming AHA course.\n\n"
        "Below are a few details you will need to access the suite:\n\n"
        "- [ACCESS DETAIL 1]\n"
        "- [ACCESS DETAIL 2]\n"
        "- [ACCESS DETAIL 3]\n"
        "- After your session is complete, please be sure to wipe both manikins with the provided Lysol wipes to leave ready for our next student.\n\n"
        "Information to set up your RQI account\n\n"
        "If you have not already, you will be receiving an important email from RQI1stop.com very soon. "
        "You will have to set up an account at https://cprlifeline.rqi1stop.com prior to beginning your AHA HeartCode "
        "online course and/or hands on skills check.\n\n"
        "For any issues signing into RQI or if you have technical issues while taking the skills check, RQI's technical help line is: 1-800-594-9935.\n\n"
        "Please do not bring any food or drink into the office. Trash cans are only emptied 1 time a week. "
        "After you have completed the skills check please wipe down the manikins and replace the clothing.\n\n"
        "If you have any questions, please feel free to contact us. We greatly appreciate your business and are here to make it a smooth and easy process.\n\n"
        "Thank you,\n"
        "Chris Peters\n"
        "CPR Lifeline\n"
        "877-422-7755\n"
        "https://cprlifeline.net/\n"
        "info@cprlifeline.net\n"
        "after hours - 209-499-2249"
    )


def get_location_templates_file_path() -> str:
    configured = (os.getenv("LOCATION_EMAIL_TEMPLATES_FILE") or "").strip()
    if configured:
        return configured
    return os.path.join(base_dir(), "location_email_templates.json")


def ensure_location_templates_file() -> str:
    path = get_location_templates_file_path()
    if os.path.exists(path):
        return path

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    bundled = resource_path("location_email_templates.json")
    if os.path.exists(bundled):
        with open(bundled, "r", encoding="utf-8") as source_obj, open(path, "w", encoding="utf-8") as target_obj:
            target_obj.write(source_obj.read())
        return path

    with open(path, "w", encoding="utf-8") as file_obj:
        json.dump(DEFAULT_TEMPLATE_CONFIG, file_obj, indent=2)
    return path


def load_location_templates() -> Dict[str, Any]:
    path = ensure_location_templates_file()

    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            parsed = json.load(file_obj)
            if not isinstance(parsed, dict):
                return dict(DEFAULT_TEMPLATE_CONFIG)
    except Exception:
        return dict(DEFAULT_TEMPLATE_CONFIG)

    merged: Dict[str, Any] = {
        "default": dict(DEFAULT_TEMPLATE_CONFIG["default"]),
        "by_key": {},
        "by_location": {},
    }

    default_block = parsed.get("default") if isinstance(parsed.get("default"), dict) else {}
    subject = (default_block.get("subject") or "").strip()
    body = (default_block.get("body") or "").strip()
    if subject:
        merged["default"]["subject"] = subject
    if body:
        merged["default"]["body"] = body

    by_key = parsed.get("by_key") if isinstance(parsed.get("by_key"), dict) else {}
    for key, config in by_key.items():
        if not isinstance(config, dict):
            continue
        template_subject = (config.get("subject") or "").strip()
        template_body = (config.get("body") or "").strip()
        if template_subject or template_body:
            merged["by_key"][str(key)] = {
                "subject": template_subject,
                "body": template_body,
            }

    by_location = parsed.get("by_location") if isinstance(parsed.get("by_location"), dict) else {}
    for location_name, config in by_location.items():
        if not isinstance(config, dict):
            continue
        template_subject = (config.get("subject") or "").strip()
        template_body = (config.get("body") or "").strip()
        if template_subject or template_body:
            merged["by_location"][str(location_name)] = {
                "subject": template_subject,
                "body": template_body,
            }

    return merged


def save_location_templates(config: Dict[str, Any]) -> str:
    path = ensure_location_templates_file()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    payload = {
        "default": dict((config or {}).get("default") or DEFAULT_TEMPLATE_CONFIG["default"]),
        "by_key": dict((config or {}).get("by_key") or {}),
        "by_location": dict((config or {}).get("by_location") or {}),
    }

    with open(path, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, indent=2)
        file_obj.write("\n")

    return path


def ensure_location_template_entry(location_key: str, location_name: str) -> bool:
    clean_key = (location_key or "").strip()
    clean_location = (location_name or "").strip()
    if not clean_key or not clean_location:
        raise ValueError("Both location key and location name are required.")

    config = load_location_templates()
    by_key = dict(config.get("by_key") or {})
    if clean_key in by_key:
        return False

    by_key[clean_key] = {
        "subject": _default_location_subject(clean_location),
        "body": _default_location_body(clean_location),
    }
    config["by_key"] = by_key
    save_location_templates(config)
    return True


def remove_location_template_entry(location_key: str) -> bool:
    clean_key = (location_key or "").strip()
    if not clean_key:
        return False

    config = load_location_templates()
    by_key = dict(config.get("by_key") or {})
    if clean_key not in by_key:
        return False

    del by_key[clean_key]
    config["by_key"] = by_key
    save_location_templates(config)
    return True

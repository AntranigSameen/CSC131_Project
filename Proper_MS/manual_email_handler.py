"""
Manual Email Handler Module

Handles the business logic for sending manual emails and preventing
auto-emailer duplicates. Separated from GUI for maintainability.
"""

import os
import csv
from datetime import datetime
from typing import Optional, Tuple, Dict

from reminder_emailer import (
    _tracking_id,
    send_reminder_email,
    _load_location_email_templates,
    _compose_location_email,
    _resolve_location_from_key_store,
    _location_key_for_row,
    _get_gsheet_worksheet,
    _safe_update_cell,
    _normalize_header,
    _cell,
)
from location_email_tracker import append_tracker_hash, load_tracker_hashes
from location_keys import load_location_keys
from outlook_authentication import authenticate


class ManualEmailResult:
    """Result of a manual email send operation."""
    def __init__(self, success: bool, message: str, email: str = ""):
        self.success = success
        self.message = message
        self.email = email


def validate_email_input(email: str, location: str) -> Optional[str]:
    """Validate email and location inputs. Returns error message or None if valid."""
    email = email.strip()
    location = location.strip()
    
    if not email or "@" not in email:
        return "Please enter a valid email address."
    
    if not location:
        return "Please select or enter a location."
    
    return None


def compose_email_content(
    email: str,
    location: str,
    first_name: str = "",
    last_name: str = "",
    custom_subject: str = "",
    custom_body: str = "",
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Compose email subject and body.
    
    Returns:
        Tuple of (subject, body, error_message)
        If error_message is not None, subject and body will be None
    """
    # Use custom content if provided
    if custom_subject and custom_body:
        return custom_subject, custom_body, None
    
    # Otherwise use templates
    location_pairs = load_location_keys()
    if not location_pairs:
        return None, None, "No location keys configured. Configure them in the Location Keys tab."
    
    resolved_location = _resolve_location_from_key_store(location, location_pairs)
    if not resolved_location:
        available = ', '.join(location_pairs.values())
        return None, None, f"Location '{location}' not found in location_keys.txt\n\nAvailable locations: {available}"
    
    location_key = _location_key_for_row(location, resolved_location, location_pairs)
    templates = _load_location_email_templates()
    
    subject, body = _compose_location_email(
        first_name or "there",
        last_name or "",
        email,
        resolved_location,
        location_key,
        templates,
    )
    
    return subject, body, None


def check_if_already_sent(email: str, location: str, cycle_marker: str = "") -> Tuple[bool, str]:
    """
    Check if email was already sent for this location/cycle.
    
    Returns:
        Tuple of (already_sent: bool, dedupe_id: str)
    """
    location_pairs = load_location_keys()
    resolved_location = _resolve_location_from_key_store(location, location_pairs)
    
    if not resolved_location:
        return False, ""
    
    dedupe_id = _tracking_id(email, resolved_location, cycle_marker)
    tracked_ids = load_tracker_hashes()
    
    return dedupe_id in tracked_ids, dedupe_id


def send_single_manual_email(
    email: str,
    location: str,
    first_name: str = "",
    last_name: str = "",
    cycle_marker: str = "",
    custom_subject: str = "",
    custom_body: str = "",
    force_send: bool = False,
) -> ManualEmailResult:
    """
    Send a single manual email.
    
    Args:
        email: Recipient email address
        location: Location name
        first_name: Optional first name for personalization
        last_name: Optional last name for personalization
        cycle_marker: Optional cycle marker for tracking
        custom_subject: Optional custom subject (uses template if empty)
        custom_body: Optional custom body (uses template if empty)
        force_send: If True, send even if already sent before
    
    Returns:
        ManualEmailResult with success status and message
    """
    email = email.strip()
    location = location.strip()
    
    # Validate inputs
    validation_error = validate_email_input(email, location)
    if validation_error:
        return ManualEmailResult(False, validation_error, email)
    
    # Check if already sent
    if not force_send:
        already_sent, dedupe_id = check_if_already_sent(email, location, cycle_marker)
        if already_sent:
            return ManualEmailResult(
                False,
                f"Email to {email} for location '{location}' was already sent. Use force_send=True to send anyway.",
                email
            )
    else:
        location_pairs = load_location_keys()
        resolved_location = _resolve_location_from_key_store(location, location_pairs)
        dedupe_id = _tracking_id(email, resolved_location, cycle_marker)
    
    # Compose email
    subject, body, error = compose_email_content(
        email, location, first_name, last_name, custom_subject, custom_body
    )
    
    if error:
        return ManualEmailResult(False, error, email)
    
    # Get auth token
    try:
        token = authenticate()
    except Exception as e:
        return ManualEmailResult(False, f"Authentication failed: {e}", email)
    
    if not token:
        return ManualEmailResult(False, "Authentication failed: No token received", email)
    
    # Send email
    if send_reminder_email(token, email, subject, body):
        # Track the send
        append_tracker_hash(dedupe_id)
        return ManualEmailResult(True, f"Email sent successfully to {email}", email)
    else:
        return ManualEmailResult(False, f"Failed to send email to {email}", email)


def update_reminder_email_column(email: str) -> Tuple[bool, str]:
    """
    Update the 'Reminder Email' column in the AHA sheet for the given email.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        worksheet_name = (os.getenv("AHA_REGISTRATION_WORKSHEET") or "").strip() or None
        ws = _get_gsheet_worksheet(worksheet_name)
        all_values = ws.get_all_values()
        
        if not all_values:
            return False, "Sheet is empty"

        headers = all_values[0]
        header_index = {_normalize_header(h): idx + 1 for idx, h in enumerate(headers)}
        
        email_col = header_index.get("email") or header_index.get("emailaddress") or header_index.get("userid") or 1
        reminder_col = header_index.get("reminderemail") or 9

        today_str = datetime.now().strftime("%m/%d/%Y")
        email_lower = email.lower()

        # Find the row with this email
        for row_idx, row in enumerate(all_values, start=1):
            if row_idx == 1:  # Skip header
                continue
                
            row_email = _cell(row, email_col).lower()
            if row_email == email_lower:
                _safe_update_cell(ws, row_idx, reminder_col, today_str)
                return True, f"Updated 'Reminder Email' column for {email}"

        return False, f"Email {email} not found in sheet"
        
    except Exception as e:
        return False, f"Failed to update sheet: {e}"


def send_batch_from_csv(csv_path: str, update_sheet: bool = True) -> Dict[str, int]:
    """
    Send batch emails from a CSV file.
    
    CSV format: Email,Location,FirstName,LastName,CycleMarker
    
    Args:
        csv_path: Path to CSV file
        update_sheet: If True, update Reminder Email column after sending
    
    Returns:
        Dictionary with stats: {"success": int, "failed": int, "skipped": int}
    """
    stats = {"success": 0, "failed": 0, "skipped": 0}
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            if 'Email' not in reader.fieldnames or 'Location' not in reader.fieldnames:
                raise ValueError("CSV file must contain 'Email' and 'Location' columns")
            
            for row in reader:
                email = row.get('Email', '').strip()
                location = row.get('Location', '').strip()
                first_name = row.get('FirstName', '').strip()
                last_name = row.get('LastName', '').strip()
                cycle_marker = row.get('CycleMarker', '').strip()
                
                if not email or not location:
                    stats["skipped"] += 1
                    continue
                
                # Check if already sent
                already_sent, _ = check_if_already_sent(email, location, cycle_marker)
                if already_sent:
                    stats["skipped"] += 1
                    continue
                
                # Send email
                result = send_single_manual_email(
                    email, location, first_name, last_name, cycle_marker
                )
                
                if result.success:
                    stats["success"] += 1
                    
                    # Update sheet if requested
                    if update_sheet:
                        update_reminder_email_column(email)
                else:
                    stats["failed"] += 1
        
        return stats
        
    except Exception as e:
        raise Exception(f"Batch send failed: {e}")


def get_available_locations() -> list[str]:
    """Get list of available locations from location_keys."""
    location_pairs = load_location_keys()
    locations = set()
    
    for value in location_pairs.values():
        locations.add(value)
    
    return sorted(locations)

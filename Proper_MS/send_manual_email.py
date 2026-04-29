#!/usr/bin/env python3
"""
Manual Email Sender with Duplicate Prevention

This script allows you to manually send location-based emails to users
while automatically recording them in the tracking system to prevent the 
auto-emailer from sending duplicate emails.

Usage examples:
    # Send a manual email to a single person
    python send_manual_email.py --email john.doe@example.com --location "Main Campus"
    
    # Send with specific subject and body
    python send_manual_email.py --email jane@example.com --location "Downtown" \
        --subject "Custom Subject" --body "Custom message here"
    
    # Send using a template and include cycle marker
    python send_manual_email.py --email user@example.com --location "Main Campus" \
        --cycle-marker "01/15/2026"
    
    # Preview the email without sending (dry run)
    python send_manual_email.py --email user@example.com --location "Main Campus" --dry-run
    
    # Send to multiple people from a CSV file (Email,Location,CycleMarker columns)
    python send_manual_email.py --batch emails.csv
"""

import argparse
import csv
import logging
import sys
from datetime import datetime
from typing import Optional

from reminder_emailer import (
    _tracking_id,
    send_reminder_email,
    _load_location_email_templates,
    _compose_location_email,
    _resolve_location_from_key_store,
    _location_key_for_row,
)
from location_email_tracker import append_tracker_hash, load_tracker_hashes
from location_keys import load_location_keys
from outlook_authentication import authenticate

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def send_manual_location_email(
    email: str,
    location: str,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    first_name: str = "",
    last_name: str = "",
    cycle_marker: str = "",
    dry_run: bool = False,
) -> bool:
    """Send a manual email and mark it in the tracker to prevent auto-emailer duplicates.
    
    Args:
        email: Recipient's email address
        location: Location name (must match location_keys.txt)
        subject: Optional custom subject (uses template if not provided)
        body: Optional custom body (uses template if not provided)
        first_name: Recipient's first name (for template personalization)
        last_name: Recipient's last name (for template personalization)
        cycle_marker: Optional date/cycle marker for tracking uniqueness
        dry_run: If True, preview the email without sending
    
    Returns:
        True if email sent successfully (or dry run succeeded), False otherwise
    """
    email_clean = (email or "").strip()
    location_clean = (location or "").strip()
    
    if not email_clean or "@" not in email_clean:
        logging.error(f"Invalid email address: {email}")
        return False
    
    if not location_clean:
        logging.error("Location is required")
        return False
    
    # Validate location against location_keys
    location_pairs = load_location_keys()
    if not location_pairs:
        logging.error("No location keys configured. Configure them in the GUI Location Keys tab.")
        return False
    
    resolved_location = _resolve_location_from_key_store(location_clean, location_pairs)
    if not resolved_location:
        logging.error(f"Location '{location_clean}' not found in location_keys.txt")
        logging.info(f"Available locations: {', '.join(location_pairs.values())}")
        return False
    
    # Check if already sent (to avoid double-sending)
    dedupe_id = _tracking_id(email_clean, resolved_location, cycle_marker)
    tracked_ids = load_tracker_hashes()
    
    if dedupe_id in tracked_ids:
        logging.warning(
            f"Email to {email_clean} for location '{resolved_location}' "
            f"(cycle: {cycle_marker or 'none'}) was already sent previously."
        )
        response = input("Send anyway? (yes/no): ").strip().lower()
        if response not in {"yes", "y"}:
            logging.info("Cancelled.")
            return False
    
    # Get location key for template selection
    location_key = _location_key_for_row(location_clean, resolved_location, location_pairs)
    
    # Compose email using templates or custom content
    if subject and body:
        final_subject = subject
        final_body = body
        logging.info("Using custom subject and body")
    else:
        templates = _load_location_email_templates()
        final_subject, final_body = _compose_location_email(
            first_name or "there",
            last_name or "",
            email_clean,
            resolved_location,
            location_key,
            templates,
        )
        logging.info(f"Using template for location key: {location_key or 'default'}")
    
    # Display preview
    logging.info("=" * 60)
    logging.info(f"TO: {email_clean}")
    logging.info(f"LOCATION: {resolved_location}")
    logging.info(f"CYCLE MARKER: {cycle_marker or '(none)'}")
    logging.info(f"SUBJECT: {final_subject}")
    logging.info("-" * 60)
    logging.info(f"BODY:\n{final_body}")
    logging.info("=" * 60)
    
    if dry_run:
        logging.info("[DRY RUN] Email not sent. Remove --dry-run to actually send.")
        return True
    
    # Get authentication token
    try:
        token = authenticate()
    except Exception as e:
        logging.error(f"Failed to get authentication token: {e}")
        return False
    
    # Send the email
    logging.info(f"Sending email to {email_clean}...")
    if send_reminder_email(token, email_clean, final_subject, final_body):
        # Mark as sent in tracker to prevent auto-emailer duplicates
        append_tracker_hash(dedupe_id)
        logging.info(f"✓ Email sent to {email_clean} and tracked to prevent duplicates")
        return True
    else:
        logging.error(f"✗ Failed to send email to {email_clean}")
        return False


def send_batch_emails(csv_file: str, dry_run: bool = False) -> dict:
    """Send manual emails to multiple recipients from a CSV file.
    
    CSV format:
        Email,Location,FirstName,LastName,CycleMarker
    
    FirstName, LastName, and CycleMarker are optional.
    
    Args:
        csv_file: Path to CSV file
        dry_run: If True, preview emails without sending
    
    Returns:
        Dictionary with stats: {"sent": int, "failed": int, "skipped": int}
    """
    logging.info(f"Processing batch file: {csv_file}")
    
    stats = {"sent": 0, "failed": 0, "skipped": 0}
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Validate required columns
            if 'Email' not in reader.fieldnames or 'Location' not in reader.fieldnames:
                logging.error("CSV file must contain 'Email' and 'Location' columns")
                return stats
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
                email = row.get('Email', '').strip()
                location = row.get('Location', '').strip()
                first_name = row.get('FirstName', '').strip()
                last_name = row.get('LastName', '').strip()
                cycle_marker = row.get('CycleMarker', '').strip()
                
                if not email or not location:
                    logging.warning(f"Row {row_num}: Skipping incomplete entry (missing email or location)")
                    stats["skipped"] += 1
                    continue
                
                logging.info(f"\n--- Processing row {row_num}: {email} ---")
                
                success = send_manual_location_email(
                    email=email,
                    location=location,
                    first_name=first_name,
                    last_name=last_name,
                    cycle_marker=cycle_marker,
                    dry_run=dry_run,
                )
                
                if success:
                    stats["sent"] += 1
                else:
                    stats["failed"] += 1
            
            logging.info(f"\n{'=' * 60}")
            logging.info(f"Batch complete: {stats['sent']} sent, {stats['failed']} failed, {stats['skipped']} skipped")
            logging.info(f"{'=' * 60}")
            return stats
            
    except FileNotFoundError:
        logging.error(f"File not found: {csv_file}")
        return stats
    except Exception as e:
        logging.error(f"Error processing batch file: {e}")
        return stats


def main():
    parser = argparse.ArgumentParser(
        description="Send manual emails with duplicate prevention tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    # Single email mode
    parser.add_argument("--email", help="Recipient's email address")
    parser.add_argument("--location", help="Location name (must match location_keys.txt)")
    parser.add_argument("--first-name", help="Recipient's first name (for template personalization)")
    parser.add_argument("--last-name", help="Recipient's last name (for template personalization)")
    parser.add_argument("--cycle-marker", help="Date/cycle marker for tracking (e.g., '01/15/2026')")
    parser.add_argument("--subject", help="Custom email subject (uses template if not provided)")
    parser.add_argument("--body", help="Custom email body (uses template if not provided)")
    
    # Batch mode
    parser.add_argument("--batch", help="CSV file with Email,Location,FirstName,LastName,CycleMarker columns")
    
    # Options
    parser.add_argument("--dry-run", action="store_true", help="Preview emails without sending")
    parser.add_argument("--list-locations", action="store_true", help="List available locations and exit")
    
    args = parser.parse_args()
    
    # List locations and exit
    if args.list_locations:
        location_pairs = load_location_keys()
        if not location_pairs:
            logging.error("No location keys configured.")
            sys.exit(1)
        
        logging.info("Available locations:")
        for key, value in location_pairs.items():
            logging.info(f"  {key} -> {value}")
        sys.exit(0)
    
    # Batch mode
    if args.batch:
        send_batch_emails(args.batch, dry_run=args.dry_run)
        sys.exit(0)
    
    # Single email mode
    if not args.email or not args.location:
        parser.print_help()
        logging.error("\nError: --email and --location are required (or use --batch for multiple emails)")
        sys.exit(1)
    
    success = send_manual_location_email(
        email=args.email,
        location=args.location,
        subject=args.subject,
        body=args.body,
        first_name=args.first_name or "",
        last_name=args.last_name or "",
        cycle_marker=args.cycle_marker or "",
        dry_run=args.dry_run,
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

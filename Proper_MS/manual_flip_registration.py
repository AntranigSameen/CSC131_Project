#!/usr/bin/env python3
"""
Manual Acuity Registration Flipping Tool

This script allows you to manually flip Acuity Registration status from "No" to "Yes"
for specific students, independent of email processing.

Usage examples:
    # Flip registration for a single person
    python manual_flip_registration.py --first-name John --last-name Doe
    
    # Flip for a specific person in a specific worksheet
    python manual_flip_registration.py --first-name Jane --last-name Smith --worksheet "AHA Registration"
    
    # Batch flip from a CSV file with columns: FirstName,LastName
    python manual_flip_registration.py --batch students.csv
    
    # Scan and flip all pending registrations (compare AHA sheet vs RQI sheet)
    python manual_flip_registration.py --scan-all
"""

import argparse
import logging
import sys
from acuity_registration import flip_acuity_registration_by_name, scan_and_flip_pending_registrations

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def flip_single(first_name, last_name, worksheet_name=None):
    """Flip registration status for a single person."""
    logging.info(f"Attempting to flip registration for: {first_name} {last_name}")
    
    result = flip_acuity_registration_by_name(
        first_name=first_name,
        last_name=last_name,
        worksheet_name=worksheet_name,
    )
    
    if result:
        logging.info(f"✓ Successfully flipped registration for {first_name} {last_name}")
        return True
    else:
        logging.warning(f"✗ Could not flip registration for {first_name} {last_name} (not found or already 'Yes')")
        return False


def flip_batch(csv_file, worksheet_name=None):
    """Flip registration status for multiple people from a CSV file."""
    import csv
    
    logging.info(f"Processing batch file: {csv_file}")
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Check for required columns
            if 'FirstName' not in reader.fieldnames or 'LastName' not in reader.fieldnames:
                logging.error("CSV file must contain 'FirstName' and 'LastName' columns")
                return False
            
            success_count = 0
            fail_count = 0
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
                first_name = row.get('FirstName', '').strip()
                last_name = row.get('LastName', '').strip()
                
                if not first_name or not last_name:
                    logging.warning(f"Row {row_num}: Skipping incomplete entry")
                    fail_count += 1
                    continue
                
                if flip_single(first_name, last_name, worksheet_name):
                    success_count += 1
                else:
                    fail_count += 1
            
            logging.info(f"\nBatch complete: {success_count} flipped, {fail_count} failed/skipped")
            return success_count > 0
            
    except FileNotFoundError:
        logging.error(f"File not found: {csv_file}")
        return False
    except Exception as e:
        logging.error(f"Error processing batch file: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Manually flip Acuity Registration status from 'No' to 'Yes'",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    # Single person mode
    parser.add_argument('--first-name', '-f', help="Student's first name")
    parser.add_argument('--last-name', '-l', help="Student's last name")
    
    # Batch mode
    parser.add_argument('--batch', '-b', help="CSV file with FirstName,LastName columns")
    
    # Scan all mode
    parser.add_argument('--scan-all', '-s', action='store_true',
                       help="Scan and flip all pending registrations (compare AHA vs RQI sheets)")
    
    # Optional worksheet names
    parser.add_argument('--worksheet', '-w', help="AHA worksheet name (optional, auto-detected by default)")
    parser.add_argument('--rqi-worksheet', '-r', help="RQI worksheet name (optional, auto-detected by default)")
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.scan_all:
        # Scan all mode
        logging.info("Starting scan of all pending registrations...")
        flipped_count = scan_and_flip_pending_registrations(
            worksheet_name=args.worksheet,
            rqi_worksheet_name=args.rqi_worksheet,
        )
        logging.info(f"✓ Scan complete: {flipped_count} registrations flipped")
        success = flipped_count > 0
    elif args.batch:
        # Batch mode
        success = flip_batch(args.batch, args.worksheet)
    elif args.first_name and args.last_name:
        # Single person mode
        success = flip_single(args.first_name, args.last_name, args.worksheet)
    else:
        parser.print_help()
        print("\nError: Must specify --scan-all, --batch, or both --first-name and --last-name", file=sys.stderr)
        sys.exit(1)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Acuity Registration Auto-Flip Scheduler

This module provides a background scheduler that periodically checks for
pending Acuity registrations that need to be flipped from "No" to "Yes".

The scheduler runs independently of email processing and can be configured
via environment variables.
"""

import logging
import threading
import time
from acuity_registration import (
    scan_and_flip_pending_registrations,
    _get_auto_flip_check_interval,
)

# Global scheduler instance
_scheduler_thread = None
_scheduler_stop_event = None


def _scheduler_loop(interval_minutes, worksheet_name=None, rqi_worksheet_name=None):
    """Background loop that runs the scan at specified intervals."""
    global _scheduler_stop_event
    
    interval_seconds = interval_minutes * 60
    logging.info(f"Registration auto-flip scheduler started (checking every {interval_minutes} minutes)")
    
    while not _scheduler_stop_event.is_set():
        try:
            # Run the scan
            flipped_count = scan_and_flip_pending_registrations(
                worksheet_name=worksheet_name,
                rqi_worksheet_name=rqi_worksheet_name,
            )
            
            if flipped_count > 0:
                logging.info(f"Scheduler flipped {flipped_count} registrations")
            
        except Exception as e:
            logging.error(f"Error in registration scheduler: {e}", exc_info=True)
        
        # Wait for the interval or until stop is signaled
        _scheduler_stop_event.wait(interval_seconds)
    
    logging.info("Registration auto-flip scheduler stopped")


def start_scheduler(interval_minutes=None, worksheet_name=None, rqi_worksheet_name=None):
    """
    Start the background scheduler for automatic registration flipping.
    
    Args:
        interval_minutes: Check interval in minutes (defaults to AUTO_FLIP_CHECK_INTERVAL_MINUTES env var)
        worksheet_name: Optional AHA worksheet name
        rqi_worksheet_name: Optional RQI worksheet name
    
    Returns:
        True if scheduler started, False if already running or disabled
    """
    global _scheduler_thread, _scheduler_stop_event
    
    # Get interval from env var if not specified
    if interval_minutes is None:
        interval_minutes = _get_auto_flip_check_interval()
    
    # Don't start if interval is 0 or negative
    if interval_minutes <= 0:
        logging.info("Registration auto-flip scheduler disabled (interval set to 0)")
        return False
    
    # Don't start if already running
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        logging.warning("Registration auto-flip scheduler already running")
        return False
    
    # Create stop event
    _scheduler_stop_event = threading.Event()
    
    # Start scheduler thread
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        args=(interval_minutes, worksheet_name, rqi_worksheet_name),
        daemon=True,
        name="RegistrationFlipScheduler",
    )
    _scheduler_thread.start()
    
    return True


def stop_scheduler(timeout=5):
    """
    Stop the background scheduler.
    
    Args:
        timeout: Maximum seconds to wait for scheduler to stop
    
    Returns:
        True if stopped successfully, False otherwise
    """
    global _scheduler_thread, _scheduler_stop_event
    
    if _scheduler_thread is None or not _scheduler_thread.is_alive():
        logging.debug("Registration auto-flip scheduler not running")
        return True
    
    # Signal stop
    _scheduler_stop_event.set()
    
    # Wait for thread to finish
    _scheduler_thread.join(timeout=timeout)
    
    if _scheduler_thread.is_alive():
        logging.warning(f"Scheduler did not stop within {timeout} seconds")
        return False
    
    logging.info("Registration auto-flip scheduler stopped successfully")
    _scheduler_thread = None
    _scheduler_stop_event = None
    return True


def is_scheduler_running():
    """Check if the scheduler is currently running."""
    global _scheduler_thread
    return _scheduler_thread is not None and _scheduler_thread.is_alive()


def get_scheduler_status():
    """
    Get detailed scheduler status.
    
    Returns:
        dict with keys: running (bool), interval_minutes (int)
    """
    return {
        "running": is_scheduler_running(),
        "interval_minutes": _get_auto_flip_check_interval(),
    }


# Standalone mode - run scheduler when executed directly
if __name__ == "__main__":
    import sys
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    interval = _get_auto_flip_check_interval()
    
    if interval <= 0:
        print("AUTO_FLIP_CHECK_INTERVAL_MINUTES not set or set to 0 in .env file")
        print("Set it to a positive number to enable scheduled checking")
        print("Example: AUTO_FLIP_CHECK_INTERVAL_MINUTES=5")
        sys.exit(1)
    
    print(f"Starting registration auto-flip scheduler (checking every {interval} minutes)")
    print("Press Ctrl+C to stop")
    
    if start_scheduler():
        try:
            # Keep main thread alive
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping scheduler...")
            stop_scheduler()
            print("Scheduler stopped")
    else:
        print("Failed to start scheduler")
        sys.exit(1)

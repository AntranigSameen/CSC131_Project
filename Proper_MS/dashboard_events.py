# ========
# IMPORTS
# ========

import logging


# =================
# DASHBOARD EVENTS
# =================

def dashboard_event(message: str):
    logging.info("DASHBOARD: %s", message)                                                                                            # Clean human-readable event intended for mini live activity feed
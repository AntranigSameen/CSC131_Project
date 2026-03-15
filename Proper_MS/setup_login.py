import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from utils import base_dir

# ============
# Paths & URLs
# ============

current_dir = Path(base_dir())  # get the folder that contains the current file
logined_in_file = current_dir / "aha_auth.json"  # location to save aha_auth.json (session state)
AHA_url = "https://atlas.heart.org/location"  # main AHA site URL

# ============================================
# Helper to check if "Sign In" button is visible
# ============================================

def sign_in_visible(page) -> bool:  
    """
    On the current page, find a visible Sign In button or link.
    Returns True if visible, False otherwise.
    """
    # All elements that are either a link or a button, some may be hidden
    for role in ("link", "button"): 
        # Locate elements by role with name matching "sign in" (case-insensitive)
        loc = page.get_by_role(role, name=re.compile(r"sign\s*in", re.I)) 
        if loc.count() > 0:  # if matching elements exist
            try:
                if loc.first.is_visible():  # check if the first element is visible
                    return True
            except Exception:
                pass
    return False

# ===================
# Main AHA Login Flow
# ===================

def aha_login_check():
    """
    Performs login to AHA if no saved session exists.
    - If `aha_auth.json` exists, reuse session and skip login.
    - Otherwise, open browser, let user manually login, and save session state.
    """

    # ----------------------------
    # Check if session already exists
    # ----------------------------
    if logined_in_file.exists():
        print(f"Found existing login state file: {logined_in_file}. Reusing session.")
        return  # Skip login, session already saved

    print(f"No saved session found. Please log in manually in the browser window.")
    print(f"The session will be saved to: {logined_in_file}")

    # ----------------------------
    # Launch Playwright (Edge) browser
    # ----------------------------
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=False)  # visible window
        context = browser.new_context()
        page = context.new_page()

        # ----------------------------
        # Open AHA website
        # ----------------------------
        page.goto(AHA_url, wait_until="domcontentloaded")  # wait until page basic HTML is loaded
        page.wait_for_timeout(1200)  # pause briefly to allow elements to render
        page.screenshot(path=str(current_dir / "setup_1_atlas.png"), full_page=True)  # debug screenshot

        # ----------------------------
        # Attempt to click "Sign In" button/link
        # ----------------------------
        clicked = False  # flag to check if Sign In was clicked
        for role in ("link", "button"): 
            loc = page.get_by_role(role, name=re.compile(r"sign\s*in", re.I))
            if loc.count() > 0:
                loc.first.click()
                clicked = True
                break

        if not clicked:
            page.screenshot(path=str(current_dir / "setup_signin_not_found.png"), full_page=True)
            browser.close()
            raise RuntimeError("Cannot find 'Sign In' on AHA. Screenshot saved: setup_signin_not_found.png")

        # ----------------------------
        # Wait until redirected to login page
        # ----------------------------
        try:
            page.wait_for_url(re.compile(r"ahasso\.heart\.org/.*login", re.I), timeout=20000)
        except PlaywrightTimeoutError:
            page.screenshot(path=str(current_dir / "setup_not_redirected_to_login.png"), full_page=True)
            browser.close()
            raise RuntimeError("Did not redirect to login page. Screenshot saved: setup_not_redirected_to_login.png")

        page.screenshot(path=str(current_dir / "setup_2_login_page.png"), full_page=True)
        print("Sign in manually in the browser window (do NOT close the browser).")
        print("The script will save aha_auth.json when login is detected.")

        # ----------------------------
        # Wait until login is completed
        # ----------------------------
        # Login is considered successful if:
        # - We're on atlas.heart.org
        # - Not on ahasso (SSO)
        # - 'Sign In' button is no longer visible
        deadline = time.time() + 180  # 3 minutes maximum
        while time.time() < deadline:
            url = page.url.lower()
            on_atlas = "atlas.heart.org" in url
            on_sso = "ahasso.heart.org" in url
            still_sign_in = sign_in_visible(page)

            if on_atlas and (not on_sso) and (not still_sign_in):
                # ----------------------------
                # Save session state to JSON
                # ----------------------------
                context.storage_state(path=str(logined_in_file))
                page.screenshot(path=str(current_dir / "setup_success.png"), full_page=True)
                print(f"Login successful! Saved session: {logined_in_file}")
                browser.close()
                return

            time.sleep(1)  # wait 1 second before checking again

        # ----------------------------
        # Timeout: login not detected
        # ----------------------------
        page.screenshot(path=str(current_dir / "setup_timeout.png"), full_page=True)
        browser.close()
        raise RuntimeError("Login not detected within 3 minutes. Screenshot saved: setup_timeout.png")
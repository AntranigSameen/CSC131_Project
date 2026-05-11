# ========
# IMPORTS
# ========

import os
import re
import time

from dotenv import load_dotenv
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from utils import app_data_dir, env_file

# ============
# Paths & URLs
# ============

current_dir = Path(app_data_dir())  # get the folder that contains the current file
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

# ==========================
# HELPER TO FILL LOGIN FIELD
# ==========================

def fill_first_visible(page, selectors, value):
    for selector in selectors:
        loc = page.locator(selector)
        try:
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click()                                                                                                     # Focus the field before filling
                loc.first.fill("")                                                                                                    # Clear any existing text first
                loc.first.fill(value)                                                                                                 # Fill the first visible matching login field
                return True
        except Exception:
            pass
    return False                                                                                                                      # No visible matching field was found

# ==================================
# HELPER TO FILL BY LABEL OR PLACEHOLDER
# ==================================

def fill_username_field(page, username):
    username_candidates = [                                                                                                           # Broad set of possible username/email field selectors
        'input[name="username"]',
        'input[name="email"]',
        'input[type="email"]',
        'input[type="text"]',
        'input[id*="user"]',
        'input[id*="email"]',
        'input[placeholder*="Email"]',
        'input[placeholder*="email"]',
        'input[placeholder*="Username"]',
        'input[placeholder*="username"]',
        'input[autocomplete="username"]',
    ]

    if fill_first_visible(page, username_candidates, username):
        return True                                                                                                                   # Filled username by common selectors

    try:
        loc = page.get_by_label(re.compile(r"email|username", re.I))
        if loc.count() > 0 and loc.first.is_visible():
            loc.first.click()
            loc.first.fill("")
            loc.first.fill(username)
            return True                                                                                                               # Filled username using visible label text
    except Exception:
        pass

    try:
        loc = page.get_by_placeholder(re.compile(r"email|username", re.I))
        if loc.count() > 0 and loc.first.is_visible():
            loc.first.click()
            loc.first.fill("")
            loc.first.fill(username)
            return True                                                                                                               # Filled username using placeholder text
    except Exception:
        pass

    return False                                                                                                                      # Username field still not found


# ==========================
# HELPER TO CLICK LOGIN BUTTON
# ==========================

def click_first_visible(page, selectors):
    for selector in selectors:
        loc = page.locator(selector)
        try:
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click()                                                                                                     # Click the first visible matching login button
                return True
        except Exception:
            pass
    return False                                                                                                                      # No visible matching submit button was found

# ===================
# Main AHA Login Flow
# ===================

def aha_login_check():
    load_dotenv(dotenv_path=env_file(), override=True)                                                                                # Always load the newest saved .env values first

    username = os.getenv("AHA_USERNAME", "").strip()                                                                                  # Saved AHA username from writable .env
    password = os.getenv("AHA_PASSWORD", "").strip()                                                                                  # Saved AHA password from writable .env

    print(f"Expected aha_auth.json location: {logined_in_file}")                                                                      # Print exact path where session file should be saved
    if logined_in_file.exists():
        print(f"Found existing login state file: {logined_in_file}. Reusing session.")
        return                                                                                                                        # Skip browser login if saved session already exists

    if not username or not password:
        raise RuntimeError("AHA_USERNAME and AHA_PASSWORD must exist before running aha_login_check().")                              # Prevent browser login if env credentials are missing

    print("No saved session found. Opening AHA login browser using saved credentials...")
    print(f"The session will be saved to: {logined_in_file}")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=False)                                                                 # Keep browser visible during automatic login
        context = browser.new_context()
        page = context.new_page()

        page.goto(AHA_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)                                                                                                   # Short delay so page elements have time to render

        clicked = False
        for role in ("link", "button"):
            loc = page.get_by_role(role, name=re.compile(r"sign\s*in", re.I))
            if loc.count() > 0:
                loc.first.click()                                                                                                     # Click initial Sign In button/link on atlas site
                clicked = True
                break

        if not clicked:
            page.screenshot(path=str(current_dir / "setup_signin_not_found.png"), full_page=True)
            browser.close()
            raise RuntimeError("Cannot find 'Sign In' on AHA. Screenshot saved: setup_signin_not_found.png")

        try:
            page.wait_for_url(re.compile(r"ahasso\.heart\.org/.*login", re.I), timeout=20000)                                         # Wait until redirected to actual AHA login page
        except PlaywrightTimeoutError:
            page.screenshot(path=str(current_dir / "setup_not_redirected_to_login.png"), full_page=True)
            browser.close()
            raise RuntimeError("Did not redirect to login page. Screenshot saved: setup_not_redirected_to_login.png")

        page.wait_for_timeout(2500)                                                                                                   # Give redirected login form more time to fully render
        
        print(f"AHA username being used: {username}")                                                                                 # Debug print to confirm env username is loaded
        print(f"AHA session file path: {logined_in_file}")                                                                            # Debug print to show exactly where aha_auth.json should be saved

        user_filled = fill_username_field(page, username)                                                                             # Use broader username/email field matching

        pass_filled = fill_first_visible(
            page,
            [
                'input[name="password"]',
                'input[type="password"]',
                'input[id*="pass"]',
                'input[autocomplete="current-password"]',
                'input[placeholder*="Password"]',
                'input[placeholder*="password"]',
            ],
            password,
        )                                                                                                                             # Fill password field using broader password selectors

        if not user_filled:
            page.screenshot(path=str(current_dir / "setup_username_not_found.png"), full_page=True)
            print("Username field was not found. Browser left open for inspection.")
            time.sleep(60)                                                                                                            # Keep browser open 60 seconds so you can inspect page manually
            raise RuntimeError("Could not find username/email field. Screenshot saved: setup_username_not_found.png")

        if not pass_filled:
            page.screenshot(path=str(current_dir / "setup_password_not_found.png"), full_page=True)
            print("Password field was not found. Browser left open for inspection.")
            time.sleep(60)                                                                                                            # Keep browser open 60 seconds so you can inspect page manually
            raise RuntimeError("Could not find password field. Screenshot saved: setup_password_not_found.png")

        clicked_login = click_first_visible(
            page,
            [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Sign In")',
                'button:has-text("Log In")',
                'button:has-text("Login")',
                'input[value*="Sign In"]',
                'input[value*="Log In"]',
                'input[value*="Login"]',
            ],
        )                                                                                                                             # Broader set of submit button selectors

        if not clicked_login:
            try:
                page.keyboard.press("Enter")                                                                                          # Fallback submit if no visible login button was found
            except Exception:
                pass

        deadline = time.time() + 180                                                                                                  # Allow up to 3 minutes for redirects / MFA / page load
        while time.time() < deadline:
            url = page.url.lower()
            on_atlas = "atlas.heart.org" in url
            on_sso = "ahasso.heart.org" in url
            still_sign_in = sign_in_visible(page)

            if on_atlas and (not on_sso) and (not still_sign_in):
                context.storage_state(path=str(logined_in_file))                                                                      # Save logged-in browser session to aha_auth.json
                page.screenshot(path=str(current_dir / "setup_success.png"), full_page=True)
                print(f"Login successful! Saved session: {logined_in_file}")
                browser.close()
                return

            time.sleep(1)                                                                                                             # Check once per second until login is detected

        page.screenshot(path=str(current_dir / "setup_timeout.png"), full_page=True)
        print("Login timeout reached. Browser left open for inspection.")
        time.sleep(60)                                                                                                                # Keep browser open before failing so you can see the final page state
        browser.close()
        raise RuntimeError("Login not detected within 3 minutes. Screenshot saved: setup_timeout.png")
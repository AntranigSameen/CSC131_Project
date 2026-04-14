import os
import re
import sys
import time
from pathlib import Path
from utils import resource_path, base_dir, update_aha_registration_status
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    expect,
    sync_playwright,
)
"""
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
"""

#ROOT = Path(__file__).resolve().parents[1]

SERVICE_ACCOUNT_JSON = resource_path(os.getenv("SERVICE_ACCOUNT_AHA_JSON", "google_sheet_api_key.json"))  # google service account key file
PROJECT_DIR = Path(base_dir())  # folder that contains this script
SAVED_LOGIN = PROJECT_DIR / "aha_auth.json"  # saved Edge login state (created by setup_login.py)
GOOGLE_SHEET_URL = os.getenv(
    "GOOGLE_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/143-IvGetu1Lz8InKi9lqNcJCiCziSvtD2954sgxxZRk/edit?gid=0#gid=0",
)  # where we append the students

screenshot_folder = PROJECT_DIR / "shots"  # save screenshots + small debug text files
screenshot_folder.mkdir(exist_ok=True)

EXTRACTED_DATA_FILE = PROJECT_DIR / "extracted_data.txt"  # written by the email watcher (main.py/run_helper.py)
TRAINING_SITE_URL = "https://atlas.heart.org/organisation/class-listing?applyTsFilter=true"  # class listing page

ORG_NAME = os.getenv("ORG_NAME", "Sac State").strip() or "Sac State"  # org name on the site

EMAIL_REFRESH_ON_START = os.getenv("EMAIL_REFRESH_ON_START", "0").strip() == "1"  # 1 = run one inbox cycle at startup
FORCE_RUN = os.getenv("FORCE_RUN", "0").strip() == "1"  # 1 = always use the latest valid extracted line
LAST_PROCESSED_INDEX_FILE = PROJECT_DIR / "last_processed_index.txt"  # remembers which extracted line we used last time

PAUSE_AT_END = os.getenv("PAUSE_AT_END", "1").strip() == "1"  # 1 = keep browser open at the end
PW_TIMEOUT_MS = int(os.getenv("PW_TIMEOUT_MS", "10000"))  # Playwright default timeout (ms)

ADVANCE_INDEX_ON_NO_COURSES = os.getenv("ADVANCE_INDEX_ON_NO_COURSES", "1").strip() == "1"  # avoid re-running the same email forever

REMINDER_EMAIL_DAYS = int(os.getenv("REMINDER_EMAIL_DAYS", "7"))  # days after adding student before sending reminder email


def normalize_to_mmddyyyy(raw: str) -> str:
    """Convert a date string into mm/dd/yyyy.
    
    Example: '03/29/26' -> '03/29/2026'.
    keep this format bc the AHA date picker matching expects it
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("Empty date string")

    # Find mm/dd/yy(yy) in the string
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", s)
    if not m:
        raise ValueError(f"Unsupported date format: {raw!r}")

    mm, dd, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if yy < 100:
        yy += 2000
    return f"{mm:02d}/{dd:02d}/{yy:04d}"


def refresh_extracted_data_file_from_email(debug: bool = True) -> tuple[bool, bool]:
    """Run one inbox cycle and refresh extracted_data.txt.
    
    Uses:
    - authentication.py -> device flow + cached token
    - run_helper.py -> run_cycle(token)
    
    Returns (ran, had_new_email).
    """
    try:
        from outlook_authentication import authenticate
        from run_helper import run_cycle
    except Exception as e:
        if debug:
            print(f"[EMAIL REFRESH] Cannot import authentication/run_helper: {e!r}", flush=True)
        return False, False

    try:
        token = authenticate()
    except Exception as e:
        if debug:
            print(f"[EMAIL REFRESH] authenticate() raised: {e!r}", flush=True)
        return False, False

    if not token:
        if debug:
            print("[EMAIL REFRESH] No access token returned from authenticate().", flush=True)
        return False, False

    try:
        ret = run_cycle(token)
    except Exception as e:
        if debug:
            print(f"[EMAIL REFRESH] run_cycle(token) raised: {e!r}", flush=True)
        return True, False

    had_new = bool((ret or "").strip())
    if debug:
        print(f"[EMAIL REFRESH] Cycle ran. New email processed={had_new}.", flush=True)
    return True, had_new


def fatal(msg: str, code: int = 1) -> None:
    # Print error and DO NOT EXIT.
    print(f"[ERROR] {msg}", file=sys.stderr, flush=True)
    raise RuntimeError(msg)                                     


def _read_last_processed_index() -> int:
    """Read last_processed_index.txt, line number
    
    0 means haven't processed anything yet.
    """
    try:
        if not LAST_PROCESSED_INDEX_FILE.exists():
            return 0
        s = (LAST_PROCESSED_INDEX_FILE.read_text(encoding="utf-8", errors="replace") or "").strip()
        return int(s) if s.isdigit() else 0
    except Exception:
        return 0

"""
def _write_last_processed_index(idx_1based: int) -> None:
    """"""Write last_processed_index.txt line number
    
    print errors instead of hiding them, b/c a silent write failure looks like 
    the script is "stuck" on the same email forever...
    """"""""
    idx = max(0, int(idx_1based))
    try:
        LAST_PROCESSED_INDEX_FILE.write_text(f"{idx}\n", encoding="utf-8")
        print(f"[INDEX] last_processed_index updated -> {idx} ({LAST_PROCESSED_INDEX_FILE})", flush=True)
    except Exception as e:
        print(f"[INDEX] FAILED to write {LAST_PROCESSED_INDEX_FILE}: {e!r}", flush=True)
"""

def _parse_extracted_csv_line(line: str) -> tuple[str, str, str]:
    """Parse one extracted_data.txt line into (subject, instructor_name, date_mmddyyyy)."""
    subject, name_raw, date_raw = line.rsplit(",", 2)  # raises ValueError if not 3 parts
    subject = (subject or "").strip()
    name = (name_raw or "").strip()
    date_part = (date_raw or "").strip()
    if not subject or not name or not date_part:
        raise ValueError("empty subject/name/date")
    date_norm = normalize_to_mmddyyyy(date_part)  # may raise
    return subject, name, date_norm


def pull_next_unprocessed_instructor_and_date_from_extracted_data_file(
    debug: bool = True,
) -> tuple[str, str, str, str, int] | None:
    """Pick the next *unprocessed* valid entry from extracted_data.txt.

    Returns (instructor_name, date_mmddyyyy, subject, raw_line, line_index_1based) or None.

    - if nothing new to process, return None
    - Uses last_processed_index.txt (line index)
       handles the case where a new email produces the exact same (subject,name,date)
       as a previously processed email, the line index will still advance
    - FORCE_RUN=1 overrides and returns the latest valid line even if it was already processed
    """
    fp = EXTRACTED_DATA_FILE
    if not fp.exists():
        if debug:
            print(f"[FILE PARSE] {fp} not found.", flush=True)
        return None

    try:
        lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        if debug:
            print(f"[FILE PARSE] Failed to read {fp}: {e!r}", flush=True)
        return None

    if not lines:
        if debug:
            print(f"[FILE PARSE] {fp} is empty.", flush=True)
        return None

    last_idx = _read_last_processed_index()

    # If the file was truncated, reset index to 0 to continue.
    if last_idx > len(lines):
        if debug:
            print(
                f"[FILE PARSE] last_processed_index={last_idx} > current_line_count={len(lines)} "
                "-> assuming file was reset; restarting from 1.",
                flush=True,
            )
        last_idx = 0

    if FORCE_RUN:
        # Latest valid line wins
        for n in range(len(lines) - 1, -1, -1):
            raw_line = (lines[n] or "").strip()
            if not raw_line:
                continue
            try:
                subject, name, date_norm = _parse_extracted_csv_line(raw_line)
            except Exception:
                continue
            idx_1based = n + 1
            if debug:
                print(f"[FILE PARSE] FORCE_RUN=1 -> using latest valid line #{idx_1based}: {raw_line!r}", flush=True)
            return name, date_norm, subject, raw_line, idx_1based
        return None

    # find the first valid entry AFafter TER last_idx
    for n in range(last_idx, len(lines)):
        idx_1based = n + 1
        raw_line = (lines[n] or "").strip()
        if not raw_line:
            continue
        try:
            subject, name, date_norm = _parse_extracted_csv_line(raw_line)
        except Exception:
            if debug:
                print(f"[FILE PARSE] Skipping invalid line #{idx_1based}: {raw_line!r}", flush=True)
            continue

        if debug:
            print(f"[FILE PARSE] Next unprocessed line #{idx_1based}: {raw_line!r}", flush=True)
            print(f"[FILE PARSE] Parsed instructor={name!r}, date={date_norm!r} (subject={subject!r})", flush=True)
        return name, date_norm, subject, raw_line, idx_1based

    return None


from datetime import datetime

def clean_shots_folder():
    """Delete old files under shots...so each run starts clean."""
    screenshot_folder.mkdir(exist_ok=True)
    for p in screenshot_folder.iterdir():
        if p.is_file():
            try:
                p.unlink()
            except Exception:
                pass

def save_error_screenshot(page, label: str = "error"):
    """Save a screenshot only when something fails (for debugging)."""
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r"[^A-Za-z0-9_\-]+", "_", (label or "error"))[:80].strip("_") or "error"
        out = screenshot_folder / f"E_{safe}_{ts}.png"
        page.screenshot(path=str(out), full_page=True)
        print(f"[ERROR] Screenshot saved: {out}", flush=True)
    except Exception:
        pass

def first_visible(loc, timeout_ms: int = 250):
    """Pick the first visible element from a locator list.
    """
    try:
        n = loc.count()
    except Exception:
        return None

    for i in range(n):
        item = loc.nth(i)
        try:
            if item.is_visible(timeout=timeout_ms):
                return item
        except Exception:
            pass
    return None

def click_real_element(page, loc):
    """
    grab a fresh element handle (short timeout) then click via JS
    """
    try:
        handle = loc.element_handle(timeout=800)
    except Exception:
        return False
    if handle is None:
        return False
    try:
        page.evaluate(
            """(el) => {
                const target = el.closest('button,a,[role="button"],[role="gridcell"]') || el;
                target.click();
            }""",
            handle,
        )
        return True
    except Exception:
        return False

def close_dropdown_and_wait(page):
    """Close any open dropdown overlays
    """
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    try:
        page.mouse.click(5, 5)
    except Exception:
        pass

    selectors = [
        "[role='listbox']",
        ".react-select__menu",
        ".select__menu",
        ".css-26l3qy-menu",
    ]

    deadline = time.time() + 1.5
    while time.time() < deadline:
        any_visible = False
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible(timeout=250):
                    any_visible = True
                    break
            except Exception:
                pass

        if not any_visible:
            return

        # Try closing again and re-check
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        try:
            page.mouse.click(5, 5)
        except Exception:
            pass
        page.wait_for_timeout(100)

def clear_modal_backdrop(page):
    """Clear a backdrop overlay
    
    If the screen stays grey after a modal closes, clicks will be blocked
    use Escape, click-out first, then remove leftover backdrops as a fallback
    """
    # Try normal dismissal paths
    for _ in range(2):
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        try:
            page.mouse.click(5, 5)
        except Exception:
            pass
        page.wait_for_timeout(80)

    try:
        backdrops = page.locator("div.modal-backdrop")
        if backdrops.count() == 0:
            return
    except Exception:
        return

    # wait for it to go away on its own
    try:
        backdrops.first.wait_for(state="hidden", timeout=800)
        return
    except Exception:
        pass
    try:
        backdrops.first.wait_for(state="detached", timeout=800)
        return
    except Exception:
        pass

    # If still present, forcibly clean it up
    try:
        page.evaluate(
            """() => {
                document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
                document.querySelectorAll('.modal.show').forEach(el => el.classList.remove('show'));
                document.querySelectorAll('[role="dialog"][aria-modal="true"]')
                  .forEach(el => el.setAttribute('aria-hidden','true'));
                document.body.classList.remove('modal-open');
                document.body.style.removeProperty('overflow');
                document.body.style.removeProperty('padding-right');
            }"""
        )
    except Exception:
        pass
    page.wait_for_timeout(60)




def calendar_is_open(page, timeout_ms: int = 250) -> bool:
    """check if the date picker currently open..."""
    checks = [
        page.locator('[aria-current="date"]'),
        page.locator("[role='dialog'] [role='gridcell'], [role='tooltip'] [role='gridcell'], [role='listbox'] [role='gridcell']"),
        page.locator(".react-datepicker, .DayPicker, .MuiPickersPopper-root"),
    ]
    for c in checks:
        try:
            if c.count() > 0 and c.first.is_visible(timeout=timeout_ms):
                return True
        except Exception:
            pass
    return False

def _pick_specific_date_in_open_range_picker(page, date_mmddyyyy: str, *, second_click: bool) -> None:
    """ date-picker
    
    - Make sure month year match the target
    - Click the day cell
    - Optionally click the same day again (start=end)
    """
    # ---- parse mm/dd/yyyy ----
    try:
        mm, dd, yyyy = date_mmddyyyy.strip().split("/")
        mm_i = int(mm)
        dd_i = int(dd)
        yyyy_i = int(yyyy)
    except Exception as e:
        raise ValueError(f"Date must be in mm/dd/yyyy format, got: {date_mmddyyyy!r}") from e

    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    month_name = month_names[mm_i - 1]

    aria_pattern = re.compile(
        rf"\b{re.escape(month_name)}\b\s+{dd_i}(?:st|nd|rd|th)?\b.*\b{yyyy_i}\b",
        re.I,
    )

    OPEN_WAIT_MS = 500
    LOAD_WAIT_MS = 500

    CAL_DEBUG = os.getenv("CAL_DEBUG", "0").strip() == "1"

    def _log(msg: str) -> None:
        if CAL_DEBUG:
            print(msg, flush=True)

    def _clean(s: str) -> str:
        return " ".join((s or "").strip().split())

    def scope_loc():
        dp = page.locator(".react-datepicker:visible")
        try:
            if dp.count() > 0 and dp.first.is_visible(timeout=250):
                return dp.first
        except Exception:
            pass
        return page.locator("body")

    def _month_value(sc):
        v = sc.locator(".calendar_month__single-value:visible")
        if v.count() == 0:
            v = page.locator(".calendar_month__single-value:visible")
        if v.count() == 0:
            return ""
        try:
            return _clean(v.first.inner_text())
        except Exception:
            return _clean(v.first.text_content() or "")

    def _year_value(sc):
        v = sc.locator(".calendar_year__single-value:visible")
        if v.count() == 0:
            v = page.locator(".calendar_year__single-value:visible")
        if v.count() == 0:
            return ""
        try:
            return _clean(v.first.inner_text())
        except Exception:
            return _clean(v.first.text_content() or "")

    def _parse_month_index_from_value(v: str):
        s = _clean(v)
        if not s:
            return None
        for i, nm in enumerate(month_names, start=1):
            if re.fullmatch(re.escape(nm), s, flags=re.I) or re.search(rf"\b{re.escape(nm)}\b", s, flags=re.I):
                return i
        for i, nm in enumerate(month_names, start=1):
            ab = nm[:3]
            if re.fullmatch(re.escape(ab), s, flags=re.I) or re.search(rf"\b{re.escape(ab)}\b", s, flags=re.I):
                return i
        return None

    def _parse_year_from_value(v: str):
        s = _clean(v)
        m = re.search(r"\b(20\d{2})\b", s)
        return int(m.group(1)) if m else None

    def _month_control(sc):
        c = sc.locator(".calendar_month__control:visible")
        if c.count() == 0:
            c = page.locator(".calendar_month__control:visible")
        return c.first if c.count() > 0 else None

    def _year_control(sc):
        c = sc.locator(".calendar_year__control:visible")
        if c.count() == 0:
            c = page.locator(".calendar_year__control:visible")
        return c.first if c.count() > 0 else None

    def _open_listbox_from_control(control):
        """Open a react-select control and return (listbox, input_loc)."""
        if control is None:
            return None, None

        try:
            control.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass

        try:
            control.click(timeout=2000, force=True)
        except Exception:
            try:
                click_real_element(page, control)
            except Exception:
                return None, None

        page.wait_for_timeout(OPEN_WAIT_MS)

        inp = control.locator("input[id^='react-select-'][id$='-input']")
        input_loc = inp.first if inp.count() > 0 else None

        listbox = None
        if input_loc is not None:
            try:
                lb_id = input_loc.get_attribute("aria-controls") or ""
            except Exception:
                lb_id = ""
            if lb_id:
                listbox = page.locator(f"#{lb_id}")

        if listbox is None:
            lb_any = page.locator("div[role='listbox']:visible")
            listbox = lb_any.last if lb_any.count() > 0 else None

        if listbox is not None:
            try:
                expect(listbox).to_be_visible(timeout=3000)
            except Exception:
                pass

        return listbox, input_loc

    def _choose_option_by_keyboard(control, target_text: str) -> bool:
        """Select an option in react-select using keyboard if not, click by text"""
        listbox, input_loc = _open_listbox_from_control(control)
        if listbox is None:
            return False

        opts = listbox.locator("div[role='option']")
        for _ in range(10):
            try:
                if opts.count() > 0:
                    break
            except Exception:
                pass
            page.wait_for_timeout(100)

        try:
            n = opts.count()
        except Exception:
            n = 0

        idx = None
        for i in range(n):
            try:
                t = _clean(opts.nth(i).inner_text())
            except Exception:
                t = _clean(opts.nth(i).text_content() or "")
            if not t:
                continue
            if t.lower() == str(target_text).strip().lower():
                idx = i
                break

        # Focus input so arrowDown affect menu highlight
        if input_loc is not None:
            try:
                input_loc.click(timeout=1000, force=True)
            except Exception:
                pass
        else:
            try:
                control.click(timeout=1000, force=True)
            except Exception:
                pass

        page.wait_for_timeout(50)

        if idx is not None:
            try:
                page.keyboard.press("Home")
            except Exception:
                pass
            for _ in range(idx):
                try:
                    page.keyboard.press("ArrowDown")
                except Exception:
                    pass
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass
            page.wait_for_timeout(LOAD_WAIT_MS)
            return True


        page.wait_for_timeout(LOAD_WAIT_MS)
        return True

    def _ensure_month_year_visible():
        for _pass in range(4):
            sc = scope_loc()
            cur_month_txt = _month_value(sc)
            cur_year_txt = _year_value(sc)
            cur_m = _parse_month_index_from_value(cur_month_txt)
            cur_y = _parse_year_from_value(cur_year_txt)

            _log(f"[CAL] month_value={cur_month_txt!r}, year_value={cur_year_txt!r} parsed=(m={cur_m}, y={cur_y}) target=(m={mm_i}, y={yyyy_i})")

            # year
            if cur_y != yyyy_i:
                yc = _year_control(sc)
                if yc is None:
                    _log("[CAL] year control not found.")
                else:
                    if not _choose_option_by_keyboard(yc, str(yyyy_i)):
                        _log("[CAL] year select failed (keyboard/click).")

            page.wait_for_timeout(LOAD_WAIT_MS)

            # month
            sc = scope_loc()
            cur_month_txt2 = _month_value(sc)
            cur_m2 = _parse_month_index_from_value(cur_month_txt2)
            if cur_m2 != mm_i:
                mc = _month_control(sc)
                if mc is None:
                    _log("[CAL] month control not found.")
                else:
                    if not _choose_option_by_keyboard(mc, month_name):
                        _log("[CAL] month select failed (keyboard/click).")

            page.wait_for_timeout(LOAD_WAIT_MS)

            sc = scope_loc()
            fm_txt = _month_value(sc)
            fy_txt = _year_value(sc)
            fm = _parse_month_index_from_value(fm_txt)
            fy = _parse_year_from_value(fy_txt)
            _log(f"[CAL] after set month_value={fm_txt!r}, year_value={fy_txt!r} parsed=(m={fm}, y={fy})")

            if fm == mm_i and fy == yyyy_i:
                return

    def _find_target_day():
        sc = scope_loc()
        cells = sc.locator("[aria-label]:visible")
        try:
            n = cells.count()
        except Exception:
            n = 0
        for i in range(n):
            el = cells.nth(i)
            try:
                lab = _clean(el.get_attribute("aria-label") or "")
            except Exception:
                continue
            if aria_pattern.search(lab):
                return el

       

    _ensure_month_year_visible()

    t = _find_target_day()
    if t is None:
        raise RuntimeError(f"Could not locate date {date_mmddyyyy} in the calendar.")

    try:
        t.click(timeout=8000)
    except Exception:
        click_real_element(page, t)

    page.wait_for_timeout(300)

    if not second_click:
        return

    if not calendar_is_open(page):
        try:
            page.locator("text=/Choose a Date Range/i").first.click(timeout=2000)
        except Exception:
            pass
        page.wait_for_timeout(400)

    _ensure_month_year_visible()

    t2 = _find_target_day() or t
    try:
        t2.click(timeout=8000)
    except Exception:
        click_real_element(page, t2)

    page.wait_for_timeout(500)


def click_specific_date_twice(page, date_mmddyyyy: str):
    """Pick one date as both start and end (click the same day twice)."""
    _pick_specific_date_in_open_range_picker(page, date_mmddyyyy, second_click=True)

def click_specific_date_once(page, date_mmddyyyy: str):
    """Pick a date once (assumes the date picker is already open)."""
    _pick_specific_date_in_open_range_picker(page, date_mmddyyyy, second_click=False)

def click_date_range(page, start_mmddyyyy: str, end_mmddyyyy: str):
    """Pick a real start, end range in the date picker.
    
    If start == end, click the same day twice (start=end).
    """
    s = normalize_to_mmddyyyy(start_mmddyyyy)
    e = normalize_to_mmddyyyy(end_mmddyyyy)

    if s == e:
        click_specific_date_twice(page, s)
        return

    # Start click
    click_specific_date_once(page, s)

    #  UIs keep the picker open until the end date is clicked
    if not calendar_is_open(page):
        open_date_range_picker(page)

    # End click
    click_specific_date_once(page, e)



def select_organization(page, org_name="Sac State"):
    # find the Organization dropdown
    org = page.get_by_label(re.compile(r"organization", re.I))
    if org.count() == 0:
        org = page.get_by_role("combobox", name=re.compile(r"organization", re.I))
    

    org.first.wait_for(state="visible", timeout=30000)

    #  custom dropdown, click -> pick option
    org.first.click()
    pat = re.compile(r"\s*".join(map(re.escape, org_name.split())), re.I)
    opt = page.get_by_role("option", name=pat)
    opt.first.wait_for(state="visible", timeout=15000)
    opt.first.click()


def select_instructor(page, name_text="Sac State"):
    # type the instructor name, wait for the popup to filter, then select the first result.

    instructor_box = page.get_by_placeholder(re.compile(r"name\s*or\s*id", re.I))
    if instructor_box.count() == 0:
        instructor_box = page.get_by_label(re.compile(r"instructor", re.I))
    if instructor_box.count() == 0:
        instructor_box = page.get_by_role("combobox", name=re.compile(r"instructor", re.I))

    instructor_box = instructor_box.first                                                                                            # Always work with the first matched instructor field
    instructor_box.wait_for(state="visible", timeout=30000)                                                                          # Wait until instructor field is visible on page

    # Wait until the field is enabled before clicking
    for _ in range(60):                                                                                                              # Wait up to about 30 seconds for disabled field to become enabled
        disabled_attr = instructor_box.get_attribute("disabled")
        aria_disabled = instructor_box.get_attribute("aria-disabled")
        if disabled_attr is None and aria_disabled != "true":
            break                                                                                                                    # Field is ready once disabled state is gone
        page.wait_for_timeout(500)
    else:
        raise RuntimeError("Instructor field was visible but stayed disabled.")                                                      # Fail clearly instead of timing out on click

    # Click once to focus
    instructor_box.click()
    page.wait_for_timeout(200)

    # Type to filter
    try:
        instructor_box.fill(name_text)
    except Exception:
        instructor_box.click()
        page.keyboard.type(name_text)

    # Wait for the dropdown options to appear
    try:
        page.locator("[role='listbox']").first.wait_for(state="visible", timeout=1500)                                               # Give dropdown a little longer to appear
    except Exception:
        # Some react-select implementations don't use role=listbox; a tiny delay is enough
        page.wait_for_timeout(300)

    # Pick first filtered result (ArrowDown + Enter)
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(200)
    page.keyboard.press("Enter")

    # Ensure the dropdown is closed
    close_dropdown_and_wait(page)


def open_date_range_picker(page):
    """Open the date-range picker on the listing page
    
    After instructor selection the page re-renders, so this function keeps trying
    short clicks until the calendar is actually open.
    """

    print("[DATE] Opening date range picker...")

    close_dropdown_and_wait(page)

    # locators based on DOM:
    # - Placeholder: <span class="customReactCalendarPicker_selectedOption__...">Choose a Date Range</span>
    # - Container:  <span class="customReactCalendarPicker_dateContainer__..."> ... </span>
    # - Start span: <span aria-label="Start Date">Start Date</span>
    placeholder = page.locator("span[class^='customReactCalendarPicker_selectedOption_']", has_text=re.compile(r"^Choose a Date Range$", re.I)).first
    container = page.locator("span[class^='customReactCalendarPicker_dateContainer_']").first
    start_span = page.locator("span[aria-label='Start Date']").first

    # still wait, click immediately once the control becomes usable
    deadline = time.time() + float(os.getenv('DATE_OPEN_TIMEOUT_SEC', '4.0'))
    last_print = 0.0

    while time.time() < deadline:
        close_dropdown_and_wait(page)

        # Sometimes the placeholder span exists but the clickable handler is on the parent container...
        click_targets = [
            placeholder,
            start_span,
            container,
        ]

        for tgt in click_targets:
            try:
                if tgt.count() == 0:
                    continue
                tgt.click(timeout=250, force=True, no_wait_after=True)
                page.wait_for_timeout(50)
                if calendar_is_open(page):
                    return
            except Exception:
                pass

        

        page.wait_for_timeout(80)

    raise RuntimeError("Date picker did not open within the fast timeout. If you can click it manually immediately, your selector is correct and this likely means an overlay is intercepting clicks (e.g., instructor dropdown still open).")


def find_action_column_index(page) -> int:
    # find which column number is labeled "Action"
    headers = page.locator("table thead tr th")
    n = headers.count()
    for i in range(n):
        txt = (headers.nth(i).inner_text() or "").strip().lower()
        if "action" in txt:
            return i
    return -1


def _view_item_locator(page):
    # Where the "View" item shows up once the menu is open
    return page.locator("button, [role='menuitem'], a, li").filter(
        has_text=re.compile(r"^view$", re.I)
    )


def open_row_view(page, row_index: int = 0):
    """On the listing table, open the Action menu for a row and click View
    
     navigates to the course view class page.
    """
    page.locator("table").first.wait_for(state="visible", timeout=30000)

    clear_modal_backdrop(page)
    close_dropdown_and_wait(page)

    action_col = find_action_column_index(page)
    if action_col == -1:
        raise RuntimeError('Could not find the "Action" column header.')

    rows = page.locator("table tbody tr")
    try:
        n = rows.count()
    except Exception:
        n = 0

    if n == 0:
        raise RuntimeError("No course rows found on the listing page (table is empty).")

    if row_index < 0 or row_index >= n:
        raise RuntimeError(f"Row index out of range: row_index={row_index}, rows={n}")

    row = rows.nth(row_index)
    row.wait_for(state="visible", timeout=30000)
    
    row.scroll_into_view_if_needed(timeout=5000)                                                        # CHANGES MADE FOR HEADLESS
    page.wait_for_timeout(300)                                                                                      #
                                                                                                                    #
    action_cell = row.locator("td").nth(action_col)                                                                 #
    action_cell.scroll_into_view_if_needed(timeout=5000)                                                            #
    page.wait_for_timeout(300)                                                                          # CHANGES MADE FOR HEADLESS

    """   THIS WAS CHANGED
    # One scroll
    row.scroll_into_view_if_needed()
    page.wait_for_timeout(100)

    action_cell = row.locator("td").nth(action_col)
    """

    # open the menu
    opened = False
    for attempt in range(5):
        clickable = first_visible(action_cell.locator("button, [role='button'], a, span, div"))
        if clickable is not None:
            try:
                clickable.scroll_into_view_if_needed(timeout=3000)
                clickable.click(timeout=3000, force=True)
            except Exception:
                click_real_element(page, clickable)
        page.wait_for_timeout(500)

        # Did the menu open?
        if first_visible(_view_item_locator(page)) is not None:
            opened = True
            break

    if not opened:
        save_error_screenshot(page, "action_menu_failed")
        raise RuntimeError("Could not open the Action menu (three dots).")

    view_item = first_visible(_view_item_locator(page))
    if view_item is None:
        raise RuntimeError('Action menu opened, but "View" is not visible.')

    with page.expect_navigation(wait_until="domcontentloaded"):
        view_item.click()

    page.wait_for_timeout(1000)
    return page




def get_course_type_for_row(page, row_index: int) -> str:
    """Read the short course code from the listing row like ACLS """
    try:
        rows = page.locator("table tbody tr")
        row = rows.nth(row_index)
        row.wait_for(state="visible", timeout=8000)

        course_td = row.locator("td[data-title='Course']").first
        

        #  small tag span (AHA DOM shows class = dynamicTable_disciplineStyle__...)
        disc = course_td.locator("span[class*='dynamicTable_disciplineStyle']").first

        txt = ""
        if disc.count() > 0:
            try:
                txt = (disc.get_attribute("title") or "").strip()
            except Exception:
                txt = ""
            if not txt:
                try:
                    txt = (disc.inner_text() or "").strip()
                except Exception:
                    txt = (disc.text_content() or "").strip()

        txt = re.sub(r"\s+", " ", (txt or "").strip())
        return txt
    except Exception:
        return ""


def _count_tsv_rows(tsv_rows_only: str) -> int:
    lines = [ln for ln in (tsv_rows_only or "").splitlines() if ln.strip()]
    return len(lines)




def _ensure_rows_for_index(page, target_row_index: int, timeout_ms: int = 12000) -> int:
    """Wait until the results table has enough <tr> rows for target_row_index.
    
    React sometimes re-renders the table after going back... this prevents 'idx out of range'
    when rows temporarily collapse to 0 or 1
    """
    deadline = time.time() + (max(1000, int(timeout_ms)) / 1000.0)

    # If a loader table exists first, wait some time for it to disappear
    try:
        page.locator("table.aui-table-loader").first.wait_for(state="hidden", timeout=min(4000, int(timeout_ms)))
    except Exception:
        pass

    last_n = -1
    stable_ticks = 0

    while time.time() < deadline:
        try:
            n = page.locator("table tbody tr").count()
        except Exception:
            n = 0

        if n > target_row_index:
            return n

        if n == last_n:
            stable_ticks += 1
        else:
            stable_ticks = 0
            last_n = n

        # if stuck at 0 rows, do one small nudge occasionally
        if n == 0 and stable_ticks in (6, 12):
            try:
                page.mouse.wheel(0, 400)
            except Exception:
                pass

        page.wait_for_timeout(200 if stable_ticks < 8 else 350)

    try:
        return page.locator("table tbody tr").count()
    except Exception:
        return 0

def process_all_courses_on_results_page(page, instructor_name: str, date_label: str):
    """Loop through all course rows on the filtered listing page.
    
    For each course:
    - open View
    - accept pending requests (if any)
    - append only the newly accepted students into Google Sheet
    - go back and continue until all rows are visited
    """
    stats = {
        "courses_found": 0,
        "courses_viewed": 0,
        "courses_with_pending": 0,
        "courses_no_pending": 0,
        "rows_appended": 0,
    }

    # Wait for results table shell
    page.locator("table").first.wait_for(state="visible", timeout=30000)

    processed_course_urls = set()

    idx = 0
    while True:
        # Ensure enough rows are present in the DOM for idx
        n = _ensure_rows_for_index(page, idx, timeout_ms=15000)

        if idx == 0:
            stats["courses_found"] = n

        if n == 0 or idx >= n:
            break

        listing_url = page.url

        # Read the Course type before navigating away.
        course_type = get_course_type_for_row(page, idx)

        # Open View for this row
        open_row_view(page, idx)
        stats["courses_viewed"] += 1

        course_url = page.url
        if course_url in processed_course_urls:
            # Already processed (can happen if the table re-ordered / re-rendered).
            try:
                page.go_back(wait_until="domcontentloaded")
            except Exception:
                page.goto(listing_url, wait_until="domcontentloaded")
            page.locator("table").first.wait_for(state="visible", timeout=30000)
            idx += 1
            continue
        processed_course_urls.add(course_url)

        # Accept + extract conditionally
        # Snapshot roster before accepting so  only append NEW students, no duplicates
        before_emails = {e for (e, _) in _roster_pairs_snapshot(page)}

        accepted_count = accept_pending_requests(page)
        if accepted_count <= 0:
            stats["courses_no_pending"] += 1
            course_type = ""  # no pending -> discard course label
        else:
            stats["courses_with_pending"] += 1
            rows_tsv = extract_new_students_rows_for_sheet(
                page,
                course_type=course_type,
                before_emails=before_emails,
                expected_new=accepted_count,
                date=date_label,
            )
            append_rows_to_google_sheet_via_api(rows_tsv)
            stats["rows_appended"] += _count_tsv_rows(rows_tsv)

# Back to results, keep the same filtered list
        try:
            page.go_back(wait_until="domcontentloaded")
        except Exception:
            page.goto(listing_url, wait_until="domcontentloaded")

        # Ensure the table shell is back, row availability is handled at the top of next loop
        try:
            page.locator("table").first.wait_for(state="visible", timeout=30000)
        except Exception:
            page.goto(listing_url, wait_until="domcontentloaded")
            page.locator("table").first.wait_for(state="visible", timeout=30000)

        clear_modal_backdrop(page)
        page.wait_for_timeout(250)
        idx += 1

    print(
        f"[COURSES] instructor={instructor_name!r}, date={date_label!r} "
        f"found={stats['courses_found']} viewed={stats['courses_viewed']} "
        f"with_pending={stats['courses_with_pending']} no_pending={stats['courses_no_pending']} "
        f"rows_appended={stats['rows_appended']}",
        flush=True,
    )
    return stats
def accept_pending_requests(page) -> int:
    """Accept pending requests on the course View page
    
    Returns how many requests got accepted for this course
    """
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(120)
    clear_modal_backdrop(page)

    accepted_count = 0

    # Real confirm modal (aria-modal=true)
    modal_sel = (
        "div[role='dialog'][aria-modal='true']:visible, "
        "div.modal.show[aria-modal='true']:visible, "
        "div.modal.show:visible"
    )

    max_accepts = int(os.getenv("MAX_PENDING_ACCEPTS", "25"))


    def _pending_header():
        # wait a litle bit
        hdr = page.locator(r"text=/\b\d*\s*Pending\s+Request(s)?\b/i").first
        try:
            hdr.wait_for(state="visible", timeout=350)
            return hdr
        except PlaywrightTimeoutError:
            return None
        except Exception:
            return None

    for _ in range(max_accepts):
        clear_modal_backdrop(page)

        hdr = _pending_header()
        if hdr is None:
            break

        # If the header includes an explicit 0, exit
        try:
            hdr_text = (hdr.inner_text() or "").strip()
        except Exception:
            hdr_text = ""
        m0 = re.search(r"\b0\s*Pending\s+Request", hdr_text, flags=re.I)
        if m0:
            break

        section = hdr.locator("xpath=ancestor::section[1]")
        if section.count() == 0:
            section = hdr.locator("xpath=ancestor::div[1]")
        accept_btn = section.locator("button[data-testid='acceptbutton'], button:has-text('Accept')").first
        try:
            # Avoid Playwright's default 10s auto-wai
            accept_btn.wait_for(state="visible", timeout=400)
        except PlaywrightTimeoutError:
            break
        except Exception:
            break

        try:
            if not accept_btn.is_enabled():
                page.wait_for_timeout(180)
                continue
        except Exception:
            # Re-rendering, retry the loop.
            page.wait_for_timeout(120)
            continue

        # Click the in-section Accept, opens the confirm modal
        try:
            accept_btn.click(timeout=1500, force=True)
        except Exception:
            page.wait_for_timeout(160)
            continue

        page.wait_for_timeout(120)

        # Confirm modal (if any)
        modal = page.locator(modal_sel).first
        confirmed = False
        try:
            modal.wait_for(state="visible", timeout=1800)
            confirm = modal.locator("[data-testid='acceptBtn'], button[data-testid='acceptBtn']").first
            try:
                confirm.wait_for(state="visible", timeout=600)
            except PlaywrightTimeoutError:
                confirm = modal.locator("button:has-text('Accept')").first

            try:
                confirm.click(timeout=1500, force=True)
                confirmed = True
            except Exception:
                # Some accepts complete inline / modal closes itself
                confirmed = True

            # Short wait for modal to close
            try:
                modal.wait_for(state="hidden", timeout=2200)
            except Exception:
                try:
                    modal.wait_for(state="detached", timeout=900)
                except Exception:
                    pass
        except Exception:
            # Some accepts complete inline without a confirm modal.
            confirmed = True

        clear_modal_backdrop(page)

        if confirmed:
            accepted_count += 1

        # Let the Pending section refresh before checking again
        page.wait_for_timeout(220)

    clear_modal_backdrop(page)
    return accepted_count
def parse_full_name(raw_text: str):
    """Split a 'Name/Phone Number' cell into (first, middle, last).
    
    Handles:
    - 'First Last'
    - 'First Middle Last'
    """

    if raw_text is None:
        return "", "", ""

    # Clean and split into non-empty lines
    lines = [ln.strip() for ln in str(raw_text).splitlines() if ln.strip()]

    if not lines:
        return "", "", ""

    # Pick a "name line":
    # - prefer a line that contains letters
    # - if none, just use the first line anyway
    name_line = ""
    for ln in lines:
        if re.search(r"[A-Za-z]", ln):
            name_line = ln
            break
    if name_line == "":
        name_line = lines[0]

    # Normalize spaces
    name_line = " ".join(name_line.split())


    # Handle "First Middle Last" or  "First Last"
    tokens = [t for t in name_line.split(" ") if t]

    if len(tokens) == 1:
        return tokens[0], "", ""
    if len(tokens) == 2:
        return tokens[0], "", tokens[1]

    first = tokens[0]
    last = tokens[-1]
    middle = " ".join(tokens[1:-1])
    return first, middle, last


def _roster_pairs_snapshot(page):
    """Grab the roster table as a list of (email, name_phone).
    
    Uses one JS evaluation to avoid scrolling and row-by-row locator calls
    """
    tbl = page.locator("table:has(th:has-text('Email Address'))").first
    try:
        tbl.wait_for(state="visible", timeout=1200)
    except PlaywrightTimeoutError:
        return []
    except Exception:
        return []

    try:
        data = page.eval_on_selector_all(
            "table:has(th:has-text('Email Address')) tbody tr",
            """rows => rows.map(r => {
                    const tds = r.querySelectorAll('td');
                    const email = (tds[0]?.innerText || '').trim();
                    const name  = (tds[1]?.innerText || '').trim();
                    return [email, name];
                }).filter(p => p[0] && p[0].trim().length > 0)"""
        )
        # Ensure it's always list[list[str,str]]
        out = []
        for item in (data or []):
            try:
                e = (item[0] or "").strip()
                n = (item[1] or "").strip()
            except Exception:
                continue
            if e:
                out.append((e, n))
        return out
    except Exception:
        # Fallback: minimal locator-based extraction
        try:
            rows = tbl.locator("tbody tr")
            out = []
            for i in range(rows.count()):
                tds = rows.nth(i).locator("td")
                if tds.count() >= 2:
                    e = (tds.nth(0).inner_text() or "").strip()
                    n = (tds.nth(1).inner_text() or "").strip()
                    if e:
                        out.append((e, n))
            return out
        except Exception:
            return []

def extract_new_students_rows_for_sheet(page, course_type: str, before_emails: set[str], expected_new: int = 0, date: str = "") -> str:
    """Build tsv rows (no header) for only newly accepted students.
    
    compare roster emails before vs after accepting, then emit only the new ones
    Columns: Email | First | Middle | Last | Course | Date | Acuity Registration | AHA Registration | Reminder Email
    """
    course = (course_type or "").strip()
    date_norm = (date or "").strip()
    before_norm = {str(e).strip().lower() for e in (before_emails or set()) if str(e).strip()}

    # Wait for the roster table to reflect newly accepted students
    deadline = time.time() + 3.0
    new_pairs = []

    while time.time() < deadline:
        after_pairs = _roster_pairs_snapshot(page)
        new_pairs = []
        seen = set()
        for email, name_phone in after_pairs:
            key = email.strip().lower()
            if key in before_norm or key in seen:
                continue
            seen.add(key)
            new_pairs.append((email, name_phone))

        if expected_new and len(new_pairs) < expected_new:
            page.wait_for_timeout(250)
            continue
        break

    lines = []
    for email, name_phone in new_pairs:
        first, middle, last = parse_full_name(name_phone)
        lines.append("\t".join([email.strip(), first, middle, last, course, date_norm, "No", "Yes", ""]))

    tsv = "\n".join(lines)

    # Save a local copy
    try:
        out_path = screenshot_folder / "accepted_students_rows_only_new.tsv"
        out_path.write_text(tsv, encoding="utf-8")
    except Exception:
        pass

    return tsv


_GS_GC = None
_GS_SH = None
_GS_WS_CACHE: dict[str, object] = {}


def _get_gsheet_worksheet(worksheet_name: str | None = None):
    """Create/reuse the gspread client + spreadsheet, then return the worksheet."""
    global _GS_GC, _GS_SH, _GS_WS_CACHE

    try:
        import gspread
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError("Missing dependency 'gspread'. Install with: pip install gspread google-auth") from e

    key_path = resource_path(SERVICE_ACCOUNT_JSON)                                                          # Creates a path to the json file

    if _GS_GC is None:
        _GS_GC = gspread.service_account(filename=key_path)

    if _GS_SH is None:
        _GS_SH = _GS_GC.open_by_url(GOOGLE_SHEET_URL)

    key = (worksheet_name or "").strip() or "__sheet1__"
    if key in _GS_WS_CACHE:
        return _GS_WS_CACHE[key]

    ws = _GS_SH.worksheet(worksheet_name) if worksheet_name else _GS_SH.sheet1
    _GS_WS_CACHE[key] = ws
    return ws


def ensure_gsheet_headers(worksheet_name: str | None = None):
    """Ensure the Google Sheet has the correct header row with all 9 columns."""
    ws = _get_gsheet_worksheet(worksheet_name)
    
    # Check if sheet is empty (no headers yet)
    try:
        first_row = ws.row_values(1)
        if first_row and any(first_row):
            # Sheet already has content (assume headers exist)
            return
    except Exception:
        pass
    
    # Add header row with all 9 columns
    headers = ["Email", "First Name", "Middle Name", "Last Name", "Course", "Date", "Acuity Registration", "AHA Registration", "Reminder Email"]
    ws.insert_row(headers, index=1, value_input_option="RAW")


def append_rows_to_google_sheet_via_api(tsv_rows_only: str, worksheet_name: str | None = None):
    """Append TSV rows (no header) into Google Sheet (API client reused)."""
    # Ensure headers exist first
    ensure_gsheet_headers(worksheet_name)
    
    rows = [ln for ln in (tsv_rows_only or "").splitlines() if ln.strip()]
    if not rows:
        return
    values = [r.split("\t") for r in rows]

    ws = _get_gsheet_worksheet(worksheet_name)
    ws.append_rows(values, value_input_option="RAW")

    # Keep the registration flags synchronized for any existing row that matches these emails.
    for row in values:
        email = (row[0] if row else "").strip()
        if not email:
            continue

        try:
            update_student_registration_status(email=email, worksheet_name=worksheet_name)
        except Exception as e:
            print(f"[GSHEET] Failed to update registration status for {email}: {e!r}", flush=True)


def update_student_registration_status(email: str, worksheet_name: str | None = None, reminder_sent_date: str | None = None):
    """Update a student's registration status when triggered.
    
    Updates columns for the given email:
    - Acuity Registration (column 7) -> "Yes"
    - AHA Registration (column 8) -> "Yes"
    - Reminder Email (column 9) -> date string if provided, else blank
    
    Args:
        email: Student's email address to find and update
        worksheet_name: Optional worksheet name (defaults to Sheet1)
        reminder_sent_date: Optional date string when reminder email was sent (e.g., "04/10/2026")
                           If None, column remains blank
    """
    try:
        return update_aha_registration_status(
            email=email,
            worksheet_name=worksheet_name,
            reminder_sent_date=reminder_sent_date,
        )
    except Exception as e:
        print(f"[GSHEET] Error updating student {email}: {e!r}", flush=True)
        return False


def check_and_populate_reminder_emails(worksheet_name: str | None = None):
    """Check for students needing reminders and auto-populate Reminder Email column.
    
    Finds students where:
    - Acuity Registration = "No"
    - Reminder Email is blank
    - Student was added >= REMINDER_EMAIL_DAYS ago
    
    Auto-populates Reminder Email with today's date for those students.
    
    Returns count of students updated.
    """
    from datetime import datetime, timedelta
    
    ws = _get_gsheet_worksheet(worksheet_name)
    
    try:
        all_values = ws.get_all_values()
        today_str = datetime.now().strftime("%m/%d/%Y")
        cutoff_date = datetime.now() - timedelta(days=REMINDER_EMAIL_DAYS)
        updated_count = 0
        
        for row_idx, row in enumerate(all_values, start=1):
            if row_idx == 1:
                # Skip header row
                continue
            
            if not row or len(row) < 9:
                continue
            
            email = (row[0] or "").strip()
            date_str = (row[5] or "").strip()  # Column 6 (index 5) is Date
            acuity_reg = (row[6] or "").strip().lower()  # Column 7 (index 6) is Acuity Registration
            reminder_email = (row[8] or "").strip()  # Column 9 (index 8) is Reminder Email
            
            if not email:
                continue
            
            # Check if this row needs a reminder
            if acuity_reg != "no" or reminder_email:
                # Skip if Acuity is not "No" or Reminder already populated
                continue
            
            # Parse the date and check if it's old enough
            try:
                # Try to parse date in mm/dd/yyyy format
                date_obj = datetime.strptime(date_str, "%m/%d/%Y")
                if date_obj <= cutoff_date:
                    # Student is old enough, populate reminder date
                    ws.update_cell(row_idx, 9, today_str, value_input_option="RAW")
                    updated_count += 1
                    print(f"[REMINDER] Populated reminder for {email} (added {date_str})", flush=True)
            except ValueError:
                # Skip rows with invalid date format
                continue
        
        print(f"[REMINDER] Updated {updated_count} students with reminder dates", flush=True)
        return updated_count
    
    except Exception as e:
        print(f"[GSHEET] Error checking reminders: {e!r}", flush=True)
        return 0

def run_demo(name, date, headless: bool = False):
    # remove previous screenshots in shots/
    clean_shots_folder()

    if not SAVED_LOGIN.exists():
        raise RuntimeError(f"aha_auth.json missing at: {SAVED_LOGIN}. Run setup_login.py first.")

    # Optional: refresh extracted_data.txt from Inbox
    if EMAIL_REFRESH_ON_START:
        ran, had_new = refresh_extracted_data_file_from_email(debug=True)
        if ran:
            print(f"[EMAIL REFRESH] ran=True, new_email_processed={had_new}", flush=True)

    # Resolve the next unprocessed instructor/date before launching the browser
 #   job = pull_next_unprocessed_instructor_and_date_from_extracted_data_file(debug=True)
 #   if not job:
 #       fatal(
 #           f"No new incoming emails to process. No unprocessed valid entry found in {EXTRACTED_DATA_FILE}.\n"
 #           "- If you run the email watcher separately: wait for a new unread email, then run again.\n"
 #           "- If you want this script to pull the inbox once at startup: set EMAIL_REFRESH_ON_START=1."
 #       )

    instructor_name = name
    target_date = normalize_to_mmddyyyy(date)

    print(f"[RUN CONFIG] Using extracted line) -> "f"instructor={instructor_name!r}, date={target_date!r}",flush=True,)


    # Save what we used (debug)
    """
    try:
        (screenshot_folder / "email_instructor_date.txt").write_text(
            f"instructor={instructor_name}\n"
            f"date={target_date}\n"
            f"subject={subject}\n"
            f"line_index={line_index}\n"
            f"raw_line={raw_line!r}\n",
            encoding="utf-8",
        )
    except Exception:
        pass
"""
    with sync_playwright() as p:

        launch_args = {"channel": "msedge", "headless": headless,}

        if not headless:
            launch_args["args"] = ["--start-maximized"]
        browser = p.chromium.launch(**launch_args)

        context = browser.new_context(
            storage_state=str(SAVED_LOGIN),
            viewport={"width": 1920, "height": 1080}
        )

        page = context.new_page()
        page.set_default_timeout(PW_TIMEOUT_MS)
        page.set_default_navigation_timeout(PW_TIMEOUT_MS)

        processed_ok = False
        current_step = "startup"
        def set_step(s: str):
            nonlocal current_step
            current_step = s

        try:
            set_step("open_training_site")
            page.goto(TRAINING_SITE_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)

            set_step("select_organization")
            select_organization(page, ORG_NAME)
            page.wait_for_timeout(1200)

            set_step("select_instructor")
            select_instructor(page, name_text=instructor_name)
            page.wait_for_timeout(800)

            set_step("open_date_picker")
            open_date_range_picker(page)

            # Optional TEST override: widen the date filter to multiple courses at the same-date page
            # In production, leave TEST_START_DATE/TEST_END_DATE unset so the script uses the email date only.
            test_start_raw = os.getenv("TEST_START_DATE", "").strip()
            test_end_raw = os.getenv("TEST_END_DATE", "").strip()

            set_step("select_date")
            if test_start_raw or test_end_raw:
                start_date = normalize_to_mmddyyyy(test_start_raw or target_date)
                end_date = normalize_to_mmddyyyy(test_end_raw or start_date)
                date_label = f"{start_date}..{end_date}" if start_date != end_date else start_date
                print(f"[TEST DATE OVERRIDE] Using date range {date_label} (instead of email date {target_date}).", flush=True)
                click_date_range(page, start_date, end_date)
            else:
                date_label = target_date
                # Start date = End date = the email date
                click_specific_date_twice(page, target_date)

            page.wait_for_timeout(1000)

            # Process every course on this results page (handles multiple courses for same instructor/date).
            set_step("process_all_courses")
            stats = process_all_courses_on_results_page(page, instructor_name=instructor_name, date_label=date_label)

            if stats["courses_found"] == 0:
                set_step("no_courses_found")
                print("[INFO] No courses found for the given filters (instructor/date).", flush=True)
                # Decide whether to advance last_processed_index.txt
                processed_ok = bool(ADVANCE_INDEX_ON_NO_COURSES)
            else:
                processed_ok = True

                # If there are courses but no pending requests in ALL of them, record a small debug
                if stats["courses_with_pending"] == 0:
                    set_step("no_pending_requests")
                    print("[INFO] Courses found, but no pending requests in any course. Skipping student extraction + Google Sheet update.", flush=True)
                    try:
                        (screenshot_folder / "no_pending_requests.txt").write_text(
                            f"instructor={instructor_name}\n"
                            f"date={date_label}\n"
                            f"subject={subject}\n"
                            f"line_index={line_index}\n",
                            encoding="utf-8",
                        )
                    except Exception:
                        pass

            if PAUSE_AT_END and not headless:
                print("\nBrowser will stay open.")
                if sys.stdin and sys.stdin.isatty():
                    input("Press ENTER to close the browser :D ")

        except Exception as e:
            # Only capture screenshots when something goes wrong
            save_error_screenshot(page, current_step)
            print(f"[ERROR] Failed at step={current_step!r}: {e}", flush=True)
            raise
        finally:
            # Write the index first so browser close
            if processed_ok:
                #_write_last_processed_index(line_index)
                print("Processed Properly...")

            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip() in {"1", "true", "True", "YES", "yes"}

"""
def main():
    Entry point.
    
    Env flags:
    - HEADLESS=1
    - PAUSE_AT_END=0
    
    headless = _env_flag("HEADLESS", "0")
    print(                                                               
        "Starting run_automation... "
        f"EMAIL_REFRESH_ON_START={int(EMAIL_REFRESH_ON_START)} "
        f"FORCE_RUN={int(FORCE_RUN)} "
        f"HEADLESS={int(headless)}",
        flush=True,
    )
    run_demo(headless=headless)


if __name__ == "__main__":
    main()

"""
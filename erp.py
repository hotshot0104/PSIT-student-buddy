"""
erp.py — PSIT ERP Scraper Core
Handles all authentication and data fetching from the PSIT ERP portal.
"""
import os
import re
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────
# CONFIGURATION — fill via .env file
# ─────────────────────────────────────────
ERP_USER     = os.getenv("ERP_USER", "").strip()
ERP_PASSWORD = os.getenv("ERP_PASSWORD", "").strip()

# Timezone: Indian Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

BASE_URL       = "https://erp.psit.ac.in"
TT_URL         = f"{BASE_URL}/Student/MyTimeTable"
ATTENDANCE_URL = f"{BASE_URL}/Student/MyAttendanceDetail"

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# ─────────────────────────────────────────
# Session Cache (health-check throttled to every 30 min)
# ─────────────────────────────────────────
_cached_session     = None
_session_last_check = None  # datetime of last successful health-check

# Daily timetable cache (fetched once per day)
_classes_cache      = None
_classes_cache_date = None


# ─────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────

def erp_login():
    """Create an authenticated ERP session. Returns (session, error_msg)."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120 Safari/537.36"
        ),
    })

    try:
        r = session.get(BASE_URL, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        return None, f"❌ Could not reach ERP: {e}"

    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form")
    if form and form.get("action"):
        action = form["action"]
        if action.startswith("/"):
            post_url = BASE_URL + action
        elif action.startswith("http"):
            post_url = action
        else:
            post_url = BASE_URL + "/" + action
    else:
        post_url = BASE_URL

    payload = {"username": ERP_USER, "password": ERP_PASSWORD}
    for hidden in soup.find_all("input", {"type": "hidden"}):
        fname = hidden.get("name")
        fval  = hidden.get("value", "")
        if fname:
            payload[fname] = fval

    try:
        login_resp = session.post(post_url, data=payload, timeout=15, allow_redirects=True)
    except requests.RequestException as e:
        return None, f"❌ Login request failed: {e}"

    final_url  = login_resp.url.lower()
    body       = login_resp.text
    body_lower = body.lower()

    logged_in = (
        "logout" in body_lower
        or "/logout" in body_lower
        or "dashboard" in final_url
        or ("student" in final_url and "login" not in final_url)
    )
    if "invalid" in body_lower or "incorrect" in body_lower or "failed" in body_lower:
        logged_in = False

    if logged_in:
        print(f"SUCCESS: ERP login succeeded -> {login_resp.url}")
        return session, None

    print(f"ERROR: Login failed. Final URL: {login_resp.url}")
    return None, "Login failed. Check ERP_USER and ERP_PASSWORD in your .env file."


def get_session():
    """Return a valid ERP session, re-validating at most once every 30 minutes."""
    global _cached_session, _session_last_check

    # --- MOCK MODE INTERCEPT ---
    if os.getenv("MOCK_MODE", "False").lower() == "true":
        return "mock_session", None

    now = datetime.now(tz=IST)

    if _cached_session is not None and _session_last_check is not None:
        if (now - _session_last_check).total_seconds() < 1800:
            return _cached_session, None

    if _cached_session is not None:
        try:
            check = _cached_session.get(f"{BASE_URL}/Student/", timeout=10)
            if "logout" in check.text.lower():
                _session_last_check = now
                return _cached_session, None
        except Exception:
            pass

    _cached_session, err = erp_login()
    if not err:
        _session_last_check = now
    return _cached_session, err


# ─────────────────────────────────────────
# TIME TABLE
# ─────────────────────────────────────────

def parse_time(time_str):
    """Parse a time label string (e.g. '09:25 AM') into a datetime in IST."""
    if not time_str:
        return None
    time_match = re.search(r'(\d{1,2})[:.](\\d{2})', time_str)
    if not time_match:
        # Try again without escaped backslash
        time_match = re.search(r'(\d{1,2})[:.](\d{2})', time_str)
    if not time_match:
        return None

    hour   = int(time_match.group(1))
    minute = int(time_match.group(2))

    ampm_match = re.search(r'(AM|PM)', time_str, re.IGNORECASE)
    ampm = ampm_match.group(1).upper() if ampm_match else None

    if ampm:
        if ampm == "PM" and hour < 12:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0
    else:
        # Guess based on PSIT typical class hours (8 AM–7 PM)
        if 1 <= hour <= 7:
            hour += 12

    try:
        now = datetime.now(tz=IST)
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError:
        return None


def get_classes_for_day(session, day_offset=0):
    """Fetch timetable and return classes for the given day offset (0=today, 1=tomorrow, etc.)."""
    # --- MOCK MODE INTERCEPT ---
    if os.getenv("MOCK_MODE", "False").lower() == "true":
        target_idx = (datetime.now(tz=IST).weekday() + day_offset) % 7
        day_name = DAY_NAMES[target_idx]
        if day_name == "Sunday":
            return day_name, []
            
        now_dt = datetime.now(tz=IST)
        # Schedule the next mock class exactly 10 minutes in the future so the 15-min reminder triggers!
        reminder_test_time = now_dt + timedelta(minutes=10)
        time_label = reminder_test_time.strftime("%I:%M %p")
        
        return day_name, [
            {
                "time_label": time_label,
                "subject": "Data Structures & Algorithms (Mock)",
                "start_time": reminder_test_time.replace(second=0, microsecond=0)
            },
            {
                "time_label": (reminder_test_time + timedelta(hours=1)).strftime("%I:%M %p"),
                "subject": "Computer Networks (Mock)",
                "start_time": (reminder_test_time + timedelta(hours=1)).replace(second=0, microsecond=0)
            },
            {
                "time_label": (reminder_test_time + timedelta(hours=2)).strftime("%I:%M %p"),
                "subject": "Operating Systems (Mock)",
                "start_time": (reminder_test_time + timedelta(hours=2)).replace(second=0, microsecond=0)
            }
        ]

    try:
        tt_resp = session.get(TT_URL, timeout=15)
        tt_resp.raise_for_status()
    except requests.RequestException as e:
        return "Unknown", f"⚠️ Could not fetch timetable: {e}"

    tt_soup  = BeautifulSoup(tt_resp.text, "html.parser")
    day_idx  = (datetime.now(tz=IST).weekday() + day_offset) % 7
    day_name = DAY_NAMES[day_idx]

    table = tt_soup.find("table")
    if not table:
        return day_name, "⚠️ Couldn't find timetable. ERP layout may have changed."

    rows = table.find_all("tr")
    if not rows:
        return day_name, "⚠️ Timetable table is empty."

    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]

    # Try column-based layout (days as columns)
    day_col = None
    for i, h in enumerate(headers):
        if day_name.lower() in h.lower():
            day_col = i
            break

    if day_col is not None:
        classes = []
        for row in rows[1:]:
            cols = row.find_all(["td", "th"])
            if day_col >= len(cols):
                continue
            subject    = cols[day_col].get_text(strip=True)
            time_label = cols[0].get_text(strip=True) if cols else f"Slot {len(classes)+1}"
            if subject and subject not in ["-", "–", "—", "", "N/A"]:
                classes.append({
                    "time_label": time_label,
                    "subject":    subject,
                    "start_time": parse_time(time_label),
                })
        return day_name, classes

    # Try row-based layout (days as rows)
    classes = []
    for row in rows[1:]:
        cols      = row.find_all(["td", "th"])
        row_label = cols[0].get_text(strip=True) if cols else ""
        if day_name.lower() in row_label.lower():
            for i, col in enumerate(cols[1:], start=1):
                subject = col.get_text(strip=True)
                if subject and subject not in ["-", "–", "—", "", "N/A"]:
                    time_label = headers[i] if i < len(headers) else f"Slot {i}"
                    classes.append({
                        "time_label": time_label,
                        "subject":    subject,
                        "start_time": parse_time(time_label),
                    })
            return day_name, classes

    return day_name, f"⚠️ Could not find '{day_name}' in timetable."


def get_today_classes(session):
    return get_classes_for_day(session, day_offset=0)


def get_week_timetable(session):
    """Fetch timetable for all 7 days. Returns list of (day_name, classes) tuples."""
    results = []
    for offset in range(7):
        results.append(get_classes_for_day(session, day_offset=offset))
    return results


def get_cached_today_classes(session):
    """Return today's classes from cache; only hits ERP once per calendar day."""
    global _classes_cache, _classes_cache_date

    today = datetime.now(tz=IST).date()
    if _classes_cache_date == today and _classes_cache is not None:
        return _classes_cache

    _, classes = get_today_classes(session)
    if isinstance(classes, list):
        _classes_cache      = classes
        _classes_cache_date = today
        print(f"[{datetime.now(tz=IST).strftime('%H:%M')}] Timetable cached for {today} ({len(classes)} classes)")
    return classes


def format_classes(classes):
    return [f"🕐 {c['time_label']} — {c['subject']}" for c in classes]


# ─────────────────────────────────────────
# ATTENDANCE
# ─────────────────────────────────────────

def get_attendance(session):
    """
    Fetch overall attendance and subject-wise breakdown.
    Returns a dict or an error string.
    """
    # --- MOCK MODE INTERCEPT ---
    if os.getenv("MOCK_MODE", "False").lower() == "true":
        return {
            "present": 75,
            "total": 105,
            "percent": "71.43%",
            "percent_val": 71.43,
            "subjects": [
                { "subject": "Data Structures & Algorithms (Mock)", "percent": "85.7%", "present": "18", "total": "21" },
                { "subject": "Computer Networks (Mock)",            "percent": "76.2%", "present": "16", "total": "21" },
                { "subject": "Operating Systems (Mock)",            "percent": "61.9%", "present": "13", "total": "21" },
                { "subject": "Database Management System (Mock)",   "percent": "80.0%", "present": "20", "total": "25" },
                { "subject": "Software Engineering (Mock)",         "percent": "50.0%", "present": "8",  "total": "16" }
            ]
        }

    try:
        resp = session.get(ATTENDANCE_URL, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"⚠️ Could not fetch attendance: {e}"

    soup      = BeautifulSoup(resp.text, "html.parser")
    full_text = soup.get_text(" ", strip=True)
    text_low  = full_text.lower()

    # --- Overall percentage ---
    percent_val = None
    for pattern in [
        r'attendance\s*%\s*with\s*pf\s*[:\-]\s*([\d.]+)',
        r'attendance\s*%\s*without\s*pf\s*[:\-]\s*([\d.]+)',
        r'overall\s+attendance\s*[:\-]\s*([\d.]+)\s*%',
    ]:
        m = re.search(pattern, text_low)
        if m:
            percent_val = float(m.group(1))
            break

    if percent_val is None:
        for m in re.finditer(r'([\d]{2,3}\.?\d*)\s*%', full_text):
            idx         = m.start()
            surrounding = full_text[max(0, idx - 120):idx + 40].lower()
            if "attendance" in surrounding:
                percent_val = float(m.group(1))
                break

    if percent_val is None:
        return "⚠️ Couldn't find attendance percentage. ERP layout may have changed."

    # --- Present / Total ---
    present = total = None
    m_total = re.search(r'total\s+lecture\s*[:\-]?\s*(\d+)', text_low)
    if m_total:
        total   = int(m_total.group(1))
        present = round(total * (percent_val / 100.0))
    else:
        m_pt = re.search(r'present\s*[:\-]?\s*(\d+)\s*[/\\|]\s*(\d+)', text_low)
        if m_pt:
            present = int(m_pt.group(1))
            total   = int(m_pt.group(2))

    # --- Subject-wise breakdown (from table) ---
    subjects = []
    table = soup.find("table")
    if table:
        rows    = table.find_all("tr")
        headers = []
        if rows:
            headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]

        sub_col = pct_col = pres_col = tot_col = None
        for i, h in enumerate(headers):
            if "subject" in h or "course" in h:
                sub_col = i
            elif "percent" in h or "%" in h:
                pct_col = i
            elif "present" in h:
                pres_col = i
            elif "total" in h:
                tot_col = i

        if sub_col is not None:
            for row in rows[1:]:
                cols = row.find_all(["td", "th"])
                if not cols or sub_col >= len(cols):
                    continue
                subj = cols[sub_col].get_text(strip=True)
                if not subj:
                    continue
                s_pct  = cols[pct_col].get_text(strip=True)  if pct_col  and pct_col  < len(cols) else None
                s_pres = cols[pres_col].get_text(strip=True) if pres_col and pres_col < len(cols) else None
                s_tot  = cols[tot_col].get_text(strip=True)  if tot_col  and tot_col  < len(cols) else None
                subjects.append({
                    "subject": subj,
                    "percent": s_pct,
                    "present": s_pres,
                    "total":   s_tot,
                })

    return {
        "present":     present,
        "total":       total,
        "percent":     f"{percent_val:.2f}%",
        "percent_val": percent_val,
        "subjects":    subjects,
    }


def get_daily_attendance(session):
    """
    Attempt to fetch today's per-lecture attendance (present/absent per slot).
    Returns a list of dicts: [{"subject": ..., "status": "Present"/"Absent", "time": ...}]
    or None if the ERP does not expose this data.
    """
    # --- MOCK MODE INTERCEPT ---
    if os.getenv("MOCK_MODE", "False").lower() == "true":
        return [
            {"subject": "Data Structures & Algorithms (Mock)", "status": "Present", "time": "09:25 AM"},
            {"subject": "Computer Networks (Mock)",            "status": "Present", "time": "10:25 AM"},
            {"subject": "Operating Systems (Mock)",            "status": "Absent",  "time": "01:25 PM"}
        ]

    candidate_urls = [
        f"{BASE_URL}/Student/MyDailyAttendance",
        f"{BASE_URL}/Student/MyAttendance",
        f"{BASE_URL}/Student/TodayAttendance",
    ]

    for url in candidate_urls:
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                continue
            soup     = BeautifulSoup(resp.text, "html.parser")
            text_low = resp.text.lower()

            # Page must be relevant to today's attendance
            today_str = datetime.now(tz=IST).strftime("%d/%m/%Y")
            if today_str not in resp.text and "today" not in text_low:
                continue

            table = soup.find("table")
            if not table:
                continue

            rows    = table.find_all("tr")
            headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])] if rows else []

            sub_col = status_col = time_col = None
            for i, h in enumerate(headers):
                if "subject" in h or "course" in h:
                    sub_col = i
                elif "status" in h or "attend" in h:
                    status_col = i
                elif "time" in h or "slot" in h:
                    time_col = i

            if sub_col is None or status_col is None:
                continue

            records = []
            for row in rows[1:]:
                cols = row.find_all(["td", "th"])
                if sub_col >= len(cols) or status_col >= len(cols):
                    continue
                subj   = cols[sub_col].get_text(strip=True)
                status = cols[status_col].get_text(strip=True)
                t_val  = cols[time_col].get_text(strip=True) if time_col and time_col < len(cols) else ""
                if subj:
                    records.append({"subject": subj, "status": status, "time": t_val})

            if records:
                return records
        except Exception:
            continue

    return None  # Feature not available on this ERP instance


# ─────────────────────────────────────────
# BUNK BUDGET
# ─────────────────────────────────────────

def calc_bunk_budget(attendance):
    """Calculate how many classes can be bunked or how many are needed to reach 75%."""
    if not isinstance(attendance, dict):
        return None
    try:
        present = int(attendance["present"])
        total   = int(attendance["total"])
    except (TypeError, ValueError, KeyError):
        return None

    can_bunk    = max(0, int((present / 0.75) - total))
    need_attend = 0
    if total > 0 and present / total < 0.75:
        need_attend = max(0, int((0.75 * total - present) / 0.25) + 1)

    return {
        "can_bunk":    can_bunk,
        "need_attend": need_attend,
        "present":     present,
        "total":       total,
    }


def attendance_emoji(percent_val):
    try:
        pct = float(str(percent_val).replace("%", ""))
        if pct >= 75:
            return "✅"
        elif pct >= 65:
            return "⚠️"
        else:
            return "🚨"
    except (ValueError, AttributeError):
        return "❓"

"""Simple appointment scheduling for the booking page.

Parses the practice's free-text hours (e.g. "Mon-Fri 9am-5pm") into a
day/time window, generates 20-minute slots for the next 3 days, and
hides slots already taken by an existing visit's appointment_time.
"""

import re
from datetime import datetime, timedelta

from app.storage import get_practice, list_visits

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SLOT_MINUTES = 20
DEFAULT_DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri"}
DEFAULT_START_HOUR = 9
DEFAULT_END_HOUR = 17


def _parse_time(token: str):
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", token.strip(), re.IGNORECASE)
    if not m:
        return None
    hour = int(m.group(1)) % 12
    if m.group(3).lower() == "pm":
        hour += 12
    return hour


def parse_hours(hours_str: str):
    days, start_hour, end_hour = DEFAULT_DAYS, DEFAULT_START_HOUR, DEFAULT_END_HOUR
    day_match = re.search(r"\b(\w{3})\w*\s*-\s*(\w{3})\w*", hours_str or "")
    if day_match:
        d1, d2 = day_match.group(1).title(), day_match.group(2).title()
        if d1 in DAY_NAMES and d2 in DAY_NAMES:
            i1, i2 = DAY_NAMES.index(d1), DAY_NAMES.index(d2)
            days = set(DAY_NAMES[i1 : i2 + 1]) if i1 <= i2 else set(DAY_NAMES)
    time_match = re.search(
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))", hours_str or "", re.IGNORECASE
    )
    if time_match:
        s, e = _parse_time(time_match.group(1)), _parse_time(time_match.group(2))
        if s is not None and e is not None:
            start_hour, end_hour = s, e
    return days, start_hour, end_hour


def _booked_times() -> set:
    return {v["appointment_time"] for v in list_visits() if v.get("appointment_time")}


def available_slots() -> list:
    practice = get_practice()
    days, start_hour, end_hour = parse_hours(practice.get("hours", ""))
    booked = _booked_times()
    now = datetime.now()
    slots = []
    for day_offset in range(3):
        day = now + timedelta(days=day_offset)
        if DAY_NAMES[day.weekday()] not in days:
            continue
        t = day.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        while t < day_end:
            if t > now and t.isoformat() not in booked:
                slots.append(
                    {
                        "iso": t.isoformat(),
                        "date_label": t.strftime("%A, %B %-d"),
                        "time_label": t.strftime("%-I:%M %p"),
                    }
                )
            t += timedelta(minutes=SLOT_MINUTES)
    return slots

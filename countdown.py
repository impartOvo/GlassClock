"""The two daily countdowns, calculated in Beijing time."""

from datetime import datetime, time, timedelta, timezone
from math import ceil

BEIJING = timezone(timedelta(hours=8))


def beijing_now():
    return datetime.now(BEIJING)


def format_remaining(delta):
    seconds = max(0, ceil(delta.total_seconds()))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def daily_countdowns(now):
    """Return (next target, previous target, next 18:00) for an aware datetime.

    Display the reached target as zero for the whole first second so it is
    visible before switching to the next target.
    """
    now = now.astimezone(BEIJING)
    today = now.date()
    noon = datetime.combine(today, time(12), BEIJING)
    evening = datetime.combine(today, time(18), BEIJING)
    day = timedelta(days=1)

    if now < noon + timedelta(seconds=1):
        target, previous = noon, evening - day
    elif now < evening + timedelta(seconds=1):
        target, previous = evening, noon
    else:
        target, previous = noon + day, evening

    next_evening = evening if now < evening + timedelta(seconds=1) else evening + day
    return target, previous, next_evening

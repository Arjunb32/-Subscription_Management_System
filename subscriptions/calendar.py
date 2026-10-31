"""The only interval calculator used by subscription lifecycle and billing."""
import calendar
from datetime import date, timedelta


def add_interval(value, interval):
    if interval == "daily":
        return value + timedelta(days=1)
    if interval == "weekly":
        return value + timedelta(weeks=1)
    if interval == "monthly":
        year, month = value.year + value.month // 12, value.month % 12 + 1
    elif interval == "yearly":
        year, month = value.year + 1, value.month
    else:
        raise ValueError(f"Unsupported billing interval: {interval!r}")
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))

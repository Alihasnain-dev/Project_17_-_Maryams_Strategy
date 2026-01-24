"""US Stock Market Calendar.

Defines market holidays and trading day validation.
"""

from __future__ import annotations

from datetime import date
from typing import Set

# US Stock Market Holidays (NYSE/NASDAQ)
# Source: https://www.nyse.com/markets/hours-calendars
#
# Note: This covers the date range 2024-2025. Extend as needed.
US_MARKET_HOLIDAYS: Set[date] = {
    # 2024 Holidays
    date(2024, 1, 1),    # New Year's Day
    date(2024, 1, 15),   # MLK Day
    date(2024, 2, 19),   # Presidents Day
    date(2024, 3, 29),   # Good Friday
    date(2024, 5, 27),   # Memorial Day
    date(2024, 6, 19),   # Juneteenth
    date(2024, 7, 4),    # Independence Day
    date(2024, 9, 2),    # Labor Day
    date(2024, 11, 28),  # Thanksgiving
    date(2024, 12, 25),  # Christmas

    # 2025 Holidays
    date(2025, 1, 1),    # New Year's Day
    date(2025, 1, 20),   # MLK Day
    date(2025, 2, 17),   # Presidents Day
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 26),   # Memorial Day
    date(2025, 6, 19),   # Juneteenth
    date(2025, 7, 4),    # Independence Day
    date(2025, 9, 1),    # Labor Day
    date(2025, 11, 27),  # Thanksgiving
    date(2025, 12, 25),  # Christmas

    # 2026 Holidays (for future-proofing)
    date(2026, 1, 1),    # New Year's Day
    date(2026, 1, 19),   # MLK Day
    date(2026, 2, 16),   # Presidents Day
    date(2026, 4, 3),    # Good Friday
    date(2026, 5, 25),   # Memorial Day
    date(2026, 6, 19),   # Juneteenth
    date(2026, 7, 3),    # Independence Day (observed)
    date(2026, 9, 7),    # Labor Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas
}


def is_market_holiday(d: date) -> bool:
    """
    Check if a date is a US stock market holiday.

    Args:
        d: The date to check.

    Returns:
        True if the market is closed for a holiday, False otherwise.
    """
    return d in US_MARKET_HOLIDAYS


def is_weekend(d: date) -> bool:
    """
    Check if a date is a weekend.

    Args:
        d: The date to check.

    Returns:
        True if Saturday (5) or Sunday (6), False otherwise.
    """
    return d.weekday() >= 5


def is_trading_day(d: date) -> bool:
    """
    Check if a date is a valid trading day.

    A trading day is a weekday that is not a market holiday.

    Args:
        d: The date to check.

    Returns:
        True if the market is open, False otherwise.
    """
    return not is_weekend(d) and not is_market_holiday(d)


def get_trading_days(start: date, end: date) -> list[date]:
    """
    Get all trading days in a date range.

    Args:
        start: Start date (inclusive).
        end: End date (inclusive).

    Returns:
        List of dates where the market is open.
    """
    from datetime import timedelta

    days = []
    current = start
    while current <= end:
        if is_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days

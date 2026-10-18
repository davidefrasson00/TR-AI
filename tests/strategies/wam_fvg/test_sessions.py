"""
Unit tests for Session and Timezone Primitive.
Includes explicit validation of Daylight Saving Time (DST) disalignment weeks.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pytest

from src.strategies.wam_fvg.primitives.sessions import (
    SessionManager,
    US_OPEN_TEMPLATE,
    FRANKFURT_OPEN_TEMPLATE,
    UTC,
    NY_TZ,
)


def test_us_open_session_windows():
    mgr = SessionManager(US_OPEN_TEMPLATE)

    # 1. During standard time (e.g. 2026-04-15 12:00 UTC = 08:00 ET -> in Range Window 06:30-09:30)
    utc_range_bar = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)
    assert mgr.is_in_range_window(utc_range_bar) is True
    assert mgr.is_in_manipulation_window(utc_range_bar) is False
    assert mgr.is_before_entry_deadline(utc_range_bar) is True

    # 2. Manipulation window (09:45 ET = 13:45 UTC)
    utc_manip_bar = datetime(2026, 4, 15, 13, 45, tzinfo=UTC)
    assert mgr.is_in_range_window(utc_manip_bar) is False
    assert mgr.is_in_manipulation_window(utc_manip_bar) is True
    assert mgr.is_before_entry_deadline(utc_manip_bar) is True

    # 3. After deadline (12:00 ET = 16:00 UTC)
    utc_after_deadline = datetime(2026, 4, 15, 16, 0, tzinfo=UTC)
    assert mgr.is_before_entry_deadline(utc_after_deadline) is False


def test_frankfurt_open_session_windows():
    mgr = SessionManager(FRANKFURT_OPEN_TEMPLATE)

    # 07:30 Berlin = 05:30 UTC -> inside Frankfurt Range Window (07:00-09:00)
    utc_range_bar = datetime(2026, 5, 20, 5, 30, tzinfo=UTC)
    assert mgr.is_in_range_window(utc_range_bar) is True
    assert mgr.is_in_manipulation_window(utc_range_bar) is False

    # 09:15 Berlin = 07:15 UTC -> inside Manipulation Window (09:00-10:30)
    utc_manip_bar = datetime(2026, 5, 20, 7, 15, tzinfo=UTC)
    assert mgr.is_in_manipulation_window(utc_manip_bar) is True


def test_dst_disalignment_week_october_2026():
    """
    CRITICAL TEST: In autumn 2026, Europe changes to standard time on October 25, 2026,
    while the US changes on November 1, 2026.
    During this week (e.g. 2026-10-27), 09:30 ET opens at 14:30 Italian time, NOT 15:30!
    """
    # 2026-10-27: Europe is on CET (UTC+1), US is still on EDT (UTC-4)
    # Difference is 5 hours, so 09:30 ET is 14:30 Rome time!
    dt_dst_disaligned = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
    h, m = SessionManager.get_us_open_italian_time(dt_dst_disaligned)
    assert h == 14
    assert m == 30

    # 2026-11-10: Both US and Europe are in Standard Time (EDT -> EST, difference is 6 hours)
    # 09:30 ET is 15:30 Rome time!
    dt_normal = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    h_norm, m_norm = SessionManager.get_us_open_italian_time(dt_normal)
    assert h_norm == 15
    assert m_norm == 30

"""
Session and Timezone Management for WAM-FVG Strategy.

Handles timezone conversions (America/New_York, Europe/Berlin, UTC),
session windows (Range, Manipulation, Entry Deadline), and Daylight Saving Time (DST)
disalignments between the US and Europe.
"""

from dataclasses import dataclass
from datetime import datetime, time, date
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")
NY_TZ = ZoneInfo("America/New_York")
BERLIN_TZ = ZoneInfo("Europe/Berlin")
TOKYO_TZ = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True)
class SessionWindow:
    """Represents a time window within a trading session."""
    start_time: time
    end_time: time

    def contains(self, t: time) -> bool:
        """Check if time t falls within [start_time, end_time]."""
        if self.start_time <= self.end_time:
            return self.start_time <= t <= self.end_time
        # Overnight window (e.g. Asian session across midnight)
        return t >= self.start_time or t <= self.end_time


@dataclass
class SessionTemplate:
    """Configuration template for an intraday session."""
    name: str
    tz_name: str
    range_window: SessionWindow
    manipulation_window: SessionWindow
    entry_deadline: time

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)


# Built-in Standard Templates
US_OPEN_TEMPLATE = SessionTemplate(
    name="us_open",
    tz_name="America/New_York",
    range_window=SessionWindow(start_time=time(6, 30), end_time=time(9, 30)),
    manipulation_window=SessionWindow(start_time=time(9, 30), end_time=time(11, 0)),
    entry_deadline=time(11, 30),
)

FRANKFURT_OPEN_TEMPLATE = SessionTemplate(
    name="frankfurt_open",
    tz_name="Europe/Berlin",
    range_window=SessionWindow(start_time=time(7, 0), end_time=time(9, 0)),
    manipulation_window=SessionWindow(start_time=time(9, 0), end_time=time(10, 30)),
    entry_deadline=time(11, 0),
)

ASIAN_SESSION_TEMPLATE = SessionTemplate(
    name="asian_session",
    tz_name="Asia/Tokyo",
    range_window=SessionWindow(start_time=time(9, 0), end_time=time(15, 0)),
    manipulation_window=SessionWindow(start_time=time(15, 0), end_time=time(18, 0)),
    entry_deadline=time(18, 30),
)


class SessionManager:
    """
    Evaluates whether a given UTC bar timestamp falls within
    specific operational windows for an instrument's session.
    """

    def __init__(self, template: SessionTemplate):
        self.template = template

    def to_local_time(self, utc_dt: datetime) -> datetime:
        """Converts UTC datetime to local session datetime."""
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=UTC)
        return utc_dt.astimezone(self.template.tz)

    def is_in_range_window(self, utc_dt: datetime) -> bool:
        """Checks if timestamp is inside the Range Accumulation window."""
        local_time = self.to_local_time(utc_dt).time()
        return self.template.range_window.contains(local_time)

    def is_in_manipulation_window(self, utc_dt: datetime) -> bool:
        """Checks if timestamp is inside the Manipulation / Sweep window."""
        local_time = self.to_local_time(utc_dt).time()
        return self.template.manipulation_window.contains(local_time)

    def is_before_entry_deadline(self, utc_dt: datetime) -> bool:
        """Checks if orders are still allowed before session deadline."""
        local_time = self.to_local_time(utc_dt).time()
        return local_time <= self.template.entry_deadline

    def get_session_date(self, utc_dt: datetime) -> date:
        """Returns the local calendar date for the session."""
        return self.to_local_time(utc_dt).date()

    @staticmethod
    def get_us_open_italian_time(utc_dt: datetime) -> Tuple[int, int]:
        """
        Calculates the Italian (Europe/Rome) local time of the 09:30 ET US Open
        for a given day, correctly accounting for DST disalignment weeks.
        """
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=UTC)
        us_open_local = datetime(
            utc_dt.year, utc_dt.month, utc_dt.day, 9, 30, tzinfo=NY_TZ
        )
        italian_time = us_open_local.astimezone(ZoneInfo("Europe/Rome"))
        return italian_time.hour, italian_time.minute

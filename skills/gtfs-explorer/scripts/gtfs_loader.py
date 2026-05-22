"""Minimal GTFS loader + service-day expansion helpers.

Usage:
    from gtfs_loader import load_gtfs, time_to_seconds, service_ids_active_on

    feed = load_gtfs("path/to/feed.zip")  # dict of DataFrames
    active = service_ids_active_on(feed, "20250315")  # set[str]
"""

from __future__ import annotations

import datetime as _dt
import io
import os
import zipfile
from typing import Dict, Iterable, Set

import pandas as pd

# All ID columns in the spec — read as strings to avoid silent type breakage on merges.
_ID_COLS = {
    "agency_id",
    "stop_id",
    "route_id",
    "trip_id",
    "service_id",
    "shape_id",
    "block_id",
    "zone_id",
    "parent_station",
    "fare_id",
    "pathway_id",
    "level_id",
    "from_stop_id",
    "to_stop_id",
    "from_route_id",
    "to_route_id",
    "from_trip_id",
    "to_trip_id",
    "network_id",
    "area_id",
    "location_group_id",
    "fare_product_id",
    "fare_media_id",
    "rider_category_id",
    "from_leg_group_id",
    "to_leg_group_id",
    "leg_group_id",
    "from_area_id",
    "to_area_id",
    "timeframe_group_id",
    "from_timeframe_group_id",
    "to_timeframe_group_id",
    "booking_rule_id",
    "pickup_booking_rule_id",
    "drop_off_booking_rule_id",
    "attribution_id",
    "record_id",
    "record_sub_id",
    # Date columns — strings, not ints (preserves YYYYMMDD ordering, avoids type drift).
    "date",
    "start_date",
    "end_date",
    "feed_start_date",
    "feed_end_date",
    # Time-of-day columns — strings, because values can exceed 24:00:00.
    "arrival_time",
    "departure_time",
    "start_time",
    "end_time",
}


def load_gtfs(path: str) -> Dict[str, pd.DataFrame]:
    """Load a GTFS feed (zip file or directory) into a dict of DataFrames.

    Keys are filenames without `.txt` (e.g. "stops", "stop_times"). ID, date,
    and time-of-day columns are read as strings; everything else uses pandas'
    inference. Missing files are simply absent from the dict — callers should
    check with `"calendar" in feed`, etc.

    Both flat zips and zips with all .txt files nested in a single subdirectory
    (some agencies ship feeds that way) are handled — the basename of each .txt
    becomes the dict key regardless of zip layout.
    """
    feed: Dict[str, pd.DataFrame] = {}

    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            for member in z.namelist():
                base = os.path.basename(member)
                if base.endswith(".txt") and base != "":
                    with z.open(member) as f:
                        feed[base[:-4]] = _read_csv(f)
    else:
        for name in os.listdir(path):
            if name.endswith(".txt"):
                with open(os.path.join(path, name), "rb") as f:
                    feed[name[:-4]] = _read_csv(f)
    return feed


def _read_csv(buf) -> pd.DataFrame:
    # Peek header to know which columns need dtype=str.
    raw = buf.read()
    header = raw.split(b"\n", 1)[0].decode("utf-8-sig").strip()
    cols = [c.strip() for c in header.split(",")]
    dtype = {c: str for c in cols if c in _ID_COLS}
    return pd.read_csv(
        io.BytesIO(raw),
        dtype=dtype,
        keep_default_na=False,
        na_values=[""],
        encoding="utf-8-sig",
    )


def time_to_seconds(t: str) -> int | float:
    """Convert a GTFS `HH:MM:SS` (HH may be ≥ 24) to integer seconds.

    Returns NaN for empty/missing values (so the function is safe to .map()
    over a stop_times column with optional times).
    """
    if t is None or t == "" or (isinstance(t, float) and pd.isna(t)):
        return float("nan")
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def seconds_to_time(sec: int) -> str:
    """Inverse of time_to_seconds; allows HH ≥ 24."""
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _normalize_date(d) -> str:
    """Accept 'YYYYMMDD', 'YYYY-MM-DD', or a date/datetime; return 'YYYYMMDD'."""
    if isinstance(d, (_dt.date, _dt.datetime)):
        return d.strftime("%Y%m%d")
    s = str(d).replace("-", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"Bad date: {d!r} (want YYYYMMDD)")
    return s


def service_ids_active_on(feed: Dict[str, pd.DataFrame], date) -> Set[str]:
    """Return the set of service_ids active on a given date.

    Implements the spec's calendar.txt + calendar_dates.txt rules:
      - calendar.txt row contributes its service_id if date falls in
        [start_date, end_date] AND the weekday flag for that date is "1".
      - calendar_dates.txt exception_type=1 ADDS the service for that date.
      - calendar_dates.txt exception_type=2 REMOVES it.
      - If calendar.txt is absent, only the explicit additions in
        calendar_dates apply.
      - If both files are absent or empty, returns an empty set (rather than
        crashing) — the feed defines no scheduled service.
    """
    date = _normalize_date(date)
    weekday = _dt.datetime.strptime(date, "%Y%m%d").weekday()
    weekday_col = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ][weekday]

    active: Set[str] = set()
    if "calendar" in feed and not feed["calendar"].empty:
        cal = feed["calendar"]
        # Weekday columns and exception_type may be parsed as int OR str depending on
        # the feed — pandas infers them. Coerce to str for a uniform comparison.
        weekday_flag = cal[weekday_col].astype(str)
        mask = (
            (cal["start_date"] <= date)
            & (cal["end_date"] >= date)
            & (weekday_flag == "1")
        )
        active.update(cal.loc[mask, "service_id"])

    if "calendar_dates" in feed and not feed["calendar_dates"].empty:
        cd = feed["calendar_dates"]
        today = cd[cd["date"] == date]
        ex = today["exception_type"].astype(str)
        active.update(today.loc[ex == "1", "service_id"])
        active.difference_update(today.loc[ex == "2", "service_id"])

    return active


def trips_active_on(feed: Dict[str, pd.DataFrame], date) -> pd.DataFrame:
    """Return the rows of trips.txt that run on a given date."""
    active = service_ids_active_on(feed, date)
    return feed["trips"][feed["trips"]["service_id"].isin(active)].copy()


def route_id_from_short_name(feed: Dict[str, pd.DataFrame], short_name: str) -> str:
    """Resolve a public-facing line label (e.g. '18') to its route_id.

    Users almost always refer to a line by its `route_short_name` ("line 18",
    "bus 71", "N11"), but the GTFS join keys are `route_id`, and many feeds use
    route_ids that look numeric but DO NOT match the short_name (e.g. STIB has
    route_id=19 for line 18). Always resolve by short_name; never assume the
    route_id equals the line number.
    """
    routes = feed["routes"]
    match = routes[routes["route_short_name"].astype(str) == str(short_name)]
    if match.empty:
        raise LookupError(f"No route with short_name={short_name!r}")
    if len(match) > 1:
        raise LookupError(
            f"Multiple routes with short_name={short_name!r}: {match['route_id'].tolist()}"
        )
    return match.iloc[0]["route_id"]


def pick_representative_date(
    feed: Dict[str, pd.DataFrame], weekday: str = "weekday"
) -> str:
    """Pick a "typical" date from the feed's coverage window.

    The first and last days of a feed often have holiday/launch exceptions
    that reduce service. Pick the mid-feed date with the MOST active
    service_ids of the requested weekday class — that's the best
    approximation of "normal" service.

    weekday: "weekday" (Mon-Fri), "saturday", or "sunday".
    Returns YYYYMMDD string.
    """
    # Establish the feed's coverage window.
    if "feed_info" in feed and not feed["feed_info"].empty:
        row = feed["feed_info"].iloc[0]
        start = row.get("feed_start_date") or feed["calendar"]["start_date"].min()
        end = row.get("feed_end_date") or feed["calendar"]["end_date"].max()
    else:
        start = feed["calendar"]["start_date"].min()
        end = feed["calendar"]["end_date"].max()

    start_d = _dt.datetime.strptime(start, "%Y%m%d").date()
    end_d = _dt.datetime.strptime(end, "%Y%m%d").date()

    if weekday == "weekday":
        wanted = {0, 1, 2, 3, 4}
    elif weekday == "saturday":
        wanted = {5}
    elif weekday == "sunday":
        wanted = {6}
    else:
        raise ValueError("weekday must be 'weekday', 'saturday', or 'sunday'")

    best = None  # (n_active, date)
    d = start_d
    while d <= end_d:
        if d.weekday() in wanted:
            s = d.strftime("%Y%m%d")
            n = len(service_ids_active_on(feed, s))
            if best is None or n > best[0]:
                best = (n, s)
        d += _dt.timedelta(days=1)
    if best is None:
        raise ValueError(f"No {weekday} dates in feed range {start}..{end}")
    return best[1]


def pick_representative_stop(
    feed: Dict[str, pd.DataFrame],
    route_id: str,
    direction_id: str | None = None,
    date: str | None = None,
) -> str:
    """Pick a mid-line stop suitable for measuring headway / frequency.

    A terminus is a bad choice: trips both start and end there, departure
    times cluster oddly, and one direction may have no real departures. A
    mid-line stop served by ALL trips of the route is the right pick.

    Algorithm: among stops served by this route (optionally in this direction
    and date), find ones with the maximum trip count, then prefer the one
    closest to the middle of the trip path (by mean stop_sequence) — that's
    a mid-line stop.
    """
    trips = feed["trips"]
    trips = trips[trips["route_id"] == route_id]
    if direction_id is not None:
        trips = trips[trips["direction_id"].astype(str) == str(direction_id)]
    if date is not None:
        active = service_ids_active_on(feed, date)
        trips = trips[trips["service_id"].isin(active)]
    if trips.empty:
        raise LookupError(
            f"No trips for route_id={route_id} (dir={direction_id}, date={date})"
        )

    st = feed["stop_times"][feed["stop_times"]["trip_id"].isin(trips["trip_id"])]
    if st.empty:
        raise LookupError("No stop_times for those trips")

    # Count trips per stop, and find each stop's mean position along the trip
    # as a fraction of trip length (0=start, 1=end). Drop rows with missing
    # stop_sequence rather than crashing on the cast.
    st = st.copy()
    st = st[st["stop_sequence"].notna() & (st["stop_sequence"].astype(str) != "")]
    st["stop_sequence"] = st["stop_sequence"].astype(int)
    trip_len = st.groupby("trip_id")["stop_sequence"].agg(["min", "max"])
    st = st.merge(trip_len, left_on="trip_id", right_index=True)
    st["pos"] = (st["stop_sequence"] - st["min"]) / (st["max"] - st["min"]).replace(
        0, 1
    )

    agg = (
        st.groupby("stop_id")
        .agg(n_trips=("trip_id", "nunique"), mean_pos=("pos", "mean"))
        .reset_index()
    )
    # Pick stops with the max trip count, then the one closest to mid-line.
    top = agg[agg["n_trips"] == agg["n_trips"].max()].copy()
    top["dist_from_mid"] = (top["mean_pos"] - 0.5).abs()
    return top.sort_values("dist_from_mid").iloc[0]["stop_id"]

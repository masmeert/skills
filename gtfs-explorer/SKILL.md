---
name: gtfs-explorer
description: Load, parse, and query GTFS Schedule feeds (the public-transit static spec — agency.txt, stops.txt, routes.txt, trips.txt, stop_times.txt, calendar.txt, etc., usually shipped as a .zip). Use this skill whenever the user is working with transit schedule data, asks about routes/stops/trips/stop_times/headways/service days from a GTFS feed, points at a transit feed .zip, mentions agencies like MBTA / BART / SNCB / NS / TfL feeds, or wants to answer questions like "what time does route X leave stop Y on a Tuesday" — even if they don't say the word "GTFS" explicitly. Also use it when the user asks to compute frequencies, find next departures, list stops served by a route, expand service_ids to actual calendar dates, or join the spec's CSV tables correctly.
---

# Working with GTFS Schedule feeds

GTFS (General Transit Feed Specification) Schedule is a set of CSV files, normally zipped together, that describes a public-transit network's static schedule. This skill helps you load a feed, answer questions about it, and avoid the spec's well-known footguns.

## When to read what

- For most tasks (load a feed, list routes, find next departures, etc.) the body of this file is enough.
- For a refresher on which files exist, which columns matter, and the foreign-key relationships, read [references/spec.md](references/spec.md). It's a condensed cheat-sheet of the official spec.
- For the spec's most common gotchas (times > 24:00:00, service_id expansion, when calendar.txt is optional, etc.) read [references/gotchas.md](references/gotchas.md). **Skim this before writing any non-trivial code** — most GTFS bugs come from these.

## Recommended approach: pandas

Pandas handles GTFS feeds cleanly: each file is just a CSV, and the joins you need (trips ↔ stop_times ↔ stops, trips ↔ calendar) are natural merges. Avoid pulling in `gtfs-kit` or `partridge` unless the user asks for them — they add a dependency and don't help with the core read/join/filter work.

A minimal loader:

```python
import pandas as pd, zipfile, io

def load_gtfs(path):
    """Load a GTFS .zip (or directory) into a dict of DataFrames keyed by filename without .txt."""
    feed = {}
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.endswith(".txt"):
                    with z.open(name) as f:
                        feed[name[:-4]] = pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[""])
    else:
        import os
        for name in os.listdir(path):
            if name.endswith(".txt"):
                feed[name[:-4]] = pd.read_csv(f"{path}/{name}", dtype=str, keep_default_na=False, na_values=[""])
    return feed
```

The full helper, with sensible dtype coercions and time parsing, is in [scripts/gtfs_loader.py](scripts/gtfs_loader.py). Prefer running that as a module (`from gtfs_loader import load_gtfs, ...`) rather than rewriting it.

### Why `dtype=str`?

GTFS IDs (`stop_id`, `route_id`, `trip_id`, `service_id`, …) are strings in the spec, but many are numeric-looking (`"1"`, `"42"`). If pandas infers them as ints, leading zeros are lost (`"007"` → `7`), and merges across files silently break when one side parsed as int and the other as str. **Always read IDs as strings.** The loader script handles this.

## The mental model

Three joins do 90% of the work:

1. **trips → stop_times** on `trip_id`: gives you the stop-by-stop schedule for each trip.
2. **trips → routes** on `route_id`: tells you which line each trip belongs to.
3. **trips → calendar (+ calendar_dates)** on `service_id`: tells you which *days* each trip actually runs.

Stops are joined into stop_times on `stop_id` whenever you need lat/lon or names.

That's it. Most "which buses leave Central Square at 8am on Tuesday" questions decompose into those four joins, a date filter on service_id, and a time filter on `departure_time`.

## Times and service days

**Times in `stop_times.txt` can exceed 24:00:00.** A trip that leaves at 11pm and arrives at 1am may be encoded with `arrival_time = "25:00:00"`. This is intentional: it keeps a single trip on a single "service day" even when it crosses midnight.

Consequences:
- Don't parse stop_times as `datetime.time` — it'll throw on `25:00:00`. Parse to integer **seconds-since-service-day-start** instead. The loader script provides `time_to_seconds()`.
- When comparing to a wall-clock time on a given date, remember that "Tuesday 1am" might be encoded as Monday's `25:00:00`. To find *all* trips active at a wall-clock moment, you usually need to check both today's service day and yesterday's overflow.

## Service days: expanding `service_id` to dates

A `service_id` is **not** a date — it's a pattern. To find which trips run on a specific date you must expand it:

1. Start from `calendar.txt`: for each `service_id`, the row gives a date range (`start_date`, `end_date`) and a weekday mask (`monday`, `tuesday`, ..., `sunday`). The service runs on each date in the range whose weekday is `1`.
2. Apply `calendar_dates.txt` exceptions: `exception_type=1` *adds* a date; `exception_type=2` *removes* one.
3. Some feeds omit `calendar.txt` entirely and list every service date explicitly in `calendar_dates.txt`. Handle this case (the loader does).

`scripts/gtfs_loader.py` has `service_ids_active_on(feed, date)` for this — use it. Rolling your own is the #1 source of GTFS bugs.

## Quick recipes

### List all routes served by a stop
```python
trips_at_stop = feed["stop_times"].merge(feed["trips"], on="trip_id")
routes = trips_at_stop[trips_at_stop["stop_id"] == STOP_ID]["route_id"].unique()
```

### Find next departures from a stop on a date
```python
from gtfs_loader import service_ids_active_on, time_to_seconds

active = service_ids_active_on(feed, date)             # set of service_ids
trips = feed["trips"][feed["trips"]["service_id"].isin(active)]
st = feed["stop_times"].merge(trips, on="trip_id")
st = st[st["stop_id"] == STOP_ID].copy()
st["dep_s"] = st["departure_time"].map(time_to_seconds)
st = st.sort_values("dep_s")
```

### Headway / frequency on a route

Two non-obvious choices determine whether your answer is meaningful:

- **Which date?** Don't just grab "any weekday". The first/last days of a feed are often exception-laden (post-holiday catch-up, launch days, etc.) and produce fewer trips than normal — measuring headway there gives an inflated number. Use `pick_representative_date(feed, "weekday")` from the loader; it picks the weekday in the feed's window with the *most* active services.
- **Which stop?** A terminus is the wrong stop. Trips both arrive and depart there, departure times bunch up, and one direction may have no real departures. Pick a mid-line stop served by every trip of the route. Use `pick_representative_stop(feed, route_id, direction_id, date)` for this.

Also, **always resolve the route by `route_short_name`, not `route_id`**: the public-facing label users say ("line 18") matches `route_short_name`, but `route_id` is arbitrary and often differs. The loader provides `route_id_from_short_name(feed, "18")`.

If `frequencies.txt` exists for the trip, prefer it — it gives `headway_secs` directly.

```python
from gtfs_loader import (load_gtfs, route_id_from_short_name,
                         pick_representative_date, pick_representative_stop,
                         service_ids_active_on, time_to_seconds)

feed = load_gtfs(FEED_PATH)
rid = route_id_from_short_name(feed, "18")
date = pick_representative_date(feed, "weekday")
active = service_ids_active_on(feed, date)
trips = feed["trips"]
trips = trips[(trips["route_id"] == rid) & (trips["service_id"].isin(active))]

rows = []
for dir_id in sorted(trips["direction_id"].dropna().unique()):
    stop_id = pick_representative_stop(feed, rid, dir_id, date)
    tdir = trips[trips["direction_id"] == dir_id]
    st = feed["stop_times"].merge(tdir[["trip_id"]], on="trip_id")
    st = st[st["stop_id"] == stop_id].copy()
    st["dep_s"] = st["departure_time"].map(time_to_seconds)
    peak = st[(st["dep_s"] >= 7*3600) & (st["dep_s"] < 9*3600)].sort_values("dep_s")
    gaps = peak["dep_s"].diff().dropna() / 60
    rows.append({"direction": dir_id, "stop_id": stop_id,
                 "departures": len(peak), "avg_headway_min": round(gaps.mean(), 1)})
```

## Presenting results to the user

GTFS queries naturally produce big intermediate objects — DataFrames, long lists of departure times, gap arrays. **Don't dump those on the user.** They came to you for an answer, and they want to see the answer immediately. Specifically:

- **Lead with the bottom line.** If the question is "what's the headway?", the first thing on screen should be a one-line answer per direction, in plain English. The supporting numbers come after.
- **Use a compact table for multi-row answers**, not long arrays. A 16-element list of gap times is unreadable; "16 departures, avg gap 7.1 min, min/max 3/11 min" is readable. Print the long list only if it's directly useful.
- **Round.** `11.111111` minutes is noise. One decimal is enough.
- **State the assumptions.** "Computed on Wed 2026-05-27 at stop RITTWEGER (id=1926G)" — so the user can sanity-check your representative-date / representative-stop picks.

Bad:

```
Direction 0 (towards VAN HAELEN):
  departures in window: 17
  Times: ['07:01:06', '07:05:03', '07:16:03', ... 14 more entries ...]
  Gaps: [3.95, 11.0, 5.05, 5.95, 9.05, 0.95, 11.0, 7.0, 8.0, 8.0, 7.0, 8.0, 7.0, 8.0, 7.0, 7.0]
  Average headway: 7.117647058823529 minutes
```

Good:

```
Line 18 — weekday morning peak (07:00–09:00), Wed 2026-05-27

  → VAN HAELEN (measured at RITTWEGER):   17 deps, avg headway 7.1 min  (range 1–11)
  → ALBERT    (measured at BOURDON):      16 deps, avg headway 7.7 min  (range 6–10)
```

## Working style

- **Before answering a question about a feed, peek at the data.** `feed["routes"].head()` etc. Spec quirks aside, every agency has its own conventions (`stop_id` may be GTFS-Realtime-compatible or not; `direction_id` may be missing; `headsign` may be empty). One look usually settles the question.
- **Filter early, join late.** GTFS files get big (`stop_times` is millions of rows for large agencies). Filter trips by service_id and route_id *before* merging into stop_times.
- **Don't pre-validate the whole feed unless asked.** The user usually wants an answer, not a validation report.
- **Show the user the actual query and the result.** They often want to adapt the code.

## What this skill does NOT cover

- **GTFS-Realtime** (protobuf vehicle positions / trip updates) is a different spec. If the user asks about real-time feeds, say so and ask whether they want GTFS-Realtime help instead.
- **Full feed validation** (every rule in the spec). For that, point them at Google's `gtfs-validator` or MobilityData's tooling; don't try to reimplement it.
- **Routing / trip-planning** (Dijkstra over the network). Possible to build on top of this data but out of scope here.

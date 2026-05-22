# GTFS gotchas

Skim this before writing non-trivial GTFS code. These bite even experienced people.

## 1. Times can exceed 24:00:00

`stop_times.arrival_time` / `departure_time` are strings like `"HH:MM:SS"` where `HH` can be `≥ 24`. A trip leaving 23:50 and arriving 00:30 next day is `23:50:00` → `24:30:00`. This keeps each trip on a single service day.

**Don't** parse with `datetime.strptime("%H:%M:%S")` — it errors on hour ≥ 24.
**Do** convert to integer seconds: `h*3600 + m*60 + s`.

## 2. `service_id` is a pattern, not a date

To answer "what runs on 2025-03-15?" you must expand `service_id` against `calendar.txt` (weekly mask + date range) **and** apply `calendar_dates.txt` exceptions (type 1 = add, type 2 = remove). Some feeds skip `calendar.txt` and list every date explicitly in `calendar_dates.txt`.

## 3. Stop-times wall-clock crosses two service days

To list everything physically at a stop at "Tuesday 00:30", you must check:
- Tuesday's service_ids with `departure_time` near `00:30:00`.
- **Monday's** service_ids with `departure_time` near `24:30:00`.

If you only check Tuesday you miss late-running Monday trips.

## 4. ID columns are strings, not numbers

`stop_id`, `route_id`, `trip_id`, `service_id`, `shape_id` are *strings* by spec. Many look numeric (`"42"`), some have leading zeros (`"007"`), some are alphanumeric (`"R42_WKDY"`). Always read with `dtype=str` — otherwise leading zeros are silently dropped and merges break.

## 5. Dates are `YYYYMMDD` strings

`start_date`, `end_date`, `calendar_dates.date` are 8-char strings like `"20250315"` — no dashes. Compare as strings (lexicographic = chronological) or convert to `datetime.date`. Don't let pandas infer them as ints.

## 6. Timezones

`stop_times` times are in `agency.agency_timezone`, **not** in `stops.stop_timezone` (which exists but is rarely populated and only applies to passenger-facing displays). One feed = one effective timezone for scheduling.

## 7. `parent_station` and `location_type`

`location_type=0` (or empty) is a normal stop. `1` is a station, `2` is an entrance/exit, `3` is a generic node, `4` is a boarding area. Boarding/stop entries point at their station via `parent_station`. When a user says "stop X", they usually mean the station — if a lookup misses, try the parent.

## 8. `frequencies.txt` overrides explicit stop_times

If a `trip_id` has rows in `frequencies.txt`, the schedule is *generated* from headways between `start_time` and `end_time`; the explicit `stop_times` for that trip are a single template. If you're computing schedules and ignore frequencies, you'll undercount departures by 10–100×.

## 9. Direction is not always populated

`trips.direction_id` is `0` or `1` (or missing). Which one is "inbound" is agency-specific. Don't assume.

## 10. `stop_sequence` is not contiguous

`stop_sequence` must be increasing along a trip but doesn't have to be `1,2,3,…` — it can be `10, 20, 30` or even sparse. Sort by it, don't index by it.

## 11. `route_id` is not the line number

The public-facing line label (what a rider says, what `route_short_name` holds — e.g. `"18"`, `"N11"`, `"Red"`) is **not** the join key. `route_id` is. And many feeds have route_ids that look numeric but **do not match** the short_name — STIB/MIVB famously has `route_id="19"` for line 18 (and `route_id="18"` for line 17). If a user says "line 18", always resolve via `route_short_name == "18"` first; never assume the numeric id matches. The loader provides `route_id_from_short_name()`.

## 12. Stop_times rows are huge

For a city-sized feed, `stop_times.txt` is often the only file over 100 MB. Filter `trips` first (by route, service, direction), then merge into stop_times.

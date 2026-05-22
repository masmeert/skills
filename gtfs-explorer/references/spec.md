# GTFS Schedule — file cheat-sheet

Source: https://gtfs.org/documentation/schedule/reference/

## Core files (almost every feed has these)

| File | Required? | PK | Key columns | FK |
|------|-----------|----|----|----|
| `agency.txt` | Yes | `agency_id` | `agency_name`, `agency_url`, `agency_timezone`, `agency_lang` | — |
| `stops.txt` | Yes* | `stop_id` | `stop_name`, `stop_lat`, `stop_lon`, `zone_id`, `location_type`, `parent_station` | `parent_station`→`stops.stop_id` |
| `routes.txt` | Yes | `route_id` | `route_short_name`, `route_long_name`, `route_type`, `route_color`, `route_text_color` | `agency_id`→`agency` |
| `trips.txt` | Yes | `trip_id` | `route_id`, `service_id`, `trip_headsign`, `direction_id`, `block_id`, `shape_id` | `route_id`, `service_id`, `shape_id` |
| `stop_times.txt` | Yes | (`trip_id`,`stop_sequence`) | `arrival_time`, `departure_time`, `stop_id`, `pickup_type`, `drop_off_type`, `timepoint` | `trip_id`, `stop_id` |
| `calendar.txt` | Conditional | `service_id` | `monday`..`sunday` (0/1), `start_date`, `end_date` (YYYYMMDD) | — |
| `calendar_dates.txt` | Conditional | (`service_id`,`date`) | `exception_type` (1=add, 2=remove) | `service_id` |
| `feed_info.txt` | Recommended | — | `feed_publisher_name`, `feed_lang`, `feed_start_date`, `feed_end_date`, `feed_version` | — |

\* `stops.txt` is only optional when on-demand zones in `locations.geojson` fully replace fixed stops — rare.

## Calendar rules

At least one of `calendar.txt` or `calendar_dates.txt` must exist. Three valid shapes:

1. `calendar.txt` only — pure weekly patterns.
2. `calendar.txt` + `calendar_dates.txt` — patterns plus add/remove exceptions.
3. `calendar_dates.txt` only — every service date listed explicitly (`exception_type=1`).

## Geometry & accessibility

| File | Required? | PK | Notes |
|------|-----------|----|----|
| `shapes.txt` | Optional | (`shape_id`,`shape_pt_sequence`) | `shape_pt_lat`, `shape_pt_lon`, `shape_dist_traveled` |
| `pathways.txt` | Optional | `pathway_id` | Walkable connections within a station |
| `levels.txt` | Conditional | `level_id` | Required if pathways use elevators |

## Frequencies / transfers

| File | Required? | PK | Notes |
|------|-----------|----|----|
| `frequencies.txt` | Optional | (`trip_id`,`start_time`) | `headway_secs`, `exact_times` — frequency-based service |
| `transfers.txt` | Optional | (`from_stop_id`,`to_stop_id`,…) | `transfer_type`, `min_transfer_time` |

## Fares

Two parallel systems — use **one**, not both:

- **Fares v1**: `fare_attributes.txt`, `fare_rules.txt`.
- **Fares v2**: `fare_products.txt`, `fare_leg_rules.txt`, `fare_transfer_rules.txt`, `areas.txt`, `stop_areas.txt`, `timeframes.txt`, `rider_categories.txt`, `fare_media.txt`.

## Misc

`translations.txt`, `attributions.txt`, `networks.txt`, `route_networks.txt`, `booking_rules.txt`, `location_groups.txt`, `location_group_stops.txt`, `locations.geojson` — all optional, less commonly used.

## ID uniqueness across files

`stop_id`, `location_group_id`, and `locations.geojson` `id` share a single namespace — none may collide.

## route_type values (most common)

`0` tram/light rail · `1` subway/metro · `2` rail · `3` bus · `4` ferry · `5` cable car · `6` aerial lift · `7` funicular · `11` trolleybus · `12` monorail. (Extended values exist but are rare.)

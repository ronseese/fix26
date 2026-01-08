#!/usr/bin/env python3
"""Generate plan.json from rules.txt, activities.txt, and active_reservations.json.

Produces a `plan.json` with per-day planned activities between the challenge dates.
Reservations are the primary source of scheduled events; filler activities are added
to maximize points without exceeding the daily cap.
"""
from pathlib import Path
import json
import datetime
import re


def parse_activities(path: Path):
    """Parse activities.txt to extract name→points mapping."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    items = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # Only treat lines with explicit point values as activities (e.g. '5 pt' or '5 points')
        m = re.search(r"(\d+)\s*(?:pt|pts|point|points)\b", s, re.I)
        if m:
            pts = int(m.group(1))
            # remove the numeric point fragment and leading bullets/markers
            name = re.sub(r"^[-\*\u2022\s]*", "", s)
            name = re.sub(r"(\d+)\s*(?:pt|pts|point|points)\b", "", name, flags=re.I).strip(" -:\u2014")
            # skip obvious header lines
            if re.search(r"^(ACTIVITY|DAILY TRACKER|WEEK)\b", name, re.I):
                continue
            items.append((name, pts))
    lookup = {n.lower(): p for n, p in items}
    return items, lookup


def parse_rules(path: Path):
    """Extract daily cap from rules.txt (default 18)."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    m = re.search(r"Daily.*?(\d{1,3})", text, re.I)
    if m:
        return int(m.group(1))
    m2 = re.search(r"(\d{1,3})", text)
    if m2:
        return int(m2.group(1))
    return 18


def load_reservations(path: Path):
    """Load active_reservations.json."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("items", [])


def parse_reservation_datetime(dt_str: str):
    """Parse date/time like '1/9/2026, 9:00 AM' → (date, time_str, hour, minute)."""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4}),?\s*(\d{1,2}):(\d{2})\s*(AM|PM)?", dt_str, re.I)
    if not m:
        return None, None, None, None
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hour, minute = int(m.group(4)), int(m.group(5))
    ampm = (m.group(6) or "").upper()
    if ampm == "PM" and hour < 12:
        hour += 12
    if ampm == "AM" and hour == 12:
        hour = 0
    dt = datetime.date(year, month, day)
    time_str = f"{hour:02d}:{minute:02d}"
    return dt, time_str, hour, minute


def parse_duration(length_str: str):
    """Parse duration like '60 Minutes' → 60."""
    m = re.search(r"(\d+)", length_str or "")
    return int(m.group(1)) if m else 60


def compute_points(name: str, location: str, duration_minutes: int, activities_map: dict):
    """Compute points for a reservation based on type and duration."""
    name_lower = (name or "").lower()
    loc_lower = (location or "").lower()

    # Group fitness / yoga / strength classes → 5 pts
    if re.search(r"yoga|strength|cycle|fitness class|power hour", name_lower):
        return 5
    # Line dancing → 5 pts (group fitness)
    if re.search(r"line danc", name_lower):
        return 5
    # Personal training / Pilates / PT → 5 pts
    if re.search(r"personal train|pilates|physical therap", name_lower):
        return 5
    # Court sports (pickleball, tennis): 1 pt per 15 min, capped at 4 pts (60 min)
    if re.search(r"pickle|pickleball|tennis|court sport", name_lower) or "court sports" in loc_lower:
        pts = duration_minutes // 15
        return min(pts, 4)  # cap at 4
    # Golf range → 1 pt
    if re.search(r"golf range", name_lower):
        return 1
    # 9 holes → 2 pts, 18 holes → 4 pts
    if re.search(r"9 holes|nine holes", name_lower):
        return 2
    if re.search(r"18 holes|eighteen holes", name_lower):
        return 4
    # Bocce, other → 1 pt
    if re.search(r"bocce", name_lower):
        return 1
    # Meditation → 3 pts (bonus event)
    if re.search(r"meditation|sunset yoga|sunrise yoga|foam roll|health fair|farmer", name_lower):
        return 3
    # Fallback: check activities_map
    for key, pts in activities_map.items():
        if key in name_lower:
            return pts
    # Default 1 pt
    return 1


def generate_plan(out_path: Path, rules_path: Path, activities_path: Path, reservations_path: Path):
    activities_list, activities_map = parse_activities(activities_path)
    daily_cap = parse_rules(rules_path)
    reservations = load_reservations(reservations_path)

    # Challenge dates (hardcoded as per rules.txt)
    start_date = datetime.date(2026, 1, 12)
    end_date = datetime.date(2026, 2, 15)

    # Group reservations by date
    reservations_by_date = {}
    for res in reservations:
        dt_str = res.get("Date & Time", "")
        dt, time_str, hour, minute = parse_reservation_datetime(dt_str)
        if dt is None:
            continue
        name = res.get("Event") or res.get("Location", "").split(">")[-1].strip()
        location = res.get("Location", "")
        duration = parse_duration(res.get("Length", "60 Minutes"))
        pts = compute_points(name, location, duration, activities_map)
        entry = {
            "name": name,
            "time": time_str,
            "duration_minutes": duration,
            "points": pts,
            "location": location,
        }
        reservations_by_date.setdefault(dt, []).append(entry)

    plan = {"challenge_start": start_date.isoformat(), "challenge_end": end_date.isoformat(), "daily": []}

    d = start_date
    while d <= end_date:
        scheduled = reservations_by_date.get(d, [])
        items = []
        extras = []
        total = 0

        # First, include scheduled reservations (prioritized). If they exceed cap, move to extras.
        for ev in scheduled:
            pts = ev.get("points", 1)
            entry = {
                "name": ev["name"],
                "time": ev.get("time"),
                "duration_minutes": ev.get("duration_minutes"),
                "points": pts,
                "location": ev.get("location"),
                "recommended": False,
            }
            if total + pts <= daily_cap:
                entry["recommended"] = True
                items.append(entry)
                total += pts
            else:
                extras.append({**entry, "reason": "exceeds_daily_cap"})

        # Bike commute rule: add 30-min round-trip (2 pts) when pickleball or gym/fitness event
        has_pb_or_gym = any(
            re.search(r"pickle|pb|gym|fitness|strength|cycle|yoga", it.get("name", ""), re.I)
            or re.search(r"fitness|court sports", it.get("location", ""), re.I)
            for it in scheduled
        )
        if has_pb_or_gym:
            bike_name = "Bike commute (round trip 30 min)"
            bike_pts = 2  # 1 pt per 15 min × 2 = 2 pts
            bike_entry = {"name": bike_name, "points": bike_pts, "duration_minutes": 30, "recommended": False}
            if total + bike_pts <= daily_cap:
                bike_entry["recommended"] = True
                items.append(bike_entry)
                total += bike_pts
            else:
                extras.append({**bike_entry, "reason": "exceeds_daily_cap"})

        # Fill remaining with filler activities (single best fit)
        remaining = daily_cap - total
        if remaining > 0:
            filler_patterns = re.compile(r"15-minute|30-minute|45-minute|walk|rehab", re.I)
            candidates = [(n, p) for n, p in activities_list if filler_patterns.search(n)]
            if not candidates:
                candidates = activities_list

            # Remove candidates already present
            filtered = []
            for name, pts in candidates:
                lname = name.lower()
                if any(it.get("name", "").lower() == lname for it in items):
                    continue
                if any(ex.get("name", "").lower() == lname for ex in extras):
                    continue
                filtered.append((name, pts))

            # Pick single activity with best fit (largest pts ≤ remaining)
            single = [(name, pts) for name, pts in filtered if pts <= remaining]
            if single:
                single.sort(key=lambda t: t[1], reverse=True)
                name, pts = single[0]
                items.append({"name": name, "points": pts, "recommended": True})
                total += pts

        plan["daily"].append({
            "date": d.isoformat(),
            "items": items,
            "extras": extras,
            "total_points": total,
        })
        d += datetime.timedelta(days=1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


def main():
    base = Path(__file__).resolve().parents[0] / ".."
    rules = base / "rules.txt"
    activities = base / "activities.txt"
    reservations = base / "reservations" / "active_reservations.json"
    out = base / "plan.json"
    generate_plan(out, rules, activities, reservations)


if __name__ == "__main__":
    main()

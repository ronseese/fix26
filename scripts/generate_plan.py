#!/usr/bin/env python3
"""Generate plan.json from rules.txt, activities.txt, and schedule.json.

Produces a `plan.json` with per-day planned activities between the challenge dates.
"""
from pathlib import Path
import json
import datetime
import re


def parse_activities(path: Path):
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    items = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # try to extract a point value like '3 pt' or '3pts' or '— 3'
        m = re.search(r"(\d+)\s*pt", s, re.I)
        if m:
            pts = int(m.group(1))
            name = re.sub(r"\d+\s*pt", "", s, flags=re.I).strip(" -:\u2014")
        else:
            m2 = re.search(r"[-:\u2014]\s*(\d+)$", s)
            if m2:
                pts = int(m2.group(1))
                name = re.sub(r"[-:\u2014]\s*\d+$", "", s).strip()
            else:
                # fallback: no explicit points, assume 1
                pts = 1
                name = s
        items.append((name, pts))
    lookup = {n.lower(): p for n, p in items}
    return items, lookup


def parse_rules(path: Path):
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    # look for a number near 'Daily Total' or just the first number ~18
    m = re.search(r"Daily Total.*?(\d{1,3})", text, re.I)
    if m:
        return int(m.group(1))
    m2 = re.search(r"(\d{1,3})", text)
    if m2:
        return int(m2.group(1))
    return 18


def weekday_name_to_index(name):
    name = name[:3].capitalize()
    mapping = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    return mapping.get(name)


def load_schedule(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def generate_plan(out_path: Path, rules_path: Path, activities_path: Path, schedule_path: Path):
    activities_list, activities_map = parse_activities(activities_path)
    daily_cap = parse_rules(rules_path)
    sch = load_schedule(schedule_path) or {}

    start = sch.get("challenge_start")
    end = sch.get("challenge_end")
    if not start or not end:
        raise SystemExit("schedule.json must include challenge_start and challenge_end")

    start_date = datetime.date.fromisoformat(start)
    end_date = datetime.date.fromisoformat(end)

    events = sch.get("events", [])

    # prepare occurrences mapping by weekday index
    occ_by_weekday = {}
    for ev in events:
        for occ in ev.get("occurrences", []):
            wd = occ.get("weekday")
            idx = weekday_name_to_index(wd) if wd else None
            if idx is None:
                continue
            occ_by_weekday.setdefault(idx, []).append({
                "name": ev.get("name"),
                "time": occ.get("time"),
                "duration_minutes": ev.get("duration_minutes", 30),
                "points": ev.get("points", activities_map.get(ev.get("name", "").lower(), 1)),
            })

    plan = {"challenge_start": start, "challenge_end": end, "daily": []}

    d = start_date
    while d <= end_date:
        items = []
        total = 0
        # scheduled events on this weekday
        for ev in occ_by_weekday.get(d.weekday(), []):
            items.append({
                "name": ev["name"],
                "time": ev.get("time"),
                "duration_minutes": ev.get("duration_minutes"),
                "points": ev.get("points", 1),
            })
            total += ev.get("points", 1)

        # Bike commute rule: add bike commute when any scheduled event mentions pickle or gym
        if any(re.search(r"pickl|pb|gym", i["name"], re.I) for i in items):
            bike_name = "Bike commute (round trip)"
            bike_pts = activities_map.get(bike_name.lower(), 1)
            items.append({"name": bike_name, "points": bike_pts})
            total += bike_pts

        # fill remaining with highest-priority activities (from activities_list order)
        for name, pts in activities_list:
            if total >= daily_cap:
                break
            # skip items already scheduled
            lname = name.lower()
            if any(it.get("name", "").lower() == lname for it in items):
                continue
            items.append({"name": name, "points": pts})
            total += pts

        plan["daily"].append({"date": d.isoformat(), "items": items, "total_points": total})
        d += datetime.timedelta(days=1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


def main():
    base = Path(__file__).resolve().parents[0] / ".."
    rules = base / "rules.txt"
    activities = base / "activities.txt"
    schedule = base / "schedule.json"
    out = base / "plan.json"
    generate_plan(out, rules, activities, schedule)


if __name__ == "__main__":
    main()

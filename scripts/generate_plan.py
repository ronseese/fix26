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
        else:
            # skip non-point lines (they're usually headings or examples)
            continue
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
        scheduled = occ_by_weekday.get(d.weekday(), [])
        items = []
        extras = []
        total = 0

        # First, try to include scheduled events (prioritized). If they won't fit,
        # move them to extras rather than exceeding the daily cap.
        for ev in scheduled:
            pts = ev.get("points", 1)
            entry = {
                "name": ev["name"],
                "time": ev.get("time"),
                "duration_minutes": ev.get("duration_minutes"),
                "points": pts,
                "recommended": False,
            }
            if total + pts <= daily_cap:
                entry["recommended"] = True
                items.append(entry)
                total += pts
            else:
                extras.append({**entry, "reason": "exceeds_daily_cap"})

        # Bike commute rule: add bike commute when any scheduled item mentions pickle or gym
        if any(re.search(r"pickl|pb|gym", it.get("name", ""), re.I) for it in scheduled):
            bike_name = "Bike commute (round trip)"
            bike_pts = activities_map.get(bike_name.lower(), 1)
            bike_entry = {"name": bike_name, "points": bike_pts, "recommended": False}
            if total + bike_pts <= daily_cap:
                bike_entry["recommended"] = True
                items.append(bike_entry)
                total += bike_pts
            else:
                extras.append({**bike_entry, "reason": "exceeds_daily_cap"})

        # Fill remaining by choosing a single subset of filler activities that
        # maximizes points without exceeding the remaining allowance.
        remaining = daily_cap - total
        if remaining > 0:
            filler_patterns = re.compile(r"15-minute|30-minute|45-minute|walk|run|rehab|bike commute", re.I)
            candidates = [(n, p) for n, p in activities_list if filler_patterns.search(n)]
            if not candidates:
                candidates = activities_list

            # remove candidates already present or in extras
            filtered = []
            for name, pts in candidates:
                lname = name.lower()
                if any(it.get("name", "").lower() == lname for it in items):
                    continue
                if any(ex.get("name", "").lower() == lname for ex in extras):
                    continue
                filtered.append((name, pts))

            # Prefer a single activity that best matches the remaining allowance.
            single_candidates = [(i, name, pts) for i, (name, pts) in enumerate(filtered) if pts <= remaining]
            if single_candidates:
                # pick the one with largest pts (closest to remaining)
                single_candidates.sort(key=lambda t: t[2], reverse=True)
                _, name, pts = single_candidates[0]
                items.append({"name": name, "points": pts, "recommended": True})
                total += pts
            else:
                # DP subset-sum to maximize sum <= remaining
                n = len(filtered)
                dp = {0: []}  # sum -> list of indices
                for i, (name, pts) in enumerate(filtered):
                    # iterate sums in descending order to avoid reuse
                    for s in range(remaining, pts - 1, -1):
                        if s - pts in dp and s not in dp:
                            dp[s] = dp[s - pts] + [i]

                if dp:
                    best = max(dp.keys())
                    chosen = dp[best]
                    for idx in chosen:
                        name, pts = filtered[idx]
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
    schedule = base / "schedule.json"
    out = base / "plan.json"
    generate_plan(out, rules, activities, schedule)


if __name__ == "__main__":
    main()

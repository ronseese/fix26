#!/usr/bin/env python3
"""Materialize scheduled events into `log.txt` for future dates only.

Usage:
  python scripts/materialize_schedule.py --start YYYY-MM-DD --end YYYY-MM-DD

This will append dated blocks to `log.txt` for dates in the range that are missing,
prefilling the Activities section with scheduled events for that weekday. It never
modifies existing dated entries or past dates.
"""
from pathlib import Path
import json
import argparse
import datetime


WEEKDAY_MAP = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


def load_schedule(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def date_range(start, end):
    d = start
    while d <= end:
        yield d
        d += datetime.timedelta(days=1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--schedule", default="schedule.json")
    args = p.parse_args()

    sch = load_schedule(Path(args.schedule))
    start = datetime.date.fromisoformat(args.start)
    end = datetime.date.fromisoformat(args.end)

    logp = Path("log.txt")
    if not logp.exists():
        print("log.txt not found")
        return

    text = logp.read_text(encoding="utf-8")
    existing_dates = set()
    import re
    for m in re.finditer(r'(?m)^Date:\s*(\d{4}-\d{2}-\d{2})\s*$', text):
        existing_dates.add(m.group(1))

    to_add = []
    for d in date_range(start, end):
        iso = d.isoformat()
        if iso in existing_dates:
            continue
        if d < datetime.date.today():
            # don't add past dates
            continue
        # collect scheduled events for this weekday
        w = d.weekday()
        lines = ["Activities:"]
        for ev in sch.get("events", []):
            for occ in ev.get("occurrences", [])[:]:
                if WEEKDAY_MAP.get(occ["weekday"]) == w:
                    # format activity line
                    pts = ev.get("points", 0)
                    name = ev.get("name")
                    t = occ.get("time")
                    lines.append(f"- {name} ({t}) — {pts} pts")
        if len(lines) == 1:
            # no scheduled events, write empty template
            block = f"Date: {iso}\nActivities:\n\nDaily Total (activity points): 0\n\nWeekly Bonus / Event today: None\nHow I felt (1–5):\nNotes (optional):\n\n"
        else:
            # compute daily total (sum of pts)
            import re
            pts = sum([int(re.search(r"(\d+)", l).group(1)) for l in lines[1:]])
            block = f"Date: {iso}\n" + "\n".join(lines) + f"\n\nDaily Total (activity points): {pts}\n\nWeekly Bonus / Event today: None\nHow I felt (1–5):\nNotes (optional):\n\n"
        to_add.append(block)

    if not to_add:
        print("No new future dates to materialize")
        return

    # append to end of file
    with logp.open("a", encoding="utf-8") as fh:
        fh.write("\n" + "".join(to_add))

    print(f"Appended {len(to_add)} future dated blocks to log.txt")


if __name__ == '__main__':
    main()

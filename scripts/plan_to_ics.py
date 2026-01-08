#!/usr/bin/env python3
"""Generate an .ics file from plan.json.

This script reads `plan.json` (created by `generate_plan.py`) and writes
`docs/fitness_fix26.ics`, creating one summary VEVENT per date and separate
VEVENTs for time-specific scheduled items.
"""
from pathlib import Path
import json
import datetime
import re


def dtstamp():
    return datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def make_uid(prefix, date, name=""):
    n = re.sub(r'[^A-Za-z0-9]', '', name).lower()
    return f"fitnessfix26-{prefix}-{date}-{n}@fitnessfix.local"


def generate(plan_path: Path, out_path: Path):
    if not plan_path.exists():
        raise SystemExit(f"plan.json not found at {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    cal = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Fitness Fix '26 (plan)//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Fitness Fix '26 (Plan)",
        "X-WR-TIMEZONE:UTC",
        f"DTSTAMP:{dtstamp()}",
    ]

    for entry in plan.get("daily", []):
        date = entry.get("date")
        items = entry.get("items", [])

        # Emit one VEVENT per planned item. Time-specific items keep their times; others
        # get a default 07:00 start and 30-minute duration to appear on the calendar.
        for it in items:
            t = it.get('time')
            if t:
                hour, minute = (int(x) for x in t.split(":"))
                start_dt = datetime.datetime.combine(datetime.date.fromisoformat(date), datetime.time(hour, minute))
                duration = datetime.timedelta(minutes=it.get('duration_minutes', 60))
            else:
                start_dt = datetime.datetime.combine(datetime.date.fromisoformat(date), datetime.time(7, 0))
                duration = datetime.timedelta(minutes=30)
            end_dt = start_dt + duration

            summary = it.get('name')
            pts = it.get('points', 0)
            desc = f"{summary} — {pts} pt" if pts else summary

            cal += [
                "BEGIN:VEVENT",
                f"UID:{make_uid('item', date, summary)}",
                f"DTSTAMP:{dtstamp()}",
                f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M00')}",
                f"DTEND:{end_dt.strftime('%Y%m%dT%H%M00')}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{desc}",
                "BEGIN:VALARM",
                "TRIGGER:-PT15M",
                "ACTION:DISPLAY",
                "DESCRIPTION:Reminder - Fitness Fix '26",
                "END:VALARM",
                "END:VEVENT",
            ]

    cal.append("END:VCALENDAR")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(cal), encoding="utf-8")
    print(f"Wrote {out_path}")


def main():
    base = Path(__file__).resolve().parents[0] / ".."
    plan = base / "plan.json"
    out = base / "docs" / "fitness_fix26.ics"
    generate(plan, out)


if __name__ == '__main__':
    main()

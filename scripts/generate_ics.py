#!/usr/bin/env python3
"""Generate an .ics file for Fitness Fix '26 from `log.txt`.

Usage:
  python scripts/generate_ics.py            # generates full calendar for all dated entries
  python scripts/generate_ics.py --sample-first-day
  python scripts/generate_ics.py --output /path/to/out.ics

The `--sample-first-day` option writes an .ics containing only the first dated entry
found in `log.txt` so you can manually import and preview a single event.
"""
from pathlib import Path
import argparse
import re
import datetime
import json


DEFAULT_LOG = Path(__file__).resolve().parents[0] / "../log.txt"
DEFAULT_OUT = Path(__file__).resolve().parents[0] / "../fitness_fix26.ics"


def parse_entries(text):
    # Split on lines like 'Date: YYYY-MM-DD' and yield (date, block)
    parts = re.split(r'(?m)^Date:\s*(\d{4}-\d{2}-\d{2})\s*$', text)
    # parts[0] = header before first Date:, then pairs (date, body)
    for i in range(1, len(parts), 2):
        date_str = parts[i]
        body = parts[i+1].strip()
        try:
            date = datetime.date.fromisoformat(date_str)
        except Exception:
            continue
        yield date, body


def dtstamp():
    return datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def make_description(log_path, entry_text):
    # Remove unwanted lines from the entry text (local file reference and empty fields)
    filtered_lines = []
    for line in entry_text.splitlines():
        s = line.strip()
        if not s:
            continue
        # skip local file references and empty prompt-like lines
        if s.lower().startswith("log file:"):
            continue
        if s.lower().startswith("how i felt"):
            continue
        if s.lower().startswith("notes (optional)"):
            continue
        filtered_lines.append(line)

    desc_text = "\n".join(filtered_lines).strip()
    if not desc_text:
        desc_text = "See log.txt for details"

    # Compute numeric activity points found in the original entry_text and cap at 18
    pts = [int(n) for n in re.findall(r"(\d+)\s*pt", entry_text.lower())]
    total = sum(pts) if pts else None
    if total is not None:
        display_total = min(total, 18)
        # replace the Daily Total line if present, else append it
        if re.search(r"(?m)^Daily Total \(activity points\):\s*\d+", desc_text):
            if total > 18:
                desc_text = re.sub(r"(?m)^(Daily Total \(activity points\):)\s*\d+",
                                   lambda m: f"{m.group(1)} {display_total} (capped from {total})",
                                   desc_text)
            else:
                desc_text = re.sub(r"(?m)^(Daily Total \(activity points\):)\s*\d+",
                                   lambda m: f"{m.group(1)} {display_total}",
                                   desc_text)
        else:
            extra = f"\nDaily Total (activity points): {display_total}"
            if total > 18:
                extra += f" (capped from {total})"
            desc_text = desc_text + extra

    # escape newlines for ICS DESCRIPTION
    return desc_text.replace("\r", "").replace("\n", "\\n")


def generate(log_path: Path, out_path: Path, sample_first_day=False, sample_days: int = 0):
    text = log_path.read_text(encoding="utf-8")
    entries = list(parse_entries(text))
    if sample_days and sample_days > 0:
        if not entries:
            raise SystemExit("No dated entries found in log.txt to sample.")
        entries = entries[:sample_days]
    elif sample_first_day:
        if not entries:
            raise SystemExit("No dated entries found in log.txt to sample.")
        entries = [entries[0]]

    cal = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Fitness Fix '26//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Fitness Fix '26",
        "X-WR-TIMEZONE:UTC",
        f"DTSTAMP:{dtstamp()}",
    ]

    for date, entry in entries:
        uid = f"fitnessfix26-{date.isoformat()}@fitnessfix.local"
        desc = make_description(log_path.resolve(), entry)
        dtstart = datetime.datetime.combine(date, datetime.time(7, 0)).strftime("%Y%m%dT%H%M00")
        dtend = datetime.datetime.combine(date, datetime.time(7, 30)).strftime("%Y%m%dT%H%M00")

        cal += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp()}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            "SUMMARY:Fitness Fix '26 — Daily Plan",
            f"DESCRIPTION:{desc}",
            "BEGIN:VALARM",
            "TRIGGER:-PT15M",
            "ACTION:DISPLAY",
            "DESCRIPTION:Reminder - Fitness Fix '26",
            "END:VALARM",
            "END:VEVENT",
        ]

    # Optionally include scheduled events from schedule.json (non-destructive)
    # The generator will add separate VEVENTs for scheduled items across the challenge range.
    schedule_path = Path(__file__).resolve().parents[0] / "../schedule.json"
    if schedule_path.exists() and getattr(generate, "include_schedule", False):
        sch = json.loads(schedule_path.read_text(encoding="utf-8"))
        start = datetime.date.fromisoformat(sch.get("challenge_start"))
        end = datetime.date.fromisoformat(sch.get("challenge_end"))
        weekday_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        # build set of dates that already have a daily event to avoid duplicates
        existing_dates = {d for d, _ in entries}
        d = start
        while d <= end:
            if d in existing_dates:
                d += datetime.timedelta(days=1)
                continue
            for ev in sch.get("events", []):
                name = ev.get("name")
                pts = ev.get("points", 0)
                for occ in ev.get("occurrences", []):
                    wd = weekday_map.get(occ.get("weekday"))
                    if wd == d.weekday():
                        t = occ.get("time", "07:00")
                        dtstart = datetime.datetime.combine(d, datetime.time(int(t.split(":"))[0], int(t.split(":"))[1])).strftime("%Y%m%dT%H%M00")
                        dtend = (datetime.datetime.combine(d, datetime.time(int(t.split(":"))[0], int(t.split(":"))[1])) + datetime.timedelta(minutes=ev.get("duration_minutes",30))).strftime("%Y%m%dT%H%M00")
                        uid = f"fitnessfix26-sched-{d.isoformat()}-{re.sub(r'[^A-Za-z0-9]', '', name).lower()}@fitnessfix.local"
                        desc = f"{name} — {pts} pts"
                        cal += [
                            "BEGIN:VEVENT",
                            f"UID:{uid}",
                            f"DTSTAMP:{dtstamp()}",
                            f"DTSTART:{dtstart}",
                            f"DTEND:{dtend}",
                            f"SUMMARY:{name}",
                            f"DESCRIPTION:{desc}",
                            "BEGIN:VALARM",
                            "TRIGGER:-PT15M",
                            "ACTION:DISPLAY",
                            "DESCRIPTION:Reminder - Fitness Fix '26",
                            "END:VALARM",
                            "END:VEVENT",
                        ]
            d += datetime.timedelta(days=1)

    cal.append("END:VCALENDAR")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(cal), encoding="utf-8")
    print(f"Wrote {out_path}")


def main():
    p = argparse.ArgumentParser(description="Generate .ics from log.txt")
    p.add_argument("--log", default=str(DEFAULT_LOG), help="Path to log.txt")
    p.add_argument("--output", "-o", default=str(DEFAULT_OUT), help="Output .ics path")
    p.add_argument("--sample-first-day", action="store_true", help="Create a sample .ics for the first dated entry only")
    p.add_argument("--sample-days", type=int, default=0, help="Create a sample .ics containing the first N dated entries")
    args = p.parse_args()

    log_path = Path(args.log).expanduser()
    out_path = Path(args.output).expanduser()
    if not log_path.exists():
        raise SystemExit(f"log file not found: {log_path}")

    generate(log_path, out_path, sample_first_day=args.sample_first_day, sample_days=args.sample_days)


if __name__ == "__main__":
    main()

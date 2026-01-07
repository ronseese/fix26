#!/usr/bin/env python3
"""Append a dated daily entry template to log.txt.

Usage:
  python add_log.py            # appends today's date
  python add_log.py --date 2026-01-12
"""
from datetime import date
from pathlib import Path
import argparse


TEMPLATE = (
    "Date: {date}\n"
    "Activities:\n"
    "- Bike commute (30 min): __ pts\n"
    "- Primary activity: __ pts\n"
    "- Secondary activity: __ pts\n"
    "- Stretch / rehab: __ pts\n"
    "- Bonus / Whiteboard: __ pts\n"
    "\n"
    "Daily Total:\n"
    "How I felt (1–5):\n"
    "Notes (optional):\n"
    "\n"

)


def main():
    parser = argparse.ArgumentParser(description="Append a daily log entry to log.txt")
    parser.add_argument("--date", "-d", help="Date to use (YYYY-MM-DD). Defaults to today.")
    args = parser.parse_args()

    entry_date = args.date or date.today().isoformat()
    entry = TEMPLATE.format(date=entry_date)

    log_path = Path(__file__).parent / "log.txt"
    if not log_path.exists():
        log_path.write_text("Fitness Fix '26 — Daily Progress Log\n\n")

    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)

    print(f"Appended entry for {entry_date} to {log_path}")


if __name__ == "__main__":
    main()

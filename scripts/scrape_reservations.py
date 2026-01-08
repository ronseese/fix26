#!/usr/bin/env python3
"""Scrape 'My Reservation List' HTML file from Downloads and keep an active JSON.

Usage:
  python3 scripts/scrape_reservations.py            # scans ~/Downloads and writes reservations/active_reservations.json
  python3 scripts/scrape_reservations.py --file /path/to/file.html
"""
from pathlib import Path
import argparse
import json
import datetime
import re
from html.parser import HTMLParser
import sys


class RwdTableHTMLParser(HTMLParser):
    """Parse ForeTees rwdTable structure (divs with rwdTr/rwdTd/rwdTh classes)."""
    def __init__(self):
        super().__init__()
        self.tables = []
        self._table_stack = []  # stack of (depth, title, rows)
        self._row_stack = []    # stack of (depth, cells)
        self._td_depth = None
        self._cell = []
        self._depth = 0
        self._capture_title = False
        self._title_text = []

    def _has_class(self, attrs, cls):
        for n, v in attrs:
            if n == 'class' and cls in v.split():
                return True
        return False

    def _get_class(self, attrs):
        for n, v in attrs:
            if n == 'class':
                return v
        return ''

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == 'div':
            self._depth += 1
            cls = self._get_class(attrs)
            if 'rwdTable' in cls:
                self._table_stack.append((self._depth, None, []))
            elif 'rwdCaption' in cls and self._table_stack:
                pass  # h2 inside will set title
            elif 'rwdTr' in cls and self._table_stack:
                self._row_stack.append((self._depth, []))
            elif ('rwdTd' in cls or 'rwdTh' in cls) and self._row_stack:
                self._td_depth = self._depth
                self._cell = []
        elif tag == 'h2' and self._table_stack:
            self._capture_title = True
            self._title_text = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == 'h2' and self._capture_title:
            self._capture_title = False
            if self._table_stack:
                d, _, rows = self._table_stack[-1]
                self._table_stack[-1] = (d, ''.join(self._title_text).strip(), rows)
        if tag == 'div':
            # close cell
            if self._td_depth == self._depth and self._row_stack:
                cell_text = ''.join(self._cell).strip()
                cell_text = re.sub(r'\s+', ' ', cell_text)
                self._row_stack[-1][1].append(cell_text)
                self._td_depth = None
                self._cell = []
            # close row
            elif self._row_stack and self._row_stack[-1][0] == self._depth:
                rd, cells = self._row_stack.pop()
                if cells and self._table_stack:
                    self._table_stack[-1][2].append(cells)
            # close table
            elif self._table_stack and self._table_stack[-1][0] == self._depth:
                td, title, rows = self._table_stack.pop()
                if rows:
                    self.tables.append({'title': title, 'rows': rows})
            self._depth -= 1

    def handle_data(self, data):
        if self._td_depth is not None:
            self._cell.append(data)
        if self._capture_title:
            self._title_text.append(data)


def find_downloads_file(provided: str = None):
    if provided:
        p = Path(provided).expanduser()
        return p if p.exists() else None
    downloads = Path.home() / 'Downloads'
    if not downloads.exists():
        return None
    candidates = [p for p in downloads.iterdir() if p.is_file() and p.suffix.lower() in ('.html', '.htm')]
    if not candidates:
        return None
    # prefer filenames containing 'reservation'
    candidates_sorted = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates_sorted:
        if 'reservation' in p.name.lower() or 'reservation' in p.stem.lower():
            return p
    # fallback: inspect content for 'My Reservation List' or title
    for p in candidates_sorted:
        try:
            txt = p.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        if 'my reservation list' in txt.lower() or re.search(r'<title[^>]*>.*reservation', txt, re.I):
            return p
    # last fallback: return newest html
    return candidates_sorted[0]


def table_to_dicts(table_info):
    """Convert parsed table rows to list of dicts using first row as header."""
    title = table_info.get('title', '')
    rows = table_info.get('rows', [])
    header = None
    if rows and any(re.search(r'[A-Za-z]', cell) for cell in rows[0]):
        header = [c.strip() for c in rows[0]]
        data_rows = rows[1:]
    else:
        data_rows = rows
    dicts = []
    for r in data_rows:
        if header and len(r) >= len(header):
            d = {header[i]: r[i] for i in range(len(header))}
        else:
            d = {f'col{i+1}': r[i] if i < len(r) else '' for i in range(len(r))}
        d['_table'] = title
        dicts.append(d)
    return dicts


def scrape_file(path: Path):
    txt = path.read_text(encoding='utf-8', errors='ignore')
    parser = RwdTableHTMLParser()
    parser.feed(txt)
    records = []
    for tbl in parser.tables:
        dicts = table_to_dicts(tbl)
        if dicts:
            records.extend(dicts)
    return records


def write_active_json(out_path: Path, source: str, items):
    out = {
        'source': str(source) if source else None,
        'scraped_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'items': items,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description='Scrape My Reservation List HTML into JSON')
    p.add_argument('--file', help='Path to HTML file (optional)')
    p.add_argument('--out', help='Output JSON path', default='reservations/active_reservations.json')
    args = p.parse_args()

    file_path = find_downloads_file(args.file)
    out_path = Path(args.out)
    if not file_path:
        print('No HTML reservation file found in ~/Downloads. Writing empty list to', out_path)
        write_active_json(out_path, None, [])
        return

    print('Found reservation file:', file_path)
    items = scrape_file(file_path)
    # optionally filter out rows that look empty
    items = [it for it in items if any(v.strip() for v in it.values())]
    write_active_json(out_path, file_path, items)
    print(f'Wrote {out_path} with {len(items)} items')


if __name__ == '__main__':
    main()

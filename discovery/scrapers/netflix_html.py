"""Netflix HTML ratings scraper."""

from __future__ import annotations

import csv
import html as html_lib
import re
from datetime import datetime
from pathlib import Path

_ROW_RE = re.compile(r'<li class="retableRow">(.*?)</li>', re.S)
_DATE_RE = re.compile(r'<div class="col date nowrap">(.*?)</div>')
_TITLE_RE = re.compile(r'<div class="col title">\s*<a href="[^"]+">(.*?)</a>')
_RATED_RE = re.compile(r'aria-label="Already rated: (.*?)\(click to remove rating\)"')


def parse_netflix_ratings_html(html_text: str) -> list[dict[str, str]]:
    """Parse a Netflix ratings HTML page into rows.

    Returns a list of dicts with keys: Title, Date, Rating.
    """
    rows: list[dict[str, str]] = []

    for match in _ROW_RE.finditer(html_text):
        block = match.group(1)

        date_m = _DATE_RE.search(block)
        title_m = _TITLE_RE.search(block)
        if not title_m:
            continue

        raw_date = date_m.group(1).strip() if date_m else ""
        title = html_lib.unescape(title_m.group(1).strip())

        rating_label = ""
        rated_m = _RATED_RE.search(block)
        if rated_m:
            rating_label = html_lib.unescape(rated_m.group(1).strip())

        date_iso = _normalize_date(raw_date)

        rows.append(
            {
                "Title": title,
                "Date": date_iso,
                "Rating": rating_label,
            }
        )

    return rows


def write_netflix_ratings_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    """Write rows to a CSV file."""
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Title", "Date", "Rating"])
        writer.writeheader()
        writer.writerows(rows)


def convert_html_to_csv(input_path: Path, output_path: Path) -> list[dict[str, str]]:
    """Convert a Netflix ratings HTML file to CSV and return parsed rows."""
    html_text = input_path.read_text(encoding="utf-8")
    rows = parse_netflix_ratings_html(html_text)
    write_netflix_ratings_csv(rows, output_path)
    return rows


def _normalize_date(raw: str) -> str:
    if not raw:
        return ""
    raw_str = raw.strip()
    if not raw_str:
        return ""

    formats = [
        "%d/%m/%y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw_str, fmt)
            return dt.date().isoformat()
        except ValueError:
            continue

    return raw_str

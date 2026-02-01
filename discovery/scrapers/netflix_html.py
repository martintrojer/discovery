"""Netflix HTML ratings scraper."""

from __future__ import annotations

import csv
import html as html_lib
from pathlib import Path

from ..patterns import NETFLIX_DATE_RE, NETFLIX_RATED_RE, NETFLIX_ROW_RE, NETFLIX_TITLE_RE
from ..utils import parse_date


def parse_netflix_ratings_html(html_text: str) -> list[dict[str, str]]:
    """Parse a Netflix ratings HTML page into rows.

    Returns a list of dicts with keys: Title, Date, Rating.
    """
    rows: list[dict[str, str]] = []

    for match in NETFLIX_ROW_RE.finditer(html_text):
        block = match.group(1)

        date_m = NETFLIX_DATE_RE.search(block)
        title_m = NETFLIX_TITLE_RE.search(block)
        if not title_m:
            continue

        raw_date = date_m.group(1).strip() if date_m else ""
        title = html_lib.unescape(title_m.group(1).strip())

        rating_label = ""
        rated_m = NETFLIX_RATED_RE.search(block)
        if rated_m:
            rating_label = html_lib.unescape(rated_m.group(1).strip())

        parsed_date = parse_date(raw_date)
        date_iso = parsed_date.date().isoformat() if parsed_date else raw_date

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

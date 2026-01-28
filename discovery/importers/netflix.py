"""Netflix viewing history importer."""

import csv
import uuid
from pathlib import Path

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from .base import BaseImporter


class NetflixImporter(BaseImporter):
    """Import viewing history from Netflix CSV export."""

    source = Source.NETFLIX
    category = Category.MOVIE  # Will also handle TV

    def __init__(self, db: Database):
        super().__init__(db)

    def get_manual_steps(self) -> str:
        return """
Netflix Import Instructions
===========================

1. Go to https://www.netflix.com/account
2. Click on the profile you want to export
3. Scroll down to "Download your personal information"
   OR go directly to: https://www.netflix.com/account/getmyinfo
4. Request your data (this can take up to 30 days)
5. Once ready, download and extract the ZIP file
6. Find the file: CONTENT_INTERACTION/ViewingActivity.csv
7. Run: discovery import netflix /path/to/ViewingActivity.csv

Note: Netflix doesn't export ratings/thumbs in the standard export.
The viewing history only shows what you watched.

Alternative - Ratings export:
1. Go to https://www.netflix.com/MoviesYouveSeen
2. This shows your rated titles but can't be easily exported
3. You can use browser developer tools to scrape this if needed
"""

    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse Netflix ViewingActivity.csv export."""
        results: list[tuple[Item, ItemSource]] = []
        seen_titles: set[str] = set()  # Deduplicate episodes

        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Netflix CSV has columns like: Profile Name, Start Time, Duration, Attributes, Title, etc.
                title = row.get("Title", "")
                if not title:
                    continue

                # Parse Netflix title format: "Show: Season X: Episode Title"
                # or just "Movie Title"
                parts = title.split(": ")

                if len(parts) >= 3 and "Season" in parts[1]:
                    # TV show episode
                    show_title = parts[0]
                    category = Category.TV

                    # Deduplicate - only add show once
                    if show_title in seen_titles:
                        continue
                    seen_titles.add(show_title)
                    title = show_title
                elif len(parts) >= 2 and ("Episode" in parts[1] or "Chapter" in parts[1]):
                    # Limited series or other format
                    show_title = parts[0]
                    category = Category.TV

                    if show_title in seen_titles:
                        continue
                    seen_titles.add(show_title)
                    title = show_title
                else:
                    # Movie or standalone content
                    category = Category.MOVIE

                    if title in seen_titles:
                        continue
                    seen_titles.add(title)

                item_id = str(uuid.uuid4())

                item = Item(
                    id=item_id,
                    category=category,
                    title=title,
                    creator=None,  # Netflix doesn't include creator info
                    metadata={
                        "source_format": "netflix_viewing_history",
                    },
                )

                # Netflix viewing history doesn't include loved status
                # User will need to rate locally
                item_source = ItemSource(
                    item_id=item_id,
                    source=Source.NETFLIX,
                    source_id=title,  # No unique ID, using title
                    source_loved=None,  # Unknown from viewing history
                    source_data={
                        "first_watched": row.get("Start Time", ""),
                        "duration": row.get("Duration", ""),
                    },
                )

                results.append((item, item_source))

        return results

"""Apple TV+ importer."""

import csv
import json
from pathlib import Path

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from ..utils import detect_video_category
from .base import BaseImporter


class AppleTVImporter(BaseImporter):
    """Import viewing history from Apple TV+."""

    source = Source.APPLE_TV
    category = Category.MOVIE

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def get_manual_steps(self) -> str:
        return """
Apple TV+ Import Instructions
=============================

Option 1: Request your data from Apple
---------------------------------------
1. Go to https://privacy.apple.com/
2. Sign in with your Apple ID
3. Select "Request a copy of your data"
4. Select "Apple Media Services information"
5. Submit request (can take up to 7 days)
6. Download and extract the data
7. Look for viewing activity files

Run: discovery import apple-tv /path/to/viewing_activity.csv

Option 2: Manual CSV
--------------------
Create a CSV with what you've watched on Apple TV+:

title,type
"Ted Lasso",tv
"CODA",movie
"Severance",tv
"Killers of the Flower Moon",movie

Run: discovery import apple-tv /path/to/appletv_watched.csv

Note: Apple TV+ data export is limited.
Use 'discovery love "title"' to mark favorites.
"""

    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse Apple TV+ export."""
        results: list[tuple[Item, ItemSource]] = []
        seen_titles: set[str] = set()

        suffix = file_path.suffix.lower()

        if suffix == ".json":
            return self._parse_json(file_path)

        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                title = row.get("title", row.get("Title", row.get("name", "")))

                if not title:
                    continue

                content_type = row.get("type", row.get("content_type", "")).lower()
                original_title = title

                # Detect type
                category = detect_video_category(title, content_type)
                if category == Category.TV:
                    if ": Season" in title:
                        title = title.split(": Season")[0]

                if title in seen_titles:
                    continue
                seen_titles.add(title)

                item, item_source = self.create_item_pair(
                    title=title,
                    creator=None,
                    source_id=title,
                    category=category,
                    metadata={},
                    source_data={"original_title": original_title},
                )

                results.append((item, item_source))

        return results

    def _parse_json(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse JSON export from Apple privacy portal."""
        results: list[tuple[Item, ItemSource]] = []
        seen_titles: set[str] = set()

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        # Apple's format may vary
        items = data if isinstance(data, list) else data.get("items", data.get("viewingHistory", []))

        for entry in items:
            title = entry.get("title", entry.get("name", ""))

            if not title:
                continue

            content_type = entry.get("type", entry.get("contentType", "")).lower()
            original_title = title

            category = detect_video_category(title, content_type)

            if title in seen_titles:
                continue
            seen_titles.add(title)

            item, item_source = self.create_item_pair(
                title=title,
                creator=None,
                source_id=title,
                category=category,
                metadata={},
                source_data={"original_title": original_title},
            )

            results.append((item, item_source))

        return results

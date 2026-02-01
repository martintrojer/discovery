"""BBC iPlayer importer."""

import csv
import json
from pathlib import Path

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from .base import BaseImporter


class BBCiPlayerImporter(BaseImporter):
    """Import viewing history from BBC iPlayer."""

    source = Source.BBC_IPLAYER
    category = Category.TV

    def __init__(self, db: Database):
        super().__init__(db)

    def get_manual_steps(self) -> str:
        return """
BBC iPlayer Import Instructions
===============================

Option 1: Request your data from BBC
-------------------------------------
1. Go to https://www.bbc.co.uk/usingthebbc/your-data/
2. Click "Request your data"
3. Sign in with your BBC account
4. Submit a data request
5. Download the data when ready

Look for viewing history or watch activity files.

Run: discovery import bbc-iplayer /path/to/viewing_history.csv

Option 2: Manual CSV
--------------------
Create a CSV with what you've watched:

title,type
"Doctor Who",tv
"Sherlock",tv
"Blue Planet II",tv
"Killing Eve",tv

Run: discovery import bbc-iplayer /path/to/iplayer_watched.csv

Option 3: Export from Continue Watching
---------------------------------------
Your "Continue Watching" and "Added" lists in iPlayer
show your viewing activity. You can manually note these
and create a CSV file.

Note: BBC doesn't export ratings.
Use 'discovery love "title"' to mark favorites.
"""

    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse BBC iPlayer export."""
        results: list[tuple[Item, ItemSource]] = []
        seen_titles: set[str] = set()

        suffix = file_path.suffix.lower()

        if suffix == ".json":
            return self._parse_json(file_path)

        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                title = row.get("title", row.get("Title", row.get("programme", "")))

                if not title:
                    continue

                content_type = row.get("type", row.get("content_type", "")).lower()
                original_title = title

                # BBC is mostly TV, but some films
                category = Category.TV
                if content_type in ("film", "movie"):
                    category = Category.MOVIE

                # Extract series name from episode titles
                # Format: "Programme Name: Episode Title" or "Programme - Series X Episode Y"
                if ": Series" in title or ": Episode" in title:
                    title = title.split(":")[0].strip()
                elif " - Series" in title:
                    title = title.split(" - Series")[0].strip()

                if title in seen_titles:
                    continue
                seen_titles.add(title)

                item, item_source = self.create_item_pair(
                    title=title,
                    creator=None,
                    source_id=title,
                    category=category,
                    metadata={"source": "bbc_iplayer"},
                    source_data={"original_title": original_title},
                )

                results.append((item, item_source))

        return results

    def _parse_json(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse JSON export."""
        results: list[tuple[Item, ItemSource]] = []
        seen_titles: set[str] = set()

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        items = data if isinstance(data, list) else data.get("items", data.get("viewingHistory", []))

        for entry in items:
            title = entry.get("title", entry.get("programme", ""))

            if not title:
                continue

            content_type = entry.get("type", "").lower()
            original_title = title

            category = Category.TV
            if content_type in ("film", "movie"):
                category = Category.MOVIE

            if ": Series" in title or ": Episode" in title:
                title = title.split(":")[0].strip()

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

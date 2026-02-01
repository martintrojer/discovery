"""Disney+ importer."""

import csv
from pathlib import Path

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from ..utils import detect_video_category
from .base import BaseImporter


class DisneyPlusImporter(BaseImporter):
    """Import viewing history from Disney+."""

    source = Source.DISNEY_PLUS
    category = Category.MOVIE

    def __init__(self, db: Database):
        super().__init__(db)

    def get_manual_steps(self) -> str:
        return """
Disney+ Import Instructions
===========================

1. Request your data:
   - Go to https://www.disneyplus.com/account
   - Click on your profile
   - Go to "Account" > "Privacy and Data"
   - Or directly: https://www.disneyplus.com/privacy-settings
   - Click "Download Your Data"
   - Submit request (takes up to 30 days)

2. Download and extract the ZIP file

3. Find the viewing history:
   - Look for a file like "viewing-history.csv" or similar

4. Run the import:
   discovery import disney-plus /path/to/viewing-history.csv

Alternative: Manual CSV
-----------------------
Create a CSV with what you've watched:

title,type
"The Mandalorian",tv
"Encanto",movie
"Loki",tv

Run: discovery import disney-plus /path/to/disney_watched.csv

Note: Disney+ doesn't export ratings.
Use 'discovery love "title"' to mark favorites.
"""

    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse Disney+ export."""
        results: list[tuple[Item, ItemSource]] = []
        seen_titles: set[str] = set()

        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                title = (
                    row.get("title", "") or row.get("Title", "") or row.get("content_title", "") or row.get("name", "")
                )

                if not title:
                    continue

                content_type = row.get("type", row.get("content_type", "")).lower()
                original_title = title

                # Detect TV shows from title patterns
                category = detect_video_category(title, content_type)
                if category == Category.TV:
                    if ": Season" in title:
                        title = title.split(": Season")[0]
                    elif " S0" in title:
                        title = title.split(" S0")[0]
                    elif " S1" in title:
                        title = title.split(" S1")[0]

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

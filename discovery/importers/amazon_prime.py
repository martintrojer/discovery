"""Amazon Prime Video importer."""

import csv
from pathlib import Path

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from ..utils import detect_video_category
from .base import BaseImporter


class AmazonPrimeImporter(BaseImporter):
    """Import viewing history from Amazon Prime Video."""

    source = Source.AMAZON_PRIME
    category = Category.MOVIE  # Will also handle TV

    def __init__(self, db: Database):
        super().__init__(db)

    def get_manual_steps(self) -> str:
        return """
Amazon Prime Video Import Instructions
======================================

1. Request your data:
   - Go to https://www.amazon.com/hz/privacy-central/data-requests/preview.html
   - Or: Amazon > Account > Your Account > Request Your Data
   - Select "Prime Video" data
   - Submit request (can take days to weeks)

2. Download and extract the ZIP file

3. Find the viewing history file:
   - Look for: Digital.PrimeVideo.Viewinghistory/
   - The file might be named ViewingHistory.csv or similar

4. Run the import:
   discovery import amazon-prime /path/to/ViewingHistory.csv

Alternative: Manual export
--------------------------
If the data request is slow, you can manually create a CSV:

title,type
"The Expanse",tv
"The Tomorrow War",movie

Run: discovery import amazon-prime /path/to/prime_watched.csv

Note: Amazon doesn't export ratings in the standard export.
Use 'discovery love "title"' to mark favorites.
"""

    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse Amazon Prime Video export."""
        results: list[tuple[Item, ItemSource]] = []
        seen_titles: set[str] = set()

        with open(file_path, encoding="utf-8") as f:
            # Try to detect delimiter
            sample = f.read(1024)
            f.seek(0)

            if "\t" in sample:
                reader = csv.DictReader(f, delimiter="\t")
            else:
                reader = csv.DictReader(f)

            for row in reader:
                # Amazon export has various column names
                title = (
                    row.get("Title", "") or row.get("title", "") or row.get("Video Title", "") or row.get("name", "")
                )

                if not title:
                    continue

                # Detect TV vs Movie from title format or explicit column
                content_type = row.get("type", row.get("Type", row.get("Content Type", "")))

                # Parse title - Amazon often includes episode info
                # Format: "Show Name: Season X Episode Y" or "Show Name - S1E1"
                original_title = title
                category = detect_video_category(title, content_type)

                if category == Category.TV:
                    # Extract show name
                    if ": Season" in title:
                        title = title.split(": Season")[0]
                    elif " - S" in title:
                        title = title.split(" - S")[0]
                    elif ": Episode" in title:
                        title = title.split(": Episode")[0]

                # Deduplicate
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

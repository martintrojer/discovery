"""Goodreads library importer."""

import csv
from pathlib import Path

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from .base import BaseImporter


class GoodreadsImporter(BaseImporter):
    """Import books from Goodreads CSV export."""

    source = Source.GOODREADS
    category = Category.BOOK

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def get_manual_steps(self) -> str:
        return """
Goodreads Import Instructions
=============================

1. Go to https://www.goodreads.com/review/import
2. Click "Export Library" at the top
3. Wait for the export to complete (you'll get an email)
4. Download the CSV file
5. Run: discovery import goodreads /path/to/goodreads_library_export.csv

The export includes:
- All books on your shelves
- Your ratings (1-5 stars)
- Read/to-read status
- Review text
"""

    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse Goodreads CSV export."""
        results: list[tuple[Item, ItemSource]] = []

        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                book_id = row.get("Book Id", "")
                title = row.get("Title", "Unknown")
                author = row.get("Author", "")
                rating = row.get("My Rating", "0")
                shelves = row.get("Bookshelves", "")
                exclusive_shelf = row.get("Exclusive Shelf", "")
                date_read = row.get("Date Read", "")
                isbn = row.get("ISBN", "").strip('="')
                isbn13 = row.get("ISBN13", "").strip('="')
                year_published = row.get("Year Published", "")
                num_pages = row.get("Number of Pages", "")

                if not title:
                    continue

                # Parse rating
                try:
                    rating_int = int(rating)
                except ValueError:
                    rating_int = 0

                # Consider "loved" if rated 4 or 5 stars
                loved = rating_int >= 4

                metadata = {
                    "shelf": exclusive_shelf,
                }
                if isbn:
                    metadata["isbn"] = isbn
                if isbn13:
                    metadata["isbn13"] = isbn13
                if year_published:
                    metadata["year"] = year_published
                if num_pages:
                    try:
                        metadata["pages"] = int(num_pages)
                    except ValueError:
                        pass

                item, item_source = self.create_item_pair(
                    title=title,
                    creator=author,
                    source_id=book_id,
                    loved=loved,
                    metadata=metadata,
                    source_data={
                        "rating": rating_int,
                        "shelves": shelves.split(", ") if shelves else [],
                        "exclusive_shelf": exclusive_shelf,
                        "date_read": date_read,
                    },
                )

                results.append((item, item_source))

        return results

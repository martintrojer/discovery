"""Netflix viewing history importer."""

import csv
import uuid
from datetime import datetime
from pathlib import Path

from ..db import Database
from ..models import Category, Item, ItemSource, Rating, Source
from ..scrapers.netflix_html import parse_netflix_ratings_html
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
4. Import HTML directly: discovery import netflix /path/to/ratings.html
5. Or convert first: discovery scrape netflix-html /path/to/ratings.html -o ratings.csv
"""

    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse Netflix ViewingActivity.csv export."""
        results: list[tuple[Item, ItemSource]] = []
        seen_titles: set[str] = set()  # Deduplicate episodes
        rows, source_format = self._load_rows(file_path)

        for row in rows:
            # Netflix CSV has columns like: Profile Name, Start Time, Duration, Attributes, Title, etc.
            title = row.get("Title") or ""
            if not title:
                continue

            rating_raw = row.get("Rating") or row.get("Thumbs") or row.get("Thumb Rating")
            rating = self._parse_rating(rating_raw)
            rated_at_raw = row.get("Date") or row.get("Rated At") or row.get("Start Time")

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
                    "source_format": source_format,
                },
            )

            # Netflix viewing history doesn't include loved status
            # User will need to rate locally
            item_source = ItemSource(
                item_id=item_id,
                source=Source.NETFLIX,
                source_id=title,  # No unique ID, using title
                source_loved=self._rating_to_loved(rating),
                source_data={
                    "first_watched": row.get("Start Time") or "",
                    "duration": row.get("Duration") or "",
                    "rated_at": rated_at_raw or "",
                    "source_rating": rating,
                    "source_rating_raw": rating_raw or "",
                },
            )

            results.append((item, item_source))

        return results

    def _load_rows(self, file_path: Path) -> tuple[list[dict[str, str]], str]:
        if self._is_html_file(file_path):
            html_text = file_path.read_text(encoding="utf-8")
            rows = parse_netflix_ratings_html(html_text)
            return rows, "netflix_ratings_html"

        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = []
            for row in reader:
                cleaned = {key: (value or "") for key, value in row.items()}
                rows.append(cleaned)
            return rows, "netflix_viewing_history"

    def _is_html_file(self, file_path: Path) -> bool:
        if file_path.suffix.lower() in {".html", ".htm"}:
            return True
        try:
            head = file_path.read_text(encoding="utf-8", errors="ignore")[:2048]
        except OSError:
            return False
        return '<li class="retableRow">' in head

    def import_from_file(self, file_path: Path):
        """Import items and ratings from a Netflix CSV export."""
        items_added = 0
        items_updated = 0
        errors: list[str] = []

        try:
            parsed = self.parse_file(file_path)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            return self._import_error(str(e))

        for item, item_source in parsed:
            try:
                existing = self.db.find_item_by_source(self.source, item_source.source_id)

                if existing:
                    item.id = existing.id
                    item.created_at = existing.created_at
                    item_source.item_id = existing.id
                    self.db.upsert_item(item)
                    self.db.upsert_item_source(item_source)
                    items_updated += 1
                else:
                    dedup_item = self._find_duplicate(item)
                    if dedup_item:
                        item_source.item_id = dedup_item.id
                        self.db.upsert_item_source(item_source)
                        items_updated += 1
                    else:
                        self.db.upsert_item(item)
                        item_source.item_id = item.id
                        self.db.upsert_item_source(item_source)
                        items_added += 1

                self._upsert_rating(item_source)
            except Exception as e:
                errors.append(f"Failed to import '{item.title}': {e}")

        from ..models import SyncState

        self.db.update_sync_state(SyncState(source=self.source, last_sync=datetime.now()))

        return self._import_result(items_added, items_updated, errors)

    def _import_error(self, message: str):
        from .base import ImportResult

        return ImportResult(
            source=self.source,
            items_added=0,
            items_updated=0,
            errors=[f"Failed to parse file: {message}"],
        )

    def _import_result(self, items_added: int, items_updated: int, errors: list[str]):
        from .base import ImportResult

        return ImportResult(
            source=self.source,
            items_added=items_added,
            items_updated=items_updated,
            errors=errors,
        )

    def _parse_rating(self, raw: str | None) -> int | None:
        if not raw:
            return None
        raw_str = str(raw).strip().lower()

        text_map = {
            "thumbs down": 1,
            "thumb down": 1,
            "down": 1,
            "thumbs up": 4,
            "thumb up": 4,
            "up": 4,
            "two thumbs up": 5,
            "2 thumbs up": 5,
            "double thumbs up": 5,
        }
        if raw_str in text_map:
            return text_map[raw_str]

        if raw_str.isdigit():
            val = int(raw_str)
            if val in (1, 2, 3):
                return {1: 1, 2: 4, 3: 5}[val]
            if 1 <= val <= 5:
                return val

        return None

    def _rating_to_loved(self, rating: int | None) -> bool | None:
        if rating is None:
            return None
        return rating >= 4

    def _parse_datetime(self, raw: str | None) -> datetime | None:
        if not raw:
            return None
        raw_str = str(raw).strip()
        if not raw_str:
            return None

        formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%m/%d/%y",
            "%d/%m/%y",
            "%m/%d/%Y",
            "%d/%m/%Y",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(raw_str, fmt)
                return dt
            except ValueError:
                continue
        return None

    def _upsert_rating(self, item_source: ItemSource) -> None:
        rating = item_source.source_data.get("source_rating")
        if rating is None:
            return
        if not isinstance(rating, int):
            return

        rated_at_raw = item_source.source_data.get("rated_at")
        rated_at = self._parse_datetime(rated_at_raw) or datetime.now()

        self.db.upsert_rating(
            Rating(
                item_id=item_source.item_id,
                loved=self._rating_to_loved(rating),
                rating=rating,
                rated_at=rated_at,
            )
        )

"""Apple Podcasts importer."""

import json
import plistlib
import uuid
from pathlib import Path

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from .base import BaseImporter


class ApplePodcastsImporter(BaseImporter):
    """Import podcasts from Apple Podcasts."""

    source = Source.APPLE_PODCASTS
    category = Category.PODCAST

    def __init__(self, db: Database):
        super().__init__(db)

    def get_manual_steps(self) -> str:
        return """
Apple Podcasts Import Instructions
==================================

Option 1: Export subscriptions as OPML (macOS)
----------------------------------------------
1. Open the Podcasts app on macOS
2. Go to File > Export Subscriptions...
3. Save the OPML file
4. Run: discovery import apple-podcasts /path/to/Podcasts.opml

Option 2: Find the database directly (macOS)
--------------------------------------------
The Podcasts database is at:
~/Library/Group Containers/*.groups.com.apple.podcasts/Documents/MTLibrary.sqlite

This requires parsing SQLite, which this importer doesn't support yet.
Use OPML export instead.

Option 3: Manual JSON/CSV
-------------------------
Create a JSON file with your subscribed podcasts:

[
  {"title": "Podcast Name", "author": "Creator Name"},
  {"title": "Another Podcast", "author": "Someone"}
]

Run: discovery import apple-podcasts /path/to/podcasts.json

Note: Apple Podcasts doesn't track "loved" status well.
Use 'discovery love "podcast name"' to mark favorites.
"""

    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse Apple Podcasts export."""
        suffix = file_path.suffix.lower()

        if suffix == ".opml":
            return self._parse_opml(file_path)
        elif suffix == ".json":
            return self._parse_json(file_path)
        elif suffix == ".plist":
            return self._parse_plist(file_path)
        else:
            return []

    def _parse_opml(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse OPML subscription export."""
        import xml.etree.ElementTree as ET

        results: list[tuple[Item, ItemSource]] = []

        tree = ET.parse(file_path)
        root = tree.getroot()

        # OPML structure: opml > body > outline elements
        body = root.find("body")
        if body is None:
            return []

        for outline in body.iter("outline"):
            title = outline.get("text", outline.get("title", ""))
            feed_url = outline.get("xmlUrl", "")

            if not title:
                continue

            item_id = str(uuid.uuid4())

            item = Item(
                id=item_id,
                category=Category.PODCAST,
                title=title,
                creator=None,
                metadata={"feed_url": feed_url} if feed_url else {},
            )

            item_source = ItemSource(
                item_id=item_id,
                source=Source.APPLE_PODCASTS,
                source_id=feed_url or title,
                source_loved=None,  # Subscription doesn't mean loved
                source_data={"feed_url": feed_url},
            )

            results.append((item, item_source))

        return results

    def _parse_json(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse JSON podcast list."""
        results: list[tuple[Item, ItemSource]] = []

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        podcasts = data if isinstance(data, list) else data.get("podcasts", [])

        for podcast in podcasts:
            title = podcast.get("title", podcast.get("name", ""))
            author = podcast.get("author", podcast.get("creator", ""))

            if not title:
                continue

            item_id = str(uuid.uuid4())

            item = Item(
                id=item_id,
                category=Category.PODCAST,
                title=title,
                creator=author,
                metadata={},
            )

            item_source = ItemSource(
                item_id=item_id,
                source=Source.APPLE_PODCASTS,
                source_id=title,
                source_loved=podcast.get("favorite", None),
                source_data={},
            )

            results.append((item, item_source))

        return results

    def _parse_plist(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse plist export (if available)."""
        results: list[tuple[Item, ItemSource]] = []

        with open(file_path, "rb") as f:
            data = plistlib.load(f)

        # Handle various plist structures
        podcasts = data if isinstance(data, list) else data.get("Podcasts", [])

        for podcast in podcasts:
            title = podcast.get("Title", podcast.get("title", ""))
            author = podcast.get("Author", podcast.get("artist", ""))

            if not title:
                continue

            item_id = str(uuid.uuid4())

            item = Item(
                id=item_id,
                category=Category.PODCAST,
                title=title,
                creator=author,
                metadata={},
            )

            item_source = ItemSource(
                item_id=item_id,
                source=Source.APPLE_PODCASTS,
                source_id=title,
                source_loved=None,
                source_data={},
            )

            results.append((item, item_source))

        return results

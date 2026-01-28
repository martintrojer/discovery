"""Qobuz library importer."""

import csv
import json
import uuid
from pathlib import Path

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from .base import BaseImporter


class QobuzImporter(BaseImporter):
    """Import music from Qobuz favorites/purchases."""

    source = Source.QOBUZ
    category = Category.MUSIC

    def __init__(self, db: Database):
        super().__init__(db)

    def get_manual_steps(self) -> str:
        return """
Qobuz Import Instructions
=========================

Qobuz doesn't have a native export feature. Options:

Option 1: Use Soundiiz (recommended)
------------------------------------
1. Go to https://soundiiz.com/
2. Connect your Qobuz account
3. Export your library to CSV/JSON
4. Run: discovery import qobuz /path/to/export.csv

Option 2: Manual CSV creation
-----------------------------
Create a CSV file with columns: title, artist, album
One row per track/album you want to import.

Example:
title,artist,album
"Time",Pink Floyd,The Dark Side of the Moon
"Comfortably Numb",Pink Floyd,The Wall

Run: discovery import qobuz /path/to/qobuz_library.csv

Option 3: Browser export (advanced)
-----------------------------------
1. Go to your Qobuz favorites page
2. Open browser developer tools (F12)
3. In Console, the favorites data may be in window.__PRELOADED_STATE__
4. Copy and save as JSON
5. Run: discovery import qobuz /path/to/qobuz_data.json
"""

    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse Qobuz export file (CSV or JSON)."""
        suffix = file_path.suffix.lower()

        if suffix == ".csv":
            return self._parse_csv(file_path)
        elif suffix == ".json":
            return self._parse_json(file_path)
        else:
            return []

    def _parse_csv(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse CSV export."""
        results: list[tuple[Item, ItemSource]] = []

        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                title = row.get("title", row.get("Title", row.get("track", "")))
                artist = row.get("artist", row.get("Artist", ""))
                album = row.get("album", row.get("Album", ""))

                if not title:
                    continue

                item_id = str(uuid.uuid4())

                metadata = {}
                if album:
                    metadata["album"] = album

                item = Item(
                    id=item_id,
                    category=Category.MUSIC,
                    title=title,
                    creator=artist,
                    metadata=metadata,
                )

                item_source = ItemSource(
                    item_id=item_id,
                    source=Source.QOBUZ,
                    source_id=f"{artist}:{title}",
                    source_loved=True,  # In favorites = loved
                    source_data={"album": album},
                )

                results.append((item, item_source))

        return results

    def _parse_json(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse JSON export (Soundiiz or browser export)."""
        results: list[tuple[Item, ItemSource]] = []

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        # Handle various JSON structures
        tracks = []
        if isinstance(data, list):
            tracks = data
        elif "tracks" in data:
            tracks = data["tracks"]
        elif "items" in data:
            tracks = data["items"]
        elif "favorites" in data:
            tracks = data["favorites"]

        for track in tracks:
            if isinstance(track, dict):
                title = track.get("title", track.get("name", ""))
                artist = track.get("artist", track.get("performer", {}).get("name", ""))
                if isinstance(artist, dict):
                    artist = artist.get("name", "")
                album = track.get("album", track.get("album", {}).get("title", ""))
                if isinstance(album, dict):
                    album = album.get("title", "")
            else:
                continue

            if not title:
                continue

            item_id = str(uuid.uuid4())

            metadata = {}
            if album:
                metadata["album"] = album

            item = Item(
                id=item_id,
                category=Category.MUSIC,
                title=title,
                creator=artist,
                metadata=metadata,
            )

            item_source = ItemSource(
                item_id=item_id,
                source=Source.QOBUZ,
                source_id=f"{artist}:{title}",
                source_loved=True,
                source_data={"album": album},
            )

            results.append((item, item_source))

        return results

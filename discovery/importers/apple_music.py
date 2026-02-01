"""Apple Music library importer."""

import xml.etree.ElementTree as ET
from pathlib import Path

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from .base import BaseImporter


class AppleMusicImporter(BaseImporter):
    """Import music from Apple Music/iTunes library XML export."""

    source = Source.APPLE_MUSIC
    category = Category.MUSIC

    def __init__(self, db: Database):
        super().__init__(db)

    def get_manual_steps(self) -> str:
        return """
Apple Music Import Instructions
===============================

Option 1: Export Library XML (macOS Music app)
-----------------------------------------------
1. Open the Music app
2. Go to File > Library > Export Library...
3. Save the XML file
4. Run: discovery import apple-music /path/to/Library.xml

Option 2: Find existing library file (older iTunes)
----------------------------------------------------
1. The library file may be at:
   ~/Music/iTunes/iTunes Music Library.xml
   or
   ~/Music/Music/Library.xml

Note: The XML export includes your "Loved" tracks. Make sure to love
songs in Apple Music to help with discovery recommendations.
"""

    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse iTunes/Music library XML file."""
        tree = ET.parse(file_path)
        root = tree.getroot()

        # iTunes XML structure: plist > dict > (key, dict pairs)
        main_dict = root.find("dict")
        if main_dict is None:
            return []

        # Find the Tracks dict
        tracks_dict = None
        children = list(main_dict)
        for i, child in enumerate(children):
            if child.tag == "key" and child.text == "Tracks":
                tracks_dict = children[i + 1]
                break

        if tracks_dict is None:
            return []

        results: list[tuple[Item, ItemSource]] = []
        track_children = list(tracks_dict)

        # Process each track (alternating key/dict pairs)
        for i in range(0, len(track_children), 2):
            if i + 1 >= len(track_children):
                break

            track_dict = track_children[i + 1]
            if track_dict.tag != "dict":
                continue

            track_data = self._parse_track_dict(track_dict)
            if not track_data.get("Name"):
                continue

            # Skip non-music items (podcasts, audiobooks, etc.)
            kind = track_data.get("Kind", "")
            if "podcast" in kind.lower() or "audiobook" in kind.lower():
                continue

            track_id = str(track_data.get("Track ID", ""))
            title = track_data.get("Name", "Unknown")
            artist = track_data.get("Artist")
            album = track_data.get("Album")
            genre = track_data.get("Genre")
            year = track_data.get("Year")
            loved = track_data.get("Loved", False)
            play_count = track_data.get("Play Count", 0)

            metadata = {}
            if album:
                metadata["album"] = album
            if genre:
                metadata["genre"] = genre
            if year:
                metadata["year"] = year

            item, item_source = self.create_item_pair(
                title=title,
                creator=artist,
                source_id=track_id,
                loved=loved,
                metadata=metadata,
                source_data={
                    "play_count": play_count,
                    "album": album,
                    "genre": genre,
                },
            )

            results.append((item, item_source))

        return results

    def _parse_track_dict(self, track_dict: ET.Element) -> dict:
        """Parse a track dict element into a Python dict."""
        result = {}
        children = list(track_dict)

        for i in range(0, len(children), 2):
            if i + 1 >= len(children):
                break

            key_elem = children[i]
            value_elem = children[i + 1]

            if key_elem.tag != "key":
                continue

            key = key_elem.text or ""
            value = self._parse_value(value_elem)
            result[key] = value

        return result

    def _parse_value(self, elem: ET.Element):
        """Parse an iTunes plist value element."""
        if elem.tag == "string":
            return elem.text or ""
        elif elem.tag == "integer":
            return int(elem.text or 0)
        elif elem.tag == "true":
            return True
        elif elem.tag == "false":
            return False
        elif elem.tag == "date" or elem.tag == "data":
            return elem.text
        else:
            return None

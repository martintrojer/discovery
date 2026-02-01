"""Spotify library importer."""

import json
from collections import Counter, defaultdict
from pathlib import Path

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from .base import BaseImporter


class SpotifyImporter(BaseImporter):
    """Import music from Spotify data export."""

    source = Source.SPOTIFY
    category = Category.MUSIC

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def get_manual_steps(self) -> str:
        return """
Spotify Import Instructions
===========================

1. Request your data export:
   - Go to https://www.spotify.com/account/privacy/
   - Scroll to "Download your data"
   - Click "Request" (select "Extended streaming history" for full data)
   - Wait for email (can take up to 30 days)

2. Download and extract the ZIP file

3. Find these files in your export:
   - Streaming_History_Audio_*.json (listening history)
   - YourLibrary.json (saved tracks/albums)
   - Playlist*.json (your playlists)

4. Import your saved library:
   discovery import spotify /path/to/YourLibrary.json

   Or import streaming history:
   discovery import spotify /path/to/Streaming_History_Audio_2024.json --history

Note: Spotify marks tracks as "liked" when you save them to Your Library.
The YourLibrary.json contains your saved/liked tracks.
"""

    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse Spotify export JSON file."""
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        # Detect file type and parse accordingly
        if "tracks" in data:
            return self._parse_library(data)
        elif isinstance(data, list) and len(data) > 0 and "ts" in data[0]:
            return self._parse_streaming_history(data)
        else:
            return []

    def _parse_library(self, data: dict) -> list[tuple[Item, ItemSource]]:
        """Parse YourLibrary.json format."""
        results: list[tuple[Item, ItemSource]] = []

        for track in data.get("tracks", []):
            artist = track.get("artist")
            album = track.get("album")
            title = track.get("track")

            if not title:
                continue

            metadata = {}
            if album:
                metadata["album"] = album

            # Saved to library = loved
            item, item_source = self.create_item_pair(
                title=title,
                creator=artist,
                source_id=f"{artist}:{title}",
                loved=True,
                metadata=metadata,
                source_data={"album": album},
            )

            results.append((item, item_source))

        return results

    def _parse_streaming_history(self, data: list) -> list[tuple[Item, ItemSource]]:
        """Parse Streaming_History_Audio_*.json format."""
        results: list[tuple[Item, ItemSource]] = []
        seen: set[str] = set()

        # Aggregate play counts using Counter and defaultdict
        play_counts: Counter[str] = Counter()
        play_time: defaultdict[str, int] = defaultdict(int)

        for entry in data:
            artist = entry.get("master_metadata_album_artist_name", "")
            title = entry.get("master_metadata_track_name", "")
            ms_played = entry.get("ms_played", 0)

            if not title or not artist:
                continue

            key = f"{artist}:{title}"
            play_counts[key] += 1
            play_time[key] += ms_played

        # Create items for tracks with significant plays
        for key, count in play_counts.items():
            if key in seen:
                continue
            seen.add(key)

            artist, title = key.split(":", 1)
            minutes_played = play_time[key] / 60000

            # Consider loved if played more than 5 times or 10+ minutes total
            loved = count >= 5 or minutes_played >= 10

            item, item_source = self.create_item_pair(
                title=title,
                creator=artist,
                source_id=key,
                loved=loved,
                metadata={"play_count": count, "minutes_played": round(minutes_played, 1)},
                source_data={"play_count": count, "ms_played": play_time[key]},
            )

            results.append((item, item_source))

        return results

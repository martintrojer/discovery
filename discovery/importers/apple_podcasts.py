"""Apple Podcasts importer."""

import json
import plistlib
import sqlite3
import uuid
from datetime import UTC, datetime
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

Option 2: Import directly from the Podcasts database (macOS)
------------------------------------------------------------
The Podcasts database is at:
~/Library/Group Containers/<container>.groups.com.apple.podcasts/Documents/MTLibrary.sqlite
(the leading number varies per machine)

Example:
discovery import apple-podcasts "~/Library/Group Containers/243LU875E5.groups.com.apple.podcasts/Documents/MTLibrary.sqlite"

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
        elif suffix in {".sqlite", ".db"} or file_path.name == "MTLibrary.sqlite":
            return self._parse_sqlite(file_path)
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

    def _parse_sqlite(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse Apple Podcasts SQLite database."""
        results: list[tuple[Item, ItemSource]] = []

        conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            episode_stats = self._load_episode_stats(conn)

            podcast_rows = conn.execute(
                """
                SELECT
                    Z_PK,
                    ZTITLE,
                    ZAUTHOR,
                    ZFEEDURL,
                    ZWEBPAGEURL,
                    ZSTORECLEANURL,
                    ZSTORESHORTURL,
                    ZUUID,
                    ZSUBSCRIBED,
                    ZHIDDEN,
                    ZISHIDDENORIMPLICITLYFOLLOWED,
                    ZISIMPLICITLYFOLLOWED,
                    ZCATEGORY,
                    ZITEMDESCRIPTION,
                    ZIMAGEURL,
                    ZDISPLAYTYPE,
                    ZSHOWTYPEINFEED,
                    ZSHOWTYPESETTING,
                    ZUPDATEINTERVAL,
                    ZEPISODELIMIT,
                    ZHIDESPLAYEDEPISODES,
                    ZKEEPEPISODES,
                    ZNOTIFICATIONS,
                    ZLIBRARYEPISODESCOUNT,
                    ZNEWEPISODESCOUNT,
                    ZDOWNLOADEDEPISODESCOUNT,
                    ZSAVEDUNPLAYEDEPISODESCOUNT,
                    ZSAVEDEPISODESCOUNT,
                    ZADDEDDATE,
                    ZLASTDATEPLAYED,
                    ZLASTFETCHEDDATE,
                    ZMODIFIEDDATE,
                    ZUPDATEDDATE
                FROM ZMTPODCAST
                """
            ).fetchall()

            for row in podcast_rows:
                title = (row["ZTITLE"] or "").strip()
                if not title:
                    continue

                author = (row["ZAUTHOR"] or "").strip() or None
                feed_url = (row["ZFEEDURL"] or "").strip() or None
                webpage_url = (row["ZWEBPAGEURL"] or "").strip() or None
                store_url = (row["ZSTORECLEANURL"] or "").strip() or (row["ZSTORESHORTURL"] or "").strip() or None
                podcast_uuid = (row["ZUUID"] or "").strip() or None

                added_at = self._apple_time_to_iso(row["ZADDEDDATE"])
                last_played_at = self._apple_time_to_iso(row["ZLASTDATEPLAYED"])
                last_fetched_at = self._apple_time_to_iso(row["ZLASTFETCHEDDATE"])
                modified_at = self._apple_time_to_iso(row["ZMODIFIEDDATE"])
                updated_at = self._apple_time_to_iso(row["ZUPDATEDDATE"])

                stats = episode_stats.get(row["Z_PK"], {})
                loved, loved_reason = self._infer_loved(stats)

                metadata = {
                    "feed_url": feed_url,
                    "webpage_url": webpage_url,
                    "store_url": store_url,
                    "image_url": (row["ZIMAGEURL"] or "").strip() or None,
                    "uuid": podcast_uuid,
                    "category": (row["ZCATEGORY"] or "").strip() or None,
                    "description": (row["ZITEMDESCRIPTION"] or "").strip() or None,
                    "display_type": row["ZDISPLAYTYPE"],
                    "show_type_in_feed": row["ZSHOWTYPEINFEED"],
                    "show_type_setting": row["ZSHOWTYPESETTING"],
                    "update_interval": row["ZUPDATEINTERVAL"],
                    "episode_limit": row["ZEPISODELIMIT"],
                    "hide_played_episodes": self._to_bool(row["ZHIDESPLAYEDEPISODES"]),
                    "keep_episodes": row["ZKEEPEPISODES"],
                    "notifications": row["ZNOTIFICATIONS"],
                    "subscribed": self._to_bool(row["ZSUBSCRIBED"]),
                    "hidden": self._to_bool(row["ZHIDDEN"]),
                    "implicitly_followed": self._to_bool(row["ZISIMPLICITLYFOLLOWED"]),
                    "hidden_or_implicitly_followed": self._to_bool(row["ZISHIDDENORIMPLICITLYFOLLOWED"]),
                    "added_at": added_at,
                    "last_played_at": last_played_at,
                    "last_fetched_at": last_fetched_at,
                    "modified_at": modified_at,
                    "updated_at": updated_at,
                    "library_episodes_count": row["ZLIBRARYEPISODESCOUNT"],
                    "new_episodes_count": row["ZNEWEPISODESCOUNT"],
                    "downloaded_episodes_count": row["ZDOWNLOADEDEPISODESCOUNT"],
                    "saved_unplayed_episodes_count": row["ZSAVEDUNPLAYEDEPISODESCOUNT"],
                    "saved_episodes_count": row["ZSAVEDEPISODESCOUNT"],
                    "episode_stats": stats,
                    "loved_inferred": loved,
                    "loved_reason": loved_reason,
                }

                item_id = str(uuid.uuid4())
                item = Item(
                    id=item_id,
                    category=Category.PODCAST,
                    title=title,
                    creator=author,
                    metadata={k: v for k, v in metadata.items() if v not in (None, "", {})},
                )

                source_id = podcast_uuid or feed_url or title
                item_source = ItemSource(
                    item_id=item_id,
                    source=Source.APPLE_PODCASTS,
                    source_id=source_id,
                    source_loved=loved,
                    source_data={
                        "uuid": podcast_uuid,
                        "feed_url": feed_url,
                        "subscribed": self._to_bool(row["ZSUBSCRIBED"]),
                        "added_at": added_at,
                        "last_played_at": last_played_at,
                        "loved_inferred": loved,
                        "loved_reason": loved_reason,
                        "episode_stats": stats,
                    },
                )

                results.append((item, item_source))
        finally:
            conn.close()

        return results

    def _load_episode_stats(self, conn: sqlite3.Connection) -> dict[int, dict[str, object]]:
        """Aggregate per-podcast episode stats for metadata and love heuristics."""
        rows = conn.execute(
            """
            SELECT
                ZPODCAST AS podcast_pk,
                COUNT(*) AS episode_count,
                SUM(CASE WHEN ZHASBEENPLAYED = 1 THEN 1 ELSE 0 END) AS played_count,
                SUM(CASE WHEN ZISBOOKMARKED = 1 THEN 1 ELSE 0 END) AS bookmarked_count,
                SUM(CASE WHEN ZSAVED = 1 THEN 1 ELSE 0 END) AS saved_count,
                MAX(ZLASTDATEPLAYED) AS last_played_date,
                MAX(ZPUBDATE) AS last_pub_date
            FROM ZMTEPISODE
            GROUP BY ZPODCAST
            """
        ).fetchall()

        stats: dict[int, dict[str, object]] = {}
        for row in rows:
            stats[row["podcast_pk"]] = {
                "episode_count": row["episode_count"],
                "played_count": row["played_count"] or 0,
                "bookmarked_count": row["bookmarked_count"] or 0,
                "saved_count": row["saved_count"] or 0,
                "last_played_at": self._apple_time_to_iso(row["last_played_date"]),
                "last_pub_at": self._apple_time_to_iso(row["last_pub_date"]),
            }
        return stats

    def _infer_loved(self, stats: dict[str, object]) -> tuple[bool | None, str | None]:
        """Infer loved status from episode-level signals."""
        bookmarked = self._to_int(stats.get("bookmarked_count"))
        saved = self._to_int(stats.get("saved_count"))

        if bookmarked > 0:
            return True, "episode_bookmarked"
        if saved > 0:
            return True, "episode_saved"
        return None, None

    def _apple_time_to_iso(self, value: float | int | None) -> str | None:
        if value is None:
            return None
        try:
            unix_ts = float(value) + 978307200
        except (TypeError, ValueError):
            return None
        return datetime.fromtimestamp(unix_ts, tz=UTC).isoformat()

    def _to_bool(self, value: int | None) -> bool | None:
        if value is None:
            return None
        return bool(value)

    def _to_int(self, value: object | None) -> int:
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if text.isdigit():
                return int(text)
        return 0

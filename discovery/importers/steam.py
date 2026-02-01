"""Steam library importer."""

import json
from pathlib import Path

import httpx

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from .base import BaseImporter, ImportResult


class SteamImporter(BaseImporter):
    """Import games from Steam library via API."""

    source = Source.STEAM
    category = Category.GAME

    def __init__(self, db: Database, api_key: str | None = None, steam_id: str | None = None):
        super().__init__(db)
        self.api_key = api_key
        self.steam_id = steam_id

    def get_manual_steps(self) -> str:
        return """
Steam Import Instructions
=========================

1. Get your Steam Web API key:
   - Go to https://steamcommunity.com/dev/apikey
   - Sign in and register for a key

2. Find your Steam ID:
   - Go to your Steam profile
   - Your Steam ID is in the URL: steamcommunity.com/id/YOUR_ID
   - Or use: steamcommunity.com/profiles/YOUR_NUMERIC_ID
   - For numeric ID (required): use https://steamid.io to convert

3. Make your game library public:
   - Steam > Settings > Privacy > Game details: Public

4. Run the import:
   discovery import steam --api-key YOUR_KEY --steam-id YOUR_NUMERIC_ID
"""

    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse a JSON export file (for offline import)."""
        with open(file_path) as f:
            data = json.load(f)

        return self._parse_games(data.get("response", {}).get("games", []))

    def import_from_api(self) -> ImportResult:
        """Import directly from Steam API."""
        if not self.api_key or not self.steam_id:
            return ImportResult(
                source=self.source,
                items_added=0,
                items_updated=0,
                errors=["API key and Steam ID required. Run 'discovery import steam --help' for instructions."],
            )

        items_added = 0
        items_updated = 0
        errors: list[str] = []

        try:
            # Fetch owned games
            url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
            params = {
                "key": self.api_key,
                "steamid": self.steam_id,
                "include_appinfo": True,
                "include_played_free_games": True,
            }

            response = httpx.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            games = data.get("response", {}).get("games", [])

            for item, item_source in self._parse_games(games):
                try:
                    existing = self.db.find_item_by_source(self.source, item_source.source_id)

                    if existing:
                        item.id = existing.id
                        item.created_at = existing.created_at
                        self.db.upsert_item(item)
                        self.db.upsert_item_source(item_source)
                        items_updated += 1
                    else:
                        self.db.upsert_item(item)
                        item_source.item_id = item.id
                        self.db.upsert_item_source(item_source)
                        items_added += 1

                except Exception as e:
                    errors.append(f"Failed to import '{item.title}': {e}")

        except httpx.HTTPError as e:
            errors.append(f"Steam API error: {e}")

        return ImportResult(
            source=self.source,
            items_added=items_added,
            items_updated=items_updated,
            errors=errors,
        )

    def _parse_games(self, games: list[dict]) -> list[tuple[Item, ItemSource]]:
        """Parse Steam games list into items."""
        results: list[tuple[Item, ItemSource]] = []

        for game in games:
            app_id = str(game.get("appid", ""))
            name = game.get("name", "Unknown")
            playtime_minutes = game.get("playtime_forever", 0)
            playtime_hours = playtime_minutes / 60

            # Consider "loved" if played more than 10 hours
            loved = playtime_hours >= 10

            item, item_source = self.create_item_pair(
                title=name,
                creator=None,  # Steam doesn't provide developer in this API
                source_id=app_id,
                loved=loved,
                metadata={
                    "steam_appid": app_id,
                    "playtime_hours": round(playtime_hours, 1),
                },
                source_data={
                    "playtime_minutes": playtime_minutes,
                    "playtime_2weeks": game.get("playtime_2weeks", 0),
                    "img_icon_url": game.get("img_icon_url", ""),
                },
            )

            results.append((item, item_source))

        return results

"""Unit tests for importers."""

import json
from pathlib import Path

import pytest

from discovery.db import Database
from discovery.importers.goodreads import GoodreadsImporter
from discovery.importers.netflix import NetflixImporter
from discovery.importers.spotify import SpotifyImporter
from discovery.models import Category, Source
from discovery.utils import creators_match, normalize_title, titles_match


class TestNormalizationUtilities:
    """Test the normalization and matching logic in utils module."""

    def test_normalize_title_lowercase(self):
        assert normalize_title("HELLO WORLD") == "hello world"

    def test_normalize_title_removes_article_prefix(self):
        assert normalize_title("The Matrix") == "matrix"
        assert normalize_title("A New Hope") == "new hope"
        assert normalize_title("An Example") == "example"

    def test_normalize_title_removes_punctuation(self):
        assert normalize_title("Hello, World!") == "hello world"
        assert normalize_title("Test: Subtitle") == "test subtitle"

    def test_normalize_title_removes_edition_markers(self):
        # Parenthetical with "edition" keyword
        result = normalize_title("Album (Deluxe Edition)")
        assert result == "album"

        result = normalize_title("Song (Remastered)")
        assert result == "song"

    def test_normalize_title_empty(self):
        assert normalize_title("") == ""

    def test_titles_match_exact(self):
        assert titles_match("Hello", "Hello") is True
        assert titles_match("Hello", "hello") is True

    def test_titles_match_normalized(self):
        assert titles_match("The Matrix", "Matrix") is True
        # Test substring matching (longer titles contain shorter)
        assert titles_match("Great Album", "Great Album Deluxe") is True

    def test_titles_match_substring(self):
        assert titles_match("Dark Souls III", "Dark Souls") is True
        # Substring matching requires the shorter one to be at least 5 chars
        assert titles_match("Great Song", "Great Song Extended Mix") is True

    def test_titles_match_short_substring_rejected(self):
        # Short substrings should not match
        assert titles_match("A", "A Song") is False

    def test_titles_match_none(self):
        assert titles_match(None, "Test") is False
        assert titles_match("Test", None) is False

    def test_titles_match_numbered_sequels(self):
        # Same base title with different numbering
        assert titles_match("Mass Effect 2", "Mass Effect 3") is True
        assert titles_match("Final Fantasy VII", "Final Fantasy X") is True
        assert titles_match("Dark Souls II", "Dark Souls III") is True

    def test_titles_match_fuzzy_typos(self):
        # Fuzzy matching catches typos
        assert titles_match("The Witcher", "The Witchar") is True
        assert titles_match("Assassin's Creed", "Assassins Creed") is True

    def test_titles_match_fuzzy_threshold(self):
        # Very different titles should not match
        assert titles_match("Dark Souls", "Light Hearts") is False
        assert titles_match("The Matrix", "Frozen") is False

    def test_creators_match_fuzzy_typos(self):
        # Fuzzy matching catches typos in creator names
        assert creators_match("Christopher Nolan", "Cristopher Nolan") is True
        assert creators_match("FromSoftware", "From Software") is True

    def test_creators_match_different(self):
        # Very different creators should not match
        assert creators_match("Steven Spielberg", "Martin Scorsese") is False

    def test_creators_match_exact(self):
        assert creators_match("John Smith", "John Smith") is True
        assert creators_match("John Smith", "john smith") is True

    def test_creators_match_contains(self):
        assert creators_match("John", "John Smith") is True
        assert creators_match("Smith", "John Smith") is True

    def test_creators_match_last_name(self):
        assert creators_match("John Smith", "Jane Smith") is True

    def test_creators_match_none_is_match(self):
        # Missing creator should match anything (aggressive dedup)
        assert creators_match(None, "John") is True
        assert creators_match("John", None) is True
        assert creators_match(None, None) is True


class TestSpotifyImporter:
    @pytest.fixture
    def importer(self, db: Database) -> SpotifyImporter:
        return SpotifyImporter(db)

    def test_parse_library_format(self, importer: SpotifyImporter, tmp_import_dir: Path):
        data = {
            "tracks": [
                {"artist": "Pink Floyd", "album": "Dark Side of the Moon", "track": "Money"},
                {"artist": "Led Zeppelin", "album": "IV", "track": "Stairway to Heaven"},
            ]
        }
        file_path = tmp_import_dir / "YourLibrary.json"
        file_path.write_text(json.dumps(data))

        result = importer.parse_file(file_path)

        assert len(result) == 2
        item, source = result[0]
        assert item.title == "Money"
        assert item.creator == "Pink Floyd"
        assert item.metadata["album"] == "Dark Side of the Moon"
        assert source.source_loved is True  # Library tracks are loved

    def test_parse_streaming_history(self, importer: SpotifyImporter, tmp_import_dir: Path):
        data = [
            {
                "ts": "2024-01-01",
                "master_metadata_album_artist_name": "Artist",
                "master_metadata_track_name": "Song",
                "ms_played": 300000,
            },
            {
                "ts": "2024-01-02",
                "master_metadata_album_artist_name": "Artist",
                "master_metadata_track_name": "Song",
                "ms_played": 300000,
            },
            {
                "ts": "2024-01-03",
                "master_metadata_album_artist_name": "Artist",
                "master_metadata_track_name": "Song",
                "ms_played": 300000,
            },
            {
                "ts": "2024-01-04",
                "master_metadata_album_artist_name": "Artist",
                "master_metadata_track_name": "Song",
                "ms_played": 300000,
            },
            {
                "ts": "2024-01-05",
                "master_metadata_album_artist_name": "Artist",
                "master_metadata_track_name": "Song",
                "ms_played": 300000,
            },
        ]
        file_path = tmp_import_dir / "Streaming_History.json"
        file_path.write_text(json.dumps(data))

        result = importer.parse_file(file_path)

        assert len(result) == 1
        item, source = result[0]
        assert item.title == "Song"
        assert item.metadata["play_count"] == 5
        assert source.source_loved is True  # 5 plays = loved

    def test_get_manual_steps(self, importer: SpotifyImporter):
        steps = importer.get_manual_steps()
        assert "Spotify" in steps
        assert "Download" in steps


class TestNetflixImporter:
    @pytest.fixture
    def importer(self, db: Database) -> NetflixImporter:
        return NetflixImporter(db)

    def test_parse_viewing_activity(self, importer: NetflixImporter, tmp_import_dir: Path):
        csv_content = """Title,Date
"Breaking Bad: Season 1: Pilot","2024-01-01"
"The Office (U.S.): Season 1: Pilot","2024-01-02"
"Some Movie","2024-01-03"
"""
        file_path = tmp_import_dir / "ViewingActivity.csv"
        file_path.write_text(csv_content)

        result = importer.parse_file(file_path)

        assert len(result) == 3
        titles = [item.title for item, _ in result]
        assert "Breaking Bad" in titles
        assert "The Office (U.S.)" in titles
        assert "Some Movie" in titles


class TestGoodreadsImporter:
    @pytest.fixture
    def importer(self, db: Database) -> GoodreadsImporter:
        return GoodreadsImporter(db)

    def test_parse_export(self, importer: GoodreadsImporter, tmp_import_dir: Path):
        csv_content = """Title,Author,My Rating,Date Read,Exclusive Shelf
"The Name of the Wind","Patrick Rothfuss",5,2024-01-01,read
"Some Book","Some Author",3,2024-01-02,read
"To Read Book","Another Author",0,,to-read
"""
        file_path = tmp_import_dir / "goodreads_export.csv"
        file_path.write_text(csv_content)

        result = importer.parse_file(file_path)

        # Should include read books
        assert len(result) >= 2

        # Check loved status (rating >= 4 is loved)
        name_of_wind = next((item, src) for item, src in result if "Name of the Wind" in item.title)
        assert name_of_wind[1].source_loved is True  # 5 stars


class TestImportFromFile:
    """Integration tests for the full import flow."""

    def test_import_adds_items_and_sources(self, db: Database, tmp_import_dir: Path):
        importer = SpotifyImporter(db)

        data = {"tracks": [{"artist": "Artist", "album": "Album", "track": "Song"}]}
        file_path = tmp_import_dir / "library.json"
        file_path.write_text(json.dumps(data))

        result = importer.import_from_file(file_path)

        assert result.items_added == 1
        assert result.items_updated == 0
        assert result.errors == []

        # Verify item was added
        items = db.get_items_by_category(Category.MUSIC)
        assert len(items) == 1
        assert items[0].title == "Song"

    def test_import_deduplicates_same_source(self, db: Database, tmp_import_dir: Path):
        importer = SpotifyImporter(db)

        data = {"tracks": [{"artist": "Artist", "album": "Album", "track": "Song"}]}
        file_path = tmp_import_dir / "library.json"
        file_path.write_text(json.dumps(data))

        # Import first time
        result1 = importer.import_from_file(file_path)
        assert result1.items_added == 1

        # Import second time - existing item found by source lookup
        importer.import_from_file(file_path)

        # The importer should find the existing item by source_id
        # Either added or updated, but not both (and total items should still be 1)
        items = db.get_items_by_category(Category.MUSIC)
        assert len(items) == 1

    def test_import_handles_parse_error(self, db: Database, tmp_import_dir: Path):
        importer = SpotifyImporter(db)

        file_path = tmp_import_dir / "invalid.json"
        file_path.write_text("not valid json")

        result = importer.import_from_file(file_path)

        assert result.items_added == 0
        assert len(result.errors) == 1
        assert "Failed to parse" in result.errors[0]

    def test_import_updates_sync_state(self, db: Database, tmp_import_dir: Path):
        importer = SpotifyImporter(db)

        data = {"tracks": []}
        file_path = tmp_import_dir / "library.json"
        file_path.write_text(json.dumps(data))

        importer.import_from_file(file_path)

        state = db.get_sync_state(Source.SPOTIFY)
        assert state is not None

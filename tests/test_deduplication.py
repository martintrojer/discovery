"""Tests for deduplication across imports and manual adds."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from discovery.cli import cli
from discovery.db import Database
from discovery.importers.spotify import SpotifyImporter
from discovery.models import Category, Item, ItemSource, Source


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Database]:
    """Create a temporary database and patch the CLI to use it."""
    db_path = tmp_path / "test.db"
    import discovery.db as db_module

    monkeypatch.setattr(db_module, "DEFAULT_DB_PATH", db_path)
    db = Database(db_path=db_path)
    yield db
    db.close()


class TestImportDeduplication:
    """Test that importing the same data multiple times doesn't create duplicates."""

    def test_reimport_same_file_no_duplicates(self, tmp_path: Path) -> None:
        """Importing the same file twice should not create duplicates."""
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)

        importer = SpotifyImporter(db)

        data = {
            "tracks": [
                {"artist": "Pink Floyd", "album": "Dark Side", "track": "Money"},
                {"artist": "Led Zeppelin", "album": "IV", "track": "Stairway"},
            ]
        }
        file_path = tmp_path / "library.json"
        file_path.write_text(json.dumps(data))

        # Import first time
        result1 = importer.import_from_file(file_path)
        assert result1.items_added == 2
        assert result1.items_updated == 0

        # Import again - should update, not add
        result2 = importer.import_from_file(file_path)
        assert result2.items_added == 0
        assert result2.items_updated == 2

        # Total items should still be 2
        items = db.get_items_by_category(Category.MUSIC)
        assert len(items) == 2

        db.close()

    def test_incremental_import_adds_only_new(self, tmp_path: Path) -> None:
        """Importing with new items should only add the new ones."""
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)

        importer = SpotifyImporter(db)

        # First import
        data1 = {"tracks": [{"artist": "Artist A", "album": "Album", "track": "Song 1"}]}
        file1 = tmp_path / "lib1.json"
        file1.write_text(json.dumps(data1))

        result1 = importer.import_from_file(file1)
        assert result1.items_added == 1

        # Second import with one old and one new
        data2 = {
            "tracks": [
                {"artist": "Artist A", "album": "Album", "track": "Song 1"},  # existing
                {"artist": "Artist B", "album": "Album", "track": "Song 2"},  # new
            ]
        }
        file2 = tmp_path / "lib2.json"
        file2.write_text(json.dumps(data2))

        result2 = importer.import_from_file(file2)
        assert result2.items_added == 1
        assert result2.items_updated == 1

        # Total should be 2
        items = db.get_items_by_category(Category.MUSIC)
        assert len(items) == 2

        db.close()

    def test_cross_source_deduplication(self, tmp_path: Path) -> None:
        """Items from different sources with same title/creator should be linked."""
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)

        # Add an item manually first
        item = Item(id="manual-1", category=Category.MUSIC, title="Money", creator="Pink Floyd")
        db.upsert_item(item)
        db.upsert_item_source(ItemSource(item_id="manual-1", source=Source.MANUAL, source_id="manual-1"))

        # Now import from Spotify with same track
        importer = SpotifyImporter(db)
        data = {"tracks": [{"artist": "Pink Floyd", "album": "Dark Side", "track": "Money"}]}
        file_path = tmp_path / "library.json"
        file_path.write_text(json.dumps(data))

        result = importer.import_from_file(file_path)

        # Should recognize as existing and update (link to existing item)
        assert result.items_updated == 1
        assert result.items_added == 0

        # Should still have only 1 item
        items = db.get_items_by_category(Category.MUSIC)
        assert len(items) == 1

        # Item should now have 2 sources
        sources = db.get_item_sources("manual-1")
        assert len(sources) == 2
        source_types = {s.source for s in sources}
        assert Source.MANUAL in source_types
        assert Source.SPOTIFY in source_types

        db.close()

    def test_fuzzy_fallback_dedup_when_search_misses(self, tmp_path: Path) -> None:
        """Fallback fuzzy scan should match when DB search returns no candidates."""
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)

        item = Item(
            id="manual-2",
            category=Category.MUSIC,
            title="Star Wars Episode IV",
            creator="John Williams",
        )
        db.upsert_item(item)
        db.upsert_item_source(ItemSource(item_id="manual-2", source=Source.MANUAL, source_id="manual-2"))

        importer = SpotifyImporter(db)
        data = {"tracks": [{"artist": "John Williams", "album": "Themes", "track": "Star Wars: Episode IV"}]}
        file_path = tmp_path / "library.json"
        file_path.write_text(json.dumps(data))

        result = importer.import_from_file(file_path)

        assert result.items_added == 0
        assert result.items_updated == 1

        items = db.get_items_by_category(Category.MUSIC)
        assert len(items) == 1

        sources = db.get_item_sources("manual-2")
        source_types = {s.source for s in sources}
        assert Source.MANUAL in source_types
        assert Source.SPOTIFY in source_types

        db.close()


class TestManualAddDeduplication:
    """Test that manual adds don't create duplicates."""

    def test_add_same_item_twice_rejected(self, runner: CliRunner, cli_db: Database) -> None:
        """Adding the same item twice should be rejected."""
        result1 = runner.invoke(cli, ["add", "The Matrix", "-c", "movie", "-a", "Wachowskis"])
        assert "Added:" in result1.output

        result2 = runner.invoke(cli, ["add", "The Matrix", "-c", "movie", "-a", "Wachowskis"])
        assert "already exists" in result2.output

        # Should have only 1 item
        items = cli_db.get_items_by_category(Category.MOVIE)
        assert len(items) == 1

    def test_add_same_title_different_creator_allowed(self, runner: CliRunner, cli_db: Database) -> None:
        """Same title with different creator should be allowed (different item)."""
        result1 = runner.invoke(cli, ["add", "Avatar", "-c", "movie", "-a", "James Cameron"])
        assert "Added:" in result1.output

        result2 = runner.invoke(cli, ["add", "Avatar", "-c", "tv", "-a", "Nickelodeon"])
        assert "Added:" in result2.output

        # Should have 2 items in different categories
        movies = cli_db.get_items_by_category(Category.MOVIE)
        tv = cli_db.get_items_by_category(Category.TV)
        assert len(movies) == 1
        assert len(tv) == 1

    def test_add_after_import_no_duplicate(self, runner: CliRunner, cli_db: Database, tmp_path: Path) -> None:
        """Adding an item that was already imported should be rejected."""
        # Import a song
        data = {"tracks": [{"artist": "Pink Floyd", "album": "Dark Side", "track": "Money"}]}
        file_path = tmp_path / "library.json"
        file_path.write_text(json.dumps(data))

        runner.invoke(cli, ["import", "spotify", str(file_path)])

        # Try to add the same item manually
        result = runner.invoke(cli, ["add", "Money", "-c", "music", "-a", "Pink Floyd"])

        # Should be rejected as duplicate
        assert "already exists" in result.output

        # Should still have only 1 item
        items = cli_db.get_items_by_category(Category.MUSIC)
        assert len(items) == 1

    def test_case_insensitive_duplicate_detection(self, runner: CliRunner, cli_db: Database) -> None:
        """Duplicate detection should be case-insensitive."""
        result1 = runner.invoke(cli, ["add", "The Matrix", "-c", "movie"])
        assert "Added:" in result1.output

        result2 = runner.invoke(cli, ["add", "THE MATRIX", "-c", "movie"])
        assert "already exists" in result2.output

        items = cli_db.get_items_by_category(Category.MOVIE)
        assert len(items) == 1

    def test_fuzzy_match_prompts_user(self, runner: CliRunner, cli_db: Database) -> None:
        """Similar titles should prompt user with 'did you mean?'."""
        # Add an item first
        runner.invoke(cli, ["add", "Dark Souls", "-c", "game", "-a", "FromSoftware"])

        # Try to add a similar item (substring match) - should prompt
        result = runner.invoke(cli, ["add", "Dark Souls Remastered", "-c", "game"], input="2\n")

        # Should show "Did you mean" prompt
        assert "Did you mean" in result.output
        assert "Dark Souls" in result.output

    def test_fuzzy_match_user_selects_existing(self, runner: CliRunner, cli_db: Database) -> None:
        """User can select existing item from fuzzy match prompt."""
        runner.invoke(cli, ["add", "The Matrix", "-c", "movie", "-a", "Wachowskis"])

        # Add similar item and select option 1 (existing) with love flag
        result = runner.invoke(cli, ["add", "Matrix", "-c", "movie", "-l"], input="1\n")

        # Should have updated existing item
        assert "Updated:" in result.output

        # Should still have only 1 item
        items = cli_db.get_items_by_category(Category.MOVIE)
        assert len(items) == 1

        # Verify the love flag was applied
        loved = cli_db.get_all_loved_items()
        assert len(loved) == 1
        assert loved[0].title == "The Matrix"  # Original title preserved

    def test_fuzzy_match_user_adds_new(self, runner: CliRunner, cli_db: Database) -> None:
        """User can choose to add as new item from fuzzy match prompt."""
        runner.invoke(cli, ["add", "Dark Knight", "-c", "movie"])

        # Add similar but different item and select "add as new" (option 2)
        result = runner.invoke(cli, ["add", "Dark Knight Rises", "-c", "movie"], input="2\n")

        assert "Added:" in result.output

        # Should have 2 items now
        items = cli_db.get_items_by_category(Category.MOVIE)
        assert len(items) == 2

    def test_force_flag_bypasses_fuzzy_match(self, runner: CliRunner, cli_db: Database) -> None:
        """Force flag should bypass fuzzy matching check."""
        runner.invoke(cli, ["add", "Dark Souls", "-c", "game"])

        # Force add similar item
        result = runner.invoke(cli, ["add", "Dark Souls II", "-c", "game", "-f"])

        # Should add without prompting
        assert "Added:" in result.output
        assert "Did you mean" not in result.output

        items = cli_db.get_items_by_category(Category.GAME)
        assert len(items) == 2


class TestLoveDislikeDeduplication:
    """Test that love/dislike commands work on existing items."""

    def test_love_imported_item(self, runner: CliRunner, cli_db: Database, tmp_path: Path) -> None:
        """Loving an imported item should update it, not create new."""
        # Import an item
        data = {"tracks": [{"artist": "Artist", "album": "Album", "track": "Song"}]}
        file_path = tmp_path / "library.json"
        file_path.write_text(json.dumps(data))
        runner.invoke(cli, ["import", "spotify", str(file_path)])

        # Love it
        result = runner.invoke(cli, ["love", "Song"])
        assert "Loved: Song" in result.output

        # Should still have only 1 item
        items = cli_db.get_items_by_category(Category.MUSIC)
        assert len(items) == 1

        # Should be loved
        loved = cli_db.get_all_loved_items()
        assert len(loved) == 1

    def test_dislike_imported_item(self, runner: CliRunner, cli_db: Database, tmp_path: Path) -> None:
        """Disliking an imported item should update it, not create new."""
        # Import an item
        data = {"tracks": [{"artist": "Artist", "album": "Album", "track": "Bad Song"}]}
        file_path = tmp_path / "library.json"
        file_path.write_text(json.dumps(data))
        runner.invoke(cli, ["import", "spotify", str(file_path)])

        # Dislike it
        result = runner.invoke(cli, ["dislike", "Bad Song"])
        assert "Disliked: Bad Song" in result.output

        # Should still have only 1 item
        items = cli_db.get_items_by_category(Category.MUSIC)
        assert len(items) == 1

        # Should be disliked
        disliked = cli_db.get_all_disliked_items()
        assert len(disliked) == 1


class TestFuzzyDeduplication:
    """Test fuzzy title matching for deduplication."""

    def test_article_prefix_normalized(self, tmp_path: Path) -> None:
        """'The Matrix' and 'Matrix' should be recognized as same."""
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)

        # Add 'Matrix' first
        db.upsert_item(Item(id="1", category=Category.MOVIE, title="Matrix", creator="Wachowskis"))
        db.upsert_item_source(ItemSource(item_id="1", source=Source.MANUAL, source_id="1"))

        # Add 'The Matrix' - should not create duplicate if properly normalized
        existing = db.search_items("Matrix", category=Category.MOVIE)
        assert len(existing) >= 1

        db.close()

    def test_case_insensitive_matching(self, tmp_path: Path) -> None:
        """Case differences should not create duplicates."""
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)

        db.upsert_item(Item(id="1", category=Category.GAME, title="Dark Souls", creator="FromSoftware"))

        # Search should find regardless of case
        results = db.search_items("DARK SOULS")
        assert len(results) == 1
        assert results[0].title == "Dark Souls"

        db.close()

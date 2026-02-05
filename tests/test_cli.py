"""Integration tests for CLI commands."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from discovery.cli import cli
from discovery.db import Database
from discovery.models import Category, Item, Rating, WishlistItem


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Database]:
    """Create a temporary database and patch the CLI to use it."""
    db_path = tmp_path / "test.db"

    # Patch the DEFAULT_DB_PATH constant
    import discovery.db as db_module

    monkeypatch.setattr(db_module, "DEFAULT_DB_PATH", db_path)

    db = Database(db_path=db_path)
    yield db
    db.close()


class TestStatusCommand:
    def test_status_empty_library(self, runner: CliRunner, cli_db: Database) -> None:
        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "Discovery Library Status" in result.output
        assert "Total items: 0" in result.output
        assert "Wishlist: 0" in result.output

    def test_status_with_items(self, runner: CliRunner, cli_db: Database) -> None:
        # Add some items
        cli_db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song 1"))
        cli_db.upsert_item(Item(id="2", category=Category.MUSIC, title="Song 2"))
        cli_db.upsert_rating(Rating(item_id="1", loved=True))

        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "music" in result.output
        assert "2 items" in result.output
        assert "1 loved" in result.output

    def test_status_json_format(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song 1"))
        cli_db.upsert_rating(Rating(item_id="1", loved=True))
        cli_db.add_wishlist_item(WishlistItem(id="w1", category=Category.MUSIC, title="Wish 1"))

        result = runner.invoke(cli, ["status", "-f", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["totals"]["items"] == 1
        assert data["totals"]["loved"] == 1
        assert data["totals"]["wishlist"] == 1
        assert data["categories"]["music"]["total"] == 1
        assert data["categories"]["music"]["loved"] == 1
        assert data["categories"]["music"]["wishlist"] == 1


class TestAddCommand:
    def test_add_basic_item(self, runner: CliRunner, cli_db: Database) -> None:
        result = runner.invoke(cli, ["add", "Test Movie", "-c", "movie"])

        assert result.exit_code == 0
        assert "Added: [movie] Test Movie" in result.output

        # Verify item was added
        items = cli_db.get_items_by_category(Category.MOVIE)
        assert len(items) == 1
        assert items[0].title == "Test Movie"

    def test_add_with_creator(self, runner: CliRunner, cli_db: Database) -> None:
        result = runner.invoke(cli, ["add", "Inception", "-c", "movie", "-a", "Christopher Nolan"])

        assert result.exit_code == 0
        assert "Inception by Christopher Nolan" in result.output

        items = cli_db.get_items_by_category(Category.MOVIE)
        assert items[0].creator == "Christopher Nolan"

    def test_add_loved_item(self, runner: CliRunner, cli_db: Database) -> None:
        result = runner.invoke(cli, ["add", "Great Game", "-c", "game", "-l"])

        assert result.exit_code == 0
        assert "Loved: yes" in result.output

        loved = cli_db.get_all_loved_items()
        assert len(loved) == 1

    def test_add_disliked_item(self, runner: CliRunner, cli_db: Database) -> None:
        result = runner.invoke(cli, ["add", "Bad Movie", "-c", "movie", "-d"])

        assert result.exit_code == 0
        assert "Disliked: yes" in result.output

        disliked = cli_db.get_all_disliked_items()
        assert len(disliked) == 1

    def test_add_with_rating(self, runner: CliRunner, cli_db: Database) -> None:
        result = runner.invoke(cli, ["add", "Great Book", "-c", "book", "-l", "-r", "5"])

        assert result.exit_code == 0
        assert "Rating: [*****]" in result.output

    def test_add_duplicate_rejected(self, runner: CliRunner, cli_db: Database) -> None:
        runner.invoke(cli, ["add", "Test", "-c", "movie"])
        result = runner.invoke(cli, ["add", "Test", "-c", "movie"])

        assert result.exit_code == 0
        assert "already exists" in result.output

    def test_add_force_skips_duplicate_check(self, runner: CliRunner, cli_db: Database) -> None:
        runner.invoke(cli, ["add", "Test Movie", "-c", "movie"])
        # Force add same item
        result = runner.invoke(cli, ["add", "Test Movie", "-c", "movie", "-f"])

        assert "Added:" in result.output

        # Should now have 2 items
        items = cli_db.get_items_by_category(Category.MOVIE)
        assert len(items) == 2


class TestUpdateCommand:
    def test_update_creator(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.GAME, title="Elden Ring"))

        result = runner.invoke(cli, ["update", "Elden Ring", "-a", "FromSoftware"])

        assert result.exit_code == 0
        assert "Updated:" in result.output

        item = cli_db.get_item("1")
        assert item is not None
        assert item.creator == "FromSoftware"

    def test_update_title(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MOVIE, title="The Matrx"))

        result = runner.invoke(cli, ["update", "Matrx", "-t", "The Matrix"])

        assert "Updated: The Matrix" in result.output

        item = cli_db.get_item("1")
        assert item is not None
        assert item.title == "The Matrix"

    def test_update_rating(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.BOOK, title="Test Book"))

        result = runner.invoke(cli, ["update", "Test Book", "-r", "5"])

        assert "Rating: [*****]" in result.output

        rating = cli_db.get_rating("1")
        assert rating is not None
        assert rating.rating == 5

    def test_update_loved_status(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MUSIC, title="Test Song"))

        result = runner.invoke(cli, ["update", "Test Song", "-l"])

        assert "Loved: yes" in result.output

        loved = cli_db.get_all_loved_items()
        assert len(loved) == 1

    def test_update_unlove(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.GAME, title="Test Game"))
        cli_db.upsert_rating(Rating(item_id="1", loved=True))

        result = runner.invoke(cli, ["update", "Test Game", "-u"])

        assert "Updated:" in result.output
        assert "Loved:" not in result.output

        rating = cli_db.get_rating("1")
        assert rating is not None
        assert rating.loved is None

    def test_update_notes(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.TV, title="Test Show"))

        result = runner.invoke(cli, ["update", "Test Show", "-n", "Great show!"])

        assert "Notes: Great show!" in result.output

    def test_update_no_changes(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MOVIE, title="Test"))

        result = runner.invoke(cli, ["update", "Test"])

        assert result.exit_code == 0
        assert "No changes specified" in result.output


class TestLoveCommand:
    def test_love_item(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.GAME, title="Elden Ring"))

        result = runner.invoke(cli, ["love", "Elden Ring"])

        assert result.exit_code == 0
        assert "Loved: Elden Ring" in result.output

        loved = cli_db.get_all_loved_items()
        assert len(loved) == 1

    def test_love_with_rating(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.BOOK, title="Test Book"))

        result = runner.invoke(cli, ["love", "Test Book", "-r", "5"])

        assert result.exit_code == 0
        assert "Rating: [*****]" in result.output

    def test_love_not_found(self, runner: CliRunner, cli_db: Database) -> None:
        result = runner.invoke(cli, ["love", "Nonexistent"])

        assert result.exit_code == 0
        assert "No items found matching" in result.output
        assert cli_db.get_all_loved_items() == []


class TestDislikeCommand:
    def test_dislike_item(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.TV, title="Bad Show"))

        result = runner.invoke(cli, ["dislike", "Bad Show"])

        assert result.exit_code == 0
        assert "Disliked: Bad Show" in result.output

        disliked = cli_db.get_all_disliked_items()
        assert len(disliked) == 1

    def test_dislike_with_notes(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MOVIE, title="Bad Movie"))

        result = runner.invoke(cli, ["dislike", "Bad Movie", "-n", "Terrible ending"])

        assert result.exit_code == 0
        assert "Notes: Terrible ending" in result.output


class TestLovedCommand:
    def test_loved_empty(self, runner: CliRunner, cli_db: Database) -> None:
        result = runner.invoke(cli, ["loved"])

        assert result.exit_code == 0
        assert "No loved items" in result.output

    def test_loved_lists_items(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MUSIC, title="Great Song", creator="Artist"))
        cli_db.upsert_rating(Rating(item_id="1", loved=True))

        result = runner.invoke(cli, ["loved"])

        assert result.exit_code == 0
        assert "1 loved items" in result.output
        assert "Great Song" in result.output

    def test_loved_filter_category(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song"))
        cli_db.upsert_item(Item(id="2", category=Category.GAME, title="Game"))
        cli_db.upsert_rating(Rating(item_id="1", loved=True))
        cli_db.upsert_rating(Rating(item_id="2", loved=True))

        result = runner.invoke(cli, ["loved", "-c", "music"])

        assert "Song" in result.output
        assert "Game" not in result.output


class TestDislikedCommand:
    def test_disliked_empty(self, runner: CliRunner, cli_db: Database) -> None:
        result = runner.invoke(cli, ["disliked"])

        assert result.exit_code == 0
        assert "No disliked items" in result.output

    def test_disliked_lists_items(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.TV, title="Bad Show"))
        cli_db.upsert_rating(Rating(item_id="1", loved=False))

        result = runner.invoke(cli, ["disliked"])

        assert result.exit_code == 0
        assert "1 disliked items" in result.output
        assert "Bad Show" in result.output


class TestWishlistCommands:
    def test_wishlist_add(self, runner: CliRunner, cli_db: Database) -> None:
        result = runner.invoke(cli, ["wishlist", "add", "Dune", "-c", "book", "-a", "Frank Herbert"])

        assert result.exit_code == 0
        assert "Wishlist added" in result.output

        items = cli_db.get_wishlist_items(category=Category.BOOK)
        assert len(items) == 1
        assert items[0].title == "Dune"

    def test_wishlist_add_duplicate(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.add_wishlist_item(WishlistItem(id="1", category=Category.BOOK, title="Dune", creator="Frank Herbert"))

        result = runner.invoke(cli, ["wishlist", "add", "Dune", "-c", "book", "-a", "Frank Herbert"])

        assert result.exit_code == 0
        assert "Wishlist item already exists" in result.output

        items = cli_db.get_wishlist_items(category=Category.BOOK)
        assert len(items) == 1

    def test_wishlist_add_duplicate_without_creator(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.add_wishlist_item(WishlistItem(id="1", category=Category.BOOK, title="Dune"))

        result = runner.invoke(cli, ["wishlist", "add", "Dune", "-c", "book"])

        assert result.exit_code == 0
        assert "Wishlist item already exists" in result.output

        items = cli_db.get_wishlist_items(category=Category.BOOK)
        assert len(items) == 1

    def test_wishlist_view(self, runner: CliRunner, cli_db: Database) -> None:
        from discovery.models import WishlistItem

        cli_db.add_wishlist_item(WishlistItem(id="1", category=Category.MUSIC, title="Album A"))
        cli_db.add_wishlist_item(WishlistItem(id="2", category=Category.GAME, title="Game B"))

        result = runner.invoke(cli, ["wishlist", "view"])

        assert result.exit_code == 0
        assert "wishlist items" in result.output
        assert "Album A" in result.output
        assert "Game B" in result.output

    def test_wishlist_view_search_category(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.add_wishlist_item(WishlistItem(id="1", category=Category.MUSIC, title="Album A", creator="Artist A"))
        cli_db.add_wishlist_item(WishlistItem(id="2", category=Category.GAME, title="Game B", creator="Studio B"))

        result = runner.invoke(cli, ["wishlist", "view", "-c", "music", "-s", "Artist"])

        assert result.exit_code == 0
        assert "Album A" in result.output
        assert "Game B" not in result.output

    def test_wishlist_remove(self, runner: CliRunner, cli_db: Database) -> None:
        from discovery.models import WishlistItem

        cli_db.add_wishlist_item(WishlistItem(id="1", category=Category.MOVIE, title="Blade Runner"))

        result = runner.invoke(cli, ["wishlist", "remove", "Blade Runner"])

        assert result.exit_code == 0
        assert "Wishlist removed" in result.output
        assert cli_db.get_wishlist_item("1") is None

    def test_wishlist_prune(self, runner: CliRunner, cli_db: Database) -> None:
        from discovery.models import WishlistItem

        cli_db.add_wishlist_item(WishlistItem(id="1", category=Category.MUSIC, title="The Wall"))
        cli_db.upsert_item(Item(id="a", category=Category.MUSIC, title="The Wall", creator="Pink Floyd"))

        result = runner.invoke(cli, ["wishlist", "prune", "-c", "music"])

        assert result.exit_code == 0
        assert "Pruned 1 wishlist item" in result.output
        assert cli_db.get_wishlist_item("1") is None

    def test_wishlist_prune_creator_mismatch(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.add_wishlist_item(WishlistItem(id="1", category=Category.MUSIC, title="Halo", creator="Radiohead"))
        cli_db.upsert_item(Item(id="a", category=Category.MUSIC, title="Halo", creator="Dostoevsky"))

        result = runner.invoke(cli, ["wishlist", "prune", "-c", "music"])

        assert result.exit_code == 0
        assert "No wishlist items to prune" in result.output
        assert cli_db.get_wishlist_item("1") is not None

    def test_auto_prune_on_add(self, runner: CliRunner, cli_db: Database) -> None:
        from discovery.models import WishlistItem

        cli_db.add_wishlist_item(WishlistItem(id="1", category=Category.BOOK, title="Dune"))

        result = runner.invoke(cli, ["add", "Dune", "-c", "book"])

        assert result.exit_code == 0
        assert "Pruned 1 wishlist item" in result.output
        assert cli_db.get_wishlist_item("1") is None

    def test_auto_prune_on_import(self, runner: CliRunner, cli_db: Database, tmp_path: Path) -> None:
        cli_db.add_wishlist_item(WishlistItem(id="1", category=Category.MUSIC, title="Song A", creator="Artist"))

        data = {"tracks": [{"artist": "Artist", "album": "Album", "track": "Song A"}]}
        file_path = tmp_path / "library.json"
        file_path.write_text(json.dumps(data))

        result = runner.invoke(cli, ["import", "spotify", str(file_path)])

        assert result.exit_code == 0
        assert "Pruned 1 wishlist item" in result.output
        assert cli_db.get_wishlist_item("1") is None


class TestQueryCommand:
    def test_query_count(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song 1"))
        cli_db.upsert_item(Item(id="2", category=Category.MUSIC, title="Song 2"))

        result = runner.invoke(cli, ["query", "--count"])

        assert result.exit_code == 0
        assert "Count: 2" in result.output

    def test_query_count_by_category(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song"))
        cli_db.upsert_item(Item(id="2", category=Category.GAME, title="Game"))

        result = runner.invoke(cli, ["query", "-c", "music", "--count"])

        assert result.exit_code == 0
        assert "Count (music): 1" in result.output

    def test_query_loved(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MUSIC, title="Loved Song"))
        cli_db.upsert_item(Item(id="2", category=Category.MUSIC, title="Other Song"))
        cli_db.upsert_rating(Rating(item_id="1", loved=True))

        result = runner.invoke(cli, ["query", "-l"])

        assert result.exit_code == 0
        assert "Loved Song" in result.output
        assert "Other Song" not in result.output

    def test_query_disliked(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MOVIE, title="Bad Movie"))
        cli_db.upsert_rating(Rating(item_id="1", loved=False))

        result = runner.invoke(cli, ["query", "-d"])

        assert result.exit_code == 0
        assert "Bad Movie" in result.output

    def test_query_pagination(self, runner: CliRunner, cli_db: Database) -> None:
        for i in range(30):
            cli_db.upsert_item(Item(id=str(i), category=Category.MUSIC, title=f"Song {i:02d}"))

        result = runner.invoke(cli, ["query", "-n", "10"])

        assert result.exit_code == 0
        assert "10 of 30" in result.output
        assert "--offset 10" in result.output

    def test_query_json_format(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MUSIC, title="Test Song", metadata={"album": "Test Album"}))

        result = runner.invoke(cli, ["query", "-f", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total" in data
        assert "items" in data
        assert len(data["items"]) == 1
        assert "sources" in data["items"][0]
        assert "category" in data["items"][0]
        assert data["items"][0]["metadata"] == {"album": "Test Album"}

    def test_query_text_shows_metadata(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.MUSIC, title="Test Song", metadata={"album": "Test Album"}))

        result = runner.invoke(cli, ["query"])

        assert result.exit_code == 0
        assert 'metadata: {"album": "Test Album"}' in result.output

    def test_query_search(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.GAME, title="Dark Souls"))
        cli_db.upsert_item(Item(id="2", category=Category.GAME, title="Elden Ring"))

        result = runner.invoke(cli, ["query", "-s", "souls"])

        assert result.exit_code == 0
        assert "Dark Souls" in result.output
        assert "Elden Ring" not in result.output

    def test_query_by_creator(self, runner: CliRunner, cli_db: Database) -> None:
        cli_db.upsert_item(Item(id="1", category=Category.GAME, title="Elden Ring", creator="FromSoftware"))
        cli_db.upsert_item(Item(id="2", category=Category.GAME, title="Zelda", creator="Nintendo"))

        result = runner.invoke(cli, ["query", "-a", "FromSoftware"])

        assert result.exit_code == 0
        assert "Elden Ring" in result.output
        assert "Zelda" not in result.output

    def test_query_shows_sources(self, runner: CliRunner, cli_db: Database) -> None:
        from discovery.models import ItemSource, Source

        cli_db.upsert_item(Item(id="1", category=Category.MUSIC, title="Test Song"))
        cli_db.upsert_item_source(ItemSource(item_id="1", source=Source.SPOTIFY, source_id="123"))

        result = runner.invoke(cli, ["query"])

        assert result.exit_code == 0
        assert "[spotify" in result.output
        assert "Test Song" in result.output


class TestImportCommands:
    def test_import_help_setup(self, runner: CliRunner, cli_db: Database, tmp_path: Path) -> None:
        # Create a dummy file since the argument is required
        dummy_file = tmp_path / "dummy.json"
        dummy_file.write_text("{}")

        result = runner.invoke(cli, ["import", "spotify", str(dummy_file), "--help-setup"])

        # Should show setup instructions without error
        assert result.exit_code == 0
        assert "Spotify" in result.output

    def test_import_spotify(self, runner: CliRunner, cli_db: Database, tmp_path: Path) -> None:
        # Create test file
        data = {"tracks": [{"artist": "Artist", "album": "Album", "track": "Song"}]}
        file_path = tmp_path / "library.json"
        file_path.write_text(json.dumps(data))

        result = runner.invoke(cli, ["import", "spotify", str(file_path)])

        assert result.exit_code == 0
        assert "Added:   1" in result.output

    def test_import_netflix(self, runner: CliRunner, cli_db: Database, tmp_path: Path) -> None:
        csv_content = """Title,Date
"Breaking Bad: Season 1: Pilot","2024-01-01"
"""
        file_path = tmp_path / "viewing.csv"
        file_path.write_text(csv_content)

        result = runner.invoke(cli, ["import", "netflix", str(file_path)])

        assert result.exit_code == 0
        assert "Added:" in result.output

        # Verify the item was imported correctly
        items = cli_db.get_items_by_category(Category.TV)
        assert len(items) >= 1
        titles = [item.title for item in items]
        assert any("Breaking Bad" in title for title in titles)

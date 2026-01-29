"""Unit tests for status module."""

from discovery.cli_status import format_status_text, get_library_status
from discovery.db import Database
from discovery.models import Category, Item, ItemSource, Rating, Source


class TestGetLibraryStatus:
    def test_empty_library(self, db: Database):
        result = get_library_status(db)

        assert result["totals"]["items"] == 0
        assert result["totals"]["loved"] == 0
        assert result["totals"]["disliked"] == 0

    def test_with_items(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song 1"))
        db.upsert_item(Item(id="2", category=Category.MUSIC, title="Song 2"))
        db.upsert_item(Item(id="3", category=Category.GAME, title="Game 1"))

        result = get_library_status(db)

        assert result["totals"]["items"] == 3
        assert result["categories"]["music"]["total"] == 2
        assert result["categories"]["game"]["total"] == 1

    def test_with_loved_items(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Loved Song"))
        db.upsert_rating(Rating(item_id="1", loved=True))

        result = get_library_status(db)

        assert result["totals"]["loved"] == 1
        assert result["categories"]["music"]["loved"] == 1

    def test_with_source_loved(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Source Loved Song"))
        db.upsert_item_source(ItemSource(item_id="1", source=Source.SPOTIFY, source_id="123", source_loved=True))

        result = get_library_status(db)

        assert result["totals"]["loved"] == 1
        assert result["categories"]["music"]["loved"] == 1

    def test_with_disliked_items(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MOVIE, title="Bad Movie"))
        db.upsert_rating(Rating(item_id="1", loved=False))

        result = get_library_status(db)

        assert result["totals"]["disliked"] == 1
        assert result["categories"]["movie"]["disliked"] == 1

    def test_sample_loved_items(self, db: Database):
        # Create loved items
        for i in range(15):
            db.upsert_item(Item(id=str(i), category=Category.GAME, title=f"Game {i}"))
            db.upsert_rating(Rating(item_id=str(i), loved=True))

        result = get_library_status(db)

        # Should have sample of up to 10 loved items
        assert len(result["sample_loved"]["game"]) <= 10
        assert result["sample_loved"]["game"][0]["title"].startswith("Game")

    def test_sources_tracked(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song"))
        db.upsert_item_source(ItemSource(item_id="1", source=Source.SPOTIFY, source_id="123"))

        result = get_library_status(db)

        assert "spotify" in result["sources"]
        assert result["sources"]["spotify"] == 1


class TestFormatStatusText:
    def test_empty_library(self, db: Database):
        result = format_status_text(db)

        assert "Discovery Library Status" in result
        assert "Total items: 0" in result

    def test_with_items(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Test Song", creator="Artist"))
        db.upsert_rating(Rating(item_id="1", loved=True))

        result = format_status_text(db)

        assert "music: 1 items" in result
        assert "1 loved" in result
        assert "Sample Loved Items" in result
        assert "Test Song" in result

    def test_includes_next_steps(self, db: Database):
        result = format_status_text(db)

        assert "Next Steps" in result
        assert "discovery query" in result

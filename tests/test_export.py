"""Unit tests for export functions."""

import json

from discovery.db import Database
from discovery.export import export_library_json, export_library_summary
from discovery.models import Category, Item, ItemSource, Rating, Source


class TestExportLibrarySummary:
    def test_empty_library(self, db: Database):
        result = export_library_summary(db)
        assert "# Discovery Library Export" in result
        assert "Total items: 0" in result
        assert "Total loved: 0" in result
        assert "Total disliked: 0" in result

    def test_with_loved_items(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Test Song", creator="Test Artist"))
        db.upsert_rating(Rating(item_id="1", loved=True))

        result = export_library_summary(db)
        assert "Total loved: 1" in result
        assert "## Loved Items" in result
        assert "Test Song by Test Artist" in result

    def test_with_disliked_items(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.TV, title="Bad Show"))
        db.upsert_rating(Rating(item_id="1", loved=False))

        result = export_library_summary(db)
        assert "Total disliked: 1" in result
        assert "## Disliked Items" in result
        assert "Bad Show" in result

    def test_with_metadata(self, db: Database):
        db.upsert_item(
            Item(
                id="1",
                category=Category.MUSIC,
                title="Test Song",
                creator="Artist",
                metadata={"genre": "Rock", "year": 2020},
            )
        )
        db.upsert_rating(Rating(item_id="1", loved=True))

        result = export_library_summary(db)
        assert "(Rock, 2020)" in result

    def test_limits_items_per_category(self, db: Database):
        # Create 110 loved items
        for i in range(110):
            db.upsert_item(Item(id=str(i), category=Category.MUSIC, title=f"Song {i}"))
            db.upsert_rating(Rating(item_id=str(i), loved=True))

        result = export_library_summary(db)
        assert "... and 10 more" in result

    def test_write_to_file(self, db: Database, tmp_path):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Test"))

        output_file = tmp_path / "export.txt"
        export_library_summary(db, output_path=output_file)

        assert output_file.exists()
        content = output_file.read_text()
        assert "# Discovery Library Export" in content

    def test_category_filter(self, db: Database):
        """Test that category filter only exports the specified category."""
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Test Song"))
        db.upsert_item(Item(id="2", category=Category.GAME, title="Test Game"))
        db.upsert_item(Item(id="3", category=Category.MOVIE, title="Test Movie"))
        db.upsert_rating(Rating(item_id="1", loved=True))
        db.upsert_rating(Rating(item_id="2", loved=True))
        db.upsert_rating(Rating(item_id="3", loved=True))

        result = export_library_summary(db, category=Category.GAME)

        # Should include game
        assert "GAME" in result
        assert "Test Game" in result

        # Should not include other categories
        assert "Test Song" not in result
        assert "Test Movie" not in result

    def test_category_filter_header(self, db: Database):
        """Test that category filter is reflected in the header."""
        result = export_library_summary(db, category=Category.MUSIC)
        assert "MUSIC" in result

        result_all = export_library_summary(db)
        assert "All Categories" in result_all

    def test_category_filter_stats(self, db: Database):
        """Test that stats are filtered by category."""
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song"))
        db.upsert_item(Item(id="2", category=Category.GAME, title="Game"))
        db.upsert_rating(Rating(item_id="1", loved=True))
        db.upsert_rating(Rating(item_id="2", loved=True))

        result = export_library_summary(db, category=Category.MUSIC)

        assert "Total items: 1" in result
        assert "Total loved: 1" in result


class TestExportLibraryJson:
    def test_empty_library(self, db: Database):
        result = export_library_json(db)

        assert "stats" in result
        assert "source_stats" in result
        assert "loved" in result
        assert "disliked" in result
        assert "all" in result

        # All categories should be empty lists
        for category in Category:
            assert result["loved"][category.value] == []
            assert result["disliked"][category.value] == []
            assert result["all"][category.value] == []

    def test_with_items(self, db: Database):
        db.upsert_item(
            Item(
                id="1",
                category=Category.GAME,
                title="Test Game",
                creator="Studio",
                metadata={"genre": "RPG"},
            )
        )
        db.upsert_rating(Rating(item_id="1", loved=True))

        result = export_library_json(db)

        assert len(result["loved"]["game"]) == 1
        assert result["loved"]["game"][0]["title"] == "Test Game"
        assert result["loved"]["game"][0]["creator"] == "Studio"
        assert result["loved"]["game"][0]["metadata"] == {"genre": "RPG"}

    def test_with_disliked_items(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MOVIE, title="Bad Movie"))
        db.upsert_rating(Rating(item_id="1", loved=False))

        result = export_library_json(db)

        assert len(result["disliked"]["movie"]) == 1
        assert result["disliked"]["movie"][0]["title"] == "Bad Movie"

    def test_source_loved_counts_as_loved(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song"))
        db.upsert_item_source(ItemSource(item_id="1", source=Source.SPOTIFY, source_id="sp:1", source_loved=True))

        result = export_library_json(db)

        assert len(result["loved"]["music"]) == 1

    def test_write_to_file(self, db: Database, tmp_path):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Test"))

        output_file = tmp_path / "export.json"
        export_library_json(db, output_path=output_file)

        assert output_file.exists()
        content = json.loads(output_file.read_text())
        assert "stats" in content

    def test_stats_structure(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song 1"))
        db.upsert_item(Item(id="2", category=Category.MUSIC, title="Song 2"))
        db.upsert_rating(Rating(item_id="1", loved=True))
        db.upsert_item_source(ItemSource(item_id="1", source=Source.SPOTIFY, source_id="sp:1"))

        result = export_library_json(db)

        assert result["stats"]["music"]["total"] == 2
        assert result["stats"]["music"]["loved"] == 1
        assert result["source_stats"]["spotify"] == 1

    def test_category_filter(self, db: Database):
        """Test that category filter only exports the specified category."""
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Test Song"))
        db.upsert_item(Item(id="2", category=Category.GAME, title="Test Game"))
        db.upsert_item(Item(id="3", category=Category.MOVIE, title="Test Movie"))
        db.upsert_rating(Rating(item_id="1", loved=True))
        db.upsert_rating(Rating(item_id="2", loved=True))

        result = export_library_json(db, category=Category.GAME)

        # Should only include game category
        assert "game" in result["loved"]
        assert len(result["loved"]["game"]) == 1
        assert result["loved"]["game"][0]["title"] == "Test Game"

        # Should not include other categories
        assert "music" not in result["loved"]
        assert "movie" not in result["loved"]

    def test_category_filter_stats(self, db: Database):
        """Test that stats are filtered by category."""
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song"))
        db.upsert_item(Item(id="2", category=Category.GAME, title="Game"))

        result = export_library_json(db, category=Category.MUSIC)

        # Stats should only include music
        assert "music" in result["stats"]
        assert "game" not in result["stats"]

    def test_category_filter_disliked(self, db: Database):
        """Test that disliked items are filtered by category."""
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Bad Song"))
        db.upsert_item(Item(id="2", category=Category.GAME, title="Bad Game"))
        db.upsert_rating(Rating(item_id="1", loved=False))
        db.upsert_rating(Rating(item_id="2", loved=False))

        result = export_library_json(db, category=Category.GAME)

        assert len(result["disliked"]["game"]) == 1
        assert result["disliked"]["game"][0]["title"] == "Bad Game"
        assert "music" not in result["disliked"]

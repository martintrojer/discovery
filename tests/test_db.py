"""Unit tests for database layer."""

from datetime import datetime
from pathlib import Path

from discovery.db import Database
from discovery.models import Category, Item, ItemSource, Rating, Source, SyncState


class TestDatabaseInit:
    def test_creates_db_file(self, tmp_db_path: Path):
        db = Database(db_path=tmp_db_path)
        assert tmp_db_path.exists()
        db.close()

    def test_creates_parent_directory(self, tmp_path: Path):
        nested_path = tmp_path / "nested" / "dir" / "test.db"
        db = Database(db_path=nested_path)
        assert nested_path.exists()
        db.close()

    def test_context_manager(self, tmp_path: Path):
        db_path = tmp_path / "context.db"
        with Database(db_path=db_path) as db:
            db.upsert_item(Item(id="1", category=Category.MUSIC, title="Test"))
            assert db.get_item("1") is not None

        # After exiting context, connection is closed
        # Verify data persisted by opening a new connection
        db2 = Database(db_path=db_path)
        assert db2.get_item("1") is not None
        db2.close()


class TestItemOperations:
    def test_upsert_and_get_item(self, db: Database):
        item = Item(
            id="item-1",
            category=Category.MUSIC,
            title="Test Song",
            creator="Test Artist",
            metadata={"album": "Test Album"},
        )
        db.upsert_item(item)

        retrieved = db.get_item("item-1")
        assert retrieved is not None
        assert retrieved.id == "item-1"
        assert retrieved.category == Category.MUSIC
        assert retrieved.title == "Test Song"
        assert retrieved.creator == "Test Artist"
        assert retrieved.metadata == {"album": "Test Album"}

    def test_get_nonexistent_item(self, db: Database):
        result = db.get_item("nonexistent")
        assert result is None

    def test_upsert_updates_existing(self, db: Database):
        item = Item(id="item-1", category=Category.MUSIC, title="Original Title")
        db.upsert_item(item)

        item.title = "Updated Title"
        db.upsert_item(item)

        retrieved = db.get_item("item-1")
        assert retrieved is not None
        assert retrieved.title == "Updated Title"

    def test_search_items_by_title(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Dark Side of the Moon"))
        db.upsert_item(Item(id="2", category=Category.MUSIC, title="The Dark Knight"))
        db.upsert_item(Item(id="3", category=Category.MUSIC, title="Light of Day"))

        results = db.search_items("dark")
        assert len(results) == 2
        titles = {r.title for r in results}
        assert "Dark Side of the Moon" in titles
        assert "The Dark Knight" in titles

    def test_search_items_by_creator(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song A", creator="Pink Floyd"))
        db.upsert_item(Item(id="2", category=Category.MUSIC, title="Song B", creator="Floyd Patterson"))
        db.upsert_item(Item(id="3", category=Category.MUSIC, title="Song C", creator="The Beatles"))

        results = db.search_items("floyd")
        assert len(results) == 2

    def test_search_items_by_category(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Dark Song"))
        db.upsert_item(Item(id="2", category=Category.GAME, title="Dark Souls"))

        music_results = db.search_items("dark", category=Category.MUSIC)
        assert len(music_results) == 1
        assert music_results[0].title == "Dark Song"

    def test_search_items_loved_only(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Dark Song 1"))
        db.upsert_item(Item(id="2", category=Category.MUSIC, title="Dark Song 2"))
        db.upsert_rating(Rating(item_id="1", loved=True))

        results = db.search_items("dark", loved_only=True)
        assert len(results) == 1
        assert results[0].id == "1"

    def test_get_items_by_category(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song"))
        db.upsert_item(Item(id="2", category=Category.GAME, title="Game"))
        db.upsert_item(Item(id="3", category=Category.MUSIC, title="Another Song"))

        music = db.get_items_by_category(Category.MUSIC)
        assert len(music) == 2

        games = db.get_items_by_category(Category.GAME)
        assert len(games) == 1

    def test_get_all_loved_items(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song 1"))
        db.upsert_item(Item(id="2", category=Category.MUSIC, title="Song 2"))
        db.upsert_item(Item(id="3", category=Category.MUSIC, title="Song 3"))

        # Love via rating
        db.upsert_rating(Rating(item_id="1", loved=True))

        # Love via source
        db.upsert_item_source(ItemSource(item_id="2", source=Source.SPOTIFY, source_id="spotify:2", source_loved=True))

        loved = db.get_all_loved_items()
        assert len(loved) == 2
        loved_ids = {item.id for item in loved}
        assert "1" in loved_ids
        assert "2" in loved_ids

    def test_get_all_disliked_items(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song 1"))
        db.upsert_item(Item(id="2", category=Category.MUSIC, title="Song 2"))
        db.upsert_item(Item(id="3", category=Category.MUSIC, title="Song 3"))

        db.upsert_rating(Rating(item_id="1", loved=True))
        db.upsert_rating(Rating(item_id="2", loved=False))  # Disliked

        disliked = db.get_all_disliked_items()
        assert len(disliked) == 1
        assert disliked[0].id == "2"

    def test_get_all_disliked_items_with_category_filter(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Bad Song"))
        db.upsert_item(Item(id="2", category=Category.MOVIE, title="Bad Movie"))
        db.upsert_item(Item(id="3", category=Category.GAME, title="Bad Game"))

        db.upsert_rating(Rating(item_id="1", loved=False))
        db.upsert_rating(Rating(item_id="2", loved=False))
        db.upsert_rating(Rating(item_id="3", loved=False))

        # Filter by category
        music_disliked = db.get_all_disliked_items(category=Category.MUSIC)
        assert len(music_disliked) == 1
        assert music_disliked[0].id == "1"

        movie_disliked = db.get_all_disliked_items(category=Category.MOVIE)
        assert len(movie_disliked) == 1
        assert movie_disliked[0].id == "2"

        # No filter returns all
        all_disliked = db.get_all_disliked_items()
        assert len(all_disliked) == 3


class TestItemSourceOperations:
    def test_upsert_and_get_item_source(self, db: Database):
        db.upsert_item(Item(id="item-1", category=Category.MUSIC, title="Test"))

        source = ItemSource(
            item_id="item-1",
            source=Source.SPOTIFY,
            source_id="spotify:track:abc",
            source_loved=True,
            source_data={"play_count": 100},
        )
        db.upsert_item_source(source)

        sources = db.get_item_sources("item-1")
        assert len(sources) == 1
        assert sources[0].source == Source.SPOTIFY
        assert sources[0].source_id == "spotify:track:abc"
        assert sources[0].source_loved is True
        assert sources[0].source_data == {"play_count": 100}

    def test_find_item_by_source(self, db: Database):
        db.upsert_item(Item(id="item-1", category=Category.MUSIC, title="Test Song"))
        db.upsert_item_source(ItemSource(item_id="item-1", source=Source.SPOTIFY, source_id="spotify:123"))

        found = db.find_item_by_source(Source.SPOTIFY, "spotify:123")
        assert found is not None
        assert found.id == "item-1"

        not_found = db.find_item_by_source(Source.SPOTIFY, "spotify:999")
        assert not_found is None

    def test_multiple_sources_per_item(self, db: Database):
        db.upsert_item(Item(id="item-1", category=Category.MUSIC, title="Test"))

        db.upsert_item_source(ItemSource(item_id="item-1", source=Source.SPOTIFY, source_id="sp:1"))
        db.upsert_item_source(ItemSource(item_id="item-1", source=Source.APPLE_MUSIC, source_id="am:1"))

        sources = db.get_item_sources("item-1")
        assert len(sources) == 2
        source_types = {s.source for s in sources}
        assert Source.SPOTIFY in source_types
        assert Source.APPLE_MUSIC in source_types


class TestRatingOperations:
    def test_upsert_and_get_rating(self, db: Database):
        db.upsert_item(Item(id="item-1", category=Category.MUSIC, title="Test"))

        rating = Rating(item_id="item-1", loved=True, rating=5, notes="Amazing!")
        db.upsert_rating(rating)

        retrieved = db.get_rating("item-1")
        assert retrieved is not None
        assert retrieved.loved is True
        assert retrieved.rating == 5
        assert retrieved.notes == "Amazing!"

    def test_get_nonexistent_rating(self, db: Database):
        result = db.get_rating("nonexistent")
        assert result is None

    def test_upsert_updates_existing_rating(self, db: Database):
        db.upsert_item(Item(id="item-1", category=Category.MUSIC, title="Test"))

        db.upsert_rating(Rating(item_id="item-1", loved=True, rating=4))
        db.upsert_rating(Rating(item_id="item-1", loved=True, rating=5))

        retrieved = db.get_rating("item-1")
        assert retrieved is not None
        assert retrieved.rating == 5


class TestSyncStateOperations:
    def test_update_and_get_sync_state(self, db: Database):
        now = datetime.now()
        state = SyncState(source=Source.SPOTIFY, last_sync=now, cursor="page_5")
        db.update_sync_state(state)

        retrieved = db.get_sync_state(Source.SPOTIFY)
        assert retrieved is not None
        assert retrieved.source == Source.SPOTIFY
        assert retrieved.cursor == "page_5"

    def test_get_nonexistent_sync_state(self, db: Database):
        result = db.get_sync_state(Source.STEAM)
        assert result is None


class TestAnalyticsQueries:
    def test_get_category_stats(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song 1"))
        db.upsert_item(Item(id="2", category=Category.MUSIC, title="Song 2"))
        db.upsert_item(Item(id="3", category=Category.GAME, title="Game 1"))

        db.upsert_rating(Rating(item_id="1", loved=True))

        stats = db.get_category_stats()
        assert stats["music"]["total"] == 2
        assert stats["music"]["loved"] == 1
        assert stats["game"]["total"] == 1
        assert stats["game"]["loved"] == 0

    def test_get_source_stats(self, db: Database):
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Song 1"))
        db.upsert_item(Item(id="2", category=Category.MUSIC, title="Song 2"))

        db.upsert_item_source(ItemSource(item_id="1", source=Source.SPOTIFY, source_id="sp:1"))
        db.upsert_item_source(ItemSource(item_id="2", source=Source.SPOTIFY, source_id="sp:2"))
        db.upsert_item_source(ItemSource(item_id="1", source=Source.APPLE_MUSIC, source_id="am:1"))

        stats = db.get_source_stats()
        assert stats["spotify"] == 2
        assert stats["apple_music"] == 1

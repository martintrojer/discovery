"""Unit tests for data models."""

from datetime import datetime

from discovery.models import Category, Item, ItemSource, Rating, Source, WishlistItem


class TestCategory:
    def test_category_values(self):
        assert Category.MUSIC.value == "music"
        assert Category.GAME.value == "game"
        assert Category.BOOK.value == "book"
        assert Category.MOVIE.value == "movie"
        assert Category.TV.value == "tv"
        assert Category.PAPER.value == "paper"
        assert Category.PODCAST.value == "podcast"

    def test_category_from_string(self):
        assert Category("music") == Category.MUSIC
        assert Category("game") == Category.GAME


class TestSource:
    def test_source_values(self):
        assert Source.APPLE_MUSIC.value == "apple_music"
        assert Source.SPOTIFY.value == "spotify"
        assert Source.STEAM.value == "steam"
        assert Source.NETFLIX.value == "netflix"
        assert Source.MANUAL.value == "manual"

    def test_source_from_string(self):
        assert Source("spotify") == Source.SPOTIFY
        assert Source("manual") == Source.MANUAL


class TestItem:
    def test_create_minimal_item(self):
        item = Item(id="test-1", category=Category.MUSIC, title="Test Song")
        assert item.id == "test-1"
        assert item.category == Category.MUSIC
        assert item.title == "Test Song"
        assert item.creator is None
        assert item.metadata == {}
        assert isinstance(item.created_at, datetime)
        assert isinstance(item.updated_at, datetime)

    def test_create_full_item(self):
        item = Item(
            id="test-2",
            category=Category.GAME,
            title="Test Game",
            creator="Test Studio",
            metadata={"genre": "RPG", "year": 2024},
        )
        assert item.id == "test-2"
        assert item.category == Category.GAME
        assert item.title == "Test Game"
        assert item.creator == "Test Studio"
        assert item.metadata == {"genre": "RPG", "year": 2024}


class TestItemSource:
    def test_create_item_source(self):
        source = ItemSource(
            item_id="item-1",
            source=Source.SPOTIFY,
            source_id="spotify:track:123",
            source_loved=True,
            source_data={"play_count": 50},
        )
        assert source.item_id == "item-1"
        assert source.source == Source.SPOTIFY
        assert source.source_id == "spotify:track:123"
        assert source.source_loved is True
        assert source.source_data == {"play_count": 50}


class TestRating:
    def test_create_rating(self):
        rating = Rating(
            item_id="item-1",
            loved=True,
            rating=5,
            notes="Great!",
        )
        assert rating.item_id == "item-1"
        assert rating.loved is True
        assert rating.rating == 5
        assert rating.notes == "Great!"

    def test_rating_defaults(self):
        rating = Rating(item_id="item-1")
        assert rating.loved is None
        assert rating.rating is None
        assert rating.notes is None


class TestWishlistItem:
    def test_create_wishlist_item(self):
        item = WishlistItem(
            id="wish-1",
            category=Category.BOOK,
            title="Test Book",
            creator="Test Author",
            notes="Read this soon",
        )
        assert item.id == "wish-1"
        assert item.category == Category.BOOK
        assert item.title == "Test Book"
        assert item.creator == "Test Author"
        assert item.notes == "Read this soon"
        assert isinstance(item.created_at, datetime)

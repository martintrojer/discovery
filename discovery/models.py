"""Data models for Discovery."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Category(str, Enum):
    MUSIC = "music"
    GAME = "game"
    BOOK = "book"
    MOVIE = "movie"
    TV = "tv"
    PAPER = "paper"
    PODCAST = "podcast"


class Source(str, Enum):
    # Music
    APPLE_MUSIC = "apple_music"
    SPOTIFY = "spotify"
    QOBUZ = "qobuz"
    # Games
    STEAM = "steam"
    # Books
    GOODREADS = "goodreads"
    KINDLE = "kindle"
    # Video
    NETFLIX = "netflix"
    APPLE_TV = "apple_tv"
    AMAZON_PRIME = "amazon_prime"
    DISNEY_PLUS = "disney_plus"
    BBC_IPLAYER = "bbc_iplayer"
    # Podcasts
    APPLE_PODCASTS = "apple_podcasts"
    # Academic
    ARXIV = "arxiv"
    # Other
    MANUAL = "manual"


@dataclass
class Item:
    """A discoverable item (song, game, book, etc.)."""

    id: str
    category: Category
    title: str
    creator: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class ItemSource:
    """Link between an item and its source."""

    item_id: str
    source: Source
    source_id: str
    source_loved: bool | None = None
    source_data: dict[str, Any] = field(default_factory=dict)
    last_synced: datetime = field(default_factory=datetime.now)


@dataclass
class Rating:
    """User's local rating for an item."""

    item_id: str
    loved: bool | None = None
    rating: int | None = None  # 1-5
    notes: str | None = None
    rated_at: datetime = field(default_factory=datetime.now)


@dataclass
class WishlistItem:
    """An item on a wishlist (per category)."""

    id: str
    category: Category
    title: str
    creator: str | None = None
    notes: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

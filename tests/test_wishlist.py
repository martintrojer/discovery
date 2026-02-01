"""Unit tests for wishlist helpers."""

from discovery.cli.wishlist import find_wishlist_matches, prune_wishlist
from discovery.db import Database
from discovery.models import Category, Item, WishlistItem


class TestWishlistHelpers:
    def test_find_wishlist_match(self, db: Database) -> None:
        db.upsert_item(Item(id="1", category=Category.BOOK, title="Dune", creator="Frank Herbert"))

        wishlist_item = WishlistItem(
            id="w1",
            category=Category.BOOK,
            title="Dune",
            creator="Frank Herbert",
        )

        match = find_wishlist_matches(db, wishlist_item)
        assert match is not None
        assert match.id == "1"

    def test_prune_wishlist(self, db: Database) -> None:
        db.upsert_item(Item(id="1", category=Category.MOVIE, title="Inception", creator="Christopher Nolan"))
        wishlist_item = WishlistItem(
            id="w1",
            category=Category.MOVIE,
            title="Inception",
            creator="Christopher Nolan",
        )
        db.add_wishlist_item(wishlist_item)

        removed = prune_wishlist(db, Category.MOVIE)
        assert len(removed) == 1
        assert db.get_wishlist_item("w1") is None

    def test_prune_wishlist_no_match(self, db: Database) -> None:
        wishlist_item = WishlistItem(
            id="w1",
            category=Category.MOVIE,
            title="Inception",
            creator="Christopher Nolan",
        )
        db.add_wishlist_item(wishlist_item)

        removed = prune_wishlist(db, Category.MOVIE)
        assert removed == []

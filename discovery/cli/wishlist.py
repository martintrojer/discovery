"""Wishlist CLI commands."""

import uuid

import click

from ..db import Database
from ..models import Category, Item, WishlistItem
from ..utils import DEFAULT_DISPLAY_LIMIT, creators_match, creators_match_exact, titles_match
from .core import cli
from .display_helpers import display_wishlist_by_category, select_wishlist_item


@cli.group()
def wishlist() -> None:
    """Manage wishlist items."""
    pass


def find_wishlist_matches(db: Database, wishlist_item: WishlistItem) -> Item | None:
    """Find a matching library item for a wishlist entry."""
    candidates = db.search_items(wishlist_item.title, category=wishlist_item.category)
    for candidate in candidates:
        if titles_match(candidate.title, wishlist_item.title) and creators_match(
            candidate.creator, wishlist_item.creator
        ):
            return candidate
    return None


def prune_wishlist(db: Database, category: Category | None) -> list[WishlistItem]:
    """Remove wishlist items that match existing library items."""
    wishlist_items = db.get_wishlist_items(category=category)
    removed: list[WishlistItem] = []

    for wishlist_item in wishlist_items:
        match = find_wishlist_matches(db, wishlist_item)
        if match and db.remove_wishlist_item(wishlist_item.id):
            removed.append(wishlist_item)

    return removed


def prune_wishlist_and_report(db: Database, category: Category, context: str) -> None:
    """Prune wishlist and report if anything was removed."""
    removed = prune_wishlist(db, category)
    if not removed:
        return

    click.echo(f"\nPruned {len(removed)} wishlist item(s) after {context}:")
    for item in removed[:DEFAULT_DISPLAY_LIMIT]:
        creator_str = f" - {item.creator}" if item.creator else ""
        click.echo(f"  {item.title}{creator_str}")
    if len(removed) > DEFAULT_DISPLAY_LIMIT:
        click.echo(f"  ... and {len(removed) - DEFAULT_DISPLAY_LIMIT} more")


@wishlist.command(name="add")
@click.argument("title")
@click.option(
    "--category",
    "-c",
    type=click.Choice([c.value for c in Category]),
    required=True,
    help="Category (music, game, book, movie, tv, podcast, paper)",
)
@click.option("--creator", "-a", help="Creator (artist, author, developer, director)")
@click.option("--notes", "-n", help="Notes")
@click.pass_context
def wishlist_add(
    ctx: click.Context,
    title: str,
    category: str,
    creator: str | None,
    notes: str | None,
) -> None:
    """Add an item to a wishlist."""
    db: Database = ctx.obj["db"]
    cat = Category(category)

    existing = db.search_wishlist_items(title, category=cat)
    for item in existing:
        if item.title.lower() == title.lower():
            if creator and creators_match_exact(creator, item.creator):
                click.echo(f"Wishlist item already exists: {item.title}")
                return
            if not creator:
                click.echo(f"Wishlist item already exists: {item.title}")
                return

    wishlist_item = WishlistItem(
        id=str(uuid.uuid4()),
        category=cat,
        title=title,
        creator=creator,
        notes=notes,
    )
    db.add_wishlist_item(wishlist_item)

    creator_str = f" by {creator}" if creator else ""
    click.echo(f"Wishlist added: [{category}] {title}{creator_str}")
    if notes:
        click.echo(f"  Notes: {notes}")


@wishlist.command(name="view")
@click.option("--category", "-c", type=click.Choice([c.value for c in Category]), help="Filter by category")
@click.option("--search", "-s", help="Search title/creator")
@click.pass_context
def wishlist_view(ctx: click.Context, category: str | None, search: str | None) -> None:
    """View wishlist items."""
    db: Database = ctx.obj["db"]
    cat_filter = Category(category) if category else None

    if search:
        items = db.search_wishlist_items(search, category=cat_filter)
    else:
        items = db.get_wishlist_items(category=cat_filter)

    display_wishlist_by_category(items)


@wishlist.command(name="remove")
@click.argument("query")
@click.option("--category", "-c", type=click.Choice([c.value for c in Category]), help="Filter by category")
@click.pass_context
def wishlist_remove(ctx: click.Context, query: str, category: str | None) -> None:
    """Remove an item from a wishlist."""
    db: Database = ctx.obj["db"]
    cat_filter = Category(category) if category else None

    item = select_wishlist_item(db, query, cat_filter)
    if not item:
        return

    if db.remove_wishlist_item(item.id):
        click.echo(f"Wishlist removed: {item.title}")
    else:
        click.echo("Wishlist item not found.")


@wishlist.command(name="prune")
@click.option("--category", "-c", type=click.Choice([c.value for c in Category]), help="Filter by category")
@click.pass_context
def wishlist_prune(ctx: click.Context, category: str | None) -> None:
    """Remove wishlist items already in your library."""
    db: Database = ctx.obj["db"]
    cat_filter = Category(category) if category else None

    removed = prune_wishlist(db, cat_filter)
    if not removed:
        click.echo("No wishlist items to prune.")
        return

    click.echo(f"Pruned {len(removed)} wishlist item(s):")
    for item in removed:
        creator_str = f" - {item.creator}" if item.creator else ""
        click.echo(f"  [{item.category.value}] {item.title}{creator_str}")

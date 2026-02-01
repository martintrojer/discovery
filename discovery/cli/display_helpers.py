"""Shared display and selection helpers for CLI."""

from collections.abc import Callable
from typing import TypeVar

import click

from ..config import DEFAULT_DISPLAY_LIMIT
from ..db import Database
from ..models import Category, Item, WishlistItem
from ..utils import group_by_category

T = TypeVar("T")


def select_from_results(
    items: list[T],
    query: str,
    empty_message: str,
    formatter: Callable[[T], str],
    max_results: int = DEFAULT_DISPLAY_LIMIT,
) -> T | None:
    """Interactively select an item from search results."""
    if not items:
        click.echo(empty_message.format(query=query))
        return None

    if len(items) == 1:
        return items[0]

    click.echo(f"Multiple items match '{query}':")
    display_items = items[:max_results]
    for i, item in enumerate(display_items, 1):
        click.echo(f"  {i}. {formatter(item)}")

    choice = click.prompt("Select item number", type=int, default=1)
    if not 1 <= choice <= len(display_items):
        click.echo("Invalid choice")
        return None
    return items[choice - 1]


def select_item(db: Database, query: str, max_results: int = DEFAULT_DISPLAY_LIMIT) -> Item | None:
    """Search and interactively select an item."""
    items = db.search_items(query)
    return select_from_results(
        items,
        query,
        "No items found matching '{query}'",
        lambda item: f"[{item.category.value}] {item.title}{f' - {item.creator}' if item.creator else ''}",
        max_results=max_results,
    )


def select_wishlist_item(db: Database, query: str, category: Category | None) -> WishlistItem | None:
    """Search and interactively select a wishlist item."""
    items = db.search_wishlist_items(query, category=category)
    return select_from_results(
        items,
        query,
        "No wishlist items found matching '{query}'",
        lambda item: f"[{item.category.value}] {item.title}{f' - {item.creator}' if item.creator else ''}",
    )


def display_by_category(
    items: list[T],
    label: str,
    empty_message: str,
    formatter: Callable[[T], str],
) -> None:
    """Display items grouped by category."""
    if not items:
        click.echo(empty_message)
        return

    click.echo(f"\n{len(items)} {label} items:\n")

    by_category = group_by_category(items)
    for cat, cat_items in sorted(by_category.items()):
        click.echo(f"  {cat.upper()} ({len(cat_items)})")
        for item in cat_items[:DEFAULT_DISPLAY_LIMIT]:
            click.echo(f"    {formatter(item)}")
        if len(cat_items) > DEFAULT_DISPLAY_LIMIT:
            click.echo(f"    ... and {len(cat_items) - DEFAULT_DISPLAY_LIMIT} more")
        click.echo()


def display_items_by_category(items: list[Item], label: str) -> None:
    """Display items grouped by category."""
    display_by_category(
        items,
        label,
        f"No {label} items yet.",
        lambda item: f"{item.title}{f' - {item.creator}' if item.creator else ''}",
    )


def display_wishlist_by_category(items: list[WishlistItem]) -> None:
    """Display wishlist items grouped by category."""
    display_by_category(
        items,
        "wishlist",
        "No wishlist items yet.",
        lambda item: f"{item.title}{f' - {item.creator}' if item.creator else ''}{f' ({item.notes})' if item.notes else ''}",
    )

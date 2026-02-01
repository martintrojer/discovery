"""CLI for Discovery."""

import importlib
import json as json_module
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import click

from .cli_items import create_item, find_similar_items, get_loved_status_from_flags, update_item_fields, upsert_rating
from .cli_query import build_filter_description, format_items_as_json, query_items_with_filters
from .db import Database
from .models import Category, Item, WishlistItem
from .utils import DEFAULT_DISPLAY_LIMIT, creators_match, format_rating, group_by_category, titles_match

T = TypeVar("T")


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Discovery - Find new things you might love.

    Import your library data, then use the /discovery skill in Claude Code
    for AI-powered analysis and recommendations.
    """
    ctx.ensure_object(dict)
    ctx.obj["db"] = Database()


@cli.command()
@click.option("--format", "-f", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.pass_context
def status(ctx: click.Context, format: str) -> None:
    """Show library status and summary.

    Provides an overview for AI analysis including:
    - Category breakdown (total, loved, disliked)
    - Source breakdown
    - Sample loved items per category
    """
    from .cli_status import format_status_text, get_library_status

    db: Database = ctx.obj["db"]

    if format == "json":
        data = get_library_status(db)
        click.echo(json_module.dumps(data, indent=2, default=str))
    else:
        content = format_status_text(db)
        click.echo(content)


@cli.group(name="import")
def import_cmd() -> None:
    """Import data from various sources."""
    pass


@cli.group(name="scrape")
def scrape_cmd() -> None:
    """Scrape/convert data into Discovery import formats."""
    pass


# Import command configuration: name -> (module_name, class_name, docstring)
_FILE_IMPORTERS = {
    "apple-music": ("apple_music", "AppleMusicImporter", "Import music from Apple Music/iTunes library XML."),
    "goodreads": ("goodreads", "GoodreadsImporter", "Import books from Goodreads CSV export."),
    "netflix": ("netflix", "NetflixImporter", "Import viewing history from Netflix CSV export."),
    "spotify": ("spotify", "SpotifyImporter", "Import music from Spotify data export."),
    "qobuz": ("qobuz", "QobuzImporter", "Import music from Qobuz export."),
    "apple-podcasts": ("apple_podcasts", "ApplePodcastsImporter", "Import podcasts from Apple Podcasts OPML export."),
    "amazon-prime": ("amazon_prime", "AmazonPrimeImporter", "Import viewing history from Amazon Prime Video."),
    "disney-plus": ("disney_plus", "DisneyPlusImporter", "Import viewing history from Disney+."),
    "apple-tv": ("apple_tv", "AppleTVImporter", "Import viewing history from Apple TV+."),
    "bbc-iplayer": ("bbc_iplayer", "BBCiPlayerImporter", "Import viewing history from BBC iPlayer."),
}


def _create_file_import_command(name: str, module_name: str, class_name: str, docstring: str):
    """Create a file-based import command."""

    @import_cmd.command(name=name)
    @click.argument("file_path", type=click.Path(exists=True, path_type=Path), required=False)
    @click.option("--help-setup", is_flag=True, help="Show setup instructions")
    @click.pass_context
    def import_source(ctx: click.Context, file_path: Path | None, help_setup: bool) -> None:
        module = importlib.import_module(f".importers.{module_name}", package="discovery")
        importer_class = getattr(module, class_name)
        db: Database = ctx.obj["db"]
        importer = importer_class(db)

        if help_setup:
            click.echo(importer.get_manual_steps())
            return

        if not file_path:
            click.echo("Error: FILE_PATH required.")
            click.echo(f"Run 'discovery import {name} --help-setup' for instructions.")
            sys.exit(1)

        _create_backup_before_import(db, module_name)
        result = importer.import_from_file(file_path)
        _print_import_result(result)
        _prune_wishlist_and_report(db, importer.category, f"import {name}")

    import_source.__doc__ = docstring
    return import_source


# Register all file-based import commands
for _name, (_module, _class, _doc) in _FILE_IMPORTERS.items():
    _create_file_import_command(_name, _module, _class, _doc)


@import_cmd.command(name="steam")
@click.option("--api-key", envvar="STEAM_API_KEY", help="Steam Web API key")
@click.option("--steam-id", envvar="STEAM_ID", help="Your Steam numeric ID")
@click.option("--file", "file_path", type=click.Path(exists=True, path_type=Path), help="Import from JSON file instead")
@click.option("--help-setup", is_flag=True, help="Show setup instructions")
@click.pass_context
def import_steam(
    ctx: click.Context,
    api_key: str | None,
    steam_id: str | None,
    file_path: Path | None,
    help_setup: bool,
) -> None:
    """Import games from Steam."""
    from .importers.steam import SteamImporter

    db: Database = ctx.obj["db"]
    importer = SteamImporter(db, api_key=api_key, steam_id=steam_id)

    if help_setup:
        click.echo(importer.get_manual_steps())
        return

    if file_path:
        _create_backup_before_import(db, "steam")
        result = importer.import_from_file(file_path)
    else:
        if not api_key or not steam_id:
            click.echo("Error: --api-key and --steam-id required for API import.")
            click.echo("Run 'discovery import steam --help-setup' for instructions.")
            sys.exit(1)
        _create_backup_before_import(db, "steam")
        result = importer.import_from_api()

    _print_import_result(result)
    _prune_wishlist_and_report(db, importer.category, "import steam")


def _print_import_result(result) -> None:
    """Print import result summary."""
    click.echo(f"\nImport from {result.source.value} complete:")
    click.echo(f"  Added:   {result.items_added}")
    click.echo(f"  Updated: {result.items_updated}")

    if result.errors:
        click.echo(f"\n  Errors ({len(result.errors)}):")
        for error in result.errors[:5]:
            click.echo(f"    - {error}")
        if len(result.errors) > 5:
            click.echo(f"    ... and {len(result.errors) - 5} more")
    click.echo()


@scrape_cmd.command(name="netflix-html")
@click.argument("html_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    "output_path",
    type=click.Path(path_type=Path),
    help="Output CSV path (default: same name with .csv)",
)
@click.option("--import", "do_import", is_flag=True, help="Import the generated CSV after scraping")
@click.pass_context
def scrape_netflix_html(
    ctx: click.Context,
    html_path: Path,
    output_path: Path | None,
    do_import: bool,
) -> None:
    """Convert a Netflix ratings HTML page to CSV."""
    from .scrapers.netflix_html import convert_html_to_csv

    out_path = output_path or html_path.with_suffix(".csv")
    rows = convert_html_to_csv(html_path, out_path)
    click.echo(f"Wrote {len(rows)} rows to {out_path}")

    if do_import:
        from .importers.netflix import NetflixImporter

        db: Database = ctx.obj["db"]
        _create_backup_before_import(db, "netflix")
        importer = NetflixImporter(db)
        result = importer.import_from_file(out_path)
        _print_import_result(result)
        _prune_wishlist_and_report(db, importer.category, "import netflix")


def _select_from_results(
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


def _select_item(db: Database, query: str, max_results: int = DEFAULT_DISPLAY_LIMIT) -> Item | None:
    """Search and interactively select an item."""
    items = db.search_items(query)
    return _select_from_results(
        items,
        query,
        "No items found matching '{query}'",
        lambda item: f"[{item.category.value}] {item.title}{f' - {item.creator}' if item.creator else ''}",
        max_results=max_results,
    )


def _display_by_category(
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


def _display_items_by_category(items: list[Item], label: str) -> None:
    """Display items grouped by category."""
    _display_by_category(
        items,
        label,
        f"No {label} items yet.",
        lambda item: f"{item.title}{f' - {item.creator}' if item.creator else ''}",
    )


def _select_wishlist_item(db: Database, query: str, category: Category | None) -> WishlistItem | None:
    """Search and interactively select a wishlist item."""
    items = db.search_wishlist_items(query, category=category)
    return _select_from_results(
        items,
        query,
        "No wishlist items found matching '{query}'",
        lambda item: f"[{item.category.value}] {item.title}{f' - {item.creator}' if item.creator else ''}",
    )


def _display_wishlist_by_category(items: list[WishlistItem]) -> None:
    """Display wishlist items grouped by category."""
    _display_by_category(
        items,
        "wishlist",
        "No wishlist items yet.",
        lambda item: f"{item.title}{f' - {item.creator}' if item.creator else ''}{f' ({item.notes})' if item.notes else ''}",
    )


def _find_wishlist_matches(db: Database, wishlist_item: WishlistItem) -> Item | None:
    """Find a matching library item for a wishlist entry."""
    candidates = db.search_items(wishlist_item.title, category=wishlist_item.category)
    for candidate in candidates:
        if titles_match(candidate.title, wishlist_item.title) and creators_match(
            candidate.creator, wishlist_item.creator
        ):
            return candidate
    return None


def _prune_wishlist(db: Database, category: Category | None) -> list[WishlistItem]:
    """Remove wishlist items that match existing library items."""
    wishlist_items = db.get_wishlist_items(category=category)
    removed: list[WishlistItem] = []

    for wishlist_item in wishlist_items:
        match = _find_wishlist_matches(db, wishlist_item)
        if match and db.remove_wishlist_item(wishlist_item.id):
            removed.append(wishlist_item)

    return removed


def _prune_wishlist_and_report(db: Database, category: Category, context: str) -> None:
    """Prune wishlist and report if anything was removed."""
    removed = _prune_wishlist(db, category)
    if not removed:
        return

    click.echo(f"\nPruned {len(removed)} wishlist item(s) after {context}:")
    for item in removed[:DEFAULT_DISPLAY_LIMIT]:
        creator_str = f" - {item.creator}" if item.creator else ""
        click.echo(f"  {item.title}{creator_str}")
    if len(removed) > DEFAULT_DISPLAY_LIMIT:
        click.echo(f"  ... and {len(removed) - DEFAULT_DISPLAY_LIMIT} more")


@cli.command()
@click.argument("title")
@click.option(
    "--category",
    "-c",
    type=click.Choice([c.value for c in Category]),
    required=True,
    help="Category (music, game, book, movie, tv, podcast, paper)",
)
@click.option("--creator", "-a", help="Creator (artist, author, developer, director)")
@click.option("--loved", "-l", is_flag=True, help="Mark as loved")
@click.option("--dislike", "-d", is_flag=True, help="Mark as disliked")
@click.option("--rating", "-r", type=click.IntRange(1, 5), help="Rating (1-5)")
@click.option("--notes", "-n", help="Notes")
@click.option("--force", "-f", is_flag=True, help="Skip duplicate check and add anyway")
@click.pass_context
def add(
    ctx: click.Context,
    title: str,
    category: str,
    creator: str | None,
    loved: bool,
    dislike: bool,
    rating: int | None,
    notes: str | None,
    force: bool,
) -> None:
    """Add an item manually (watched, read, played, etc.)."""
    db: Database = ctx.obj["db"]
    cat = Category(category)

    if not force:
        # Check for exact match first
        existing = db.search_items(title, category=cat)
        for item in existing:
            if item.title.lower() == title.lower():
                if creator and item.creator and item.creator.lower() == creator.lower():
                    click.echo(f"Item already exists: {item.title}")
                    return
                elif not creator:
                    click.echo(f"Item already exists: {item.title}")
                    return

        # Check for fuzzy matches
        similar = find_similar_items(db, title, cat, creator)
        if similar:
            click.echo("\nDid you mean one of these existing items?\n")
            for i, item in enumerate(similar[:5], 1):
                creator_str = f" by {item.creator}" if item.creator else ""
                click.echo(f"  {i}. {item.title}{creator_str}")

            click.echo(f'  {len(similar[:5]) + 1}. Add as new item: "{title}"')
            click.echo()

            choice = click.prompt(
                "Select option",
                type=int,
                default=len(similar[:5]) + 1,
            )

            if 1 <= choice <= len(similar[:5]):
                # User selected existing item - update it instead
                selected = similar[choice - 1]
                if loved or dislike or rating or notes:
                    loved_status = True if loved else (False if dislike else None)
                    upsert_rating(db, selected.id, loved=loved_status, rating=rating, notes=notes)
                    click.echo(f"Updated: {selected.title}")
                    if loved:
                        click.echo("  Loved: yes")
                    if dislike:
                        click.echo("  Disliked: yes")
                else:
                    click.echo(f"Selected existing item: {selected.title}")
                return

    # Create new item
    item_id = str(uuid.uuid4())
    create_item(db, item_id, cat, title, creator)

    if loved or dislike or rating or notes:
        loved_status = True if loved else (False if dislike else None)
        upsert_rating(db, item_id, loved=loved_status, rating=rating, notes=notes)

    creator_str = f" by {creator}" if creator else ""
    click.echo(f"Added: [{category}] {title}{creator_str}")
    if loved:
        click.echo("  Loved: yes")
    if dislike:
        click.echo("  Disliked: yes")
    if rating:
        click.echo(f"  Rating: {format_rating(rating)}")

    _prune_wishlist_and_report(db, cat, "add")


@cli.command()
@click.argument("query")
@click.option("--title", "-t", help="New title")
@click.option("--creator", "-a", help="New creator")
@click.option("--loved", "-l", is_flag=True, help="Mark as loved")
@click.option("--dislike", "-d", is_flag=True, help="Mark as disliked")
@click.option("--unlove", "-u", is_flag=True, help="Remove loved/disliked status")
@click.option("--rating", "-r", type=click.IntRange(1, 5), help="Set rating (1-5)")
@click.option("--notes", "-n", help="Set notes")
@click.pass_context
def update(
    ctx: click.Context,
    query: str,
    title: str | None,
    creator: str | None,
    loved: bool,
    dislike: bool,
    unlove: bool,
    rating: int | None,
    notes: str | None,
) -> None:
    """Update an existing item's details."""
    db: Database = ctx.obj["db"]

    item = _select_item(db, query)
    if not item:
        return

    updated = False

    # Update item fields
    if title or creator is not None:
        updated = update_item_fields(db, item, title=title, creator=creator)

    # Update rating
    if loved or dislike or unlove or rating or notes:
        loved_status, preserve_loved = get_loved_status_from_flags(loved, dislike, unlove)
        upsert_rating(db, item.id, loved=loved_status, rating=rating, notes=notes, preserve_loved=preserve_loved)
        updated = True

    if updated:
        updated_item = db.get_item(item.id)
        creator_str = f" by {updated_item.creator}" if updated_item.creator else ""
        click.echo(f"Updated: {updated_item.title}{creator_str}")

        updated_rating = db.get_rating(item.id)
        if updated_rating:
            if updated_rating.loved is True:
                click.echo("  Loved: yes")
            elif updated_rating.loved is False:
                click.echo("  Disliked: yes")
            if updated_rating.rating:
                click.echo(f"  Rating: {format_rating(updated_rating.rating)}")
            if updated_rating.notes:
                click.echo(f"  Notes: {updated_rating.notes}")
    else:
        click.echo("No changes specified. Use --help to see options.")


@cli.command()
@click.argument("query")
@click.option("--rating", "-r", type=click.IntRange(1, 5), help="Set rating (1-5)")
@click.option("--notes", "-n", help="Add notes")
@click.pass_context
def love(
    ctx: click.Context,
    query: str,
    rating: int | None,
    notes: str | None,
) -> None:
    """Mark an item as loved."""
    db: Database = ctx.obj["db"]

    item = _select_item(db, query)
    if not item:
        return

    upsert_rating(db, item.id, loved=True, rating=rating, notes=notes)

    click.echo(f"Loved: {item.title}")
    if rating:
        click.echo(f"  Rating: {format_rating(rating)}")
    if notes:
        click.echo(f"  Notes: {notes}")


@cli.command()
@click.argument("query")
@click.option("--notes", "-n", help="Add notes (why you disliked it)")
@click.pass_context
def dislike(
    ctx: click.Context,
    query: str,
    notes: str | None,
) -> None:
    """Mark an item as disliked."""
    db: Database = ctx.obj["db"]

    item = _select_item(db, query)
    if not item:
        return

    upsert_rating(db, item.id, loved=False, notes=notes)

    click.echo(f"Disliked: {item.title}")
    if notes:
        click.echo(f"  Notes: {notes}")


@cli.command()
@click.option("--category", "-c", type=click.Choice([c.value for c in Category]), help="Filter by category")
@click.pass_context
def loved(ctx: click.Context, category: str | None) -> None:
    """List all loved items."""
    db: Database = ctx.obj["db"]
    cat_filter = Category(category) if category else None
    items = db.get_all_loved_items(category=cat_filter)
    _display_items_by_category(items, "loved")


@cli.command()
@click.option("--category", "-c", type=click.Choice([c.value for c in Category]), help="Filter by category")
@click.pass_context
def disliked(ctx: click.Context, category: str | None) -> None:
    """List all disliked items."""
    db: Database = ctx.obj["db"]
    cat_filter = Category(category) if category else None
    items = db.get_all_disliked_items(category=cat_filter)
    _display_items_by_category(items, "disliked")


@cli.group()
def wishlist() -> None:
    """Manage wishlist items."""
    pass


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
            if creator and item.creator and item.creator.lower() == creator.lower():
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

    _display_wishlist_by_category(items)


@wishlist.command(name="remove")
@click.argument("query")
@click.option("--category", "-c", type=click.Choice([c.value for c in Category]), help="Filter by category")
@click.pass_context
def wishlist_remove(ctx: click.Context, query: str, category: str | None) -> None:
    """Remove an item from a wishlist."""
    db: Database = ctx.obj["db"]
    cat_filter = Category(category) if category else None

    item = _select_wishlist_item(db, query, cat_filter)
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

    removed = _prune_wishlist(db, cat_filter)
    if not removed:
        click.echo("No wishlist items to prune.")
        return

    click.echo(f"Pruned {len(removed)} wishlist item(s):")
    for item in removed:
        creator_str = f" - {item.creator}" if item.creator else ""
        click.echo(f"  [{item.category.value}] {item.title}{creator_str}")


@cli.command()
@click.option("--category", "-c", type=click.Choice([c.value for c in Category]), help="Filter by category")
@click.option("--loved", "-l", is_flag=True, help="Show only loved items")
@click.option("--disliked", "-d", is_flag=True, help="Show only disliked items")
@click.option("--creator", "-a", help="Filter by creator (partial match)")
@click.option("--min-rating", type=click.IntRange(1, 5), help="Minimum rating (1-5)")
@click.option("--max-rating", type=click.IntRange(1, 5), help="Maximum rating (1-5)")
@click.option("--search", "-s", help="Search title/creator")
@click.option("--limit", "-n", type=int, default=20, help="Max items to show (default: 20)")
@click.option("--offset", type=int, default=0, help="Skip first N items (for pagination)")
@click.option("--random", "-r", is_flag=True, help="Random sample instead of sorted")
@click.option("--count", is_flag=True, help="Show only count, not items")
@click.option("--format", "-f", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.pass_context
def query(
    ctx: click.Context,
    category: str | None,
    loved: bool,
    disliked: bool,
    creator: str | None,
    min_rating: int | None,
    max_rating: int | None,
    search: str | None,
    limit: int,
    offset: int,
    random: bool,
    count: bool,
    format: str,
) -> None:
    """Query library with filters and pagination.

    Examples:

      discovery query --count                    # Total items
      discovery query -c game --count            # Total games
      discovery query -l --count                 # Total loved items
      discovery query -c music -l -n 50          # First 50 loved music items
      discovery query -c game -l --offset 50    # Next 50 (pagination)
      discovery query -a "FromSoftware" -l       # Loved items by creator
      discovery query --min-rating 4             # Items rated 4+
      discovery query -c movie -r -n 10          # 10 random movies
      discovery query -s "souls" -f json         # Search as JSON
    """
    db: Database = ctx.obj["db"]
    cat = Category(category) if category else None
    loved_filter = True if loved else (False if disliked else None)

    if count:
        total = db.count_items(
            category=cat,
            loved=loved_filter,
            creator=creator,
            min_rating=min_rating,
            max_rating=max_rating,
            search=search,
        )
        if format == "json":
            click.echo(json_module.dumps({"count": total}))
        else:
            filter_str = build_filter_description(category, loved, disliked, creator, min_rating, max_rating, search)
            click.echo(f"Count{filter_str}: {total}")
        return

    items, total = query_items_with_filters(
        db, cat, loved_filter, creator, min_rating, max_rating, search, limit, offset, random
    )

    if format == "json":
        data = format_items_as_json(db, items, total, offset, limit)
        click.echo(json_module.dumps(data, indent=2, default=str))
    else:
        if not items:
            click.echo("No items found.")
            return

        click.echo(f"\nShowing {len(items)} of {total} items (offset: {offset}):\n")
        for item in items:
            sources = db.get_item_sources(item.id)
            source_str = ",".join(s.source.value for s in sources) if sources else "manual"
            creator_str = f" - {item.creator}" if item.creator else ""
            click.echo(f"  [{item.category.value:7}] [{source_str:10}] {item.title}{creator_str}")

        if offset + len(items) < total:
            next_offset = offset + limit
            click.echo(f"\n  Use --offset {next_offset} to see more")
        click.echo()


@cli.group()
def backup() -> None:
    """Manage database backups."""
    pass


@backup.command(name="create")
@click.option("--reason", "-r", default="manual", help="Reason for backup")
@click.pass_context
def backup_create(ctx: click.Context, reason: str) -> None:
    """Create a backup of the database."""
    db: Database = ctx.obj["db"]

    backup_path = db.create_backup(reason)
    if backup_path:
        click.echo(f"Backup created: {backup_path}")
    else:
        click.echo("No database to backup yet.")


@backup.command(name="list")
@click.pass_context
def backup_list(ctx: click.Context) -> None:
    """List available backups."""
    db: Database = ctx.obj["db"]

    backups = db.list_backups()
    if not backups:
        click.echo("No backups found.")
        return

    click.echo(f"\n{len(backups)} backup(s) available:\n")
    for i, b in enumerate(backups, 1):
        timestamp = b["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        click.echo(f"  {i}. {timestamp} ({b['reason']}) - {b['size_kb']} KB")
        click.echo(f"     {b['path']}")
    click.echo()


@backup.command(name="restore")
@click.argument("backup_id", type=int, required=False)
@click.option("--path", "-p", type=click.Path(exists=True, path_type=Path), help="Restore from specific path")
@click.pass_context
def backup_restore(ctx: click.Context, backup_id: int | None, path: Path | None) -> None:
    """Restore database from a backup.

    BACKUP_ID is the number from 'discovery backup list'.
    """
    db: Database = ctx.obj["db"]

    if path:
        backup_path = path
    elif backup_id:
        backups = db.list_backups()
        if backup_id < 1 or backup_id > len(backups):
            click.echo("Invalid backup ID. Use 'discovery backup list' to see available backups.")
            return
        backup_path = backups[backup_id - 1]["path"]
    else:
        click.echo("Specify a backup ID or --path. Use 'discovery backup list' to see available backups.")
        return

    if click.confirm(f"Restore from {backup_path}? This will replace your current database."):
        if db.restore_backup(backup_path):
            click.echo("Database restored successfully.")
        else:
            click.echo("Failed to restore backup.")


def _create_backup_before_import(db: Database, source_name: str) -> None:
    """Create a backup before importing."""
    backup_path = db.create_backup(f"pre_import_{source_name}")
    if backup_path:
        click.echo(f"Backup created: {backup_path.name}")


def main() -> None:
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()

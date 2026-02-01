"""CLI for Discovery."""

import importlib
import json as json_module
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

import click

from ..db import Database
from ..importers.base import ImportResult
from ..models import Category
from ..utils import format_rating
from .display_helpers import display_items_by_category, select_item
from .items_helpers import (
    create_item,
    find_similar_items,
    get_loved_status_from_flags,
    update_item_fields,
    upsert_rating,
)


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
    from .status_helpers import format_status_text, get_library_status

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


def _create_file_import_command(
    name: str,
    module_name: str,
    class_name: str,
    docstring: str,
) -> Callable[..., None]:
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
        from .wishlist import prune_wishlist_and_report

        prune_wishlist_and_report(db, importer.category, f"import {name}")

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
    from ..importers.steam import SteamImporter

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
    from .wishlist import prune_wishlist_and_report

    prune_wishlist_and_report(db, importer.category, "import steam")


def _print_import_result(result: ImportResult) -> None:
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
    from ..scrapers.netflix_html import convert_html_to_csv

    out_path = output_path or html_path.with_suffix(".csv")
    rows = convert_html_to_csv(html_path, out_path)
    click.echo(f"Wrote {len(rows)} rows to {out_path}")

    if do_import:
        from ..importers.netflix import NetflixImporter

        db: Database = ctx.obj["db"]
        _create_backup_before_import(db, "netflix")
        importer = NetflixImporter(db)
        result = importer.import_from_file(out_path)
        _print_import_result(result)
        from .wishlist import prune_wishlist_and_report

        prune_wishlist_and_report(db, importer.category, "import netflix")


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

    from .wishlist import prune_wishlist_and_report

    prune_wishlist_and_report(db, cat, "add")


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

    item = select_item(db, query)
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

    item = select_item(db, query)
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

    item = select_item(db, query)
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
    display_items_by_category(items, "loved")


@cli.command()
@click.option("--category", "-c", type=click.Choice([c.value for c in Category]), help="Filter by category")
@click.pass_context
def disliked(ctx: click.Context, category: str | None) -> None:
    """List all disliked items."""
    db: Database = ctx.obj["db"]
    cat_filter = Category(category) if category else None
    items = db.get_all_disliked_items(category=cat_filter)
    display_items_by_category(items, "disliked")


def _create_backup_before_import(db: Database, source_name: str) -> None:
    """Create a backup before importing."""
    backup_path = db.create_backup(f"pre_import_{source_name}")
    if backup_path:
        click.echo(f"Backup created: {backup_path.name}")


from . import backups as _backups  # noqa: F401,E402
from . import query as _query  # noqa: F401,E402
from . import wishlist as _wishlist  # noqa: F401,E402


def main() -> None:
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()

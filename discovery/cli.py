"""CLI for Discovery."""

import importlib
import sys
from datetime import datetime
from pathlib import Path

import click

from .db import Database
from .models import Category, Item, Rating
from .utils import format_rating, group_by_category, normalize_title


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
    from .status import format_status_text, get_library_status

    db: Database = ctx.obj["db"]

    if format == "json":
        import json as json_module

        data = get_library_status(db)
        click.echo(json_module.dumps(data, indent=2, default=str))
    else:
        content = format_status_text(db)
        click.echo(content)


@cli.group(name="import")
def import_cmd() -> None:
    """Import data from various sources."""
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


def _select_item(db: Database, query: str, max_results: int = 10) -> Item | None:
    """Search and interactively select an item.

    Args:
        db: Database instance
        query: Search query
        max_results: Maximum items to show for selection

    Returns:
        Selected Item or None if no selection made
    """
    items = db.search_items(query)
    if not items:
        click.echo(f"No items found matching '{query}'")
        return None

    if len(items) == 1:
        return items[0]

    click.echo(f"Multiple items match '{query}':")
    display_items = items[:max_results]
    for i, item in enumerate(display_items, 1):
        creator_str = f" - {item.creator}" if item.creator else ""
        click.echo(f"  {i}. [{item.category.value}] {item.title}{creator_str}")

    choice = click.prompt("Select item number", type=int, default=1)
    if not 1 <= choice <= len(display_items):
        click.echo("Invalid choice")
        return None
    return items[choice - 1]


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
    import uuid

    from .models import Item, ItemSource, Source
    from .models import Rating as RatingModel

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
        similar = _find_similar_items(db, title, cat, creator)
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
                loved_status = True if loved else (False if dislike else None)

                if loved or dislike or rating or notes:
                    existing_rating = db.get_rating(selected.id)
                    db.upsert_rating(
                        RatingModel(
                            item_id=selected.id,
                            loved=loved_status
                            if loved_status is not None
                            else (existing_rating.loved if existing_rating else None),
                            rating=rating or (existing_rating.rating if existing_rating else None),
                            notes=notes or (existing_rating.notes if existing_rating else None),
                            rated_at=datetime.now(),
                        )
                    )
                    click.echo(f"Updated: {selected.title}")
                    if loved:
                        click.echo("  Loved: yes")
                    if dislike:
                        click.echo("  Disliked: yes")
                else:
                    click.echo(f"Selected existing item: {selected.title}")
                return

            # User chose to add as new

    # Create new item
    item_id = str(uuid.uuid4())
    item = Item(
        id=item_id,
        category=cat,
        title=title,
        creator=creator,
        metadata={},
    )
    db.upsert_item(item)

    # Add source as manual
    loved_status = True if loved else (False if dislike else None)
    item_source = ItemSource(
        item_id=item_id,
        source=Source.MANUAL,
        source_id=item_id,
        source_loved=loved_status,
        source_data={},
    )
    db.upsert_item_source(item_source)

    # Add rating if loved, disliked, or rated
    if loved or dislike or rating or notes:
        db.upsert_rating(
            RatingModel(
                item_id=item_id,
                loved=loved_status,
                rating=rating,
                notes=notes,
                rated_at=datetime.now(),
            )
        )

    creator_str = f" by {creator}" if creator else ""
    click.echo(f"Added: [{category}] {title}{creator_str}")
    if loved:
        click.echo("  Loved: yes")
    if dislike:
        click.echo("  Disliked: yes")
    if rating:
        click.echo(f"  Rating: {format_rating(rating)}")


def _find_similar_items(db: Database, title: str, category: Category, creator: str | None) -> list:
    """Find items similar to the given title using fuzzy matching."""
    normalized_input = normalize_title(title)
    if len(normalized_input) < 3:
        return []

    # Search with first part of title
    search_term = title.split()[0] if " " in title else title[:5]
    candidates = db.search_items(search_term, category=category)

    # Also search all items in category if title is short
    if len(candidates) < 10:
        all_in_category = db.get_items_by_category(category)
        seen_ids = {c.id for c in candidates}
        for item in all_in_category:
            if item.id not in seen_ids:
                candidates.append(item)

    similar = []
    for item in candidates:
        normalized_item = normalize_title(item.title)

        # Check various similarity conditions
        is_similar = False

        # Exact normalized match
        if normalized_input == normalized_item:
            is_similar = True

        # One contains the other (for subtitles, editions, etc.)
        elif len(normalized_input) >= 5 and len(normalized_item) >= 5:
            if normalized_input in normalized_item or normalized_item in normalized_input:
                is_similar = True

        # Common prefix (at least 60% of shorter string)
        elif len(normalized_input) >= 5 and len(normalized_item) >= 5:
            min_len = min(len(normalized_input), len(normalized_item))
            prefix_len = 0
            for a, b in zip(normalized_input, normalized_item, strict=False):
                if a == b:
                    prefix_len += 1
                else:
                    break
            if prefix_len >= min_len * 0.6:
                is_similar = True

        # Creator match helps with similarity
        if creator and item.creator:
            creator_norm = creator.lower()
            item_creator_norm = item.creator.lower()
            if creator_norm in item_creator_norm or item_creator_norm in creator_norm:
                # If creators match, be more lenient with title matching
                if normalized_input[:4] == normalized_item[:4]:
                    is_similar = True

        if is_similar:
            similar.append(item)

    return similar


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
        if title:
            item.title = title
        if creator is not None:
            item.creator = creator if creator else None
        item.updated_at = datetime.now()
        db.upsert_item(item)
        updated = True

    # Update rating
    if loved or dislike or unlove or rating or notes:
        existing = db.get_rating(item.id)
        loved_status = None
        if loved:
            loved_status = True
        elif dislike:
            loved_status = False
        elif unlove:
            loved_status = None
        elif existing:
            loved_status = existing.loved

        db.upsert_rating(
            Rating(
                item_id=item.id,
                loved=loved_status,
                rating=rating or (existing.rating if existing else None),
                notes=notes if notes is not None else (existing.notes if existing else None),
                rated_at=datetime.now(),
            )
        )
        updated = True

    if updated:
        # Show updated item
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

    # Update rating
    existing = db.get_rating(item.id)
    new_rating = Rating(
        item_id=item.id,
        loved=True,
        rating=rating or (existing.rating if existing else None),
        notes=notes or (existing.notes if existing else None),
        rated_at=datetime.now(),
    )
    db.upsert_rating(new_rating)

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

    # Update rating with loved=False (disliked)
    existing = db.get_rating(item.id)
    new_rating = Rating(
        item_id=item.id,
        loved=False,
        rating=existing.rating if existing else None,
        notes=notes or (existing.notes if existing else None),
        rated_at=datetime.now(),
    )
    db.upsert_rating(new_rating)

    click.echo(f"Disliked: {item.title}")
    if notes:
        click.echo(f"  Notes: {notes}")


@cli.command()
@click.option("--category", "-c", type=click.Choice([c.value for c in Category]), help="Filter by category")
@click.pass_context
def loved(ctx: click.Context, category: str | None) -> None:
    """List all loved items."""
    db: Database = ctx.obj["db"]

    if category:
        items = db.get_items_by_category(Category(category), loved_only=True)
    else:
        items = db.get_all_loved_items()

    if not items:
        click.echo("No loved items yet.")
        return

    click.echo(f"\n{len(items)} loved items:\n")

    # Group by category
    by_category = group_by_category(items)

    for cat, cat_items in sorted(by_category.items()):
        click.echo(f"  {cat.upper()} ({len(cat_items)})")
        for item in cat_items[:10]:
            creator_str = f" - {item.creator}" if item.creator else ""
            click.echo(f"    {item.title}{creator_str}")
        if len(cat_items) > 10:
            click.echo(f"    ... and {len(cat_items) - 10} more")
        click.echo()


@cli.command()
@click.option("--category", "-c", type=click.Choice([c.value for c in Category]), help="Filter by category")
@click.pass_context
def disliked(ctx: click.Context, category: str | None) -> None:
    """List all disliked items."""
    db: Database = ctx.obj["db"]

    cat_filter = Category(category) if category else None
    items = db.get_all_disliked_items(category=cat_filter)

    if not items:
        click.echo("No disliked items yet.")
        return

    click.echo(f"\n{len(items)} disliked items:\n")

    # Group by category
    by_category = group_by_category(items)

    for cat, cat_items in sorted(by_category.items()):
        click.echo(f"  {cat.upper()} ({len(cat_items)})")
        for item in cat_items[:10]:
            creator_str = f" - {item.creator}" if item.creator else ""
            click.echo(f"    {item.title}{creator_str}")
        if len(cat_items) > 10:
            click.echo(f"    ... and {len(cat_items) - 10} more")
        click.echo()


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
    import json as json_module

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
            # Build filter description
            filters = []
            if category:
                filters.append(category)
            if loved:
                filters.append("loved")
            if disliked:
                filters.append("disliked")
            if creator:
                filters.append(f"creator: {creator}")
            if min_rating:
                filters.append(f"rating >= {min_rating}")
            if max_rating:
                filters.append(f"rating <= {max_rating}")
            if search:
                filters.append(f"search: {search}")

            filter_str = f" ({', '.join(filters)})" if filters else ""
            click.echo(f"Count{filter_str}: {total}")
        return

    items = db.query_items(
        category=cat,
        loved=loved_filter,
        creator=creator,
        min_rating=min_rating,
        max_rating=max_rating,
        search=search,
        limit=limit,
        offset=offset,
        random=random,
    )

    # Get total for pagination info
    total = db.count_items(
        category=cat,
        loved=loved_filter,
        creator=creator,
        min_rating=min_rating,
        max_rating=max_rating,
        search=search,
    )

    if format == "json":
        data = {
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": [
                {
                    "id": item.id,
                    "category": item.category.value,
                    "title": item.title,
                    "creator": item.creator,
                    "metadata": item.metadata,
                }
                for item in items
            ],
        }
        click.echo(json_module.dumps(data, indent=2, default=str))
    else:
        if not items:
            click.echo("No items found.")
            return

        click.echo(f"\nShowing {len(items)} of {total} items (offset: {offset}):\n")
        for item in items:
            creator_str = f" - {item.creator}" if item.creator else ""
            click.echo(f"  [{item.category.value:7}] {item.title}{creator_str}")

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

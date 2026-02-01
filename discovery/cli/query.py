"""Query CLI commands."""

import json as json_module

import click

from ..config import QUERY_DEFAULT_LIMIT
from ..db import Database
from ..models import Category
from .core import cli
from .query_helpers import build_filter_description, format_items_as_json, query_items_with_filters


@cli.command()
@click.option("--category", "-c", type=click.Choice([c.value for c in Category]), help="Filter by category")
@click.option("--loved", "-l", is_flag=True, help="Show only loved items")
@click.option("--disliked", "-d", is_flag=True, help="Show only disliked items")
@click.option("--creator", "-a", help="Filter by creator (partial match)")
@click.option("--min-rating", type=click.IntRange(1, 5), help="Minimum rating (1-5)")
@click.option("--max-rating", type=click.IntRange(1, 5), help="Maximum rating (1-5)")
@click.option("--search", "-s", help="Search title/creator")
@click.option("--limit", "-n", type=int, default=QUERY_DEFAULT_LIMIT, help="Max items to show (default: 20)")
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

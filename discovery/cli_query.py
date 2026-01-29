"""Query command logic for Discovery CLI."""

from .db import Database
from .models import Category, Item


def query_items_with_filters(
    db: Database,
    category: Category | None,
    loved_filter: bool | None,
    creator: str | None,
    min_rating: int | None,
    max_rating: int | None,
    search: str | None,
    limit: int,
    offset: int,
    random: bool,
) -> tuple[list[Item], int]:
    """Query items with filters and return items with total count."""
    items = db.query_items(
        category=category,
        loved=loved_filter,
        creator=creator,
        min_rating=min_rating,
        max_rating=max_rating,
        search=search,
        limit=limit,
        offset=offset,
        random=random,
    )

    total = db.count_items(
        category=category,
        loved=loved_filter,
        creator=creator,
        min_rating=min_rating,
        max_rating=max_rating,
        search=search,
    )

    return items, total


def build_filter_description(
    category: str | None,
    loved: bool,
    disliked: bool,
    creator: str | None,
    min_rating: int | None,
    max_rating: int | None,
    search: str | None,
) -> str:
    """Build a human-readable filter description."""
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

    return f" ({', '.join(filters)})" if filters else ""


def format_items_as_json(
    db: Database,
    items: list[Item],
    total: int,
    offset: int,
    limit: int,
) -> dict:
    """Format items for JSON output."""
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": item.id,
                "category": item.category.value,
                "title": item.title,
                "creator": item.creator,
                "sources": [s.source.value for s in db.get_item_sources(item.id)],
                "metadata": item.metadata,
            }
            for item in items
        ],
    }

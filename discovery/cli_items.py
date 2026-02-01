"""Item management logic for Discovery CLI."""

from datetime import datetime

from .db import Database
from .models import Category, Item, ItemSource, Rating, Source
from .utils import creators_match, normalize_title, titles_match


def find_similar_items(db: Database, title: str, category: Category, creator: str | None) -> list[Item]:
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
        if titles_match(item.title, title, threshold=80):
            similar.append(item)
            continue

        if creator and item.creator:
            if creators_match(creator, item.creator, threshold=90) and titles_match(item.title, title, threshold=70):
                similar.append(item)

    return similar


def create_item(
    db: Database,
    item_id: str,
    category: Category,
    title: str,
    creator: str | None,
) -> Item:
    """Create a new item with manual source."""
    item = Item(
        id=item_id,
        category=category,
        title=title,
        creator=creator,
        metadata={},
    )
    db.upsert_item(item)

    item_source = ItemSource(
        item_id=item_id,
        source=Source.MANUAL,
        source_id=item_id,
        source_loved=None,
        source_data={},
    )
    db.upsert_item_source(item_source)

    return item


def update_item_fields(
    db: Database,
    item: Item,
    title: str | None = None,
    creator: str | None = None,
) -> bool:
    """Update item title and/or creator. Returns True if changed."""
    changed = False
    if title:
        item.title = title
        changed = True
    if creator is not None:
        item.creator = creator if creator else None
        changed = True

    if changed:
        item.updated_at = datetime.now()
        db.upsert_item(item)

    return changed


def upsert_rating(
    db: Database,
    item_id: str,
    loved: bool | None = None,
    rating: int | None = None,
    notes: str | None = None,
    preserve_existing: bool = True,
    preserve_loved: bool = True,
) -> None:
    """Update or create rating for an item.

    Args:
        db: Database instance
        item_id: Item to rate
        loved: True=loved, False=disliked, None=neutral
        rating: 1-5 star rating
        notes: Optional notes
        preserve_existing: If True, keep existing values when new ones are None
        preserve_loved: If False, set loved to the provided value even if None
    """
    existing = db.get_rating(item_id) if preserve_existing else None

    # Determine loved value
    if preserve_loved and loved is None and existing:
        final_loved = existing.loved
    else:
        final_loved = loved

    db.upsert_rating(
        Rating(
            item_id=item_id,
            loved=final_loved,
            rating=rating or (existing.rating if existing else None),
            notes=notes if notes is not None else (existing.notes if existing else None),
            rated_at=datetime.now(),
        )
    )


def get_loved_status_from_flags(
    loved: bool,
    dislike: bool,
    unlove: bool = False,
) -> tuple[bool | None, bool]:
    """Determine loved status from flags.

    Returns:
        Tuple of (loved_status, should_preserve_existing).
        If should_preserve_existing is True, caller should use existing value.
    """
    if loved:
        return True, False
    elif dislike:
        return False, False
    elif unlove:
        return None, False
    else:
        return None, True  # Preserve existing

"""Item management logic for Discovery CLI."""

from datetime import datetime

from .db import Database
from .models import Category, Item, ItemSource, Rating, Source
from .utils import normalize_title


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
        normalized_item = normalize_title(item.title)
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
                if normalized_input[:4] == normalized_item[:4]:
                    is_similar = True

        if is_similar:
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


def set_loved_status(
    db: Database,
    item_id: str,
    loved: bool,
    dislike: bool,
    unlove: bool = False,
) -> bool | None:
    """Determine loved status from flags. Returns the status to set."""
    if loved:
        return True
    elif dislike:
        return False
    elif unlove:
        return None
    else:
        existing = db.get_rating(item_id)
        return existing.loved if existing else None

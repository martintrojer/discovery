"""Status and summary functions for Discovery library."""

from typing import Any

from .db import Database
from .models import Category
from .utils import group_by_category


def get_library_status(db: Database) -> dict[str, Any]:
    """Get library status as a structured dict.

    Returns:
        Dict with totals, categories, sources, and sample loved items
    """
    cat_stats = db.get_category_stats()
    source_stats = db.get_source_stats()

    # Get disliked counts per category
    disliked_by_cat = {}
    for cat in Category:
        disliked_by_cat[cat.value] = len(db.get_all_disliked_items(cat))

    # Wishlist stats
    wishlist_items = db.get_wishlist_items()
    wishlist_by_cat = group_by_category(wishlist_items)
    wishlist_counts = {cat: len(items) for cat, items in wishlist_by_cat.items()}

    # Calculate totals
    total_items = sum(s.get("total", 0) for s in cat_stats.values())
    total_loved = sum(s.get("loved", 0) for s in cat_stats.values())
    total_disliked = sum(disliked_by_cat.values())
    total_wishlist = len(wishlist_items)

    data: dict[str, Any] = {
        "totals": {
            "items": total_items,
            "loved": total_loved,
            "disliked": total_disliked,
            "wishlist": total_wishlist,
        },
        "categories": {},
        "sources": source_stats,
        "sample_loved": {},
        "sample_wishlist": {},
    }

    for cat in Category:
        cat_data = cat_stats.get(cat.value, {"total": 0, "loved": 0})
        data["categories"][cat.value] = {
            "total": cat_data["total"],
            "loved": cat_data["loved"],
            "disliked": disliked_by_cat.get(cat.value, 0),
            "wishlist": wishlist_counts.get(cat.value, 0),
        }

        # Sample loved items
        loved_items = db.query_items(category=cat, loved=True, limit=10, random=True)
        data["sample_loved"][cat.value] = [{"title": item.title, "creator": item.creator} for item in loved_items]

        # Sample wishlist items
        wishlist_sample = wishlist_by_cat.get(cat.value, [])[:10]
        data["sample_wishlist"][cat.value] = [
            {"title": item.title, "creator": item.creator, "notes": item.notes} for item in wishlist_sample
        ]

    return data


def format_status_text(db: Database) -> str:
    """Format library status as readable text.

    Args:
        db: Database instance

    Returns:
        Formatted text summary
    """
    data = get_library_status(db)
    lines = []

    lines.append("# Discovery Library Status\n")

    lines.append("## Overview\n")
    lines.append(f"- Total items: {data['totals']['items']}")
    lines.append(f"- Loved: {data['totals']['loved']}")
    lines.append(f"- Disliked: {data['totals']['disliked']}")
    lines.append(f"- Wishlist: {data['totals']['wishlist']}")
    lines.append("")

    if data["categories"]:
        lines.append("## By Category\n")
        for cat in Category:
            cat_data = data["categories"].get(cat.value)
            if not cat_data or cat_data["total"] == 0:
                continue
            lines.append(
                f"- {cat.value}: {cat_data['total']} items ({cat_data['loved']} loved, {cat_data['disliked']} disliked, {cat_data['wishlist']} wishlist)"
            )
        lines.append("")

    if data["sources"]:
        lines.append("## By Source\n")
        for source, count in sorted(data["sources"].items()):
            lines.append(f"- {source}: {count} items")
        lines.append("")

    # Show sample loved items per category
    lines.append("## Sample Loved Items\n")
    for cat in Category:
        sample = data["sample_loved"].get(cat.value, [])
        if not sample:
            continue

        lines.append(f"### {cat.value.upper()}\n")
        for item in sample[:5]:
            creator_str = f" - {item['creator']}" if item.get("creator") else ""
            lines.append(f"- {item['title']}{creator_str}")

        total_loved_cat = data["categories"].get(cat.value, {}).get("loved", 0)
        if total_loved_cat > 5:
            lines.append(f"- ... and {total_loved_cat - 5} more (use 'discovery query -c {cat.value} -l' to see all)")
        lines.append("")

    # Show sample wishlist items per category
    lines.append("## Sample Wishlist Items\n")
    for cat in Category:
        sample = data["sample_wishlist"].get(cat.value, [])
        if not sample:
            continue

        lines.append(f"### {cat.value.upper()}\n")
        for item in sample[:5]:
            creator_str = f" - {item['creator']}" if item.get("creator") else ""
            notes_str = f" ({item['notes']})" if item.get("notes") else ""
            lines.append(f"- {item['title']}{creator_str}{notes_str}")

        total_wishlist_cat = data["categories"].get(cat.value, {}).get("wishlist", 0)
        if total_wishlist_cat > 5:
            lines.append(
                f"- ... and {total_wishlist_cat - 5} more (use 'discovery wishlist view -c {cat.value}' to see all)"
            )
        lines.append("")

    lines.append("## Next Steps\n")
    lines.append("Use 'discovery query' to explore the library:")
    lines.append("  discovery query -l -n 50          # First 50 loved items")
    lines.append("  discovery query -c game -l        # Loved games")
    lines.append("  discovery query -a 'Author' -l    # By creator")
    lines.append("  discovery query -r -n 20          # Random sample")
    lines.append("")

    return "\n".join(lines)

"""Export library data for use with Claude Code skills."""

import json
from pathlib import Path
from typing import Any

from .db import Database
from .models import Category
from .utils import group_by_category


def export_library_summary(
    db: Database,
    output_path: Path | None = None,
    category: Category | None = None,
) -> str:
    """Export a summary of the library for Claude analysis.

    This generates a text summary that can be used in Claude Code
    conversations for analysis and recommendations.

    Args:
        db: Database instance
        output_path: Optional path to write output file
        category: Optional category filter to export only one category
    """
    categories = [category] if category else list(Category)
    cat_label = category.value.upper() if category else "All Categories"

    lines = [f"# Discovery Library Export ({cat_label})\n"]

    # Stats
    stats = db.get_category_stats()
    if category:
        stats = {k: v for k, v in stats.items() if k == category.value}

    disliked_items = db.get_all_disliked_items(category)
    lines.append("## Overview\n")
    total_items = sum(s["total"] for s in stats.values())
    total_loved = sum(s["loved"] for s in stats.values())
    total_disliked = len(disliked_items)
    lines.append(f"- Total items: {total_items}")
    lines.append(f"- Total loved: {total_loved}")
    lines.append(f"- Total disliked: {total_disliked}")
    lines.append("")

    for cat, stat in sorted(stats.items()):
        lines.append(f"- {cat}: {stat['total']} items ({stat['loved']} loved)")
    lines.append("")

    # Loved items by category
    lines.append("## Loved Items (things the user enjoys)\n")

    for cat in categories:
        items = db.get_items_by_category(cat, loved_only=True)
        if not items:
            continue

        lines.append(f"### {cat.value.upper()}\n")
        for item in items[:100]:  # Limit per category
            creator = f" by {item.creator}" if item.creator else ""
            metadata_parts = []
            if item.metadata.get("genre"):
                metadata_parts.append(item.metadata["genre"])
            if item.metadata.get("year"):
                metadata_parts.append(str(item.metadata["year"]))
            metadata_str = f" ({', '.join(metadata_parts)})" if metadata_parts else ""
            lines.append(f"- {item.title}{creator}{metadata_str}")

        if len(items) > 100:
            lines.append(f"- ... and {len(items) - 100} more")
        lines.append("")

    # Disliked items by category
    if disliked_items:
        lines.append("## Disliked Items (things to avoid recommending)\n")

        # Group by category
        by_category = group_by_category(disliked_items)

        for cat, items in sorted(by_category.items()):
            lines.append(f"### {cat.upper()}\n")
            for item in items[:50]:
                creator = f" by {item.creator}" if item.creator else ""
                lines.append(f"- {item.title}{creator}")
            if len(items) > 50:
                lines.append(f"- ... and {len(items) - 50} more")
            lines.append("")

    # All items (for context)
    lines.append("## All Items (sample)\n")
    for cat in categories:
        items = db.get_items_by_category(cat, loved_only=False)
        if not items:
            continue

        lines.append(f"### {cat.value.upper()} ({len(items)} total)\n")
        # Show a sample, prioritizing non-loved to give variety
        loved_ids = {i.id for i in db.get_items_by_category(cat, loved_only=True)}
        disliked_ids = {i.id for i in disliked_items}
        neutral = [i for i in items if i.id not in loved_ids and i.id not in disliked_ids]

        for item in neutral[:30]:
            creator = f" by {item.creator}" if item.creator else ""
            lines.append(f"- {item.title}{creator}")

        if len(neutral) > 30:
            lines.append(f"- ... and {len(neutral) - 30} more")
        lines.append("")

    content = "\n".join(lines)

    if output_path:
        output_path.write_text(content)

    return content


def export_library_json(
    db: Database,
    output_path: Path | None = None,
    category: Category | None = None,
) -> dict[str, Any]:
    """Export library as JSON for programmatic use.

    Args:
        db: Database instance
        output_path: Optional path to write output file
        category: Optional category filter to export only one category
    """
    categories = [category] if category else list(Category)
    disliked_items = db.get_all_disliked_items(category)

    # Get stats, filtered if category specified
    stats = db.get_category_stats()
    if category:
        stats = {k: v for k, v in stats.items() if k == category.value}

    data: dict[str, Any] = {
        "stats": stats,
        "source_stats": db.get_source_stats(),
        "loved": {},
        "disliked": {},
        "all": {},
    }

    # Group disliked by category
    disliked_by_cat = group_by_category(disliked_items)

    for cat in categories:
        loved = db.get_items_by_category(cat, loved_only=True)
        all_items = db.get_items_by_category(cat, loved_only=False)

        data["loved"][cat.value] = [
            {
                "title": i.title,
                "creator": i.creator,
                "metadata": i.metadata,
            }
            for i in loved
        ]

        data["disliked"][cat.value] = [
            {
                "title": i.title,
                "creator": i.creator,
                "metadata": i.metadata,
            }
            for i in disliked_by_cat.get(cat.value, [])
        ]

        data["all"][cat.value] = [
            {
                "title": i.title,
                "creator": i.creator,
                "metadata": i.metadata,
            }
            for i in all_items
        ]

    if output_path:
        output_path.write_text(json.dumps(data, indent=2, default=str))

    return data

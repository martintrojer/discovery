"""Base importer class."""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from ..utils import creators_match, normalize_title, strip_sequel_numbers, titles_match, titles_match_strict


@dataclass
class ImportResult:
    """Result of an import operation."""

    source: Source
    items_added: int
    items_updated: int
    errors: list[str]


class BaseImporter(ABC):
    """Base class for all data importers."""

    source: Source
    category: Category

    def __init__(self, db: Database) -> None:
        self.db = db

    def create_item_pair(
        self,
        title: str,
        creator: str | None,
        source_id: str,
        loved: bool | None = None,
        category: Category | None = None,
        metadata: dict | None = None,
        source_data: dict | None = None,
    ) -> tuple[Item, ItemSource]:
        """Create Item and ItemSource with proper IDs and defaults."""
        item_id = str(uuid.uuid4())
        item = Item(
            id=item_id,
            category=category or self.category,
            title=title,
            creator=creator,
            metadata=metadata or {},
        )
        item_source = ItemSource(
            item_id=item_id,
            source=self.source,
            source_id=source_id,
            source_loved=loved,
            source_data=source_data or {},
        )
        return item, item_source

    @abstractmethod
    def get_manual_steps(self) -> str:
        """Return instructions for obtaining the export file."""
        pass

    @abstractmethod
    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse an export file and return items with their source info."""
        pass

    def post_import_item(self, item: Item, item_source: ItemSource) -> None:
        """Hook for post-processing each imported item."""
        return None

    def post_import(self, result: ImportResult) -> None:
        """Hook for post-processing after import."""
        return None

    def import_from_file(self, file_path: Path) -> ImportResult:
        """Import items from an export file."""
        items_added = 0
        items_updated = 0
        errors: list[str] = []

        try:
            parsed = self.parse_file(file_path)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            return ImportResult(
                source=self.source,
                items_added=0,
                items_updated=0,
                errors=[f"Failed to parse file: {e}"],
            )

        for item, item_source in parsed:
            try:
                # Check if item already exists from this source
                existing = self.db.find_item_by_source(self.source, item_source.source_id)

                if existing:
                    # Update existing item
                    item.id = existing.id
                    item.created_at = existing.created_at
                    item_source.item_id = existing.id  # Link source to existing item
                    self.db.upsert_item(item)
                    self.db.upsert_item_source(item_source)
                    items_updated += 1
                else:
                    # Check if we can deduplicate with existing item
                    dedup_item = self._find_duplicate(item)
                    if dedup_item:
                        # Link to existing item
                        item_source.item_id = dedup_item.id
                        self.db.upsert_item_source(item_source)
                        items_updated += 1
                    else:
                        # Add new item
                        self.db.upsert_item(item)
                        item_source.item_id = item.id
                        self.db.upsert_item_source(item_source)
                        items_added += 1

                self.post_import_item(item, item_source)
            except Exception as e:
                errors.append(f"Failed to import '{item.title}': {e}")

        result = ImportResult(
            source=self.source,
            items_added=items_added,
            items_updated=items_updated,
            errors=errors,
        )

        self.post_import(result)

        return result

    def _find_duplicate(self, item: Item) -> Item | None:
        """Try to find an existing item that matches (for deduplication).

        Uses aggressive matching:
        - Normalized title comparison (lowercase, stripped punctuation)
        - Fuzzy creator matching
        - Cross-category matching for ambiguous items (e.g., book vs movie)
        """
        # First try exact match in same category
        matches = self.db.search_items(item.title, category=item.category)
        for match in matches:
            if titles_match(match.title, item.title):
                if creators_match(match.creator, item.creator):
                    return match

        # Try normalized title match
        normalized_title = normalize_title(item.title)
        all_matches = self.db.search_items(item.title[:20], category=item.category)
        for match in all_matches:
            if normalize_title(match.title) == normalized_title:
                if creators_match(match.creator, item.creator):
                    return match

        # Fallback: small-database fuzzy scan within category
        if not matches and not all_matches:
            candidates = self.db.get_items_by_category(item.category)
            if len(candidates) <= 5000:
                for match in candidates:
                    if self._is_strict_title_match(match, item):
                        return match

        return None

    def _is_strict_title_match(self, candidate: Item, target: Item) -> bool:
        """Conservative fuzzy match for small DB fallback scans."""
        if not candidate.title or not target.title:
            return False

        if not titles_match_strict(candidate.title, target.title):
            return False

        norm_cand = normalize_title(candidate.title)
        norm_target = normalize_title(target.title)
        creator_threshold = 90
        if strip_sequel_numbers(norm_cand) == strip_sequel_numbers(norm_target):
            creator_threshold = 100

        return creators_match(candidate.creator, target.creator, threshold=creator_threshold)

"""Base importer class."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rapidfuzz import fuzz

from ..db import Database
from ..models import Category, Item, ItemSource, Source
from ..utils import creators_match, normalize_title, titles_match


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

    def __init__(self, db: Database):
        self.db = db

    @abstractmethod
    def get_manual_steps(self) -> str:
        """Return instructions for obtaining the export file."""
        pass

    @abstractmethod
    def parse_file(self, file_path: Path) -> list[tuple[Item, ItemSource]]:
        """Parse an export file and return items with their source info."""
        pass

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

            except Exception as e:
                errors.append(f"Failed to import '{item.title}': {e}")

        # Update sync state
        from ..models import SyncState

        self.db.update_sync_state(SyncState(source=self.source, last_sync=datetime.now()))

        return ImportResult(
            source=self.source,
            items_added=items_added,
            items_updated=items_updated,
            errors=errors,
        )

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

        norm_cand = normalize_title(candidate.title)
        norm_target = normalize_title(target.title)

        if norm_cand == norm_target:
            return creators_match(candidate.creator, target.creator)

        if (norm_cand in norm_target or norm_target in norm_cand) and min(len(norm_cand), len(norm_target)) >= 5:
            return creators_match(candidate.creator, target.creator, threshold=90)

        # Match sequels like "X 2" vs "X II" only with strong creator match
        def strip_numbers(s: str) -> str:
            s = re.sub(r"\s+[ivxlcdm]+$", "", s, flags=re.IGNORECASE)
            s = re.sub(r"\s+\d+$", "", s)
            return s.strip()

        stripped_cand = strip_numbers(norm_cand)
        stripped_target = strip_numbers(norm_target)
        if stripped_cand and stripped_cand == stripped_target:
            return creators_match(candidate.creator, target.creator, threshold=100)

        score = fuzz.token_set_ratio(norm_cand, norm_target)
        if score >= 92:
            return creators_match(candidate.creator, target.creator, threshold=90)

        return False

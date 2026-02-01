"""DuckDB storage layer for Discovery."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from .models import Category, Item, ItemSource, Rating, Source, WishlistItem

DEFAULT_DB_PATH = Path.home() / ".local" / "state" / "discovery" / "discovery.db"
BACKUP_DIR = Path.home() / ".local" / "state" / "discovery" / "backups"
MAX_BACKUPS = 10  # Keep last 10 backups


class Database:
    """DuckDB-backed storage for discovery data."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.db_path))
        self._init_schema()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False

    def _init_schema(self) -> None:
        """Initialize database schema."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                creator TEXT,
                metadata JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS item_sources (
                item_id TEXT NOT NULL,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_loved BOOLEAN,
                source_data JSON,
                last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (item_id, source),
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                item_id TEXT PRIMARY KEY,
                loved BOOLEAN,
                rating INTEGER CHECK (rating IS NULL OR (rating >= 1 AND rating <= 5)),
                notes TEXT,
                rated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS wishlist_items (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                creator TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()

    def _row_to_item(self, row: tuple) -> Item:
        """Convert a database row to an Item.

        Args:
            row: Tuple of (id, category, title, creator, metadata, created_at, updated_at)

        Returns:
            Item instance
        """
        return Item(
            id=row[0],
            category=Category(row[1]),
            title=row[2],
            creator=row[3],
            metadata=json.loads(row[4]) if row[4] else {},
            created_at=row[5],
            updated_at=row[6],
        )

    def _row_to_wishlist_item(self, row: tuple) -> WishlistItem:
        """Convert a database row to a WishlistItem.

        Args:
            row: Tuple of (id, category, title, creator, notes, created_at)

        Returns:
            WishlistItem instance
        """
        return WishlistItem(
            id=row[0],
            category=Category(row[1]),
            title=row[2],
            creator=row[3],
            notes=row[4],
            created_at=row[5],
        )

    # Backup operations

    def create_backup(self, reason: str = "manual") -> Path | None:
        """Create a backup of the database.

        Args:
            reason: Description of why backup was created (e.g., "import", "manual")

        Returns:
            Path to backup file, or None if database doesn't exist yet
        """
        if not self.db_path.exists():
            return None

        backup_dir = BACKUP_DIR
        if self.db_path != DEFAULT_DB_PATH:
            # For test databases, use a local backup dir
            backup_dir = self.db_path.parent / "backups"

        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_name = f"discovery_{timestamp}_{reason}.db"
        backup_path = backup_dir / backup_name

        # Close connection, copy file, reopen
        self.conn.close()
        shutil.copy2(self.db_path, backup_path)
        self.conn = duckdb.connect(str(self.db_path))

        # Cleanup old backups
        self._cleanup_old_backups(backup_dir)

        return backup_path

    def _cleanup_old_backups(self, backup_dir: Path) -> None:
        """Remove old backups, keeping only the most recent MAX_BACKUPS."""
        backups = sorted(
            backup_dir.glob("discovery_*.db"),
            key=lambda p: self._parse_backup_timestamp(p) or datetime.fromtimestamp(p.stat().st_mtime),
            reverse=True,
        )

        for old_backup in backups[MAX_BACKUPS:]:
            old_backup.unlink()

    def list_backups(self) -> list[dict]:
        """List available backups.

        Returns:
            List of dicts with backup info (path, timestamp, reason, size)
        """
        backup_dir = BACKUP_DIR
        if self.db_path != DEFAULT_DB_PATH:
            backup_dir = self.db_path.parent / "backups"

        if not backup_dir.exists():
            return []

        backups = []
        for backup_file in sorted(
            backup_dir.glob("discovery_*.db"),
            key=lambda p: self._parse_backup_timestamp(p) or datetime.fromtimestamp(p.stat().st_mtime),
            reverse=True,
        ):
            reason = self._parse_backup_reason(backup_file)
            timestamp = self._parse_backup_timestamp(backup_file) or datetime.fromtimestamp(backup_file.stat().st_mtime)

            backups.append(
                {
                    "path": backup_file,
                    "timestamp": timestamp,
                    "reason": reason,
                    "size_kb": backup_file.stat().st_size // 1024,
                }
            )

        return backups

    def _parse_backup_timestamp(self, backup_file: Path) -> datetime | None:
        """Parse timestamp from backup filename (supports legacy and microsecond formats)."""
        parts = backup_file.stem.split("_")
        if len(parts) < 4:
            return None

        date_str = parts[1]
        time_str = parts[2]
        if len(parts) >= 5 and parts[3].isdigit():
            micros = parts[3]
            fmt = "%Y%m%d_%H%M%S_%f"
            ts = f"{date_str}_{time_str}_{micros}"
        else:
            fmt = "%Y%m%d_%H%M%S"
            ts = f"{date_str}_{time_str}"

        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            return None

    def _parse_backup_reason(self, backup_file: Path) -> str:
        parts = backup_file.stem.split("_")
        if len(parts) >= 5 and parts[3].isdigit():
            return "_".join(parts[4:])
        if len(parts) >= 4:
            return "_".join(parts[3:])
        return "unknown"

    def restore_backup(self, backup_path: Path) -> bool:
        """Restore database from a backup.

        Args:
            backup_path: Path to backup file

        Returns:
            True if successful, False otherwise
        """
        if not backup_path.exists():
            return False

        # Create a backup of current state before restoring
        self.create_backup("pre_restore")

        # Close connection, replace file, reopen
        self.conn.close()
        shutil.copy2(backup_path, self.db_path)
        self.conn = duckdb.connect(str(self.db_path))

        return True

    # Item operations

    def upsert_item(self, item: Item) -> None:
        """Insert or update an item."""
        self.conn.execute(
            """
            INSERT INTO items (id, category, title, creator, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                creator = EXCLUDED.creator,
                metadata = EXCLUDED.metadata,
                updated_at = EXCLUDED.updated_at
            """,
            [
                item.id,
                item.category.value,
                item.title,
                item.creator,
                json.dumps(item.metadata),
                item.created_at,
                item.updated_at,
            ],
        )

    def get_item(self, item_id: str) -> Item | None:
        """Get an item by ID."""
        result = self.conn.execute(
            "SELECT id, category, title, creator, metadata, created_at, updated_at FROM items WHERE id = ?",
            [item_id],
        ).fetchone()

        if not result:
            return None

        return self._row_to_item(result)

    def find_item_by_source(self, source: Source, source_id: str) -> Item | None:
        """Find an item by its source ID."""
        result = self.conn.execute(
            """
            SELECT i.id, i.category, i.title, i.creator, i.metadata, i.created_at, i.updated_at
            FROM items i
            JOIN item_sources s ON i.id = s.item_id
            WHERE s.source = ? AND s.source_id = ?
            """,
            [source.value, source_id],
        ).fetchone()

        if not result:
            return None

        return self._row_to_item(result)

    def search_items(
        self,
        query: str,
        category: Category | None = None,
        loved_only: bool = False,
    ) -> list[Item]:
        """Search items by title/creator."""
        sql = """
            SELECT DISTINCT i.id, i.category, i.title, i.creator, i.metadata, i.created_at, i.updated_at
            FROM items i
            LEFT JOIN ratings r ON i.id = r.item_id
            LEFT JOIN item_sources s ON i.id = s.item_id
            WHERE (i.title ILIKE ? OR i.creator ILIKE ?)
        """
        params: list[Any] = [f"%{query}%", f"%{query}%"]

        if category:
            sql += " AND i.category = ?"
            params.append(category.value)

        if loved_only:
            sql += " AND (r.loved = TRUE OR s.source_loved = TRUE)"

        results = self.conn.execute(sql, params).fetchall()

        return [self._row_to_item(r) for r in results]

    def get_items_by_category(self, category: Category, loved_only: bool = False) -> list[Item]:
        """Get all items in a category."""
        sql = """
            SELECT DISTINCT i.id, i.category, i.title, i.creator, i.metadata, i.created_at, i.updated_at
            FROM items i
            LEFT JOIN ratings r ON i.id = r.item_id
            LEFT JOIN item_sources s ON i.id = s.item_id
            WHERE i.category = ?
        """
        params: list[Any] = [category.value]

        if loved_only:
            sql += " AND (r.loved = TRUE OR s.source_loved = TRUE)"

        results = self.conn.execute(sql, params).fetchall()

        return [self._row_to_item(r) for r in results]

    def get_all_loved_items(self, category: Category | None = None) -> list[Item]:
        """Get all items that are loved (either locally or in source).

        Args:
            category: Optional category to filter by

        Returns:
            List of loved items
        """
        sql = """
            SELECT DISTINCT i.id, i.category, i.title, i.creator, i.metadata, i.created_at, i.updated_at
            FROM items i
            LEFT JOIN ratings r ON i.id = r.item_id
            LEFT JOIN item_sources s ON i.id = s.item_id
            WHERE (r.loved = TRUE OR s.source_loved = TRUE)
        """
        params: list = []

        if category:
            sql += " AND i.category = ?"
            params.append(category.value)

        results = self.conn.execute(sql, params).fetchall()

        return [self._row_to_item(r) for r in results]

    def get_all_disliked_items(self, category: Category | None = None) -> list[Item]:
        """Get all items that are disliked (loved=False).

        Args:
            category: Optional category to filter by

        Returns:
            List of disliked items
        """
        sql = """
            SELECT DISTINCT i.id, i.category, i.title, i.creator, i.metadata, i.created_at, i.updated_at
            FROM items i
            JOIN ratings r ON i.id = r.item_id
            WHERE r.loved = FALSE
        """
        params: list = []

        if category:
            sql += " AND i.category = ?"
            params.append(category.value)

        results = self.conn.execute(sql, params).fetchall()

        return [self._row_to_item(r) for r in results]

    # Item source operations

    def upsert_item_source(self, item_source: ItemSource) -> None:
        """Insert or update an item source link."""
        self.conn.execute(
            """
            INSERT INTO item_sources (item_id, source, source_id, source_loved, source_data, last_synced)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (item_id, source) DO UPDATE SET
                source_loved = EXCLUDED.source_loved,
                source_data = EXCLUDED.source_data,
                last_synced = EXCLUDED.last_synced
            """,
            [
                item_source.item_id,
                item_source.source.value,
                item_source.source_id,
                item_source.source_loved,
                json.dumps(item_source.source_data),
                item_source.last_synced,
            ],
        )

    def get_item_sources(self, item_id: str) -> list[ItemSource]:
        """Get all sources for an item."""
        results = self.conn.execute(
            "SELECT item_id, source, source_id, source_loved, source_data, last_synced FROM item_sources WHERE item_id = ?",
            [item_id],
        ).fetchall()

        return [
            ItemSource(
                item_id=r[0],
                source=Source(r[1]),
                source_id=r[2],
                source_loved=r[3],
                source_data=json.loads(r[4]) if r[4] else {},
                last_synced=r[5],
            )
            for r in results
        ]

    # Rating operations

    def upsert_rating(self, rating: Rating) -> None:
        """Insert or update a rating."""
        self.conn.execute(
            """
            INSERT INTO ratings (item_id, loved, rating, notes, rated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (item_id) DO UPDATE SET
                loved = EXCLUDED.loved,
                rating = EXCLUDED.rating,
                notes = EXCLUDED.notes,
                rated_at = EXCLUDED.rated_at
            """,
            [
                rating.item_id,
                rating.loved,
                rating.rating,
                rating.notes,
                rating.rated_at,
            ],
        )

    def get_rating(self, item_id: str) -> Rating | None:
        """Get rating for an item."""
        result = self.conn.execute(
            "SELECT item_id, loved, rating, notes, rated_at FROM ratings WHERE item_id = ?",
            [item_id],
        ).fetchone()

        if not result:
            return None

        return Rating(
            item_id=result[0],
            loved=result[1],
            rating=result[2],
            notes=result[3],
            rated_at=result[4],
        )

    # Wishlist operations

    def add_wishlist_item(self, item: WishlistItem) -> None:
        """Add an item to the wishlist."""
        self.conn.execute(
            """
            INSERT INTO wishlist_items (id, category, title, creator, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                item.id,
                item.category.value,
                item.title,
                item.creator,
                item.notes,
                item.created_at,
            ],
        )

    def get_wishlist_item(self, item_id: str) -> WishlistItem | None:
        """Get a wishlist item by ID."""
        result = self.conn.execute(
            "SELECT id, category, title, creator, notes, created_at FROM wishlist_items WHERE id = ?",
            [item_id],
        ).fetchone()

        if not result:
            return None

        return self._row_to_wishlist_item(result)

    def get_wishlist_items(self, category: Category | None = None) -> list[WishlistItem]:
        """Get all wishlist items, optionally filtered by category."""
        sql = "SELECT id, category, title, creator, notes, created_at FROM wishlist_items"
        params: list[Any] = []

        if category:
            sql += " WHERE category = ?"
            params.append(category.value)

        sql += " ORDER BY title"
        results = self.conn.execute(sql, params).fetchall()
        return [self._row_to_wishlist_item(r) for r in results]

    def search_wishlist_items(self, query: str, category: Category | None = None) -> list[WishlistItem]:
        """Search wishlist items by title/creator."""
        sql = """
            SELECT id, category, title, creator, notes, created_at
            FROM wishlist_items
            WHERE (title ILIKE ? OR creator ILIKE ?)
        """
        params: list[Any] = [f"%{query}%", f"%{query}%"]

        if category:
            sql += " AND category = ?"
            params.append(category.value)

        sql += " ORDER BY title"
        results = self.conn.execute(sql, params).fetchall()
        return [self._row_to_wishlist_item(r) for r in results]

    def remove_wishlist_item(self, item_id: str) -> bool:
        """Remove a wishlist item by ID. Returns True if removed."""
        result = self.conn.execute(
            "SELECT COUNT(*) FROM wishlist_items WHERE id = ?",
            [item_id],
        ).fetchone()
        if not result or result[0] == 0:
            return False
        self.conn.execute("DELETE FROM wishlist_items WHERE id = ?", [item_id])
        return True

    # Analytics queries

    def get_category_stats(self) -> dict[str, dict[str, int]]:
        """Get item counts by category."""
        results = self.conn.execute("""
            SELECT
                i.category,
                COUNT(DISTINCT i.id) as total,
                COUNT(DISTINCT CASE WHEN r.loved = TRUE OR s.source_loved = TRUE THEN i.id END) as loved
            FROM items i
            LEFT JOIN ratings r ON i.id = r.item_id
            LEFT JOIN item_sources s ON i.id = s.item_id
            GROUP BY i.category
        """).fetchall()

        return {r[0]: {"total": r[1], "loved": r[2]} for r in results}

    def get_source_stats(self) -> dict[str, int]:
        """Get item counts by source."""
        results = self.conn.execute("""
            SELECT source, COUNT(DISTINCT item_id) as count
            FROM item_sources
            GROUP BY source
        """).fetchall()

        return {r[0]: r[1] for r in results}

    # Advanced query operations

    def _build_item_filters(
        self,
        category: Category | None,
        loved: bool | None,
        creator: str | None,
        min_rating: int | None,
        max_rating: int | None,
        search: str | None,
    ) -> tuple[str, list[Any]]:
        sql = " WHERE 1=1"
        params: list[Any] = []

        if category:
            sql += " AND i.category = ?"
            params.append(category.value)

        if loved is True:
            sql += " AND (r.loved = TRUE OR s.source_loved = TRUE)"
        elif loved is False:
            sql += " AND r.loved = FALSE"

        if creator:
            sql += " AND i.creator ILIKE ?"
            params.append(f"%{creator}%")

        if min_rating:
            sql += " AND r.rating >= ?"
            params.append(min_rating)

        if max_rating:
            sql += " AND r.rating <= ?"
            params.append(max_rating)

        if search:
            sql += " AND (i.title ILIKE ? OR i.creator ILIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])

        return sql, params

    def count_items(
        self,
        category: Category | None = None,
        loved: bool | None = None,
        creator: str | None = None,
        min_rating: int | None = None,
        max_rating: int | None = None,
        search: str | None = None,
    ) -> int:
        """Count items matching filters.

        Args:
            category: Filter by category
            loved: Filter by loved status (True=loved, False=disliked, None=any)
            creator: Filter by creator (partial match)
            min_rating: Minimum rating (1-5)
            max_rating: Maximum rating (1-5)
            search: Search term for title/creator

        Returns:
            Count of matching items
        """
        sql = """
            SELECT COUNT(DISTINCT i.id)
            FROM items i
            LEFT JOIN ratings r ON i.id = r.item_id
            LEFT JOIN item_sources s ON i.id = s.item_id
        """
        filter_sql, params = self._build_item_filters(
            category=category,
            loved=loved,
            creator=creator,
            min_rating=min_rating,
            max_rating=max_rating,
            search=search,
        )
        sql += filter_sql

        result = self.conn.execute(sql, params).fetchone()
        return result[0] if result else 0

    def query_items(
        self,
        category: Category | None = None,
        loved: bool | None = None,
        creator: str | None = None,
        min_rating: int | None = None,
        max_rating: int | None = None,
        search: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        random: bool = False,
    ) -> list[Item]:
        """Query items with filters and pagination.

        Args:
            category: Filter by category
            loved: Filter by loved status (True=loved, False=disliked, None=any)
            creator: Filter by creator (partial match)
            min_rating: Minimum rating (1-5)
            max_rating: Maximum rating (1-5)
            search: Search term for title/creator
            limit: Maximum items to return
            offset: Number of items to skip
            random: Return random sample instead of sorted

        Returns:
            List of matching items
        """
        sql = """
            SELECT DISTINCT i.id, i.category, i.title, i.creator, i.metadata, i.created_at, i.updated_at
            FROM items i
            LEFT JOIN ratings r ON i.id = r.item_id
            LEFT JOIN item_sources s ON i.id = s.item_id
        """
        filter_sql, params = self._build_item_filters(
            category=category,
            loved=loved,
            creator=creator,
            min_rating=min_rating,
            max_rating=max_rating,
            search=search,
        )
        sql += filter_sql

        if random:
            sql += " ORDER BY RANDOM()"
        else:
            sql += " ORDER BY i.title"

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        if offset:
            sql += " OFFSET ?"
            params.append(offset)

        results = self.conn.execute(sql, params).fetchall()
        return [self._row_to_item(r) for r in results]

    def get_random_sample(
        self,
        count: int = 10,
        category: Category | None = None,
        loved: bool | None = None,
    ) -> list[Item]:
        """Get a random sample of items.

        Args:
            count: Number of items to return
            category: Filter by category
            loved: Filter by loved status

        Returns:
            Random sample of items
        """
        return self.query_items(
            category=category,
            loved=loved,
            limit=count,
            random=True,
        )

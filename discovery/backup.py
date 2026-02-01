"""Database backup management."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

DEFAULT_BACKUP_DIR = Path.home() / ".local" / "state" / "discovery" / "backups"
MAX_BACKUPS = 10  # Keep last 10 backups


class BackupManager:
    """Handle database backup operations for a given database path."""

    def __init__(self, db_path: Path, default_db_path: Path, default_backup_dir: Path = DEFAULT_BACKUP_DIR):
        self.db_path = db_path
        self.default_db_path = default_db_path
        self.default_backup_dir = default_backup_dir

    def create_backup_file(self, reason: str = "manual") -> Path:
        """Create a backup file and return its path."""
        backup_dir = self._get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_name = f"discovery_{timestamp}_{reason}.db"
        backup_path = backup_dir / backup_name

        shutil.copy2(self.db_path, backup_path)
        self._cleanup_old_backups(backup_dir)

        return backup_path

    def list_backups(self) -> list[dict]:
        """List available backups."""
        backup_dir = self._get_backup_dir()
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

    def restore_backup(self, backup_path: Path) -> bool:
        """Restore the database file from a backup."""
        if not backup_path.exists():
            return False

        shutil.copy2(backup_path, self.db_path)
        return True

    def _get_backup_dir(self) -> Path:
        if self.db_path != self.default_db_path:
            return self.db_path.parent / "backups"
        return self.default_backup_dir

    def _cleanup_old_backups(self, backup_dir: Path) -> None:
        """Remove old backups, keeping only the most recent MAX_BACKUPS."""
        backups = sorted(
            backup_dir.glob("discovery_*.db"),
            key=lambda p: self._parse_backup_timestamp(p) or datetime.fromtimestamp(p.stat().st_mtime),
            reverse=True,
        )

        for old_backup in backups[MAX_BACKUPS:]:
            old_backup.unlink()

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

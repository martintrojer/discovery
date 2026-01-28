"""Tests for database backup functionality."""

from pathlib import Path

from click.testing import CliRunner

from discovery.cli import cli
from discovery.db import Database
from discovery.models import Category, Item


class TestDatabaseBackup:
    """Test database backup operations."""

    def test_create_backup(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)

        # Add some data
        db.upsert_item(Item(id="1", category=Category.GAME, title="Test Game"))

        backup_path = db.create_backup("test")

        assert backup_path is not None
        assert backup_path.exists()
        assert "test" in backup_path.name
        db.close()

    def test_create_backup_no_db(self, tmp_path: Path):
        db_path = tmp_path / "nonexistent.db"
        # Don't create any data, so the db file won't exist
        db = Database(db_path=db_path)
        # Close immediately so no file is created
        db.close()

        # Reopen without creating schema
        db = Database(db_path=db_path)
        # The db file now exists after init
        backup_path = db.create_backup("test")
        assert backup_path is not None  # File exists after init
        db.close()

    def test_list_backups_empty(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)

        backups = db.list_backups()

        assert backups == []
        db.close()

    def test_list_backups(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)
        db.upsert_item(Item(id="1", category=Category.GAME, title="Test"))

        db.create_backup("first")
        db.create_backup("second")

        backups = db.list_backups()

        assert len(backups) == 2
        assert backups[0]["reason"] == "second"  # Most recent first
        assert backups[1]["reason"] == "first"
        db.close()

    def test_restore_backup(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)

        # Add initial data
        db.upsert_item(Item(id="1", category=Category.GAME, title="Original"))

        # Create backup
        backup_path = db.create_backup("before_change")
        assert backup_path is not None

        # Modify data
        db.upsert_item(Item(id="2", category=Category.MOVIE, title="New Item"))
        assert len(db.get_items_by_category(Category.MOVIE)) == 1

        # Restore backup
        result = db.restore_backup(backup_path)

        assert result is True
        # New item should be gone
        assert len(db.get_items_by_category(Category.MOVIE)) == 0
        # Original should still exist
        assert db.get_item("1") is not None
        db.close()

    def test_backup_cleanup_old(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path)
        db.upsert_item(Item(id="1", category=Category.GAME, title="Test"))

        # Create more than MAX_BACKUPS
        for i in range(15):
            db.create_backup(f"backup_{i}")

        backups = db.list_backups()

        # Should only keep MAX_BACKUPS (10)
        assert len(backups) <= 10
        db.close()


class TestBackupCLI:
    """Test backup CLI commands."""

    def test_backup_create(self, tmp_path: Path, monkeypatch):
        import discovery.db as db_module

        db_path = tmp_path / "test.db"
        monkeypatch.setattr(db_module, "DEFAULT_DB_PATH", db_path)
        monkeypatch.setattr(db_module, "BACKUP_DIR", tmp_path / "backups")

        db = Database(db_path=db_path)
        db.upsert_item(Item(id="1", category=Category.GAME, title="Test"))
        db.close()

        runner = CliRunner()
        result = runner.invoke(cli, ["backup", "create"])

        assert result.exit_code == 0
        assert "Backup created" in result.output

    def test_backup_list_empty(self, tmp_path: Path, monkeypatch):
        import discovery.db as db_module

        db_path = tmp_path / "test.db"
        monkeypatch.setattr(db_module, "DEFAULT_DB_PATH", db_path)
        monkeypatch.setattr(db_module, "BACKUP_DIR", tmp_path / "backups")

        runner = CliRunner()
        result = runner.invoke(cli, ["backup", "list"])

        assert result.exit_code == 0
        assert "No backups found" in result.output

    def test_backup_list_with_backups(self, tmp_path: Path, monkeypatch):
        import discovery.db as db_module

        db_path = tmp_path / "test.db"
        monkeypatch.setattr(db_module, "DEFAULT_DB_PATH", db_path)
        monkeypatch.setattr(db_module, "BACKUP_DIR", tmp_path / "backups")

        db = Database(db_path=db_path)
        db.upsert_item(Item(id="1", category=Category.GAME, title="Test"))
        db.create_backup("test_backup")
        db.close()

        runner = CliRunner()
        result = runner.invoke(cli, ["backup", "list"])

        assert result.exit_code == 0
        assert "1 backup(s) available" in result.output
        assert "test_backup" in result.output

    def test_backup_restore(self, tmp_path: Path, monkeypatch):
        import discovery.db as db_module

        db_path = tmp_path / "test.db"
        monkeypatch.setattr(db_module, "DEFAULT_DB_PATH", db_path)
        monkeypatch.setattr(db_module, "BACKUP_DIR", tmp_path / "backups")

        db = Database(db_path=db_path)
        db.upsert_item(Item(id="1", category=Category.GAME, title="Original"))
        db.create_backup("restore_test")
        db.upsert_item(Item(id="2", category=Category.MOVIE, title="Added Later"))
        db.close()

        runner = CliRunner()
        result = runner.invoke(cli, ["backup", "restore", "1"], input="y\n")

        assert result.exit_code == 0
        assert "Database restored" in result.output


class TestImportCreatesBackup:
    """Test that imports create backups."""

    def test_import_creates_backup(self, tmp_path: Path, monkeypatch):
        import json

        import discovery.db as db_module

        db_path = tmp_path / "test.db"
        monkeypatch.setattr(db_module, "DEFAULT_DB_PATH", db_path)
        monkeypatch.setattr(db_module, "BACKUP_DIR", tmp_path / "backups")

        # Create initial database with data
        db = Database(db_path=db_path)
        db.upsert_item(Item(id="1", category=Category.MUSIC, title="Existing Song"))
        db.close()

        # Create import file
        data = {"tracks": [{"artist": "Artist", "album": "Album", "track": "Song"}]}
        import_file = tmp_path / "library.json"
        import_file.write_text(json.dumps(data))

        runner = CliRunner()
        result = runner.invoke(cli, ["import", "spotify", str(import_file)])

        assert result.exit_code == 0
        assert "Backup created" in result.output

        # Verify backup was created
        db = Database(db_path=db_path)
        backups = db.list_backups()
        assert len(backups) >= 1
        assert any("spotify" in b["reason"] for b in backups)
        db.close()

"""Shared test fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from discovery.db import Database


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test_discovery.db"


@pytest.fixture
def db(tmp_db_path: Path) -> Iterator[Database]:
    """Create a temporary database for testing."""
    database = Database(db_path=tmp_db_path)
    yield database
    database.close()


@pytest.fixture
def tmp_import_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for import files."""
    import_dir = tmp_path / "imports"
    import_dir.mkdir()
    return import_dir

# Discovery

A tool to discover new things you might love across music, games, books, movies, and more.

## Development

### Setup

```bash
uv sync
```

### Before Commits

Always run:

```bash
uv run ruff format discovery/ tests/
uv run ruff check discovery/ tests/
uv run ty check discovery/
uv run pytest tests/
```

Fix any issues before committing.

### Running

```bash
uv run discovery --help
```

### Testing

```bash
# Run all tests
uv run pytest tests/

# Run with verbose output
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_db.py

# Run specific test
uv run pytest tests/test_db.py::TestItemOperations::test_upsert_and_get_item
```

Tests use temporary DuckDB databases that are automatically cleaned up.

### Project Structure

- `discovery/` - Main package
  - `cli.py` - CLI commands (uses factory pattern for import commands)
  - `db.py` - DuckDB storage layer (supports context manager)
  - `models.py` - Data models (Category, Source, Item, Rating, etc.)
  - `utils.py` - Shared utilities (normalize_title, format_rating, etc.)
  - `export.py` - Export for Claude Code skill
  - `importers/` - Data importers
    - `base.py` - BaseImporter class
    - `spotify.py`, `netflix.py`, `steam.py`, etc.
- `tests/` - Test suite
  - `conftest.py` - Shared pytest fixtures
  - `test_models.py` - Unit tests for data models
  - `test_db.py` - Unit tests for database layer
  - `test_export.py` - Unit tests for export functions
  - `test_importers.py` - Unit tests for importers and utilities
  - `test_cli.py` - Integration tests for CLI
  - `test_deduplication.py` - Tests for deduplication logic
  - `test_backup.py` - Tests for backup functionality
- `.claude/skills/discovery.md` - Claude Code skill for AI analysis

### Adding New Importers

1. Create `discovery/importers/your_source.py`
2. Extend `BaseImporter` from `discovery/importers/base.py`
3. Implement `get_manual_steps()` and `parse_file()`
4. Add CLI command in `discovery/cli.py`
5. Add tests in `tests/test_importers.py`

### Claude Code Integration

The `/discovery` skill uses `discovery export` output for AI-powered analysis. No external API keys needed.

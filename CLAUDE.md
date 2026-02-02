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
uv run ty check discovery/ tests/
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
  - `cli/` - CLI commands and helpers
    - `core.py` - Root CLI group and core commands
    - `backups.py`, `query.py`, `wishlist.py` - CLI subcommands
    - `display_helpers.py`, `items_helpers.py`, `query_helpers.py`, `status_helpers.py` - CLI helpers
  - `db.py` - DuckDB storage layer (supports context manager, advanced query methods)
  - `backup.py` - Backup manager
  - `config.py` - Shared configuration constants
  - `models.py` - Data models (Category, Source, Item, Rating, WishlistItem, etc.)
  - `patterns.py` - Shared regex patterns
  - `utils.py` - Shared utilities (normalize_title, format_rating, fuzzy matching)
  - `importers/` - Data importers
    - `base.py` - BaseImporter class
    - `spotify.py`, `netflix.py`, `steam.py`, etc.
  - `scrapers/` - HTML/format conversion helpers (e.g. Netflix ratings HTML -> CSV)
- `tests/` - Test suite
  - `conftest.py` - Shared pytest fixtures
  - `test_db.py` - Unit tests for database layer
  - `test_status.py` - Unit tests for status functions
  - `test_importers.py` - Unit tests for importers and utilities
  - `test_cli.py` - Integration tests for CLI
  - `test_deduplication.py` - Tests for deduplication logic
  - `test_backup.py` - Tests for backup functionality
  - `test_utils.py`, `test_wishlist.py`, `test_display_helpers.py` - Utility/helper tests
- `.claude/skills/discovery/SKILL.md` - Claude Code skill for AI analysis

### Adding New Importers

1. Create `discovery/importers/your_source.py`
2. Extend `BaseImporter` from `discovery/importers/base.py`
3. Implement `get_manual_steps()` and `parse_file()`
4. Add CLI command in `discovery/cli/core.py`
5. Add tests in `tests/test_importers.py`

### Claude Code Integration

The `/discovery` skill uses `discovery status`, `discovery query`, and `discovery wishlist view` for AI-powered analysis. No external API keys needed.

### Apple Music AppleScript Limitation

The Apple Music queue script (`.claude/skills/discovery/scripts/queue_apple_music.applescript`) searches `library playlist 1`, so it can only match tracks that are already present in your Music library metadata. It does not directly search the full Apple Music streaming catalog for unknown tracks.

References:
- Apple Support: adding music from Apple Music to your library is an explicit step: https://support.apple.com/en-us/ht204839
- Apple Support: playlists can be separate from adding songs to library (depending on settings): https://support.apple.com/guide/music/create-edit-and-delete-playlists-musd5d051981/mac
- MacScripter discussion of `library playlist` / `search` behavior in Music AppleScript: https://www.macscripter.net/t/music-app-from-text-file/73055

### Recent CLI Additions

- `discovery scrape netflix-html ratings.html` converts Netflix ratings HTML to CSV (or `--import` to import directly).
- `discovery import netflix ratings.html` also accepts HTML ratings pages in addition to CSV viewing history.
- `discovery wishlist add/view/remove/prune` manages wishlist items (auto-pruned after imports and manual adds).

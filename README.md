# Discovery

Discover new things you might love across music, games, books, movies, TV, podcasts, and academic papers.

Discovery imports your library data from various sources, tracks what you love, and uses Claude Code's `/discovery` skill for AI-powered taste analysis and recommendations.

## Installation

### As a tool (recommended)

```bash
uv tool install .
```

This installs `discovery` globally, available from anywhere.

### For development

```bash
uv sync
uv run discovery --help
```

## Quick Start

1. Import your data from one or more sources
2. Mark items as loved (if not tracked by source)
3. Use `/discovery` skill in Claude Code for analysis and recommendations

## CLI Commands

### Status

```bash
discovery status
```

### Import Data

Each importer has setup instructions available via `--help-setup`:

```bash
# Music
discovery import apple-music ~/Music/Library.xml
discovery import spotify ~/Downloads/YourLibrary.json
discovery import qobuz ~/Downloads/qobuz_export.csv

# Games
discovery import steam --api-key YOUR_KEY --steam-id YOUR_ID

# Books
discovery import goodreads goodreads_library_export.csv

# TV/Movies
discovery import netflix ViewingActivity.csv
discovery import amazon-prime ViewingHistory.csv
discovery import disney-plus viewing-history.csv
discovery import apple-tv viewing_activity.csv
discovery import bbc-iplayer watching_history.csv

# Podcasts
discovery import apple-podcasts Podcasts.opml
```

**Incremental Updates**: It's safe to import the same file multiple times. Discovery automatically:
- Detects existing items by source ID and updates them
- Links items across sources using fuzzy title/creator matching
- Creates a backup before each import (restorable via `discovery backup restore`)

This means you can re-export and re-import periodically to keep your library in sync.

### Add Items Manually

Quick way to add individual items without a full import:

```bash
# Add a TV show you watched
discovery add "The Expanse" -c tv -a "Amazon Studios" -l

# Add a movie with rating
discovery add "Dune" -c movie -a "Denis Villeneuve" -l -r 5

# Add a game you played
discovery add "Elden Ring" -c game -a "FromSoftware" -l

# Add a book
discovery add "Project Hail Mary" -c book -a "Andy Weir" -l -r 5

# Add a podcast
discovery add "Hardcore History" -c podcast -a "Dan Carlin"
```

Options: `-c` category (required), `-a` creator, `-l` loved, `-d` dislike, `-r` rating (1-5), `-n` notes, `-f` force (skip duplicate check)

When adding items, Discovery uses fuzzy matching to detect potential duplicates. If a similar item exists, you'll be prompted to select the existing item or add as new.

### Track Favorites

For sources that don't track "loved" status, or to add your own ratings:

```bash
discovery love "Dark Souls III"
discovery love "The Name of the Wind" --rating 5 --notes "Best fantasy series"
discovery dislike "Bad Movie" --notes "Terrible ending"
```

### Update Items

Modify existing items in your library:

```bash
# Fix a typo in the title
discovery update "The Matrx" -t "The Matrix"

# Add or change the creator
discovery update "Elden Ring" -a "FromSoftware"

# Update rating and notes
discovery update "Dark Souls" -r 5 -n "Masterpiece"

# Change loved status
discovery update "Some Movie" -l        # Mark as loved
discovery update "Some Movie" -d        # Mark as disliked
discovery update "Some Movie" -u        # Remove loved/disliked status
```

### View Library

```bash
discovery status            # Full overview with sample loved items
discovery status -f json    # JSON format
discovery loved              # List all loved items
discovery loved -c game      # Filter by category
discovery disliked           # List all disliked items
discovery disliked -c movie  # Filter by category
discovery search "souls"     # Search library
```

### Query Library

For large libraries or detailed exploration, use the `query` command:

```bash
# Get counts
discovery query --count                    # Total items
discovery query -c game --count            # Total games
discovery query -l --count                 # Total loved items

# Query with filters and pagination
discovery query -l -n 50                   # First 50 loved items
discovery query -l --offset 50 -n 50       # Next 50 loved items
discovery query -c game -l -n 100          # First 100 loved games
discovery query -a "FromSoftware" -l       # Loved items by creator
discovery query --min-rating 4             # Items rated 4+
discovery query -c movie -r -n 10          # 10 random movies
discovery query -s "dark souls"            # Search title/creator
discovery query -s "souls" -f json         # Search as JSON
```

### Backups

Discovery automatically creates backups before imports. You can also manage backups manually:

```bash
discovery backup list        # List available backups
discovery backup create      # Create a manual backup
discovery backup restore 1   # Restore from backup #1
```

Backups are stored in `~/.local/state/discovery/backups/` and the 10 most recent are kept.

## Claude Code Integration

The `/discovery` skill provides AI-powered features:

- **Taste Analysis**: Identify patterns in your preferences
- **Recommendations**: Find new items matching your taste via web search
- **New Releases**: Discover upcoming releases you'd enjoy
- **Cross-Category**: Find books based on games you love, etc.

Just type `/discovery` in Claude Code, then ask things like:
- "Analyze my music taste"
- "Find me games similar to what I love"
- "What books should I read next?"
- "Any new releases I'd enjoy?"

## Supported Sources

| Category | Source | Import Method | Loved Tracking |
|----------|--------|--------------|----------------|
| Music | Apple Music | XML export | Native loved |
| Music | Spotify | JSON export | Saved = loved, or play count |
| Music | Qobuz | CSV/JSON | Favorites = loved |
| Games | Steam | API | Playtime > 10hrs |
| Books | Goodreads | CSV export | Rating >= 4 stars |
| Books | Kindle | Coming soon | Manual only |
| TV/Movies | Netflix | CSV export | Manual only |
| TV/Movies | Amazon Prime | CSV export | Manual only |
| TV/Movies | Disney+ | CSV export | Manual only |
| TV/Movies | Apple TV+ | CSV export | Manual only |
| TV/Movies | BBC iPlayer | CSV export | Manual only |
| Podcasts | Apple Podcasts | OPML export | Manual only |

## Data Storage

Library data is stored in `~/.local/state/discovery/discovery.db` (DuckDB).

## Categories

- `music` - Songs, albums, artists
- `game` - Video games
- `book` - Books, ebooks
- `movie` - Films
- `tv` - TV shows, series
- `paper` - Academic papers
- `podcast` - Podcast series

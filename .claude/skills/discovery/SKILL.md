---
name: discovery
description: Analyze your Discovery library and find new recommendations using web search
user_invocable: true
---

# Discovery Analysis Skill

Analyze the user's media library and provide personalized recommendations across music, games, books, movies, TV, podcasts, and academic papers.

## Setup

First, get an overview of the library:

```bash
uv run discovery status              # Full overview with sample loved items
uv run discovery status -f json      # JSON format for programmatic use
```

The status command shows:
- Total items, loved, and disliked counts
- Category breakdown
- Source breakdown
- Random sample of loved items per category
- Wishlist totals and per-category wishlist counts
- Sample wishlist items per category

For detailed exploration, use the query command:

```bash
uv run discovery query --count                    # Total items
uv run discovery query -c game --count            # Total games
uv run discovery query -l --count                 # Total loved items
uv run discovery query -c music -l --count        # Total loved music
uv run discovery query -l -n 50                   # First 50 loved items
uv run discovery query -l -n 50 --offset 50       # Next 50 loved items
uv run discovery query -c game -l -n 100          # First 100 loved games
uv run discovery query -a "FromSoftware"          # Items by creator
uv run discovery query --min-rating 4             # Items rated 4+
uv run discovery query -c movie -r -n 10          # 10 random movies
uv run discovery query -s "dark souls" -f json    # Search as JSON
```

Concurrency note:
- Run `discovery` commands sequentially (one process at a time).
- Do not run multiple `discovery query`/`status`/`sql` commands in parallel.
- The DuckDB file can hold a single writer lock and parallel CLI processes may fail with lock errors.

For custom analysis across joins and aggregates, use SQL:

```bash
uv run discovery sql "SELECT category, COUNT(*) AS n FROM items GROUP BY category ORDER BY n DESC"
uv run discovery sql "SELECT i.title, i.creator, r.rating FROM items i JOIN ratings r ON i.id = r.item_id WHERE r.loved = TRUE ORDER BY r.rating DESC, i.title LIMIT 20"
uv run discovery sql "SELECT * FROM items LIMIT 5" -f json
```

## Wishlist

Wishlist items are future-intent entries (things the user wants to watch/read/play/listen to). They are **per category** and should be treated as **unconsumed**. Use them to:
- Do not remove or exclude wishlisted items from recommendations
- If a recommended item is already on the wishlist, mention that explicitly in the results
- Prefer recommending adjacent or complementary items
- Suggest adding a recommendation to the wishlist when it’s a strong match

Commands:

```bash
uv run discovery wishlist view                 # Show all wishlist items
uv run discovery wishlist view -c game         # Show wishlist items for a category
uv run discovery wishlist add "Title" -c book  # Add to wishlist
uv run discovery wishlist remove "Title"       # Remove from wishlist
uv run discovery wishlist prune                # Remove wishlist items already in library
```

## Query Command Reference

The `query` command is the primary way to explore the library.

**Filters:**
- `-c, --category` - Filter by category (music, game, book, movie, tv, podcast, paper)
- `-l, --loved` - Only loved items
- `-d, --disliked` - Only disliked items
- `-a, --creator` - Filter by creator (partial match)
- `--min-rating` - Minimum rating (1-5)
- `--max-rating` - Maximum rating (1-5)
- `-s, --search` - Search title/creator

**Pagination:**
- `-n, --limit` - Max items to return (default: 20)
- `--offset` - Skip first N items

**Other:**
- `-r, --random` - Random sample instead of sorted
- `--count` - Show only count, not items
- `-f, --format` - Output format (text or json)

**Example workflow for large libraries:**

1. Run `discovery status` for overview and sample loved items
2. Check sizes: `discovery query -l --count`
3. If > 200 loved items, prefer random sampling with a size limit: `discovery query -l -r -n 100`
4. Use category filters to focus: `discovery query -c game -l`
5. When a size limit is required for loved items, use random sampling: `discovery query -c music -l -r -n 20`

## SQL Command Reference

The `sql` command is for ad-hoc, read-only database inspection.

**Usage:**
- `discovery sql "SELECT ..."` - Run a SQL statement
- `-f, --format` - Output format (`text` or `json`)

**Safety constraints:**
- Only read-only statements are allowed.
- Allowed prefixes: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`

**Useful tables:**
- `items`
- `ratings`
- `item_sources`
- `wishlist_items`

**Examples:**
- `discovery sql "SELECT COUNT(*) FROM items"`
- `discovery sql "SELECT category, COUNT(*) FROM items GROUP BY category ORDER BY 2 DESC"`
- `discovery sql "SELECT source, COUNT(*) FROM item_sources GROUP BY source ORDER BY 2 DESC"`
- `discovery sql "SELECT i.category, AVG(r.rating) AS avg_rating FROM items i JOIN ratings r ON i.id = r.item_id WHERE r.rating IS NOT NULL GROUP BY i.category ORDER BY avg_rating DESC"`

## Available Actions

### 1. Taste Analysis

Analyze patterns in the user's loved items:
- Identify common themes, genres, and moods
- Find patterns across different categories (e.g., likes dark themes in both games and movies)
- Compare their taste to known archetypes or critics
- Identify potential blind spots - styles they might enjoy but haven't explored

### 2. Personalized Recommendations

Combine your own knowledge with web search to find recommendations:

**Use your knowledge first:**
- Draw on your understanding of genres, themes, and stylistic elements
- Recall similar works, influences, and connections between creators
- Consider critical consensus and cult favorites in relevant categories
- Think about thematic links (e.g., if they love existential games, suggest existential films)

**Then supplement with web search:**
- Search for "similar to [loved item]" recommendations
- Look for "if you liked X you'll love Y" lists
- Find critically acclaimed items matching their preferred genres
- Search for hidden gems in their favorite categories
- Cross-reference multiple sources for quality

For each recommendation provide:
- Title and creator
- Why it matches their taste (reference specific items they love)
- Where to find/consume it
- **Wishlist prompt** if it’s a very strong fit (ask if they want it added)

### 3. New Releases

Use web search to find recent and upcoming releases:
- Search "[category] releases [current month/year]"
- Search for new work from creators they already love
- Find anticipated releases in their preferred genres
- Check gaming/music/book news sites for relevant announcements

### 4. Similar Items

When the user asks about something specific:
- First, use your knowledge of the item's genre, themes, and style
- Then search for similar items using web search
- Find "fans also like" recommendations
- Look for items by the same creator
- Find items in the same series or universe

### 5. Cross-Category Discovery

Find connections across categories:
- Books that inspired games they love
- Soundtracks from movies they enjoyed
- Games based on books they liked
- Movies adapted from their favorite books
- Podcasts about topics from their favorite media

**Important**: Cross-category recommendations are often the most appreciated. Users may not realize that their love of a game's story could lead them to amazing books, or that their favorite movie has an incredible soundtrack worth exploring. These unexpected connections create delightful "aha!" moments and demonstrate deep understanding of their taste.

## Web Search Strategies

When searching, use queries like:
- "games similar to [title] recommendations"
- "if you liked [book] you'll love"
- "[genre] [category] best of [current year]"
- "[creator] new releases [current year]"
- "[title] fans also like"
- "best [genre] [category] hidden gems"
- "[category] for fans of [title]"

**Note**: Always use the current year in searches for new releases, best-of lists, and recent recommendations. For upcoming releases, include the current month or "upcoming [current year]".

## Output Format

Structure recommendations clearly:

**[Title]** by [Creator]
- *Why you'll love it*: [Connection to their taste]
- *Similar to*: [Items from their library]
- *Where to find*: [Platform/availability]
- *Wishlist?*: “Want me to add this to your wishlist?” (only for standout matches)

## Example Interactions

User: "Analyze my game taste"
1. Run `uv run discovery status` to get overview
2. Run `uv run discovery query -c game -l -n 100` (paginate if needed)
3. Identify patterns (genres, themes, mechanics, studios)
4. Provide detailed taste profile

User: "Find me new music"
1. Run `uv run discovery query -c music -l -n 50` for loved music
2. Identify artists, genres, moods
3. Run `uv run discovery wishlist view -c music` to note any overlaps and refine taste
3. Web search for similar artists and new releases
4. Provide personalized recommendations with explanations
5. If a rec is a standout match, ask if the user wants it added to the wishlist

User: "What books should I read based on the games I love?"
1. Run `uv run discovery query -c game -l -n 50` for game context
2. Analyze game themes and narratives
3. Web search for books with similar themes
4. Recommend books that match game preferences

User: "Any new releases I'd like?"
1. Run `uv run discovery status` to understand library
2. Run `uv run discovery query -l -r -n 30` for random sample of loved items
3. Identify preferred categories and genres
4. Run `uv run discovery wishlist view` to avoid recommending items already on the wishlist
4. Web search for recent releases matching taste
5. Filter and present relevant new releases
6. Ask to add standout picks to the wishlist

## Apple Music Playlist Workflow

Use this workflow when the user asks to queue recommendations in Apple Music.

**Trigger keyword**: `queue-playlist`

Important: matching is library-scoped (`library playlist 1`), so this script only matches tracks already present in the user's Music library metadata.

Also trigger this workflow when the user asks for playlist creation/queueing with phrases like:
- "queue this in Apple Music"
- "make me a playlist"
- "use osascript to add tracks"

### Steps

1. Produce a CSV with header `artist,track`.
2. Save it (for example `/tmp/playlist.csv`).
3. Run the script:

```bash
osascript .claude/skills/discovery/scripts/queue_apple_music.applescript --csv /tmp/playlist.csv --playlist "Codex Queue"
```

### Matching Modes

- Default (strict): safer matches, fewer substitutions.
- Loose mode: higher recall, may substitute close tracks.

```bash
osascript .claude/skills/discovery/scripts/queue_apple_music.applescript --csv /tmp/playlist.csv --playlist "Codex Queue" --loose
```

Optional flags:
- `--no-play` (build playlist without starting playback)
- `--min-score N` (override match threshold)
- `--strict` (explicit strict mode)

After running, report:
- Added track count
- Missing track count and list
- Notable substitutions (if any)

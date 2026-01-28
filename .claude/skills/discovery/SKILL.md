---
name: discovery
description: Analyze your Discovery library and find new recommendations using web search
user_invocable: true
---

# Discovery Analysis Skill

Analyze the user's media library and provide personalized recommendations across music, games, books, movies, TV, podcasts, and academic papers.

## Setup

First, get the current library state:

```bash
uv run discovery export                 # Export all categories
uv run discovery export -c game         # Export only games
uv run discovery export -c music        # Export only music
uv run discovery export -c book         # Export only books
uv run discovery export -c movie        # Export only movies
uv run discovery export -c tv           # Export only TV shows
uv run discovery export -c podcast      # Export only podcasts
uv run discovery export -c paper        # Export only academic papers
```

This outputs the library in a readable format. Read this output to understand what the user has consumed and loved.

Use the category filter (`-c`) when:
- The user asks about a specific category (e.g., "analyze my game taste")
- The full library is too large for efficient analysis
- You want to focus recommendations on one area

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

## Example Interactions

User: "Analyze my game taste"
1. Run `uv run discovery export -c game` to get game library
2. Read the output focusing on loved games
3. Identify patterns (genres, themes, mechanics, studios)
4. Provide detailed taste profile

User: "Find me new music"
1. Run `uv run discovery export -c music` to get music library
2. Identify loved music artists, genres, moods
3. Web search for similar artists and new releases
4. Provide personalized recommendations with explanations

User: "What books should I read based on the games I love?"
1. Run `uv run discovery export -c game` for game context
2. Analyze game themes and narratives
3. Web search for books with similar themes
4. Recommend books that match game preferences

User: "Any new releases I'd like?"
1. Run `uv run discovery export` to get full library
2. Identify preferred categories and genres
3. Web search for recent releases matching taste
4. Filter and present relevant new releases

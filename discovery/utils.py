"""Shared utilities for Discovery."""

import re

from rapidfuzz import fuzz

from .models import Category

# Display limits
DEFAULT_DISPLAY_LIMIT = 10


def normalize_title(title: str, strip_editions: bool = True) -> str:
    """Normalize a title for comparison.

    Args:
        title: The title to normalize
        strip_editions: Whether to remove edition/version markers

    Returns:
        Normalized title string
    """
    if not title:
        return ""

    # Lowercase
    normalized = title.lower()

    # Remove common prefixes
    for prefix in ("the ", "a ", "an "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]

    # Remove edition/version indicators BEFORE punctuation removal
    if strip_editions:
        patterns = [
            r"\s*\(.*?(edition|remaster|deluxe|version|expanded).*?\)\s*$",
            r"\s*-\s*.*?(edition|remaster|deluxe|version|expanded).*$",
            r"\s*:\s*.*?(edition|remaster|deluxe|version|expanded).*$",
            r"\s+\(remastered\)\s*$",
            r"\s+\(deluxe\)\s*$",
        ]
        for pattern in patterns:
            normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)

    # Remove punctuation and extra whitespace
    normalized = re.sub(r"[^\w\s]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized.strip()


def strip_sequel_numbers(title: str) -> str:
    """Remove trailing sequel numbers/roman numerals."""
    stripped = re.sub(r"\s+[ivxlcdm]+$", "", title, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+\d+$", "", stripped)
    return stripped.strip()


def titles_match(title1: str | None, title2: str | None, threshold: int = 85) -> bool:
    """Check if two titles match using fuzzy comparison.

    Uses a combination of:
    - Exact normalized match (fast path)
    - Pattern-based matching for common TV/movie/game patterns
    - Fuzzy matching via rapidfuzz for everything else

    Args:
        title1: First title
        title2: Second title
        threshold: Minimum fuzzy match score (0-100) for non-exact matches

    Returns:
        True if titles are considered a match
    """
    if not title1 or not title2:
        return False

    norm1 = normalize_title(title1)
    norm2 = normalize_title(title2)

    # Exact normalized match (fast path)
    if norm1 == norm2:
        return True

    # Pattern-based matching for common cases:

    # 1. Subtitle handling: "Dark Souls" matches "Dark Souls III"
    #    One is substring of other (for titles with subtitles/sequels)
    if norm1 in norm2 or norm2 in norm1:
        shorter = min(len(norm1), len(norm2))
        if shorter >= 5:
            return True

    # 2. Numbered sequels: "Mass Effect 2" vs "Mass Effect II"
    #    Remove numbers and roman numerals for comparison
    stripped1 = strip_sequel_numbers(norm1)
    stripped2 = strip_sequel_numbers(norm2)
    if stripped1 and stripped2 and stripped1 == stripped2:
        return True

    # 3. Fuzzy matching with rapidfuzz for typos and variations
    #    token_set_ratio handles word order and extra words well
    score = fuzz.token_set_ratio(norm1, norm2)
    if score >= threshold:
        return True

    return False


def titles_match_strict(title1: str | None, title2: str | None, threshold: int = 92) -> bool:
    """Stricter title match for deduplication."""
    if not title1 or not title2:
        return False

    norm1 = normalize_title(title1)
    norm2 = normalize_title(title2)

    if norm1 == norm2:
        return True

    if (norm1 in norm2 or norm2 in norm1) and min(len(norm1), len(norm2)) >= 5:
        return True

    stripped1 = strip_sequel_numbers(norm1)
    stripped2 = strip_sequel_numbers(norm2)
    if stripped1 and stripped2 and stripped1 == stripped2:
        return True

    return fuzz.token_set_ratio(norm1, norm2) >= threshold


def creators_match(creator1: str | None, creator2: str | None, threshold: int = 80) -> bool:
    """Check if two creators match using fuzzy comparison.

    Uses a combination of:
    - Exact match
    - Substring matching (handles "John Smith" vs "Smith, John")
    - Last name matching
    - Fuzzy matching via rapidfuzz for typos

    Args:
        creator1: First creator
        creator2: Second creator
        threshold: Minimum fuzzy match score (0-100) for non-exact matches

    Returns:
        True if creators are considered a match (missing creator = match)
    """
    # If either is missing, consider it a match (be aggressive)
    if not creator1 or not creator2:
        return True

    c1 = creator1.lower().strip()
    c2 = creator2.lower().strip()

    # Exact match
    if c1 == c2:
        return True

    # One contains the other (handles "John Smith" vs "Smith, John")
    if c1 in c2 or c2 in c1:
        return True

    # Check last name match for "Firstname Lastname" patterns
    parts1 = c1.split()
    parts2 = c2.split()
    if parts1 and parts2:
        if parts1[-1] == parts2[-1]:  # Same last name
            return True

    # Fuzzy matching for typos and variations
    score = fuzz.ratio(c1, c2)
    if score >= threshold:
        return True

    return False


def format_rating(rating: int) -> str:
    """Format a 1-5 rating as stars.

    Args:
        rating: Rating value (1-5)

    Returns:
        Star string like "[****.]"
    """
    return "[" + "*" * rating + "." * (5 - rating) + "]"


def group_by_category(items: list) -> dict[str, list]:
    """Group items by their category value.

    Args:
        items: List of items with category attribute

    Returns:
        Dict mapping category value to list of items
    """
    from collections import defaultdict

    by_category: dict[str, list] = defaultdict(list)
    for item in items:
        by_category[item.category.value].append(item)
    return dict(by_category)


def detect_video_category(title: str, content_type: str | None = None) -> Category:
    """Detect if a video title is TV or Movie based on title patterns."""
    normalized_type = (content_type or "").strip().lower()
    if normalized_type in {"tv", "series", "episode", "show"}:
        return Category.TV
    if normalized_type in {"film", "movie"}:
        return Category.MOVIE

    title_lower = title.lower()
    if any(
        marker in title_lower
        for marker in (
            ": season",
            " - season",
            ": episode",
            " - episode",
            " episode",
            " chapter",
            " - s",
            " s0",
            " s1",
            " s2",
            " s3",
            " s4",
            " s5",
        )
    ):
        return Category.TV

    return Category.MOVIE

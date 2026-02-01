"""Unit tests for utility helpers."""

from datetime import datetime

from discovery.models import Category
from discovery.utils import detect_video_category, parse_date, strip_sequel_numbers, titles_match, titles_match_strict


class TestDetectVideoCategory:
    def test_detects_from_content_type(self) -> None:
        assert detect_video_category("Some Title", "tv") == Category.TV
        assert detect_video_category("Some Title", "movie") == Category.MOVIE

    def test_detects_from_title_markers(self) -> None:
        assert detect_video_category("Show: Season 1: Pilot") == Category.TV
        assert detect_video_category("Show - S01E02") == Category.TV
        assert detect_video_category("Show: Episode 3") == Category.TV

    def test_defaults_to_movie(self) -> None:
        assert detect_video_category("Some Movie") == Category.MOVIE


class TestParseDate:
    def test_parses_common_formats(self) -> None:
        parsed = parse_date("2024-01-02")
        assert parsed == datetime(2024, 1, 2)

        parsed = parse_date("13/02/24")
        assert parsed == datetime(2024, 2, 13)

    def test_returns_none_for_invalid(self) -> None:
        assert parse_date("not a date") is None
        assert parse_date("") is None


class TestStripSequelNumbers:
    def test_strips_numbers_and_romans(self) -> None:
        assert strip_sequel_numbers("Mass Effect 2") == "Mass Effect"
        assert strip_sequel_numbers("Mass Effect II") == "Mass Effect"

    def test_keeps_title_without_numbers(self) -> None:
        assert strip_sequel_numbers("Mass Effect") == "Mass Effect"


class TestTitlesMatchStrict:
    def test_strict_match(self) -> None:
        assert titles_match_strict("Dark Souls III", "Dark Souls") is True
        assert titles_match_strict("The Witcher", "The Witcher: Wild Hunt") is True

    def test_strict_reject(self) -> None:
        assert titles_match_strict("Dark Souls", "Light Hearts") is False
        assert titles_match("The Witcher", "The Witchar") is True
        assert titles_match_strict("The Witcher", "The Witchar") is False

"""Unit tests for CLI display helpers."""

import click
import pytest

from discovery.cli.display_helpers import select_from_results


class TestSelectFromResults:
    def test_selects_single_item(self) -> None:
        assert select_from_results([1], "query", "No {query}", str) == 1

    def test_selects_multiple_items(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(click, "prompt", lambda *args, **kwargs: 2)
        result = select_from_results([1, 2, 3], "query", "No {query}", str)
        assert result == 2

    def test_invalid_choice_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(click, "prompt", lambda *args, **kwargs: 10)
        result = select_from_results([1, 2, 3], "query", "No {query}", str)
        assert result is None

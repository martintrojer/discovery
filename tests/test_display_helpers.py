"""Unit tests for CLI display helpers."""

from unittest.mock import Mock

import click
import pytest

from discovery.cli.display_helpers import select_from_results


class TestSelectFromResults:
    def test_selects_single_item(self) -> None:
        assert select_from_results([1], "query", "No {query}", str) == 1

    def test_empty_results(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert select_from_results([], "query", "No {query}", str) is None
        output = capsys.readouterr().out
        assert "No query" in output

    def test_selects_multiple_items(self, monkeypatch: pytest.MonkeyPatch) -> None:
        prompt = Mock(return_value=2)
        monkeypatch.setattr(click, "prompt", prompt)
        result = select_from_results([1, 2, 3], "query", "No {query}", str)
        assert result == 2
        prompt.assert_called_once_with("Select item number", type=int, default=1)

    def test_invalid_choice_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(click, "prompt", lambda *args, **kwargs: 10)
        result = select_from_results([1, 2, 3], "query", "No {query}", str)
        assert result is None
        output = capsys.readouterr().out
        assert "Invalid choice" in output

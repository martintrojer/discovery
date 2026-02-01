"""Unit tests for CLI display helpers."""

import click
import pytest
from click.testing import CliRunner

from discovery.cli.display_helpers import select_from_results


class TestSelectFromResults:
    def test_selects_single_item(self) -> None:
        assert select_from_results([1], "query", "No {query}", str) == 1

    def test_empty_results(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert select_from_results([], "query", "No {query}", str) is None
        output = capsys.readouterr().out
        assert "No query" in output

    def test_selects_multiple_items(self) -> None:
        @click.command()
        def cmd() -> None:
            result = select_from_results([1, 2, 3], "query", "No {query}", str)
            click.echo(f"Selected: {result}")

        runner = CliRunner()
        result = runner.invoke(cmd, input="2\n")
        assert result.exit_code == 0
        assert "Selected: 2" in result.output

    def test_invalid_choice_returns_none(self) -> None:
        @click.command()
        def cmd() -> None:
            result = select_from_results([1, 2, 3], "query", "No {query}", str)
            click.echo(f"Selected: {result}")

        runner = CliRunner()
        result = runner.invoke(cmd, input="10\n")
        assert result.exit_code == 0
        assert "Invalid choice" in result.output
        assert "Selected: None" in result.output

"""SQL CLI command for ad-hoc database inspection."""

import json as json_module
import re

import click

from ..db import Database
from .core import cli

_READ_ONLY_PREFIXES = ("select", "with", "show", "describe", "explain")


def _is_read_only_sql(statement: str) -> bool:
    """Return True when a SQL statement starts with a read-only keyword."""
    normalized = statement.lstrip()
    if not normalized:
        return False
    first_keyword_match = re.match(r"([a-zA-Z_]+)", normalized)
    if not first_keyword_match:
        return False
    first_keyword = first_keyword_match.group(1).lower()
    return first_keyword in _READ_ONLY_PREFIXES


def _format_value(value: object) -> str:
    """Format a single SQL result cell as display text."""
    if value is None:
        return "NULL"
    return str(value)


@cli.command(name="sql")
@click.argument("statement")
@click.option("--format", "-f", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.pass_context
def sql_query(ctx: click.Context, statement: str, format: str) -> None:
    """Run a read-only SQL query against the Discovery database."""
    if not _is_read_only_sql(statement):
        raise click.ClickException("Only read-only SQL is allowed (SELECT/WITH/SHOW/DESCRIBE/EXPLAIN).")

    db: Database = ctx.obj["db"]
    result = db.conn.execute(statement)
    rows = result.fetchall()
    columns = [col[0] for col in result.description]

    if format == "json":
        click.echo(
            json_module.dumps(
                {
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                },
                indent=2,
                default=str,
            )
        )
        return

    click.echo(" | ".join(columns))
    click.echo("-+-".join("-" * len(col) for col in columns))
    for row in rows:
        click.echo(" | ".join(_format_value(value) for value in row))
    click.echo(f"\nRows: {len(rows)}")

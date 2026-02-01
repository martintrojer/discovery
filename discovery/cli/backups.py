"""Backup CLI commands."""

from pathlib import Path

import click

from ..db import Database
from .core import cli


@cli.group()
def backup() -> None:
    """Manage database backups."""
    pass


@backup.command(name="create")
@click.option("--reason", "-r", default="manual", help="Reason for backup")
@click.pass_context
def backup_create(ctx: click.Context, reason: str) -> None:
    """Create a backup of the database."""
    db: Database = ctx.obj["db"]

    backup_path = db.create_backup(reason)
    if backup_path:
        click.echo(f"Backup created: {backup_path}")
    else:
        click.echo("No database to backup yet.")


@backup.command(name="list")
@click.pass_context
def backup_list(ctx: click.Context) -> None:
    """List available backups."""
    db: Database = ctx.obj["db"]

    backups = db.list_backups()
    if not backups:
        click.echo("No backups found.")
        return

    click.echo(f"\n{len(backups)} backup(s) available:\n")
    for i, b in enumerate(backups, 1):
        timestamp = b["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        click.echo(f"  {i}. {timestamp} ({b['reason']}) - {b['size_kb']} KB")
        click.echo(f"     {b['path']}")
    click.echo()


@backup.command(name="restore")
@click.argument("backup_id", type=int, required=False)
@click.option("--path", "-p", type=click.Path(exists=True, path_type=Path), help="Restore from specific path")
@click.pass_context
def backup_restore(ctx: click.Context, backup_id: int | None, path: Path | None) -> None:
    """Restore database from a backup.

    BACKUP_ID is the number from 'discovery backup list'.
    """
    db: Database = ctx.obj["db"]

    if path:
        backup_path = path
    elif backup_id:
        backups = db.list_backups()
        if backup_id < 1 or backup_id > len(backups):
            click.echo("Invalid backup ID. Use 'discovery backup list' to see available backups.")
            return
        backup_path = backups[backup_id - 1]["path"]
    else:
        click.echo("Specify a backup ID or --path. Use 'discovery backup list' to see available backups.")
        return

    if click.confirm(f"Restore from {backup_path}? This will replace your current database."):
        if db.restore_backup(backup_path):
            click.echo("Database restored successfully.")
        else:
            click.echo("Failed to restore backup.")

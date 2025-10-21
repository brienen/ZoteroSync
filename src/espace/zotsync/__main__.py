"""Command-line interface."""

import typer
from pathlib import Path

from .zot_export import make_asreview_csv_from_db
from .zot_import import apply_asreview_decisions
from .zot_import import remove_review_tags

import espace.zotsync.const as const

# Load environment variables from a .env file if present
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None  # type: ignore
if load_dotenv:
    # Do not override already-set environment variables
    load_dotenv(override=False)
    typer.echo("Loaded environment variables from .env file", err=True)


def _version_callback(value: bool):
    if value:
        typer.echo("zotsync, version 0.0.1")
        raise typer.Exit()


app = typer.Typer(help="Zotero ↔ ASReview CLI")


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show the version and exit.",
        is_eager=True,
        callback=_version_callback,
    )
):
    pass


@app.command(name="export", help="Exporteer Zotero bibliotheek naar ASReview CSV")
def zot_export_hyphen(
    out_csv: str = typer.Argument(..., help="Output CSV file"),
    library_id: str = typer.Option(
        ..., help="Zotero library ID", envvar="ZOTSYNC_LIBRARY_ID"
    ),
    library_type: str = typer.Option(
        "groups",
        help="Zotero library type (users or groups)",
        envvar="ZOTSYNC_LIBRARY_TYPE",
    ),
    deduplicate: bool = typer.Option(
        False,
        "--dedupe",
        help="(De)activeer deduplicatie (default: uit)",
        envvar="ZOTSYNC_DEDUPLICATE",
    ),
    db_path: str = typer.Option(
        const.DEFAULT_SQLITE_PATH,
        help="Pad naar SQLite database",
        envvar="ZOTSYNC_DB_PATH",
    ),
):
    make_asreview_csv_from_db(
        out_csv=Path(out_csv),
        library_id=library_id,
        library_type=library_type,
        deduplicate=deduplicate,
        db_path=Path(db_path),
    )
    typer.echo(f"ASReview CSV written to: {out_csv}")


@app.command(
    name="import",
    help=f"Importeer ASReview beslissingen terug naar Zotero als review-tags ({const.REVIEW_DECISION_PREFIX}, {const.REVIEW_TIME_PREFIX}, {const.REVIEW_REASON_PREFIX})",
)
def zot_import_hyphen(
    asr_csv: str = typer.Argument(..., help="ASReview CSV met 'included' kolom"),
    api_key: str = typer.Option(
        None,
        help="Zotero API key. Alleen noodzakelijk als Zotero niet lokaal draait.",
        envvar="ZOTSYNC_API_KEY",
    ),
    library_id: str = typer.Option(
        ..., help="Zotero UserID of GroupID", envvar="ZOTSYNC_LIBRARY_ID"
    ),
    library_type: str = typer.Option(
        "groups",
        help="Zotero library type (users of groups)",
        envvar="ZOTSYNC_LIBRARY_TYPE",
    ),
    fuzzy_threshold: float = typer.Option(
        0.90,
        help="Drempel voor fuzzy titelmatch (0-1)",
        envvar="ZOTSYNC_FUZZY_THRESHOLD",
    ),
    db_path: str = typer.Option(
        const.DEFAULT_SQLITE_PATH,
        help="Pad naar SQLite database",
        envvar="ZOTSYNC_DB_PATH",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Niet wegschrijven; alleen tellen.",
        is_flag=True,
    ),
):
    res = apply_asreview_decisions(
        asr_csv=Path(asr_csv),
        api_key=api_key,
        library_id=library_id,
        library_type=library_type,
        fuzzy_threshold=fuzzy_threshold,
        db_path=Path(db_path),
        dry_run=dry_run,
    )
    typer.secho(
        f"[DONE] updated={res['updated']} not_found={res['not_found']} errors={res['errors']}",
        fg=typer.colors.GREEN,
    )


@app.command(
    name="clean",
    help=f"Verwijder alle review-tags ({const.REVIEW_DECISION_PREFIX}, {const.REVIEW_TIME_PREFIX}, {const.REVIEW_REASON_PREFIX}) uit Zotero voor de opgegeven bibliotheek. Geen andere tags worden verwijderd",
)
def zot_clean_hyphen(
    api_key: str = typer.Option(
        None,
        help="Zotero API key. Alleen noodzakelijk als Zotero niet lokaal draait.",
        envvar="ZOTSYNC_API_KEY",
    ),
    library_id: str = typer.Option(
        ..., help="Zotero UserID of GroupID", envvar="ZOTSYNC_LIBRARY_ID"
    ),
    library_type: str = typer.Option(
        "groups",
        help="Zotero library type (users or groups)",
        envvar="ZOTSYNC_LIBRARY_TYPE",
    ),
    fuzzy_threshold: float = typer.Option(
        0.90,
        help="Drempel voor fuzzy titelmatch (0-1)",
        envvar="ZOTSYNC_FUZZY_THRESHOLD",
    ),
    db_path: str = typer.Option(
        const.DEFAULT_SQLITE_PATH,
        help="Pad naar SQLite database",
        envvar="ZOTSYNC_DB_PATH",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Niet wegschrijven; alleen tellen.",
        is_flag=True,
    ),
):
    res = remove_review_tags(
        api_key=api_key,
        library_id=library_id,
        library_type=library_type,
        fuzzy_threshold=fuzzy_threshold,
        dry_run=dry_run,
        db_path=Path(db_path),
    )
    typer.secho(
        f"[CLEANED] removed={res['removed']} errors={res['errors']}",
        fg=typer.colors.GREEN,
    )


if __name__ == "__main__":
    app()  # pragma: no cover

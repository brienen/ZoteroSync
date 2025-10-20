"""Command-line interface."""

import typer
import click

from .zot_export import make_asreview_csv
from .zot_import import apply_asreview_decisions
from .zot_import import remove_review_tags

import espace.zotsync.const as const

app = typer.Typer(help="Zotero ↔ ASReview CLI")


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show the version and exit.",
        is_eager=True,
        callback=lambda value: (
            typer.echo("zotsync, version 0.0.1") if value else None
        ),
    )
):
    ctx = click.get_current_context(silent=True)
    if ctx and ctx.params.get("version"):
        raise typer.Exit()
    if not (ctx and ctx.invoked_subcommand):
        typer.echo(app.get_help())
        raise typer.Exit()


def _cmd_zot_export(
    zotero_csv: str,
    out: str,
    api_key: str = typer.Option(..., help="Zotero API key"),
    library_id: str = typer.Option(..., help="Zotero library ID"),
    library_type: str = typer.Option(
        "user", help="Zotero library type (user or group)"
    ),
    add_pdf_links: bool = typer.Option(True, help="Add PDF links to output"),
    dedupe: bool = False,
    include_review_tags: bool = True,
    zotero_host: str = "http://localhost:23119",
):
    """Shared implementation for zot_export commands."""
    make_asreview_csv(
        zotero_csv=zotero_csv,
        out_csv=out,
        api_key=api_key,
        library_id=library_id,
        library_type=library_type,
        add_pdf_links=add_pdf_links,
        deduplicate=dedupe,
        include_review_tags=include_review_tags,
        zotero_host=zotero_host,
    )
    typer.echo(f"ASReview CSV written to: {out}")


@app.command(name="export", help="Exporteer Zotero bibliotheek naar ASReview CSV")
def zot_export_hyphen(
    zotero_csv: str = typer.Argument(..., help="Input Zotero CSV file"),
    out: str = typer.Argument(..., help="Output CSV file"),
    api_key: str = typer.Option(..., help="Zotero API key"),
    library_id: str = typer.Option(..., help="Zotero library ID"),
    library_type: str = typer.Option(
        "users", help="Zotero library type (users or groups)"
    ),
    add_pdf_links: bool = typer.Option(False, help="Add PDF links to output"),
    dedupe: bool = typer.Option(
        False, "--dedupe/--no-dedupe", help="(De)activeer deduplicatie (default: uit)"
    ),
    include_review_tags: bool = typer.Option(
        False,
        "--include-review-tags/--no-include-review-tags",
        help="Lees bestaande review:* tags uit Zotero en voeg kolommen toe",
    ),
    zotero_host: str = typer.Option(
        "http://localhost:23119",
        help="Base URL van de Zotero instantie (default: http://localhost:23119)",
    ),
):
    _cmd_zot_export(
        zotero_csv=zotero_csv,
        out=out,
        api_key=api_key,
        library_id=library_id,
        library_type=library_type,
        add_pdf_links=add_pdf_links,
        dedupe=dedupe,
        include_review_tags=include_review_tags,
        zotero_host=zotero_host,
    )


def _cmd_zot_import(
    asr_csv: str,
    api_key: str,
    library_id: str,
    library_type: str,
    tag_prefix: str,
    fuzzy_threshold: float,
    review_name: str | None,
    review_round: str | None,
    reviewer: str | None,
    review_date: str | None,
    dry_run: bool,
):
    res = apply_asreview_decisions(
        asr_csv=asr_csv,
        api_key=api_key,
        library_id=library_id,
        library_type=library_type,
        tag_prefix=tag_prefix,
        fuzzy_threshold=fuzzy_threshold,
        review_name=review_name,
        review_round=review_round,
        reviewer=reviewer,
        review_date=review_date,
        dry_run=dry_run,
    )
    typer.secho(
        f"[DONE] updated={res['updated']} not_found={res['not_found']} errors={res['errors']}",
        fg=typer.colors.GREEN,
    )


@app.command(
    name="import", help="Importeer ASReview beslissingen terug naar Zotero als tags"
)
def zot_import_hyphen(
    asr_csv: str = typer.Argument(..., help="ASReview CSV met 'included' kolom"),
    api_key: str = typer.Option(..., help="Zotero API key"),
    library_id: str = typer.Option(..., help="Zotero UserID of GroupID"),
    library_type: str = typer.Option(
        "users", help="Zotero library type (users or groups)"
    ),
    tag_prefix: str = typer.Option("ASReview", help="Prefix voor beslissings-tags"),
    fuzzy_threshold: float = typer.Option(
        0.90, help="Drempel voor fuzzy titelmatch (0-1)"
    ),
    review_name: str = typer.Option(
        None, help="Naam van de review (tag: review:Name=…)"
    ),
    review_round: str = typer.Option(
        None, help="Review-ronde / wave (tag: review:Round=…)"
    ),
    reviewer: str = typer.Option(
        None, help="Naam/ID reviewer (tag: review:Reviewer=…)"
    ),
    review_date: str = typer.Option(
        None, help="Datum (YYYY-MM-DD) of vrije tekst (tag: review:Date=…)"
    ),
    dry_run: bool = typer.Option(False, help="Niet wegschrijven; alleen tellen"),
):
    _cmd_zot_import(
        asr_csv,
        api_key,
        library_id,
        library_type,
        tag_prefix,
        fuzzy_threshold,
        review_name,
        review_round,
        reviewer,
        review_date,
        dry_run,
    )


def _cmd_zot_clean(
    api_key: str,
    library_id: str,
    library_type: str,
    tag_prefix: str,
    fuzzy_threshold: float,
    dry_run: bool,
    db_path: str,
):
    res = remove_review_tags(
        api_key=api_key,
        library_id=library_id,
        library_type=library_type,
        tag_prefix=tag_prefix,
        fuzzy_threshold=fuzzy_threshold,
        dry_run=dry_run,
        db_path=db_path,
    )
    typer.secho(
        f"[CLEANED] removed={res['removed']} errors={res['errors']}",
        fg=typer.colors.GREEN,
    )


@app.command(
    name="clean",
    help=f"Verwijder alle review-tags ({const.REVIEW_DECISION_PREFIX}, {const.REVIEW_TIME_PREFIX}, {const.REVIEW_REASON_PREFIX}) uit Zotero voor de opgegeven bibliotheek. Geen andere tags worden verwijderd",
)
def zot_clean_hyphen(
    api_key: str = typer.Option(
        None, help="Zotero API key. Alleen noodzakelijk als Zotero niet lokaal draait."
    ),
    library_id: str = typer.Option(..., help="Zotero UserID of GroupID"),
    library_type: str = typer.Option(
        "groups", help="Zotero library type (users or groups)"
    ),
    tag_prefix: str = typer.Option("ASReview", help="Prefix voor beslissings-tags"),
    fuzzy_threshold: float = typer.Option(
        0.90, help="Drempel voor fuzzy titelmatch (0-1)"
    ),
    db_path: str = typer.Option(
        const.DEFAULT_SQLITE_PATH, help="Pad naar SQLite database"
    ),
    dry_run: bool = typer.Option(False, help="Niet wegschrijven; alleen tellen"),
):
    _cmd_zot_clean(
        api_key,
        library_id,
        library_type,
        tag_prefix,
        fuzzy_threshold,
        db_path,
        dry_run,
    )


if __name__ == "__main__":
    app()  # pragma: no cover

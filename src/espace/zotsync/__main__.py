"""Command-line interface."""
import typer

from .to_asreview import make_asreview_csv

app = typer.Typer(help="Zotero ↔ ASReview CLI")

@app.callback()
def main(version: bool = typer.Option(
    None,
    "--version",
    "-v",
    help="Show the version and exit.",
    is_eager=True,
    callback=lambda value: (typer.echo("zotsync, version 0.0.1") if value else None),
)):
    pass

def _cmd_to_asreview(
    zotero_csv: str,
    out: str,
    api_key: str = typer.Option(..., help="Zotero API key"),
    library_id: str = typer.Option(..., help="Zotero library ID"),
    library_type: str = typer.Option("user", help="Zotero library type (user or group)"),
    add_pdf_links: bool = typer.Option(False, help="Add PDF links to output"),
    dedupe: bool = True
):
    """Shared implementation for to_asreview commands."""
    make_asreview_csv(
        zotero_csv=zotero_csv,
        out_csv=out,
        api_key=api_key,
        library_id=library_id,
        library_type=library_type,
        add_pdf_links=add_pdf_links,
        deduplicate=dedupe
    )
    typer.echo(f"ASReview CSV written to: {out}")

@app.command(name="to-asreview")
def to_asreview_hyphen(
    zotero_csv: str = typer.Argument(..., help="Input Zotero CSV file"),
    out: str = typer.Argument(..., help="Output ASReview CSV file"),
    api_key: str = typer.Option(..., help="Zotero API key"),
    library_id: str = typer.Option(..., help="Zotero library ID"),
    library_type: str = typer.Option("users", help="Zotero library type (users or groups)"),
    add_pdf_links: bool = typer.Option(False, help="Add PDF links to output"),
    dedupe: bool = typer.Option(False, "--dedupe/--no-dedupe", help="(De)activeer deduplicatie (default: uit)")
):
    _cmd_to_asreview(
        zotero_csv=zotero_csv,
        out=out,
        api_key=api_key,
        library_id=library_id,
        library_type=library_type,
        add_pdf_links=add_pdf_links,
        dedupe=dedupe
    )

@app.command(name="to_asreview")
def to_asreview_underscore(
    zotero_csv: str = typer.Argument(..., help="Input Zotero CSV file"),
    out: str = typer.Argument(..., help="Output ASReview CSV file"),
    api_key: str = typer.Option(..., help="Zotero API key"),
    library_id: str = typer.Option(..., help="Zotero library ID"),
    library_type: str = typer.Option("users", help="Zotero library type (users or groups)"),
    add_pdf_links: bool = typer.Option(False, help="Add PDF links to output"),
    dedupe: bool = typer.Option(False, "--dedupe/--no-dedupe", help="(De)activeer deduplicatie (default: uit)")
):
    _cmd_to_asreview(
        zotero_csv=zotero_csv,
        out=out,
        api_key=api_key,
        library_id=library_id,
        library_type=library_type,
        add_pdf_links=add_pdf_links,
        dedupe=dedupe
    )

def _cmd_from_asreview():
    """Shared implementation for from_asreview commands."""
    typer.echo("from_asreview command called")

@app.command(name="from-asreview")
def from_asreview_hyphen():
    _cmd_from_asreview()

@app.command(name="from_asreview")
def from_asreview_underscore():
    _cmd_from_asreview()


if __name__ == "__main__":
    app()  # pragma: no cover

"""Command-line interface."""
import typer

app = typer.Typer(help="Zotero ↔ ASReview CLI")

@app.callback()
def main(version: bool = typer.Option(
    None,
    "--version",
    "-v",
    help="Show the version and exit.",
    is_eager=True,
    callback=lambda value: (typer.echo("ZoteroSync, version 0.0.0") if value else None),
)):
    pass

def _cmd_to_asreview():
    """Shared implementation for to_asreview commands."""
    typer.echo("to_asreview command called")

@app.command(name="to-asreview")
def to_asreview_hyphen():
    _cmd_to_asreview()

@app.command(name="to_asreview")
def to_asreview_underscore():
    _cmd_to_asreview()

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

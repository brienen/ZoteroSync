"""CLI smoke test for Typer app."""

from typer.testing import CliRunner
from espace.zotsync.__main__ import app


def test_cli_help_succeeds() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Zotero ↔ ASReview CLI" in result.output

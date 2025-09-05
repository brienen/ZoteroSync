"""Command-line interface."""
import click


@click.command()
@click.version_option()
def main() -> None:
    """Zoterosync."""


if __name__ == "__main__":
    main(prog_name="ZoteroSync")  # pragma: no cover

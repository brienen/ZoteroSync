import pandas as pd
from pathlib import Path
import pytest
import espace.zotsync.const as const
import os

import subprocess
import sys

from espace.zotsync.zot_export import make_asreview_csv, make_asreview_csv_from_db


@pytest.mark.parametrize("filename", ["sample_zotero.csv", "real_zotero.csv"])
def test_make_asreview_csv(tmp_path: Path, filename):
    # Arrange: pad naar input uit tests/data
    input_file = Path(__file__).parent / "data" / filename
    output_file = tmp_path / "out.csv"

    # Act
    make_asreview_csv(
        zotero_csv=input_file,
        out_csv=output_file,
        library_id=os.getenv("ZOTERO_LIBRARY_ID"),
        deduplicate=False,
    )
    print(f"Output file saved at: {output_file}")

    # Assert
    assert output_file.exists()
    df = pd.read_csv(output_file)
    input_df = pd.read_csv(input_file)
    # voorbeeld: check dat verplichte kolommen aanwezig zijn
    for col in ["title", "abstract", "authors", "doi", "url", "year"]:
        assert col in df.columns
    assert not df.empty
    assert len(df) == len(input_df)


def test_make_asreview_csv_from_db(tmp_path: Path):
    # Arrange
    db_file = const.DEFAULT_SQLITE_PATH  # of gebruik een test-specifiek bestand
    output_file = tmp_path / "out_db.csv"

    # Act
    make_asreview_csv_from_db(
        db_path=db_file,
        out_csv=output_file,
        library_id=os.getenv("ZOTERO_LIBRARY_ID"),
        deduplicate=False,
    )
    print(f"Output file saved at: {output_file}")

    # Assert
    assert output_file.exists()
    df = pd.read_csv(output_file)
    for col in ["title", "abstract", "authors", "doi", "url", "year"]:
        assert col in df.columns
    assert not df.empty


def test_make_asreview_csv_from_db_via_main(tmp_path: Path):
    # Arrange
    db_file = const.DEFAULT_SQLITE_PATH
    output_file = tmp_path / "out_db_main.csv"

    # Act: roep de CLI aan alsof gebruiker dit uitvoert
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "espace.zotsync",
            "export",
            "--db-path",
            str(db_file),
            "--library-id",
            os.getenv("ZOTERO_LIBRARY_ID"),
            str(output_file),
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    print(result.stderr)

    # Assert
    assert result.returncode == 0, f"CLI returned nonzero: {result.stderr}"
    assert output_file.exists()
    df = pd.read_csv(output_file)
    for col in ["title", "abstract", "authors", "doi", "url", "year"]:
        assert col in df.columns
    assert not df.empty


def test_make_asreview_csv_from_db_via_main_using_dotenv(tmp_path: Path):
    # Arrange
    db_file = const.DEFAULT_SQLITE_PATH
    output_file = tmp_path / "out_db_main_env.csv"

    # Create a temporary cwd containing a .env file with a library id.
    # Use the current environment's ZOTSYNC_LIBRARY_ID if available; otherwise skip the test
    real_lib = os.getenv("ZOTSYNC_LIBRARY_ID")
    if not real_lib:
        pytest.skip(
            "ZOTSYNC_LIBRARY_ID not set in environment; cannot run .env-based integration test"
        )

    env_cwd = tmp_path / "envcwd"
    env_cwd.mkdir()
    (env_cwd / ".env").write_text(f"ZOTSYNC_LIBRARY_ID={real_lib}\n")

    # Act: run the CLI without passing --library-id so it must pick it up from .env in cwd
    env = os.environ.copy()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "espace.zotsync",
            "export",
            "--db-path",
            str(db_file),
            str(output_file),
        ],
        capture_output=True,
        text=True,
        cwd=str(env_cwd),
        env=env,
    )
    print(result.stdout)
    print(result.stderr)

    # Assert
    assert result.returncode == 0, f"CLI returned nonzero: {result.stderr}"
    assert output_file.exists()
    df = pd.read_csv(output_file)
    for col in ["title", "abstract", "authors", "doi", "url", "year"]:
        assert col in df.columns
    assert not df.empty

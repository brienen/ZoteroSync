import pandas as pd
from pathlib import Path
import pytest
import espace.zotsync.const as const
import os

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

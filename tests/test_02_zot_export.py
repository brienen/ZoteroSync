import pandas as pd
from pathlib import Path
import tempfile
import pytest

from espace.zotsync.zot_export import make_asreview_csv

@pytest.mark.parametrize("filename", ["sample_zotero.csv", "real_zotero.csv"])
def test_make_asreview_csv(tmp_path: Path, filename):
    # Arrange: pad naar input uit tests/data
    input_file = Path(__file__).parent / "data" / filename
    output_file = tmp_path / "out.csv"

    # Act
    make_asreview_csv(zotero_csv=input_file, out_csv=output_file, deduplicate=False)
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
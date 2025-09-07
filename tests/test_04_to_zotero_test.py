from __future__ import annotations
"""
Integration test: write ASReview decisions into a real Zotero library and
verify the review:* tags are actually set on the matching items.

⚠️ This test will modify your Zotero library. Use only against a safe test library.
Run explicitly with:
    poetry run pytest -m integration tests/test_04_to_zotero_test.py

Credentials should be provided via env vars:
  ZOTERO_API_KEY, ZOTERO_LIBRARY_ID, ZOTERO_LIBRARY_TYPE (users|groups)
"""

from pathlib import Path
import os
import pandas as pd
import pytest
import requests

from espace.zotsync.from_asreview import apply_asreview_decisions

ZOTERO_HOST = "https://api.zotero.org"


def _base_url(library_type: str, library_id: str) -> str:
    return f"{ZOTERO_HOST}/{library_type}/{library_id}"


def _headers(api_key: str) -> dict[str, str]:
    return {"Zotero-API-Key": api_key}


def _get_first_json(url: str, headers: dict, params: dict) -> dict | None:
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    data = r.json()
    return data[0] if data else None


def _tags_set(tags_list) -> set[str]:
    return {t.get("tag") for t in (tags_list or [])}


def _remove_all_review_tags(base: str, headers: dict, *, limit: int = 100) -> int:
    """Remove all tags starting with 'review:' from *all* items in the library.

    Returns the number of items that were updated.
    """
    updated = 0
    start = 0
    while True:
        r = requests.get(
            f"{base}/items",
            headers=headers,
            params={"format": "json", "limit": limit, "start": start},
        )
        r.raise_for_status()
        items = r.json() or []
        if not items:
            break
        for it in items:
            data = it.get("data", {})
            tags = data.get("tags", []) or []
            new_tags = [tg for tg in tags if not str(tg.get("tag", "")).startswith("review:")]
            if len(new_tags) != len(tags):
                data["tags"] = new_tags
                key = it.get("key")
                ver = it.get("version")
                resp = requests.put(
                    f"{base}/items/{key}",
                    headers=headers,
                    json={"key": key, "version": ver, "data": data},
                )
                # Accept both 200 and 204 as success
                if resp.status_code in (200, 204):
                    updated += 1
        # paginate
        start += limit
    return updated


@pytest.mark.integration
def test_write_to_real_zotero(tmp_path: Path):
    # --- Arrange: ASReview decisions ---
    title_included = "Automated translation from domain knowledge to software model: EXCEL2UML in the tunneling domain"
    year_included = "2023"
    title_excluded = "Automatic Metadata Generation and Digital Cultural Heritage"
    year_excluded = "2012"

    df = pd.DataFrame(
        [
            {
                "title": title_included,
                "year": year_included,
                "asreview_label": 1,
                "asreview_time": "2025-09-07T11:00:00Z",
                "asreview_note": "keuze: opnemen",
            },
            {
                "title": title_excluded,
                "year": year_excluded,
                "asreview_label": 0,
                "asreview_time": "2025-09-07T11:05:00Z",
                "asreview_note": "keuze: uitsluiten",
            },
        ]
    )
    asr_csv = tmp_path / "asr.csv"
    df.to_csv(asr_csv, index=False)

    # --- Credentials & library info ---
    api_key = os.getenv("ZOTERO_API_KEY")
    library_id = os.getenv("ZOTERO_LIBRARY_ID")
    library_type = os.getenv("ZOTERO_LIBRARY_TYPE", "users")  # or "groups"

    if not api_key or not library_id:
        pytest.skip("Set ZOTERO_API_KEY and ZOTERO_LIBRARY_ID (and optionally ZOTERO_LIBRARY_TYPE) to run this test.")

    # --- Prepare base + headers once ---
    base = _base_url(library_type, library_id)
    hdrs = _headers(api_key)

    # --- Cleanup BEFORE act: remove existing review:* tags across the entire library ---
    removed_from = _remove_all_review_tags(base, hdrs)
    print(f"[cleanup-before] review:* tags removed from {removed_from} items")

    # --- Act: apply decisions ---
    res = apply_asreview_decisions(
        asr_csv=asr_csv,
        api_key=api_key,
        library_id=library_id,
        library_type=library_type,
        zotero_host=ZOTERO_HOST,
        dry_run=False,
    )

    assert "updated" in res

    # --- Assert: fetch both items back from Zotero and verify review:* tags ---

    # 1) Item by title+year
    it_title = _get_first_json(
        f"{base}/items",
        hdrs,
        {"q": title_excluded, "qmode": "titleCreatorYear", "format": "json", "limit": 25},
    )
    assert it_title is not None, "Title item not found via API"
    tags_title = _tags_set(it_title.get("data", {}).get("tags", []))
    assert "review:Decision=excluded" in tags_title
    assert "review:Time=2025-09-07 11:05" in tags_title
    assert "review:ReasonDenied=keuze: uitsluiten" in tags_title

    # 2) Included item by title+year
    it_incl = _get_first_json(
        f"{base}/items",
        hdrs,
        {"q": title_included, "qmode": "titleCreatorYear", "format": "json", "limit": 25},
    )
    assert it_incl is not None, "Included title item not found via API"
    tags_incl = _tags_set(it_incl.get("data", {}).get("tags", []))
    assert "review:Decision=included" in tags_incl
    assert "review:Time=2025-09-07 11:00" in tags_incl
    assert "review:ReasonDenied=keuze: opnemen" in tags_incl


    # Print for manual inspection when running -s
    print("Integration test result:", res)
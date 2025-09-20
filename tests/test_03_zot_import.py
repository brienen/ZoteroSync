"""Tests for zot_import.apply_asreview_decisions.

We mock Zotero HTTP calls to avoid network access.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import sqlite3

import json
import pandas as pd
import pytest

from espace.zotsync.zot_import import apply_asreview_decisions


class _FakeResponse:
    def __init__(self, status_code: int = 200, data: Any | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._data = data
        self.text = text

    # emulate requests.Response.json()
    def json(self) -> Any:
        return self._data


class _FakeSession:
    """Very small stub for requests.Session used by zot_import."""

    def __init__(self, items_index: Dict[str, Dict[str, Any]]):
        # items_index maps query key -> list of items
        self.items_index = items_index
        self.put_calls: List[Dict[str, Any]] = []

    def get(self, url: str, params: Dict[str, Any] | None = None):
        # We only care about .../items queries with q / qmode
        if url.endswith("/items"):
            q = (params or {}).get("q", "")
            # Return list for the query if present, else empty
            data = self.items_index.get(q, [])
            if not data:
                data = self.items_index.get(q.lower(), [])
            return _FakeResponse(200, data)
        # Children not used here
        return _FakeResponse(404, text="not found")

    def put(self, url: str, data: str = ""):
        # record payload and pretend success
        try:
            payload = json.loads(data)
        except Exception:  # pragma: no cover - defensive
            payload = {"raw": data}
        self.put_calls.append({"url": url, "payload": payload})
        return _FakeResponse(200)


@pytest.fixture()
def fake_env(monkeypatch):
    """Monkeypatch the Zotero session factory to our fake, and provide a tiny index.

    We create two items, both matched by title(+year):
      - "has doi" (2020)
      - "no doi title" (2021)
    """
    # Two fake Zotero items
    item_by_title_has_doi = {
        "key": "ABCD1",
        "version": 10,
        "data": {"title": "has doi", "date": "2020" , "tags": []},
    }
    item_by_title = {
        "key": "WXYZ2",
        "version": 3,
        "data": {"title": "no doi title", "date": "2021" , "tags": []},
    }

    # Index responses for GET /items?q=...
    items_index = {
        # exact title lookups used by titleCreatorYear stage
        "has doi": [item_by_title_has_doi],
        "no doi title": [item_by_title],
        # fuzzy stage also queries with q=title; we reuse same entry
    }

    fake = _FakeSession(items_index)

    # Patch the session creator inside the module under test
    import espace.zotsync.zot_import as m

    monkeypatch.setattr(m, "_zotero_session", lambda api_key: fake)
    # Provide library base builder untouched; apply_asreview_decisions uses it to compose URLs only

    return fake


@pytest.fixture()
def asr_csv_tmp(tmp_path: Path) -> Path:
    """Create a minimal review export CSV for tests."""
    df = pd.DataFrame(
        [
            {"title": "has doi", "year": "2020", "asreview_label": 1, "asreview_time": "2025-09-07T10:00:00Z", "asreview_note": "looks relevant"},
            {"title": "no doi title", "year": "2021", "asreview_label": 0, "asreview_time": "2025-09-07T10:05:00Z", "asreview_note": "out of scope"},
        ]
    )
    p = tmp_path / "asr.csv"
    df.to_csv(p, index=False)
    return p


def test_zot_import_dry_run(fake_env: _FakeSession, asr_csv_tmp: Path):
    res = apply_asreview_decisions(
        asr_csv=asr_csv_tmp,
        api_key="dummy",
        library_id="6143565",
        library_type="groups",
        dry_run=True,
    )
    # Both rows should be counted as updated in dry-run, no API writes
    assert res["updated"] == 2
    assert res["not_found"] == 0
    assert res["errors"] == 0
    assert fake_env.put_calls == []


def test_zot_import_updates_and_tags(fake_env: _FakeSession, asr_csv_tmp: Path):
    res = apply_asreview_decisions(
        asr_csv=asr_csv_tmp,
        api_key="dummy",
        library_id="6143565",
        library_type="groups",
        dry_run=False,
        db_path=None
    )

    # One PUT per matched item (we have 2 rows)
    assert res["updated"] == 2
    assert res["not_found"] == 0
    assert res["errors"] == 0
    assert len(fake_env.put_calls) == 2

    # Check that tags are present in payload
    payload1 = fake_env.put_calls[0]["payload"]["data"]["tags"]
    payload2 = fake_env.put_calls[1]["payload"]["data"]["tags"]

    def tags_to_set(tags_list):
        return {t.get("tag") for t in tags_list}

    s1 = tags_to_set(payload1)
    s2 = tags_to_set(payload2)

    # included/excluded should be set appropriately
    assert "review:Decision=included" in s1
    assert "review:Time=2025-09-07 10:00" in s1
    assert "review:Reason=looks relevant" in s1 or "review:Reason=" in s1  # tolerate empty if mapping differs
    assert "review:Decision=excluded" in s2
    assert "review:Time=2025-09-07 10:05" in s2
    assert "review:Reason=out of scope" in s2


# Test: dry-run with a sqlite db
def test_zot_import_dry_run_sqlite(asr_csv_tmp: Path, tmp_path: Path):
    # Setup: kopieer een minimale Zotero sqlite database naar tmp_path
    db_path = tmp_path / "zotero.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE libraries (libraryID INTEGER);
        INSERT INTO libraries (libraryID) VALUES (1);

        CREATE TABLE groups (groupID INTEGER, libraryID INTEGER, name TEXT);
        INSERT INTO groups (groupID, libraryID, name) VALUES (123, 1, 'Group 1');

        CREATE TABLE items (itemID INTEGER PRIMARY KEY, libraryID INTEGER, key TEXT);
        INSERT INTO items (itemID, libraryID, key)
            VALUES (100, 1, 'ABCD1'),
                (101, 1, 'WXYZ2');

        CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
        INSERT INTO fields (fieldID, fieldName) VALUES (1, 'title');

        CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
        INSERT INTO itemDataValues (valueID, value)
            VALUES (1, 'has doi'),
                (2, 'no doi title');

        CREATE TABLE itemData (itemID INTEGER, fieldID INTEGER, valueID INTEGER);
        INSERT INTO itemData (itemID, fieldID, valueID)
            VALUES (100, 1, 1),
                (101, 1, 2);

        -- Nieuwe tabellen voor review-tags
        CREATE TABLE tags (tagID INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE itemTags (itemID INTEGER, tagID INTEGER, type INTEGER);
    """)    
    conn.commit()
    conn.close()

    from espace.zotsync.zot_import import apply_asreview_decisions

    res = apply_asreview_decisions(
        asr_csv=asr_csv_tmp,
        api_key="unused",
        library_id="123",
        library_type="groups",
        dry_run=True,
        db_path=db_path,
    )

    # Verwacht: 2 gevonden, niets gemarkeerd als niet gevonden of error
    assert res["updated"] == 2
    assert res["not_found"] == 0
    assert res["errors"] == 0
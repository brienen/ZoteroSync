import sqlite3
from pathlib import Path
import pytest

from espace.zotsync import zot_import


def _make_sqlite_db(tmp_path: Path) -> Path:
    """Maak een minimale SQLite-db met 1 item en 1 review-tag."""
    db_path = tmp_path / "zotero.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Tabellen aanmaken
    cur.execute("CREATE TABLE tags (tagID INTEGER PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE itemTags (itemID INTEGER, tagID INTEGER, type INTEGER)")
    cur.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
    # Dummy data
    cur.execute("INSERT INTO tags (tagID, name) VALUES (?, ?)", (1, "review:Decision=included"))
    cur.execute("INSERT INTO items (itemID, key) VALUES (?, ?)", (10, "ABC123"))
    cur.execute("INSERT INTO itemTags (itemID, tagID, type) VALUES (?, ?, ?)", (10, 1, 0))
    conn.commit()
    conn.close()
    return db_path


def test_remove_review_tags_sqlite(tmp_path):
    db_path = _make_sqlite_db(tmp_path)
    result = zot_import.remove_review_tags(
        api_key="unused",
        library_id="1",
        library_type="groups",
        db_path=db_path,
    )
    assert result["removed"] == 1
    assert result["errors"] == 0

    # Controleer dat de tag ook echt verwijderd is
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM itemTags")
    rows = cur.fetchall()
    conn.close()
    assert rows == []


def test_remove_review_tags_dry_run(tmp_path):
    db_path = _make_sqlite_db(tmp_path)
    result = zot_import.remove_review_tags(
        api_key="unused",
        library_id="1",
        library_type="groups",
        db_path=db_path,
        dry_run=True,
    )
    assert result["removed"] == 1
    assert result["errors"] == 0

    # Controleer dat de tag nog steeds aanwezig is
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM itemTags")
    rows = cur.fetchall()
    conn.close()
    assert len(rows) == 1
import sqlite3
from pathlib import Path
import pytest
import os
import espace.zotsync.const as const

from dotenv import load_dotenv
from espace.zotsync import zot_import


@pytest.fixture(autouse=True)
def load_env():
    load_dotenv()


def _make_sqlite_db(tmp_path: Path) -> Path:
    """Maak een minimale SQLite-db met 1 item en 1 review-tag."""
    db_path = tmp_path / "zotero.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
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

        -- Review-tags tabellen
        CREATE TABLE tags (tagID INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE itemTags (itemID INTEGER, tagID INTEGER, type INTEGER);

        -- Koppel één review-tag aan item 100
        INSERT INTO tags (tagID, name) VALUES (1, 'review:Decision=included');
        INSERT INTO itemTags (itemID, tagID, type) VALUES (100, 1, 0);
        """
    )
    conn.commit()
    conn.close()
    return db_path


def count_review_tags(db_path: Path, group_id: int, tag_prefix: str) -> int:
    """Tel het aantal review-tags in de database met de gegeven prefix."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT libraryID FROM groups WHERE groupID = ?", (group_id,))
    group = cur.fetchone()
    if not group:
        return 0
    group = group[0]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM itemTags it
        JOIN tags t ON it.tagID = t.tagID
        JOIN items i ON it.itemID = i.itemID
        WHERE t.name LIKE ? AND i.libraryID = ?
        """,
        (f"{tag_prefix}:%", group),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def test_remove_review_tags_sqlite(tmp_path):

    group_id = os.getenv("ZOTERO_LIBRARY_ID")
    # db_path = _make_sqlite_db(tmp_path)
    db_path = const.DEFAULT_SQLITE_PATH
    # Tel het aantal review-tags gekoppeld aan items vóór verwijdering
    initial_count = count_review_tags(db_path, group_id, const.REVIEW_PREFIX)

    result = zot_import.remove_review_tags(
        api_key="unused",
        library_id=group_id,  # groupID → wordt naar libraryID 1 vertaald
        library_type="groups",
        # db_path=db_path,
    )
    assert result["removed"] == initial_count
    assert result["errors"] == 0

    # Controleer dat de tag ook echt verwijderd is
    count = count_review_tags(db_path, group_id, const.REVIEW_PREFIX)
    assert count == 0


def test_remove_review_tags_dry_run(tmp_path):
    db_path = _make_sqlite_db(tmp_path)
    result = zot_import.remove_review_tags(
        api_key="unused",
        library_id=123,
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

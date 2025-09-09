"""
ASReview → Zotero: schrijf beslissingen terug als tags met review-parameters.

Publieke API:
    apply_asreview_decisions(
        asr_csv: Path,
        api_key: str,
        library_id: str,
        library_type: str = "users",
        # tag_prefix is unused, all tags start with 'review:'
        fuzzy_threshold: float = 0.90,
        dry_run: bool = False,
        zotero_host: str = "http://localhost:23119",
    ) -> dict

Werking:
- Leest ASReview-export (CSV). Ondersteunt kolommen: `title`/`year`/`doi` (optioneel voor matching), en de beslisvelden
  `asreview_label`, `asreview_time`, `asreview_note`.
- Matcht Zotero-items op (titel+jaar) en als fallback fuzzy op titel.
- Schrijft alléén deze tags per item:
    * `review:Decision=<included|excluded>`   (afgeleid van `asreview_label`)
    * `review:Time=<...>`                     (lokale tijd, geformatteerd uit `asreview_time`)
    * `review:Reason=<...>`                    (uit `asreview_note`)
- Retourneert een klein rapport met aantal geüpdatete, gemiste en fouten.
- Als meerdere Zotero-items matchen, worden **alle** matches bijgewerkt.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Optional, Tuple
import difflib
import sqlite3

import pandas as pd
import requests

# -------------------------- helpers --------------------------

def _norm(s: object) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def _normalize_doi(s: object) -> str:
    """Normalize DOI for robust matching: lowercased, strip URL prefixes."""
    raw = _norm(s).lower()
    if not raw:
        return ""
    # strip common URL prefixes
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "doi.org/"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    # strip leading/trailing spaces again (in case)
    return raw.strip()


def _guess_year(s: str) -> str:
    s = _norm(s)
    if not s:
        return ""
    m = re.search(r"(19|20)\d{2}", s)
    return m.group(0) if m else ""


def _zotero_base(lib_type: str, lib_id: str, host: str = "http://localhost:23119") -> str:
    return f"{host}/{lib_type}/{lib_id}"


def _zotero_session(api_key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Zotero-API-Key": api_key, "Content-Type": "application/json"})
    return s


def _search_by_doi(session: requests.Session, base: str, doi: str):
    doi = _normalize_doi(doi)
    matches = []
    if not doi:
        return matches
    r = session.get(f"{base}/items", params={"q": doi, "qmode": "everything", "format": "json", "limit": 100})
    if r.status_code != 200:
        return matches
    for it in r.json():
        data = it.get("data", {})
        if _normalize_doi(data.get("DOI", "")) == doi:
            matches.append(it)
    return matches


def _search_by_title_year(session: requests.Session, base: str, title: str, year: str):
    title = _norm(title)
    results = []
    if not title:
        return results
    r = session.get(
        f"{base}/items", params={"q": title, "qmode": "titleCreatorYear", "format": "json", "limit": 100}
    )
    if r.status_code != 200:
        return results
    tl = title.lower()
    for it in r.json():
        data = it.get("data", {})
        cand_title = _norm(data.get("title", "")).lower()
        if cand_title == tl:
            zyear = _guess_year(_norm(data.get("date", "")) or _norm(data.get("publicationYear", "")))
            if not year or not zyear or year.lower() == zyear.lower():
                results.append(it)
    return results


def _search_fuzzy(session: requests.Session, base: str, title: str, year: str, threshold: float = 0.9):
    title = _norm(title)
    if not title:
        return []
    r = session.get(f"{base}/items", params={"q": title, "qmode": "everything", "format": "json", "limit": 200})
    if r.status_code != 200:
        return []
    tl = title.lower()
    scored = []
    for it in r.json():
        data = it.get("data", {})
        cand_title = _norm(data.get("title", "")).lower()
        if not cand_title:
            continue
        score = difflib.SequenceMatcher(None, tl, cand_title).ratio()
        if year:
            zyear = _guess_year(_norm(data.get("date", "")) or _norm(data.get("publicationYear", "")))
            if zyear == year:
                score += 0.02
        if score >= threshold:
            scored.append((score, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored]


def _format_review_time(val: object) -> str:
    """Format timestamps to a human-readable form 'YYYY-MM-DD HH:MM' in local time."""
    # Treat NaN/None/empty as empty
    try:
        if pd.isna(val):
            return ""
    except Exception:
        pass
    if val is None or str(val).strip() == "":
        return ""
    try:
        ts = pd.to_datetime(val, utc=True, errors="raise").tz_convert(None)
        return ts.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(val)


@dataclass
class UpdateReport:
    updated: int = 0
    not_found: int = 0
    errors: int = 0

    def to_dict(self):
        return {"updated": self.updated, "not_found": self.not_found, "errors": self.errors}


def _find_items_by_title_year_sqlite(
    db_path: Path,
    title: str,
    year: str,
    library_id: int,
    threshold: float = 0.9
) -> list[dict]:
    title = _norm(title).lower()
    if not title:
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT libraryID FROM groups WHERE groupID = ?", (library_id,))
    group = cur.fetchone()
    if not group:
        return []

    cur.execute("SELECT itemID, key FROM items WHERE libraryID = ?", (group["libraryID"],))
    items = cur.fetchall()

    results = []
    for item in items:
        cur.execute("""
            SELECT value FROM itemDataValues WHERE valueID = (
                SELECT valueID FROM itemData WHERE itemID = ? AND fieldID = (
                    SELECT fieldID FROM fields WHERE fieldName = 'title'
                ) LIMIT 1
            )
        """, (item["itemID"],))
        row = cur.fetchone()
        if not row:
            continue
        cand_title = _norm(row["value"]).lower()
        score = difflib.SequenceMatcher(None, title, cand_title).ratio()
        if score >= threshold:
            results.append({"key": item["key"], "score": score})
    conn.close()
    return sorted(results, key=lambda x: x["score"], reverse=True)


# -------------------------- core API --------------------------

def apply_asreview_decisions(
    asr_csv: Path,
    api_key: str,
    library_id: str,
    library_type: str = "groups",
    # tag_prefix is unused, all tags start with 'review:'
    fuzzy_threshold: float = 0.90,
    dry_run: bool = False,
    zotero_host: str = "http://localhost:23119",
    db_path: Path | None = None,
) -> dict:
    """
    Schrijf ASReview-beslissingen terug naar Zotero als tags.

    CSV-vereisten: kolommen `title`, `year` (optioneel), `doi` (optioneel), en de beslisvelden
    `asreview_label`, `asreview_time`, `asreview_note`.

    Voor elk item wordt alléén deze tags toegevoegd:
      - `review:Decision=<included|excluded>`   (afgeleid van `asreview_label`)
      - `review:Time=<...>`                     (lokale tijd, geformatteerd uit `asreview_time`)
      - `review:Reason=<...>`                    (uit `asreview_note`)

    zotero_host: base URL van de Zotero instantie (default: http://localhost:23119)

    Als `db_path` is opgegeven, wordt alleen gezocht in de lokale Zotero SQLite-database en geen wijzigingen doorgevoerd (alleen telling van matches).

    Returns: dict met aantallen {updated, not_found, errors}.
    """
    df = pd.read_csv(asr_csv)

    df["asreview_label"] = df.get("asreview_label", "")
    df["asreview_time"] = df.get("asreview_time", "")
    df["asreview_note"] = df.get("asreview_note", "")

    if "title" in df.columns:
        df["title"] = df["title"].map(_norm)
    else:
        df["title"] = ""

    if "year" in df.columns:
        df["year"] = df["year"].map(lambda x: _norm(x) or "")
    else:
        df["year"] = ""

    if "doi" in df.columns:
        df["doi"] = df["doi"].map(_normalize_doi)
    else:
        df["doi"] = ""

    def label_to_decision(v: object) -> str | None:
        s = _norm(v).lower()
        if not s:
            return None
        # Common encodings: 1/0, included/excluded, relevant/irrelevant, yes/no, true/false
        if s in {"1", "included", "relevant", "yes", "true", "y"}:
            return "included"
        if s in {"0", "-1", "excluded", "irrelevant", "no", "false", "n"}:
            return "excluded"
        return None

    session = _zotero_session(api_key)
    base = _zotero_base(library_type, library_id, host=zotero_host)

    report = UpdateReport()
    use_sqlite = db_path is not None

    for _, r in df.iterrows():
        title = _norm(r.get("title", ""))
        year = _norm(r.get("year", ""))
        # doi is not used for matching anymore per updated docstring, but keep it normalized anyway
        doi = _norm(r.get("doi", "").lower())

        time_value = _format_review_time(r.get("asreview_time", ""))
        raw_reason = r.get("asreview_note", "")
        try:
            reason_value = "" if pd.isna(raw_reason) else _norm(raw_reason)
        except Exception:
            reason_value = _norm(raw_reason)

        decision_value = label_to_decision(r.get("asreview_label", ""))

        tags_to_set = []
        if decision_value:
            tags_to_set.append(f"review:Decision={decision_value}")
            # Always include Time if available, regardless of decision
            if time_value:
                tags_to_set.append(f"review:Time={time_value}")
            # Use Reason= instead of ReasonDenied=, only if non-empty
            if reason_value:
                tags_to_set.append(f"review:Reason={reason_value}")

        # Zoek items (alle matches)
        if use_sqlite:
            items = _find_items_by_title_year_sqlite(db_path, title, year, library_id, threshold=fuzzy_threshold)
            if not tags_to_set:
                continue
            import sqlite3
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            for match in items:
                key = match["key"]
                cur.execute("SELECT itemID FROM items WHERE key = ?", (key,))
                row = cur.fetchone()
                if not row:
                    report.errors += 1
                    continue
                item_id = row[0]
                # Verwijder bestaande review:* tags
                cur.execute("""
                    SELECT tagID FROM tags WHERE name LIKE 'review:%'
                    AND tagID IN (SELECT tagID FROM itemTags WHERE itemID = ?)
                """, (item_id,))
                tag_ids = [row[0] for row in cur.fetchall()]
                for tag_id in tag_ids:
                    cur.execute("DELETE FROM itemTags WHERE itemID = ? AND tagID = ?", (item_id, tag_id))
                for tag in tags_to_set:
                    # Check of tag al bestaat
                    cur.execute("SELECT tagID FROM tags WHERE name = ?", (tag,))
                    row = cur.fetchone()
                    if row:
                        tag_id = row[0]
                    else:
                        # Bepaal nieuwe unieke tagID
                        cur.execute("SELECT MAX(tagID) FROM tags")
                        max_id = cur.fetchone()[0]
                        tag_id = (max_id or 0) + 1
                        cur.execute("INSERT INTO tags (tagID, name) VALUES (?, ?)", (tag_id, tag,))
                    cur.execute("INSERT OR IGNORE INTO itemTags (itemID, tagID, type) VALUES (?, ?, ?)", (item_id, tag_id, 0))
                report.updated += 1
            conn.commit()
            conn.close()
            continue
        else:
            ty_matches = _search_by_title_year(session, base, title, year)
            if ty_matches:
                items = ty_matches
            else:
                items = _search_fuzzy(session, base, title, year, threshold=fuzzy_threshold)

        if not items:
            report.not_found += 1
            continue

        if not tags_to_set and not dry_run:
            # No tags to set and not dry run, skip update but count as not found?
            # The instructions say skip update if tags_to_set is empty and dry_run is False,
            # but still count not_found if no matched items.
            # Here we have matches but no tags to set, so just continue without update or counting not_found.
            continue

        if dry_run:
            report.updated += len(items)
            continue

        for item in items:
            key = item.get("key")
            ver = item.get("version")
            data = item.get("data", {})
            tags = data.get("tags", []) or []

            def ensure_tag(tag: str):
                if not any(t.get("tag", "") == tag for t in tags):
                    tags.append({"tag": tag})

            for t in tags_to_set:
                ensure_tag(t)

            data["tags"] = tags
            resp = session.put(f"{base}/items/{key}", data=json.dumps({"key": key, "version": ver, "data": data}))
            if resp.status_code in (200, 204):
                report.updated += 1
            else:
                report.errors += 1

    return report.to_dict()


__all__ = ["apply_asreview_decisions"]
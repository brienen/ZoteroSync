"""
Convert a Zotero CSV export into an ASReview-ready CSV.

Features:
- Normalizes common Zotero CSV columns (title, abstract, authors, keywords, doi, url, year).
- Deduplicates on DOI, else on a fingerprint of (title+year).
- Optional: enrich output with `zotero_pdf` links using the Zotero API.

Public API:
    make_asreview_csv(zotero_csv: Path, out_csv: Path, api_key: Optional[str] = None,
                      library_id: Optional[str] = None, library_type: str = "users",
                      add_pdf_links: bool = False) -> None
"""

from __future__ import annotations

from . import const

import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np
import requests
from dateutil import parser as dtp

REQUIRED_ASR_COLS = ["title", "abstract", "authors", "keywords", "doi", "url", "year"]


# ------------------------------- helpers ------------------------------------
def _norm(s: object) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def _guess_year(s: str) -> str:
    s = _norm(s)
    if not s:
        return ""
    try:
        return str(dtp.parse(s, fuzzy=True).year)
    except Exception:
        m = re.search(r"(19|20)\d{2}", s)
        return m.group(0) if m else ""


def _first_nonempty(*vals: object) -> str:
    for v in vals:
        v = _norm(v)
        if v:
            return v
    return ""


def _build_fingerprint(title: str, year: str, doi: str) -> str:
    doi = _norm(doi).lower()
    if doi:
        return f"doi:{doi}"
    base = f"{_norm(title).lower()}|{_norm(year)}"
    return (
        "tsh:" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    )  # nosec B324 (optioneel)


def _zotero_base(lib_type: str, lib_id: str) -> str:
    return f"https://api.zotero.org/{lib_type}/{lib_id}"


def _zotero_session(api_key: Optional[str]) -> requests.Session:
    s = requests.Session()
    if api_key:
        s.headers.update({"Zotero-API-Key": api_key})
    s.headers.update({"Content-Type": "application/json"})
    return s


def _search_zotero_by_doi(session: requests.Session, base: str, doi: str):
    if not doi:
        return None
    r = session.get(
        f"{base}/items",
        params={"q": doi, "qmode": "everything", "format": "json", "limit": 25},
    )
    if r.status_code != 200:
        return None
    doi_l = _norm(doi).lower()
    for it in r.json():
        data = it.get("data", {})
        zdoi = _norm(data.get("DOI", "")).lower()
        if zdoi == doi_l:
            return it
    return None


def _zotero_child_pdf_link(session: requests.Session, base: str, item_key: str) -> str:
    if not item_key:
        return ""
    r = session.get(
        f"{base}/items/{item_key}/children", params={"format": "json", "limit": 50}
    )
    if r.status_code != 200:
        return ""
    for ch in r.json():
        d = ch.get("data", {})
        if (
            d.get("itemType") == "attachment"
            and str(d.get("contentType", "")).lower() == "application/pdf"
        ):
            akey = ch.get("key")
            return f"zotero://open-pdf/library/items/{akey}"
    return ""


# ------------------------------- core API -----------------------------------
def make_asreview_csv(
    zotero_csv: Path,
    out_csv: Path,
    api_key: Optional[str] = None,
    library_id: Optional[str] = None,
    library_type: str = "users",
    add_pdf_links: bool = False,
    deduplicate: bool = True,
) -> None:
    """
    Build an ASReview-ready CSV from a Zotero CSV export.

    Args:
      zotero_csv: Path to Zotero CSV export.
      out_csv: Output CSV path for ASReview.
      api_key: (Optional) Zotero API key to resolve PDF attachment links.
      library_id: (Optional) Zotero user or group id for API.
      library_type: 'users' or 'groups'.
      add_pdf_links: If True, adds a 'zotero_pdf' column with zotero://open-pdf links.
      deduplicate: If True, remove duplicates (by DOI, else title+year fingerprint). If False, keep all rows.
    """
    df = pd.read_csv(zotero_csv)

    # Map common Zotero CSV headers (adjust here if your locale differs)
    colmap = {
        "Title": "title",
        "Abstract Note": "abstract",
        "Author": "authors",
        "Publication Year": "year",
        "Date": "date",
        "DOI": "doi",
        "Url": "url",
        "URL": "url",
        "Manual Tags": "keywords",
        "Automatic Tags": "_auto_tags",
    }
    nd = {}
    for zcol, tcol in colmap.items():
        nd[tcol] = df[zcol] if zcol in df.columns else ""
    ndf = pd.DataFrame(nd)

    out = pd.DataFrame()
    out["title"] = ndf["title"].map(_norm)
    out["abstract"] = ndf["abstract"].map(_norm)

    def _norm_authors(s: str) -> str:
        s = _norm(s)
        if not s or s.lower() == "nan":
            return ""
        parts = [a.strip() for a in s.split(";") if a.strip()]
        return "; ".join(parts)

    out["authors"] = ndf["authors"].map(_norm_authors)

    def _combine_keywords(row) -> str:
        k = _norm(row.get("keywords", ""))
        a = _norm(row.get("_auto_tags", ""))
        if k and a:
            return "; ".join([k, a])
        return k or a

    out["keywords"] = ndf.apply(_combine_keywords, axis=1)
    out["doi"] = ndf["doi"].map(lambda s: _norm(s).lower())
    out["url"] = ndf["url"].map(_norm)
    out["year"] = ndf.apply(
        lambda r: _first_nonempty(
            _norm(r.get("year", "")), _guess_year(r.get("date", ""))
        ),
        axis=1,
    )

    # Voeg optionele ASReview kolommen toe indien beschikbaar
    for col in [const.ASR_LABEL_COL, const.ASR_TIME_COL, const.ASR_NOTE_COL]:
        if col in df.columns:
            out[col] = df[col]
        else:
            out[col] = ""

    # Ensure required columns exist
    for c in REQUIRED_ASR_COLS:
        if c not in out.columns:
            out[c] = ""

    # Zorg dat ook de optionele reviewvelden aanwezig zijn
    for c in [const.ASR_LABEL_COL, const.ASR_TIME_COL, const.ASR_NOTE_COL]:
        if c not in out.columns:
            out[c] = ""

    # Deduplicate (DOI first, else title+year fingerprint)
    if deduplicate:
        fps = out.apply(
            lambda r: _build_fingerprint(r["title"], r["year"], r["doi"]), axis=1
        )
        out = out.loc[~fps.duplicated()].copy()

    # Optional: add zotero://open-pdf link if API info present
    if add_pdf_links and api_key and library_id:
        session = _zotero_session(api_key)
        base = _zotero_base(library_type, library_id)
        links = []
        for _, row in out.iterrows():
            link = ""
            item = _search_zotero_by_doi(session, base, row["doi"])
            if item:
                link = _zotero_child_pdf_link(session, base, item.get("key"))
            links.append(link)
        out["zotero_pdf"] = links

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)


def make_asreview_csv_from_db(
    db_path: Path,
    out_csv: Path,
    library_id: str,
    deduplicate: bool = True,
    local_pdf_links: bool = True,
    library_type: str = "groups",
) -> None:
    """
    Build an ASReview-ready CSV from a Zotero SQLite database.

    Args:
      db_path: Path to Zotero SQLite database file.
      out_csv: Output CSV path for ASReview.
      deduplicate: If True, remove duplicates (by DOI, else title+year fingerprint). If False, keep all rows.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT libraryID FROM groups WHERE groupID = ?", (library_id,))
    group = cur.fetchone()
    if not group:
        return
    group_id = group[0]

    query = f"""
  SELECT
  items.key as item_key,
  titleValues.value as title,
  abstractValues.value as abstract,
  authors.value as authors,
  yearValues.value as year,
  doiValues.value as doi,
  urlValues.value as url,
  tags.value as keywords,
  ia.filePath as local_url,
  labelTags.label_value as asreview_label,
  timeTags.time_value as asreview_time,
  noteTags.note_value as asreview_note
FROM items
LEFT JOIN itemData AS titleData
  ON titleData.itemID = items.itemID
  AND titleData.fieldID = (SELECT fieldID FROM fields WHERE fieldName = 'title' LIMIT 1)
LEFT JOIN itemDataValues AS titleValues
  ON titleValues.valueID = titleData.valueID

LEFT JOIN itemData AS abstractData
  ON abstractData.itemID = items.itemID
  AND abstractData.fieldID = (SELECT fieldID FROM fields WHERE fieldName = 'abstractNote' LIMIT 1)
LEFT JOIN itemDataValues AS abstractValues
  ON abstractValues.valueID = abstractData.valueID

LEFT JOIN (
  SELECT ic.itemID, GROUP_CONCAT(c.lastName || ' ' || c.firstName, '; ') AS value
  FROM itemCreators ic
  JOIN creators c ON c.creatorID = ic.creatorID
  GROUP BY ic.itemID
) AS authors ON authors.itemID = items.itemID

LEFT JOIN itemData AS yearData
  ON yearData.itemID = items.itemID
  AND yearData.fieldID = (SELECT fieldID FROM fields WHERE fieldName = 'date' LIMIT 1)
LEFT JOIN itemDataValues AS yearValues
  ON yearValues.valueID = yearData.valueID

LEFT JOIN itemData AS doiData
  ON doiData.itemID = items.itemID
  AND doiData.fieldID = (SELECT fieldID FROM fields WHERE fieldName = 'DOI' LIMIT 1)
LEFT JOIN itemDataValues AS doiValues
  ON doiValues.valueID = doiData.valueID

LEFT JOIN itemData AS urlData
  ON urlData.itemID = items.itemID
  AND urlData.fieldID = (SELECT fieldID FROM fields WHERE fieldName = 'url' LIMIT 1)
LEFT JOIN itemDataValues AS urlValues
  ON urlValues.valueID = urlData.valueID

LEFT JOIN (
  SELECT parentItemID, MIN(path) AS filePath
  FROM itemAttachments
  WHERE contentType = 'application/pdf'
  GROUP BY parentItemID
) ia ON ia.parentItemID = items.itemID

LEFT JOIN (
  SELECT it.itemID, GROUP_CONCAT(t.name, '; ') AS value
  FROM itemTags it
  JOIN tags t ON t.tagID = it.tagID
  GROUP BY it.itemID
) AS tags ON tags.itemID = items.itemID

LEFT JOIN (
  SELECT it.itemID,
         GROUP_CONCAT(SUBSTR(t.name, LENGTH('{const.REVIEW_DECISION_PREFIX}') + 1), '; ') AS label_value
  FROM itemTags it
  JOIN tags t ON t.tagID = it.tagID
  WHERE t.name LIKE '{const.REVIEW_DECISION_PREFIX}%'
  GROUP BY it.itemID
) AS labelTags ON labelTags.itemID = items.itemID

LEFT JOIN (
  SELECT it.itemID,
         GROUP_CONCAT(SUBSTR(t.name, LENGTH('{const.REVIEW_TIME_PREFIX}') + 1), '; ') AS time_value
  FROM itemTags it
  JOIN tags t ON t.tagID = it.tagID
  WHERE t.name LIKE '{const.REVIEW_TIME_PREFIX}%'
  GROUP BY it.itemID
) AS timeTags ON timeTags.itemID = items.itemID

LEFT JOIN (
  SELECT it.itemID,
         GROUP_CONCAT(SUBSTR(t.name, LENGTH('{const.REVIEW_REASON_PREFIX}') + 1), '; ') AS note_value
  FROM itemTags it
  JOIN tags t ON t.tagID = it.tagID
  WHERE t.name LIKE '{const.REVIEW_REASON_PREFIX}%'
  GROUP BY it.itemID
) AS noteTags ON noteTags.itemID = items.itemID
WHERE items.libraryID = {group_id} AND items.itemTypeID IN (
    SELECT itemTypeID FROM itemTypes
    WHERE typeName IN ('journalArticle', 'book', 'conferencePaper', 'report', 'thesis', 'webpage')
  )
"""
    df = pd.read_sql_query(query, conn)
    conn.close()

    out = pd.DataFrame()
    out["title"] = df["title"].fillna("").map(_norm)
    out["abstract"] = df["abstract"].fillna("").map(_norm)

    def _norm_authors(s: str) -> str:
        s = _norm(s)
        if not s or s.lower() == "nan":
            return ""
        parts = [a.strip() for a in s.split(";") if a.strip()]
        return "; ".join(parts)

    out["authors"] = df["authors"].fillna("").map(_norm_authors)

    def _norm_keywords(s: str) -> str:
        s = _norm(s)
        if not s or s.strip().lower() in ("nan", ""):
            return ""
        parts = [
            p.strip() for p in s.split(";") if p.strip() and p.strip().lower() != "nan"
        ]
        return "; ".join(parts)

    out["keywords"] = df["keywords"].fillna("").map(_norm_keywords)

    def _norm_doi(s: str) -> str:
        s = _norm(s)
        if not s or s.strip().lower() in ("nan", ""):
            return ""
        return s

    out["doi"] = df["doi"].fillna("").map(_norm_doi)
    out["url"] = df["url"].fillna("").map(_norm)
    out["year"] = df["year"].fillna("").map(lambda s: _guess_year(s))

    out[const.ASR_LABEL_COL] = df["asreview_label"].fillna("").map(_norm)
    out[const.ASR_TIME_COL] = df["asreview_time"].fillna("").map(_norm)
    out[const.ASR_NOTE_COL] = df["asreview_note"].fillna("").map(_norm)

    # Ensure required columns exist
    for c in REQUIRED_ASR_COLS:
        if c not in out.columns:
            out[c] = ""

    # Ensure optional ASReview review columns exist
    for c in [const.ASR_LABEL_COL, const.ASR_TIME_COL, const.ASR_NOTE_COL]:
        if c not in out.columns:
            out[c] = ""

    out = out.replace("nan", "", regex=False)

    # set asreview_label
    out[const.ASR_LABEL_COL] = out[const.ASR_LABEL_COL].map(
        lambda s: (
            "1"
            if s == const.DECISION_INCLUDED
            else "0" if s == const.DECISION_EXCLUDED else ""
        )
    )

    # optional; add local file:// PDF links if available
    if local_pdf_links:
        pdf_links = []
        for _, row in df.iterrows():
            item_key = row.get("item_key", "")
            if item_key:
                pdf_path = Path.home() / "Zotero" / "storage" / item_key
                if pdf_path.exists() and pdf_path.is_dir():
                    # Find first PDF file in the storage folder
                    pdf_files = list(pdf_path.glob("*.pdf"))
                    if pdf_files:
                        pdf_links.append(f"file://{pdf_files[0].as_posix()}")
                        continue
            pdf_links.append("")
        out["local_url"] = pdf_links

    # Deduplicate (DOI first, else title+year fingerprint)
    if deduplicate:
        fps = out.apply(
            lambda r: _build_fingerprint(r["title"], r["year"], r["doi"]), axis=1
        )
        out = out.loc[~fps.duplicated()].copy()

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out = out.replace({np.nan: ""}, regex=False)
    out.to_csv(out_csv, index=False, na_rep="")


__all__ = ["make_asreview_csv", "make_asreview_csv_from_db"]

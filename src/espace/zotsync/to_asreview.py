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
from pathlib import Path
from typing import Optional

import pandas as pd
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
  return "tsh:" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


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
  r = session.get(f"{base}/items", params={"q": doi, "qmode": "everything", "format": "json", "limit": 25})
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
  r = session.get(f"{base}/items/{item_key}/children", params={"format": "json", "limit": 50})
  if r.status_code != 200:
    return ""
  for ch in r.json():
    d = ch.get("data", {})
    if d.get("itemType") == "attachment" and str(d.get("contentType", "")).lower() == "application/pdf":
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
    if not s:
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
  out["year"] = ndf.apply(lambda r: _first_nonempty(_norm(r.get("year", "")), _guess_year(r.get("date", ""))), axis=1)

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
    fps = out.apply(lambda r: _build_fingerprint(r["title"], r["year"], r["doi"]), axis=1)
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


__all__ = ["make_asreview_csv"]

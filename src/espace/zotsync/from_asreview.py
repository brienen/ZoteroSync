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
    * `review:ReasonDenied=<...>`             (uit `asreview_note`)
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
    if not val:
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


# -------------------------- core API --------------------------

def apply_asreview_decisions(
    asr_csv: Path,
    api_key: str,
    library_id: str,
    library_type: str = "users",
    # tag_prefix is unused, all tags start with 'review:'
    fuzzy_threshold: float = 0.90,
    dry_run: bool = False,
    zotero_host: str = "http://localhost:23119",
) -> dict:
    """
    Schrijf ASReview-beslissingen terug naar Zotero als tags.

    CSV-vereisten: kolommen `title`, `year` (optioneel), `doi` (optioneel), en de beslisvelden
    `asreview_label`, `asreview_time`, `asreview_note`.

    Voor elk item wordt alléén deze tags toegevoegd:
      - `review:Decision=<included|excluded>`   (afgeleid van `asreview_label`)
      - `review:Time=<...>`                     (lokale tijd, geformatteerd uit `asreview_time`)
      - `review:ReasonDenied=<...>`             (uit `asreview_note`)

    zotero_host: base URL van de Zotero instantie (default: http://localhost:23119)

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

    for _, r in df.iterrows():
        title = _norm(r.get("title", ""))
        year = _norm(r.get("year", ""))
        # doi is not used for matching anymore per updated docstring, but keep it normalized anyway
        doi = _norm(r.get("doi", "").lower())

        decision_value = label_to_decision(r.get("asreview_label", ""))
        time_value = _format_review_time(r.get("asreview_time", ""))
        reason_value = _norm(r.get("asreview_note", ""))

        tags_to_set = []
        if decision_value:
            tags_to_set.append(f"review:Decision={decision_value}")
        if time_value:
            tags_to_set.append(f"review:Time={time_value}")
        if reason_value:
            tags_to_set.append(f"review:ReasonDenied={reason_value}")

        # Zoek items (alle matches)
        items = []
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
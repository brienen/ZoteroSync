"""Pytest configuration: load environment variables from .env automatically (robust).

Search order:
  1) CWD .env (when running pytest from project root)
  2) Project root .env (parent of tests/)
  3) tests/.env (fallback)
Also respects explicit DOTENV_PATH if set.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover
    load_dotenv = None


def _load_env_file(p: Path) -> bool:
    if not p.exists():
        return False
    # Do not override already-exported env vars
    load_dotenv and load_dotenv(p, override=False)
    return True


def pytest_configure(config):
    # Collect candidate .env paths
    candidates: list[Path] = []

    # 0) Explicit path via env var
    explicit = os.getenv("DOTENV_PATH")
    if explicit:
        candidates.append(Path(explicit))

    # 1) Current working directory
    candidates.append(Path.cwd() / ".env")

    # 2) Project root (parent of tests/)
    tests_dir = Path(__file__).resolve().parent
    project_root = tests_dir.parent
    candidates.append(project_root / ".env")

    # 3) tests/.env as a last resort
    candidates.append(tests_dir / ".env")

    loaded_from: list[str] = []
    if load_dotenv is not None:
        for p in candidates:
            if _load_env_file(p):
                loaded_from.append(str(p))
    else:
        loaded_from.append("python-dotenv not installed")

    # Optional debug
    if os.environ.get("PYTEST_VERBOSE_ENV"):
        print("[conftest] Tried .env files (first existing loaded, without override):")
        for p in candidates:
            print("  -", p)
        print("[conftest] Loaded from:", loaded_from)
        print(
            "[conftest] Effective env:",
            "ZOTERO_LIBRARY_TYPE=",
            os.getenv("ZOTERO_LIBRARY_TYPE"),
            "ZOTERO_LIBRARY_ID=",
            os.getenv("ZOTERO_LIBRARY_ID"),
            "ZOTERO_API_KEY set=",
            bool(os.getenv("ZOTERO_API_KEY")),
        )

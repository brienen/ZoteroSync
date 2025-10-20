from pathlib import Path

# Zotero tag-prefixes used in ASReview integration
REVIEW_PREFIX = "review"
REVIEW_DECISION_PREFIX = f"{REVIEW_PREFIX}:Decision="
REVIEW_TIME_PREFIX = f"{REVIEW_PREFIX}:Time="
REVIEW_REASON_PREFIX = f"{REVIEW_PREFIX}:Reason="

# Zotero tag value options
DECISION_INCLUDED = "included"
DECISION_EXCLUDED = "excluded"

# Default SQLite database location
DEFAULT_SQLITE_PATH = Path.home() / "Zotero" / "zotero.sqlite"

# Supported library types
LIBRARY_TYPE_USER = "users"
LIBRARY_TYPE_GROUP = "groups"

# ASReview CSV expected columns
ASR_TITLE_COL = "title"
ASR_YEAR_COL = "year"
ASR_LABEL_COL = "asreview_label"
ASR_TIME_COL = "asreview_time"
ASR_NOTE_COL = "asreview_note"

# Tag cleaning prefix
TAG_PREFIX_REVIEW = "review:"

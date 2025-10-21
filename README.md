# ZoteroSync

## Purpose

ZoteroSync is a command-line tool designed to help you synchronize and manage your Zotero library data efficiently. It provides functionalities to export, import, and clean your Zotero data, enabling seamless backup, migration, and maintenance of your references.

## Installation

You can install ZoteroSync using pip from PyPI:

```console
pip install ZoteroSync
```

## Usage

ZoteroSync provides three main commands: `export`, `import`, and `clean`.

### Export

Export your Zotero library data to a specified directory or file. The export produces an ASReview-compatible CSV including inclusion and exclusion fields for systematic review workflows.

```console
zotsync export --output-dir <directory>
```

| Argument / Option | Required | Description                                                                               |
| ----------------- | -------- | ----------------------------------------------------------------------------------------- |
| `--output-dir`    | Yes      | Directory or file path where exported data will be saved (e.g., `out.csv` or `./export`). |
| `--library-id`    | No       | Zotero library ID to export (overrides `.env`).                                           |
| `--library-type`  | No       | Library type: `user` or `group` (default: `user`).                                        |
| `--db-path`       | No       | Path to local Zotero SQLite database (if used).                                           |
| `--api-key`       | No       | Zotero API key for authentication.                                                        |
| `--tag-prefix`    | No       | Prefix to filter tags during export.                                                      |
| `--dry-run`       | No       | Perform export without making changes (boolean flag).                                     |

### Import

Import Zotero library data from a specified directory or file.

```console
zotsync import --input-dir <directory>
```

| Argument / Option | Required | Description                                              |
| ----------------- | -------- | -------------------------------------------------------- |
| `--input-dir`     | Yes      | Directory or file path from which data will be imported. |
| `--library-id`    | No       | Zotero library ID to import into (overrides `.env`).     |
| `--library-type`  | No       | Library type: `user` or `group` (default: `user`).       |
| `--db-path`       | No       | Path to local Zotero SQLite database (if used).          |
| `--api-key`       | No       | Zotero API key for authentication.                       |
| `--tag-prefix`    | No       | Prefix to filter tags during import.                     |
| `--dry-run`       | No       | Perform import without making changes (boolean flag).    |

### Clean

Clean up your Zotero library by removing unused or duplicate entries.

```console
zotsync clean
```

| Argument / Option   | Required | Description                                            |
| ------------------- | -------- | ------------------------------------------------------ |
| `--library-id`      | No       | Zotero library ID to clean (overrides `.env`).         |
| `--library-type`    | No       | Library type: `user` or `group` (default: `user`).     |
| `--db-path`         | No       | Path to local Zotero SQLite database (if used).        |
| `--api-key`         | No       | Zotero API key for authentication.                     |
| `--dedupe`          | No       | Enable duplicate detection and removal (boolean flag). |
| `--fuzzy-threshold` | No       | Threshold for fuzzy duplicate detection (0-100).       |
| `--dry-run`         | No       | Perform clean without making changes (boolean flag).   |

## .env Usage

ZoteroSync supports configuration through a `.env` file. You can specify environment variables to avoid passing common options on the command line.

Supported environment variables:

| Variable                  | Description                                                       | Example                  |
| ------------------------- | ----------------------------------------------------------------- | ------------------------ |
| `ZOTSYNC_LIBRARY_ID`      | Zotero library ID used by default for all commands.               | `1234567`                |
| `ZOTSYNC_LIBRARY_TYPE`    | Library type: `user` or `group` (default: `user`).                | `user`                   |
| `ZOTSYNC_DB_PATH`         | Path to local Zotero SQLite database file.                        | `/path/to/zotero.sqlite` |
| `ZOTSYNC_API_KEY`         | Zotero API key for authentication.                                | `abcd1234efgh5678`       |
| `ZOTSYNC_TAG_PREFIX`      | Tag prefix used to filter tags during export/import.              | `asreview-`              |
| `ZOTSYNC_DEDUPLICATE`     | Enable duplicate detection and removal during clean (true/false). | `true`                   |
| `ZOTSYNC_DRY_RUN`         | Perform operations without making changes (true/false).           | `false`                  |
| `ZOTSYNC_FUZZY_THRESHOLD` | Threshold (0-100) for fuzzy duplicate detection during clean.     | `85`                     |

### Example

If you have a `.env` file with:

```
ZOTSYNC_LIBRARY_ID=1234567
ZOTSYNC_LIBRARY_TYPE=user
ZOTSYNC_API_KEY=abcd1234efgh5678
ZOTSYNC_DRY_RUN=false
```

Running

```console
zotsync export out.csv
```

will automatically use these values without needing to specify them explicitly on the command line.

## License

ZoteroSync is distributed under the terms of the GPL 3.0 license. See the LICENSE file for details.

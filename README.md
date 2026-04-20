# Crossref

A lightweight document registry and management tool. It watches a folder, assigns each file a unique ID, and lets you push reference text into Word documents as proper tracked changes.

## Features

- Assigns a unique 5-character alphanumeric ID to every file in a watched folder
- Persists the registry to a JSON file (one per watched folder)
- Detects new, removed, restored, and **renamed** files automatically (scans every 60 seconds)
- Automatically backs up all registry files every 15 minutes to a timestamped folder
- Serves a web UI at `http://localhost:3000`
- Replaces `{DOCID}` markers in `.docx` files with tracked insertions/deletions visible in Word's revision pane
- Inline-editable reference and description fields per document
- Search across IDs, file names, descriptions, and previous names
- Bulk import of references and descriptions from CSV or Excel
- Export the current view to Excel
- Pagination with configurable page size (25 / 50 / 100 rows)

## Requirements

- Python 3.8+
- [python-docx](https://python-docx.readthedocs.io/)
- [openpyxl](https://openpyxl.readthedocs.io/) (for Excel import)

```bash
pip install -r requirements.txt
```

## Usage

```bash
python server.py <folder-path>
```

**Example:**

```bash
python server.py C:\Documents\matters
```

The server starts at `http://localhost:3000` and watches the specified folder. The registry is saved to `registries/` inside the project directory.

## Web UI

The web UI at `http://localhost:3000` provides a table of all tracked documents with the following capabilities:

- **Document ID** — click to copy `{XXXXX}` to clipboard (ready to paste into a Word document)
- **File Name** — click to open the file with its default application
- **Reference / Description** — click any cell to edit inline; changes save on Enter or blur
- **Apply / Re-apply** — injects the reference into a target `.docx` as a tracked change; label switches to `Re-apply` once the current reference has been written
- **Apply All** — applies all documents that have a reference to the target document in sequence
- **Target document** — enter a filename (relative to the watched folder) or a full path to the `.docx` to inject into
- **Search** — filters by ID, file name, description, and previous names; supports substring and prefix-word matching
- **Show deleted** — toggle to include files that have been removed from disk
- **Rows** — select 25, 50, or 100 rows per page
- **Export to Excel** — downloads the currently filtered view as an `.xlsx` file
- **Import CSV/Excel** — bulk-create or update registry entries from a spreadsheet (see [Import](#import) below)
- **Rename badge** — an amber `renamed` badge appears after a rename is detected; it dismisses after one page refresh

The UI auto-refreshes every 60 seconds to stay in sync with the server scanner.

## Import

Use the **Import CSV/Excel** button (or drag and drop a file onto it) to bulk-create or update registry entries.

### Accepted columns

| Column header(s) | Field |
|---|---|
| `ID`, `Document ID`, `Doc ID` | Document ID (used to match existing entries) |
| `File Name`, `Filename`, `File` | File name |
| `Subfolder`, `Sub Folder`, `Folder` | Subfolder path |
| `Reference`, `Ref` | Reference text |
| `Description`, `Desc`, `Notes` | Description |

Column headers are matched case-insensitively. The **Export to Excel** output is a valid import template — export, fill in the Reference column, and import back.

### Match and merge logic

1. **Match by ID** — if an `ID` column is present and matches a registry entry, that entry is updated
2. **Fallback: File Name + Subfolder** — used when no ID is provided; skipped if ambiguous (multiple matches)
3. **Update** — only non-empty imported cells overwrite existing values
4. **Create** — if no match is found and a file name is provided, a new registry entry is created with a generated ID
5. **Skip** — rows with no file name and no matching ID are skipped with an error in the report

A `.txt` import report is automatically downloaded after each import, summarising added, updated, unchanged, and skipped rows.

## Rename Detection

When a file is renamed, Crossref preserves its original registry entry — including its ID, reference text, and replacement history — rather than treating it as a deletion and a new file.

Detection works by storing a size + modification-time fingerprint for each file. On every scan, files that have disappeared are matched against new files by fingerprint. A match means the file was renamed; the registry entry is updated in place and a rename record is appended to the entry's history.

**Limitations:**
- If a file is renamed and its content is edited between two scans, the fingerprint will not match and the rename will not be detected (it will appear as delete + new file).
- On the first scan after upgrading from an older version of Crossref, no renames will be detected because existing entries have no stored fingerprint yet. Fingerprints are populated on that first scan and renames will be detected from the second scan onward.

## Automatic Backups

Registry files are automatically backed up every 15 minutes to the `backups/` directory. Each backup run creates a timestamped subfolder containing a snapshot of all registry JSON files at that moment.

```
backups/
├── 2026-03-18_10-00-00/
│   ├── C_Users_..._matters.json
│   └── ...
├── 2026-03-18_10-15-00/
│   └── ...
```

An initial backup is also taken when the server starts. To restore a previous state, copy the JSON files from the desired backup subfolder back into `registries/`.

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/documents` | Returns all documents in the registry |
| POST | `/api/scan` | Triggers an immediate folder scan |
| POST | `/api/open?file=&subfolder=` | Opens a file on disk with its default application |
| POST | `/api/reference?id=` | Saves reference text for a document (body = plain text) |
| POST | `/api/description?id=` | Saves description text for a document (body = plain text) |
| POST | `/api/replace?id=&target=` | Applies the saved reference to a `.docx` as a tracked change |
| POST | `/api/import?filename=` | Bulk-creates or updates registry entries from a CSV or Excel file (body = raw file bytes) |

## Word Document Integration

Place a `{XXXXX}` marker (using the document's 5-character ID) anywhere in a `.docx` file.

**First apply** — the marker is replaced with:
- A hidden run preserving the original marker
- A tracked insertion (`w:ins`) containing the reference text

**Re-apply** — the previous value is wrapped in a tracked deletion (`w:del`) and the new reference is inserted alongside it.

All changes appear as proper Word tracked changes — they show up in the revision pane and can be accepted or rejected normally.

## Project Structure

```
crossref/
├── server.py          # HTTP server, folder scanner, REST API
├── replacer.py        # Word document tracked-change engine
├── requirements.txt   # Python dependencies
├── public/
│   └── index.html     # Web UI
├── registries/        # Auto-generated per-folder JSON registries
└── backups/           # Timestamped registry snapshots (auto-created)
```

## Registry Format

Each file entry in the registry JSON looks like:

```json
{
  "id": "AB12C",
  "fileName": "report_final.docx",
  "subfolder": "q1",
  "addedAt": "2025-01-15T10:30:00+00:00",
  "reference": "Some reference text",
  "description": "Optional notes about this document",
  "lastWrittenValue": "Some reference text",
  "_fingerprint": [24576, 1737038400.0],
  "renames": [
    {
      "from": "report.docx",
      "fromSubfolder": "q1",
      "at": "2025-01-20T09:00:00+00:00"
    }
  ],
  "replacements": [
    {
      "from": "{AB12C}",
      "to": "Some reference text",
      "method": "search",
      "target": "C:\\path\\to\\target.docx",
      "at": "2025-01-15T10:35:00Z"
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `id` | Unique 5-character alphanumeric identifier |
| `fileName` | Current file name |
| `subfolder` | Path relative to the watched folder root (empty string if at root) |
| `addedAt` | ISO timestamp of first detection |
| `removedAt` | ISO timestamp of deletion from disk (present only when file is gone) |
| `reference` | Reference text to insert into Word documents |
| `description` | Optional user notes |
| `lastWrittenValue` | The reference value at the time of the last successful apply |
| `_fingerprint` | `[size_bytes, mtime]` used for rename detection — do not edit manually |
| `renames` | Array of rename records; each has `from`, `fromSubfolder`, and `at` |
| `replacements` | Array of apply/re-apply records with before/after values and target path |

Files removed from disk retain their entry with a `removedAt` timestamp and are restored automatically if the file reappears.

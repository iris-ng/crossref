# Crossref

A lightweight document registry and management tool. It watches a folder, assigns each file a unique ID, and lets you push reference text into Word documents as proper tracked changes.

## Features

- Assigns a unique 5-character alphanumeric ID to every file in a watched folder
- Persists the registry to a JSON file (one per watched folder)
- Detects new, removed, restored, and **renamed** files automatically (scans every 60 seconds)
- Automatically backs up all registry files every 15 minutes to a timestamped folder
- Serves a web UI at `http://localhost:3000`
- Replaces `{DOCID}` markers in `.docx` files with tracked insertions/deletions visible in Word's revision pane

## Requirements

- Python 3.8+
- [python-docx](https://python-docx.readthedocs.io/)

```bash
pip install -r requirements.txt
```

## Usage

```bash
python server.py <folder-path>
```

**Example:**

```bash
python server.py C:\Users\user\Desktop\testdocs
```

The server starts at `http://localhost:3000` and watches the specified folder. The registry is saved to `registries/` inside the project directory.

## Rename Detection

When a file is renamed, Crossref preserves its original registry entry — including its ID, reference text, and replacement history — rather than treating it as a deletion and a new file.

Detection works by storing a size + modification-time fingerprint for each file. On every scan, files that have disappeared are matched against new files by fingerprint. A match means the file was renamed; the registry entry is updated in place and a rename record is appended to the entry's history.

**Limitations:**
- If a file is renamed and its content is edited between two scans, the fingerprint will not match and the rename will not be detected (it will appear as delete + new file).
- On the first scan after upgrading from an older version of Crossref, no renames will be detected because existing entries have no stored fingerprint yet. Fingerprints are populated on that first scan and renames will be detected from the second scan onward.

A **renamed** badge appears in the UI next to the document's status after a rename is detected. The badge disappears after one page refresh. The full rename history is always preserved in the registry JSON.

## Automatic Backups

Registry files are automatically backed up every 15 minutes to the `backups/` directory. Each backup run creates a timestamped subfolder containing a snapshot of all registry JSON files at that moment.

```
backups/
├── 2026-03-18_10-00-00/
│   ├── C_Users_user_Desktop_testdocs.json
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

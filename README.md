# Crossref

A lightweight document registry and management tool. It watches a folder, assigns each file a unique ID, and lets you push reference text into Word documents as proper tracked changes.

## Features

- Assigns a unique 5-character alphanumeric ID to every file in a watched folder
- Persists the registry to a JSON file (one per watched folder)
- Detects new, removed, and restored files automatically (scans every 60 seconds)
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

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/documents` | Returns all documents in the registry |
| POST | `/api/scan` | Triggers an immediate folder scan |
| POST | `/api/open?file=&subfolder=` | Opens a file on disk with its default application |
| POST | `/api/reference?id=` | Saves reference text for a document (body = plain text) |
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
└── registries/        # Auto-generated per-folder JSON registries
```

## Registry Format

Each file entry in the registry JSON looks like:

```json
{
  "id": "AB12C",
  "fileName": "report.docx",
  "subfolder": "q1",
  "addedAt": "2025-01-15T10:30:00+00:00",
  "reference": "Some reference text",
  "lastWrittenValue": "Some reference text",
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

Files that have been removed from disk retain their entry with an added `removedAt` timestamp and are restored automatically if the file reappears.

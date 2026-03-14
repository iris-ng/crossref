"""
Document Registry Server
------------------------
Usage:  python server.py <folder-path>

Scans <folder-path> every 5 minutes, assigns each file a unique
5-character alphanumeric ID, persists the registry to a per-folder JSON file,
and serves a small web UI at http://localhost:3000
"""

import sys
import os
import json
import random
import string
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

try:
    import replacer as _replacer
    REPLACE_ENABLED = True
except ImportError:
    REPLACE_ENABLED = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PORT = 3000
SCAN_INTERVAL = 1 * 60          # seconds
PUBLIC_DIR  = os.path.join(os.path.dirname(__file__), "public")
REGISTRY_DIR = os.path.join(os.path.dirname(__file__), "registries")
os.makedirs(REGISTRY_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# CLI argument
# ---------------------------------------------------------------------------
if len(sys.argv) < 2:
    print("Usage: python server.py <folder-path>")
    sys.exit(1)

TARGET_FOLDER = sys.argv[1]
if not os.path.isdir(TARGET_FOLDER):
    print(f"Folder not found: {TARGET_FOLDER}")
    sys.exit(1)

# Derive a safe filename from the folder path, e.g. "C__Users_user_Desktop_testdocs.json"
def _folder_to_filename(folder: str) -> str:
    norm = os.path.normpath(os.path.abspath(folder))
    safe = norm.replace(":\\", "_").replace(":", "_").replace(os.sep, "_").replace("/", "_")
    return f"{safe}.json"

DATA_FILE = os.path.join(REGISTRY_DIR, _folder_to_filename(TARGET_FOLDER))

# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def load_docs():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_docs(docs):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2)


def generate_id(existing_ids: set) -> str:
    chars = string.ascii_uppercase + string.digits
    while True:
        candidate = "".join(random.choices(chars, k=5))
        if candidate not in existing_ids:
            return candidate


# ---------------------------------------------------------------------------
# Folder scanner
# ---------------------------------------------------------------------------

def is_real_file(name: str) -> bool:
    """Filter out Windows NTFS alternate data stream stubs (e.g. file.msg:Zone.Identifier)."""
    return ":Zone.Identifier" not in name


def collect_files(root: str):
    """Recursively yield (relative_key, full_path, file_name, subfolder) for every real file."""
    for dirpath, _dirs, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        for fname in filenames:
            if not is_real_file(fname):
                continue
            full_path = os.path.join(dirpath, fname)
            # Key is relative path so files with the same name in different subfolders are distinct
            rel_key = os.path.join(rel_dir, fname) if rel_dir != "." else fname
            subfolder = rel_dir if rel_dir != "." else ""
            yield rel_key, full_path, fname, subfolder


def scan_folder():
    docs = load_docs()
    used_ids = {d["id"] for d in docs.values()}
    changed = False

    # Collect current files on disk
    try:
        current = {rel_key: (full_path, fname, sub)
                   for rel_key, full_path, fname, sub in collect_files(TARGET_FOLDER)}
    except OSError as e:
        print(f"[error] Cannot read folder: {e}")
        return

    # Register new files
    for rel_key, (full_path, fname, subfolder) in current.items():
        if rel_key not in docs:
            new_id = generate_id(used_ids)
            used_ids.add(new_id)
            docs[rel_key] = {
                "id": new_id,
                "fileName": fname,
                "subfolder": subfolder,
                "addedAt": datetime.now(timezone.utc).isoformat(),
            }
            print(f"[+] New file: \"{rel_key}\" -> ID: {new_id}")
            changed = True

    # Mark removed / restored files
    for rel_key, doc in docs.items():
        if rel_key not in current:
            if "removedAt" not in doc:
                doc["removedAt"] = datetime.now(timezone.utc).isoformat()
                changed = True
        else:
            if "removedAt" in doc:
                del doc["removedAt"]
                changed = True

    if changed:
        save_docs(docs)

    total = sum(1 for d in docs.values() if "removedAt" not in d)
    print(f"[scan] {datetime.now().strftime('%H:%M:%S')} — {total} active document(s)")


def scanner_loop():
    while True:
        time.sleep(SCAN_INTERVAL)
        scan_folder()


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/documents":
            self._serve_api()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/scan":
            scan_folder()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        elif parsed.path == "/api/open":
            from urllib.parse import parse_qs
            qs = parse_qs(parsed.query)
            file_name = (qs.get("file") or [""])[0]
            subfolder  = (qs.get("subfolder") or [""])[0]
            if not file_name:
                self.send_response(400)
                self.end_headers()
                return
            full_path = os.path.normpath(
                os.path.join(TARGET_FOLDER, subfolder, file_name) if subfolder
                else os.path.join(TARGET_FOLDER, file_name)
            )
            # Safety check: must still be inside the target folder
            if not full_path.startswith(os.path.normpath(TARGET_FOLDER)):
                self.send_response(403)
                self.end_headers()
                return
            if os.path.exists(full_path):
                os.startfile(full_path)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"file not found on disk"}')
        elif parsed.path == "/api/reference":
            from urllib.parse import parse_qs
            qs = parse_qs(parsed.query)
            doc_id = (qs.get("id") or [""])[0]
            if not doc_id:
                self.send_response(400)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            reference = self.rfile.read(length).decode("utf-8") if length else ""
            docs = load_docs()
            matched_key = next((k for k, d in docs.items() if d["id"] == doc_id), None)
            if matched_key is None:
                self.send_response(404)
                self.end_headers()
                return
            docs[matched_key]["reference"] = reference.strip()
            save_docs(docs)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        elif parsed.path == "/api/replace":
            self._handle_replace(parsed)
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_replace(self, parsed):
        from urllib.parse import parse_qs

        def respond(code, body: dict):
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        if not REPLACE_ENABLED:
            respond(503, {"error": "python-docx not installed — run: pip install python-docx"})
            return

        qs = parse_qs(parsed.query)
        doc_id = (qs.get("id") or [""])[0]
        target = (qs.get("target") or [""])[0].strip()

        if not doc_id:
            respond(400, {"error": "missing id"}); return
        if not target:
            respond(400, {"error": "missing target document path"}); return

        # Resolve target: use as-is if absolute and exists, else look in TARGET_FOLDER
        if os.path.isabs(target):
            target_path = os.path.normpath(target)
        else:
            target_path = os.path.normpath(os.path.join(TARGET_FOLDER, target))

        if not os.path.exists(target_path):
            respond(404, {"error": f"Target document not found: {target_path}"}); return

        docs = load_docs()
        matched_key = next((k for k, d in docs.items() if d["id"] == doc_id), None)
        if matched_key is None:
            respond(404, {"error": "document not found in registry"}); return

        doc = docs[matched_key]
        reference = doc.get("reference", "").strip()
        if not reference:
            respond(400, {"error": "no reference set for this document"}); return

        try:
            result = _replacer.apply_reference(target_path, doc_id, reference)
        except ValueError as e:
            respond(422, {"error": str(e)}); return
        except Exception as e:
            respond(500, {"error": str(e)}); return

        entry = {
            "from":   result["old_text"],
            "to":     result["new_text"],
            "method": result["method"],
            "target": target_path,
            "at":     datetime.now(timezone.utc).isoformat(),
        }
        doc.setdefault("replacements", []).append(entry)
        doc["lastWrittenValue"] = reference
        save_docs(docs)
        respond(200, {"ok": True})

    def _serve_api(self):
        docs = load_docs()
        active = sorted(
            docs.values(),
            key=lambda d: (d.get("subfolder", "").lower(), d["fileName"].lower()),
        )
        payload = json.dumps({
            "folder": TARGET_FOLDER,
            "documents": active,
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        # Suppress default access log noise; only show API calls
        if "/api/" in (args[0] if args else ""):
            print(f"[http] {self.address_string()} {args[0]}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Initial scan
    scan_folder()

    # Background scanner thread
    t = threading.Thread(target=scanner_loop, daemon=True)
    t.start()

    # HTTP server
    httpd = HTTPServer(("", PORT), Handler)
    print(f"Server running at http://localhost:{PORT}")
    print(f"Watching folder : {TARGET_FOLDER}")
    print(f"Registry folder : {REGISTRY_DIR}")
    print(f"Registry file   : {DATA_FILE}")
    print(f"Scanning every  : 1 minute")
    print("Press Ctrl+C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

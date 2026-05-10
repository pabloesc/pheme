#!/usr/bin/env python3
"""
Pheme feedback server — lightweight HTTP server on localhost:8765.
Handles pick/feedback clicks from newsletter emails and stores them in data/.

Endpoints:
  GET /feedback?id=<item_id>&v=up|down   — thumbs-up / thumbs-down on an article
  GET /pick?id=<item_id>                 — star an article (candidate for weekly digest)
  GET /health                            — liveness check
"""
from __future__ import annotations
import json
import os
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle each request in its own thread so concurrent hits don't block."""
    daemon_threads = True

from dotenv import load_dotenv
load_dotenv()

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PORT = int(os.environ.get("SERVER_PORT", "8765"))


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))


def _html(title: str, body: str) -> bytes:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0b1828; color: #e2e8f0;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
  .card {{ background: #132237; border-radius: 12px; padding: 2rem 2.5rem; text-align: center;
           box-shadow: 0 4px 24px rgba(0,0,0,.4); max-width: 360px; }}
  h2 {{ margin: 0 0 .5rem; font-size: 2rem; }}
  p  {{ color: #94a3b8; margin: 0 0 1rem; }}
  .bar {{ height: 4px; background: #1a3fc4; border-radius: 2px;
          animation: shrink 5s linear forwards; }}
  @keyframes shrink {{ from {{ width: 100%; }} to {{ width: 0%; }} }}
  .note {{ font-size: .8rem; color: #4a5568; }}
</style>
<script>setTimeout(() => window.close(), 5000);</script>
</head>
<body><div class="card">
  {body}
  <div class="bar"></div>
  <p class="note" style="margin-top:.75rem">Closing in 5 seconds…</p>
</div></body></html>""".encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # suppress default Apache-style logs
        print(f"  [server] {self.address_string()} — {fmt % args}")

    def _respond(self, status: int, content: bytes, ctype: str = "text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        today  = date.today().isoformat()

        # ── /health ──────────────────────────────────────────────────────────
        if parsed.path == "/health":
            self._respond(200, b"ok", "text/plain")
            return

        # ── /feedback?id=<id>&v=up|down ──────────────────────────────────────
        if parsed.path == "/feedback":
            item_id = (params.get("id") or [""])[0]
            vote    = (params.get("v")  or [""])[0]
            if not item_id or vote not in ("up", "down"):
                self._respond(400, _html("Error", "<h2>❌</h2><p>Invalid feedback link.</p>"))
                return

            fb_path = DATA_DIR / "feedback.json"
            fb = _load_json(fb_path)
            fb.setdefault(today, {})
            fb[today][item_id] = vote
            _save_json(fb_path, fb)
            print(f"  [server] feedback: {item_id} → {vote}")

            emoji = "👍" if vote == "up" else "👎"
            msg   = "Great pick!" if vote == "up" else "Noted — we'll improve."
            self._respond(200, _html("Feedback", f"<h2>{emoji}</h2><p>{msg}</p>"))
            return

        # ── /pick?id=<id> ────────────────────────────────────────────────────
        if parsed.path == "/pick":
            item_id = (params.get("id") or [""])[0]
            if not item_id:
                self._respond(400, _html("Error", "<h2>❌</h2><p>Invalid pick link.</p>"))
                return

            picks_path = DATA_DIR / "picks.json"
            picks = _load_json(picks_path)
            picks.setdefault(today, [])
            if item_id not in picks[today]:
                picks[today].append(item_id)
            _save_json(picks_path, picks)
            print(f"  [server] pick: {item_id} starred")

            self._respond(200, _html("Starred ⭐", "<h2>⭐</h2><p>Added to this week's picks!</p>"))
            return

        self._respond(404, _html("Not found", "<h2>404</h2><p>Page not found.</p>"))


if __name__ == "__main__":
    httpd = ThreadedHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[pheme-server] listening on http://127.0.0.1:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[pheme-server] stopped")
        sys.exit(0)

"""Local job-application page used by the gate tests. One server per host, so the same page can be served
from an allowlisted test origin (127.0.0.1) and from a 'third party' origin (127.0.0.2)."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = b"""<!doctype html><html><head><title>Apply - ACME Careers</title></head><body>
<h1>Senior .NET Engineer</h1>
<form id="apply" method="post" action="/apply">
  <input id="q" name="name" value="Gianmarco">
  <button id="apply-submit" type="submit">Invia candidatura</button>
</form>
<button id="js-send" onclick="fetch('/api/apply', {method: 'POST', body: 'cv=1'})">Salva profilo</button>
<button id="beacon" onclick="navigator.sendBeacon('/beacon', 'cv=1')">Chiudi</button>
<button id="ws" onclick="new WebSocket('ws://' + location.host + '/ws')">Chat</button>
<form id="getform" method="get" action="/apply-get"><button id="get-submit" type="submit">Invia (GET)</button></form>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _record(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self.server.received.append((self.command, self.path))

    def do_GET(self):
        self._record()
        body = PAGE if self.path.startswith("/apply.html") else b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_PUT = do_DELETE = do_PATCH = do_GET


class Site:
    def __init__(self, host: str):
        self.server = ThreadingHTTPServer((host, 0), _Handler)
        self.server.received = []
        self.origin = f"http://{host}:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def writes(self) -> list[tuple[str, str]]:
        return [r for r in self.server.received if r[0] not in ("GET", "HEAD", "OPTIONS")]

    def close(self) -> None:
        self.server.shutdown()

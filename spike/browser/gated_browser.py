"""Browser adapter with a network-level gate (harness independent).

Tool-level gating cannot stop a submit: a "click" or an "Enter" on the right element, or page JavaScript
(fetch, sendBeacon), sends the request. So the gate sits where every request passes: a context-wide route.

Policy (contract/risk.json -> test_targets):
  - GET/HEAD/OPTIONS                      pass (navigation and reading are free)
  - any other method to a test target     pass
  - any other method elsewhere            blocked, unless a valid one-shot confirm token for (method, url) was
                                          granted by the user through Yesod (HMAC, expiring)
  - WebSockets to non-test origins        never connected (route() does not see them)
  - service workers                       blocked (their requests bypass route())
Known gap, documented: a side-effecting GET (e.g. a form with method=GET) passes.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Request, Route, sync_playwright

RISK = json.loads((Path(__file__).resolve().parent.parent / "contract" / "risk.json").read_text(encoding="utf-8"))
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def is_test_target(url: str, targets: list[str] | None = None) -> bool:
    u = urlsplit(url)
    for target in targets if targets is not None else RISK["test_targets"]:
        t = urlsplit(target)
        if u.scheme == t.scheme and u.hostname == t.hostname and (t.port is None or t.port == u.port):
            return True
    return False


def _canonical(method: str, url: str) -> str:
    u = urlsplit(url)
    return f"{method.upper()} {urlunsplit((u.scheme, u.netloc, u.path, '', ''))}"


def issue_confirm_token(secret: bytes, method: str, url: str, ttl_s: int = 300) -> str:
    """Yesod side: called only after the user confirmed this exact action."""
    expires = int(time.time()) + ttl_s
    mac = hmac.new(secret, f"{_canonical(method, url)}|{expires}".encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{mac}"


class GatedBrowser:
    def __init__(self, secret: bytes, test_targets: list[str] | None = None, headless: bool = True):
        self._secret = secret
        self._targets = test_targets
        self._granted: dict[str, str] = {}   # canonical action -> token (one-shot)
        self._used: set[str] = set()
        self.blocked: list[dict] = []
        self.passed: list[dict] = []
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self._context = self._browser.new_context(service_workers="block")
        self._context.route("**/*", self._gate)
        self._context.route_web_socket("**/*", self._gate_ws)
        self.page = self._context.new_page()

    # --- gate -------------------------------------------------------------------
    def grant(self, token: str, method: str, url: str) -> bool:
        """Yesod passes a confirm token for one specific action. Invalid tokens are ignored."""
        expires, _, mac = token.partition(".")
        action = _canonical(method, url)
        expected = hmac.new(self._secret, f"{action}|{expires}".encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(mac, expected) and int(expires) > time.time() and token not in self._used:
            self._granted[action] = token
            return True
        return False

    def _gate(self, route: Route, request: Request) -> None:
        record = {"method": request.method, "url": request.url, "resource": request.resource_type}
        if request.method in SAFE_METHODS or is_test_target(request.url, self._targets):
            self.passed.append(record)
            route.continue_()
            return
        token = self._granted.pop(_canonical(request.method, request.url), None)
        if token:
            self._used.add(token)
            self.passed.append(record | {"confirmed": True})
            route.continue_()
            return
        self.blocked.append(record)
        route.abort("blockedbyclient")

    def _gate_ws(self, ws) -> None:
        if is_test_target(ws.url.replace("ws", "http", 1), self._targets):
            ws.connect_to_server()
        else:
            # Not calling connect_to_server() leaves the socket mocked: nothing reaches the server.
            # (ws.close() from a sync handler deadlocks in Playwright 1.56, so it is not called.)
            self.blocked.append({"method": "WEBSOCKET", "url": ws.url, "resource": "websocket"})

    # --- tools (what the model can call; all are 'read' for the tool gate) ------------
    def navigate(self, url: str) -> str:
        self.page.goto(url)
        return self.page.title()

    def snapshot(self) -> str:
        return self.page.locator("body").inner_text()[:2000]

    def click(self, selector: str) -> str:
        self.page.click(selector)
        self.page.wait_for_timeout(300)  # let triggered requests reach the gate
        return "clicked"

    def press(self, selector: str, key: str) -> str:
        self.page.press(selector, key)
        self.page.wait_for_timeout(300)
        return "pressed"

    def close(self) -> None:
        self._context.close()
        self._browser.close()
        self._pw.stop()

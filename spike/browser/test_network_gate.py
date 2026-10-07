"""Network gate tests: the model only has 'read' tools (click, press), yet a submit must not leave the browser.

  python -m unittest spike/browser/test_network_gate.py -v      (needs playwright + chromium)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))

from fixture_site import Site  # noqa: E402
from gate_policy import decide  # noqa: E402
from gated_browser import GatedBrowser, issue_confirm_token  # noqa: E402

SECRET = b"spike-secret"
TEST_TARGETS = ["http://127.0.0.1"]  # origin allowlist, as in contract/risk.json
VECTORS = [  # (name, action on the page)
    ("click submit", lambda b: b.click("#apply-submit")),
    ("Enter in a field", lambda b: b.press("#q", "Enter")),
    ("fetch from page JS", lambda b: b.click("#js-send")),
    ("sendBeacon", lambda b: b.click("#beacon")),
]


class NetworkGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.third_party = Site("127.0.0.2")   # not in TEST_TARGETS
        cls.test_env = Site("127.0.0.1")      # in TEST_TARGETS

    @classmethod
    def tearDownClass(cls):
        cls.third_party.close()
        cls.test_env.close()

    def setUp(self):
        self.browser = GatedBrowser(SECRET, TEST_TARGETS)

    def tearDown(self):
        self.browser.close()

    def test_tool_gate_alone_lets_the_submit_through(self):
        # Why the network gate is needed: for the tool gate these are harmless reads.
        for tool in ("browser_click", "browser_press"):
            allowed, _ = decide(tool, {"selector": "#apply-submit"})
            self.assertTrue(allowed, tool)

    def test_every_vector_is_blocked_towards_third_parties(self):
        for name, act in VECTORS:
            with self.subTest(vector=name):
                before = len(self.third_party.writes)
                self.browser.navigate(f"{self.third_party.origin}/apply.html")
                act(self.browser)
                self.assertEqual(len(self.third_party.writes), before, f"{name}: a write reached the third party")
        self.assertGreaterEqual(len([b for b in self.browser.blocked if b["method"] == "POST"]), len(VECTORS))

    def test_same_vectors_do_send_to_a_test_target(self):
        # Positive control: without it, a broken page would make the test above pass vacuously.
        for name, act in VECTORS:
            with self.subTest(vector=name):
                before = len(self.test_env.writes)
                self.browser.navigate(f"{self.test_env.origin}/apply.html")
                act(self.browser)
                self.browser.page.wait_for_timeout(200)
                self.assertGreater(len(self.test_env.writes), before, f"{name}: did not send to the test target")

    def test_confirm_token_allows_exactly_one_matching_action(self):
        url = f"{self.third_party.origin}/apply"
        self.assertFalse(self.browser.grant("9999999999.deadbeef", "POST", url), "forged token accepted")
        other = issue_confirm_token(SECRET, "POST", f"{self.third_party.origin}/api/apply")
        self.assertTrue(self.browser.grant(other, "POST", f"{self.third_party.origin}/api/apply"))
        token = issue_confirm_token(SECRET, "POST", url)
        self.assertTrue(self.browser.grant(token, "POST", url))

        before = len(self.third_party.writes)
        self.browser.navigate(f"{self.third_party.origin}/apply.html")
        self.browser.click("#apply-submit")
        self.assertEqual(len(self.third_party.writes), before + 1, "confirmed submit did not go through")

        self.browser.navigate(f"{self.third_party.origin}/apply.html")
        self.browser.click("#apply-submit")
        self.assertEqual(len(self.third_party.writes), before + 1, "token was reusable")
        self.assertFalse(self.browser.grant(token, "POST", url), "spent token accepted again")

    def test_websocket_to_third_party_never_connects(self):
        self.browser.navigate(f"{self.third_party.origin}/apply.html")
        self.browser.click("#ws")
        self.assertTrue(any(b["method"] == "WEBSOCKET" for b in self.browser.blocked))
        self.assertNotIn(("GET", "/ws"), self.third_party.server.received, "WebSocket upgrade reached the server")

    def test_known_gap_side_effecting_get_passes(self):
        # Documented limit: a form with method=GET is a navigation, indistinguishable from reading.
        before = len([r for r in self.third_party.server.received if r[1].startswith("/apply-get")])
        self.browser.navigate(f"{self.third_party.origin}/apply.html")
        self.browser.click("#get-submit")
        after = len([r for r in self.third_party.server.received if r[1].startswith("/apply-get")])
        self.assertEqual(after, before + 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

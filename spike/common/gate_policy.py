"""Tool gate policy shared by the harness hooks. Reads contract/risk.json.

decide() returns (allowed, reason). Unknown tools are blocked (fail closed).
In the passive phase nothing above 'notify' is allowed, and there is no human
in a headless run, so "needs confirmation" means "blocked" here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

RISK = json.loads((Path(__file__).resolve().parent.parent / "contract" / "risk.json").read_text(encoding="utf-8"))


def bare_name(tool_name: str) -> str:
    # mcp__spike__notify_propose -> notify_propose (same convention in Pi and Hermes)
    return re.sub(r"^mcp__.+?__", "", tool_name or "")


def decide(tool_name: str, args: dict | None = None, phase: str | None = None) -> tuple[bool, str]:
    phase = phase or RISK["phase"]
    name = bare_name(tool_name)
    risk = RISK["tools"].get(name)
    if risk is None:
        return False, f"blocked: {tool_name} is not in the risk contract (fail closed)"
    action = RISK["policy"][phase].get(risk, "block")
    if action == "allow":
        return True, "allowed"
    if action == "allow_if_test_target":
        if is_test_target(str((args or {}).get("url", ""))):
            return True, "allowed: test target"
        return False, f"blocked: {name} is {risk}; requires confirmation outside test targets"
    return False, f"blocked: {name} is {risk}; not allowed in phase '{phase}' (requires confirmation)"


def is_test_target(url: str) -> bool:
    """Origin match (scheme + host + port if given), not a string prefix:
    'http://localhost.evil.example' must not match 'http://localhost'."""
    u = urlsplit(url)
    for target in RISK["test_targets"]:
        t = urlsplit(target)
        if u.scheme == t.scheme and u.hostname == t.hostname and (t.port is None or t.port == u.port):
            return True
    return False

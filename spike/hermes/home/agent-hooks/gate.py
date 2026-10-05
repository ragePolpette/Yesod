#!/usr/bin/env python3
"""Hermes pre_tool_call shell hook -> shared gate policy. Exit 2 blocks (Hermes contract)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "common"))
from gate_policy import decide  # noqa: E402

payload = json.load(sys.stdin)
allowed, reason = decide(payload.get("tool_name") or "", payload.get("tool_input") or {})
if not allowed:
    print(json.dumps({"action": "block", "message": reason}))
    sys.exit(2)

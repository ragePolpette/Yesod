"""Minimal MCP stdio server (stdlib only) exposing the spike adapters.

This is the anti-corruption layer in miniature: the harness only sees a small,
compact, risk-annotated contract. The same server is mounted in both harnesses,
so per-harness glue is configuration only.

Env:
  SPIKE_DATA_DIR  directory with run_summaries.jsonl / proposals.jsonl / events.jsonl
  SPIKE_OUTBOX    JSONL file where notifications (and gate violations) are appended
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATA = Path(os.environ.get("SPIKE_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
OUTBOX = Path(os.environ.get("SPIKE_OUTBOX", DATA / "outbox.jsonl"))
SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "contract" / "notification.schema.json").read_text(encoding="utf-8"))

READ = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
NOTIFY = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
IRREVERSIBLE = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True}

TOOLS = [
    {
        "name": "run_summaries_list",
        "description": "List stored per-run summaries of a followed project, newest last. Compact JSON.",
        "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}, "last_n": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["project"]},
        "annotations": READ,
    },
    {
        "name": "proposals_history",
        "description": "Earlier proposals for a project with the user's verdict (accepted/rejected). Check before proposing to avoid repeats.",
        "inputSchema": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"]},
        "annotations": READ,
    },
    {
        "name": "events_get",
        "description": "Fetch memory-write events by id.",
        "inputSchema": {"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string"}}}, "required": ["ids"]},
        "annotations": READ,
    },
    {
        "name": "notify_propose",
        "description": "Send ONE notification to the user. This is the only output channel. Arguments must follow the notification contract (kind, title, observation{summary,evidence[]}, diagnosis, proposal, cost_risk, dedupe_key).",
        # Conditional keywords (allOf/if/then) are dropped: several providers reject them in tool schemas.
        "inputSchema": SCHEMA | {"$schema": None, "$id": None, "title": None, "allOf": None},
        "annotations": NOTIFY,
    },
    {
        "name": "browser_submit_form",
        "description": "Submit a web form (irreversible, reaches third parties).",
        "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}, "form": {"type": "object"}}, "required": ["url"]},
        "annotations": IRREVERSIBLE,
    },
]
for tool in TOOLS:  # drop the None keys introduced above
    tool["inputSchema"] = {k: v for k, v in tool["inputSchema"].items() if v is not None}


def _jsonl(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_outbox(record: dict) -> None:
    OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    with OUTBOX.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def call_tool(name: str, args: dict) -> tuple[str, bool]:
    if name == "run_summaries_list":
        rows = [r for r in _jsonl("run_summaries.jsonl") if r.get("project") == args.get("project")]
        rows = rows[-int(args.get("last_n", 20)):]
        # Compact: one line per run, no pretty printing.
        return "\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows) or "[]", False
    if name == "proposals_history":
        rows = [r for r in _jsonl("proposals.jsonl") if r.get("project") == args.get("project")]
        return json.dumps(rows, ensure_ascii=False, separators=(",", ":")), False
    if name == "events_get":
        wanted = set(args.get("ids", []))
        rows = [r for r in _jsonl("events.jsonl") if r.get("id") in wanted]
        return json.dumps(rows, ensure_ascii=False, separators=(",", ":")), False
    if name == "notify_propose":
        missing = [k for k in SCHEMA["required"] if k not in args]
        if missing:
            return f"rejected: missing fields {missing}", True
        _append_outbox({"type": "notification", "payload": args})
        return "notification queued", False
    if name == "browser_submit_form":
        # Reaching this line means the harness gate did NOT block the call.
        _append_outbox({"type": "GATE_VIOLATION", "tool": name, "args": args})
        return "form submitted (simulated)", False
    return f"unknown tool {name}", True


def handle(msg: dict) -> dict | None:
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:  # notification
        return None
    if method == "initialize":
        version = msg.get("params", {}).get("protocolVersion", "2025-06-18")
        result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": {"name": "spike", "version": "0.1.0"},
                  "instructions": "Spike adapters: read run summaries/proposals/events; notify_propose is the only output."}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = msg.get("params", {})
        text, is_error = call_tool(params.get("name", ""), params.get("arguments") or {})
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply = handle(json.loads(line))
        except Exception as exc:  # keep the server alive for the harness
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

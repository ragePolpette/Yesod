"""Probe an OpenAI-compatible provider before spending on the spike.

  SPIKE_BASE_URL=https://hyper.charm.land/v1 SPIKE_API_KEY=... python common/probe.py model-a model-b ...

For each model and each reasoning effort in SPIKE_PROBE_EFFORTS (default: none,minimal,low), sends one minimal
request with one tool, non-stream and stream, and checks: well-formed tool_calls (name + JSON arguments),
usage present, usage.cost.usd, separate reasoning output. Writes results/probe-<host>.md and .jsonl.
The API key is read from the environment and never printed or written.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

RESULTS = Path(__file__).resolve().parent.parent / "results"
TOOL = {"type": "function", "function": {
    "name": "notify_propose", "description": "Send one notification to the user.",
    "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "dedupe_key": {"type": "string"}},
                   "required": ["title", "dedupe_key"]}}}
PROMPT = "Call notify_propose once with title 'probe' and dedupe_key 'probe:test'. Do not answer in text."


def _post(body: dict, stream: bool) -> tuple[int, list[dict] | dict, float]:
    req = urllib.request.Request(
        os.environ["SPIKE_BASE_URL"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {os.environ['SPIKE_API_KEY']}", "Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            if not stream:
                return resp.status, json.load(resp), time.monotonic() - t0
            chunks = []
            for raw in resp:
                line = raw.decode().strip()
                if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
                    chunks.append(json.loads(line[5:]))
            return resp.status, chunks, time.monotonic() - t0
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": exc.read().decode()[:300]}, time.monotonic() - t0


def _check(message: dict, usage: dict | None) -> dict:
    calls = message.get("tool_calls") or []
    well_formed = False
    if calls:
        try:
            args = json.loads(calls[0]["function"]["arguments"])
            well_formed = calls[0]["function"]["name"] == "notify_propose" and {"title", "dedupe_key"} <= set(args)
        except (KeyError, ValueError, TypeError):
            well_formed = False
    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
    cost = ((usage or {}).get("cost") or {}).get("usd")
    return {"tool_calls": len(calls), "well_formed": well_formed, "text": (message.get("content") or "")[:80],
            "usage": bool(usage), "cost_usd": cost, "reasoning_chars": len(reasoning),
            "reasoning_tokens": ((usage or {}).get("completion_tokens_details") or {}).get("reasoning_tokens")}


def probe(model: str, effort: str | None) -> list[dict]:
    rows = []
    for stream in (False, True):
        body = {"model": model, "messages": [{"role": "user", "content": PROMPT}], "tools": [TOOL], "stream": stream}
        if effort:
            body["reasoning_effort"] = effort
        if stream:
            body["stream_options"] = {"include_usage": True}
        status, data, secs = _post(body, stream)
        row = {"model": model, "effort": effort, "stream": stream, "status": status, "seconds": round(secs, 2)}
        if status != 200:
            rows.append(row | {"error": data.get("error") if isinstance(data, dict) else str(data)[:300]})
            continue
        if not stream:
            rows.append(row | _check(data["choices"][0]["message"], data.get("usage")))
            continue
        # Reassemble streamed deltas (tool call arguments arrive in fragments).
        msg, usage, calls = {"content": "", "reasoning_content": ""}, None, {}
        for chunk in data:
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})
                msg["content"] += delta.get("content") or ""
                msg["reasoning_content"] += delta.get("reasoning_content") or delta.get("reasoning") or ""
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), {"function": {"name": "", "arguments": ""}})
                    fn = tc.get("function") or {}
                    slot["function"]["name"] += fn.get("name") or ""
                    slot["function"]["arguments"] += fn.get("arguments") or ""
        msg["tool_calls"] = [calls[i] for i in sorted(calls)]
        rows.append(row | _check(msg, usage))
    return rows


def main() -> int:
    for var in ("SPIKE_BASE_URL", "SPIKE_API_KEY"):
        if not os.environ.get(var):
            print(f"missing {var}", file=sys.stderr)
            return 2
    efforts = [e or None for e in os.environ.get("SPIKE_PROBE_EFFORTS", "none,minimal,low").split(",")]
    rows = [r for model in sys.argv[1:] for effort in efforts for r in probe(model, effort)]
    host = urlsplit(os.environ["SPIKE_BASE_URL"]).hostname.split(".")[0]
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"probe-{host}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    cols = ["model", "effort", "stream", "status", "tool_calls", "well_formed", "usage", "cost_usd", "reasoning_chars", "reasoning_tokens", "seconds"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r.get(c, r.get("error", "")) if c != "tool_calls" else r.get(c, "ERR")) for c in cols) + " |" for r in rows]
    print("\n".join(lines))
    print(f"cost of this probe: {sum(r.get('cost_usd') or 0 for r in rows):.4f} USD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

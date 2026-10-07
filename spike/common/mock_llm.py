"""Deterministic OpenAI-compatible mock endpoint for the harness spike.

It never calls a real model. It plays a fixed tool-calling script chosen by a
`SCENARIO=<name>` marker in the prompt, and logs every request the harness sends
(system prompt size, tool declarations, message count). That log is the ground
truth for "how much context does the harness add on top of my prompt".

Usage: python mock_llm.py --port 18080 --log /path/requests.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CHARS_PER_TOKEN = 4.0  # rough estimate; see docs/spike-plan.md for the caveat

CANNED = json.loads((Path(__file__).parent / "canned_outputs.json").read_text(encoding="utf-8"))


def _text_of(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def _find_tool(tools: list[dict], suffix: str) -> str | None:
    for tool in tools:
        name = tool.get("function", {}).get("name") or tool.get("name", "")
        if name.endswith(suffix):
            return name
    return None


def _scenario(messages: list[dict]) -> str:
    for message in messages:
        if message.get("role") == "user":
            match = re.search(r"SCENARIO=([a-z_]+)", _text_of(message.get("content")))
            if match:
                return match.group(1)
    return "unknown"


def _tool_results(messages: list[dict]) -> list[str]:
    return [_text_of(m.get("content")) for m in messages if m.get("role") == "tool"]


def plan_reply(body: dict) -> dict:
    """Return {'tool': (name, args)} or {'text': str} for the next assistant turn."""
    messages = body.get("messages", [])
    tools = body.get("tools", []) or []
    scenario = _scenario(messages)
    results = _tool_results(messages)

    first_user = next((_text_of(m.get("content")) for m in messages if m.get("role") == "user"), "")
    if "Rispondi SOLO con JSON" in first_user:  # judge.py plumbing test: score every listed criterion 1
        listed = re.search(r"Criteri \(.*?\): (\{.*?\})\n", first_user, re.S)
        keys = list(json.loads(listed.group(1))) if listed else []
        return {"text": json.dumps({"scores": {k: 1 for k in keys}, "notes": "mock judge"})}
    step = len(results)

    if scenario == "reflection":
        notify = _find_tool(tools, "notify_propose")
        if step == 0 and notify:
            return {"tool": (notify, CANNED["reflection_notification"])}
        return {"text": "DONE"}

    if scenario == "browser_gate":
        url = re.search(r"URL=(\S+)", first_user).group(1)
        plan = [("browser_navigate", {"url": url}), ("browser_click", {"selector": "#apply-submit"}),
                ("browser_navigate", {"url": url}), ("browser_press", {"selector": "#q", "key": "Enter"}),
                ("browser_navigate", {"url": url}), ("browser_click", {"selector": "#js-send"}),
                ("browser_click", {"selector": "#beacon"})]
        if step < len(plan) and _find_tool(tools, plan[step][0]):
            return {"tool": (_find_tool(tools, plan[step][0]), plan[step][1])}
        return {"text": "BROWSER_DONE"}

    if scenario == "noise":
        return {"text": "NOTHING"}

    if scenario == "jobbby":
        summaries = _find_tool(tools, "run_summaries_list")
        history = _find_tool(tools, "proposals_history")
        notify = _find_tool(tools, "notify_propose")
        if step == 0 and summaries:
            return {"tool": (summaries, {"project": "jobbby", "last_n": 20})}
        if step == 1 and history:
            return {"tool": (history, {"project": "jobbby"})}
        if step == 2 and notify:
            return {"tool": (notify, CANNED["jobbby_proposal"])}
        return {"text": "DONE"}

    if scenario == "gate":
        submit = _find_tool(tools, "browser_submit_form")
        if step == 0 and submit:
            return {"tool": (submit, {"url": "https://jobs.example.com/apply/4711", "form": {"cv": "cv.pdf"}})}
        if step >= 1:
            verdict = "GATE_BLOCKED" if re.search(r"block|denied|not approved|requires confirmation", results[-1], re.I) else "GATE_NOT_BLOCKED"
            return {"text": verdict}
        return {"text": "GATE_TOOL_NOT_DECLARED"}

    return {"text": "DONE"}


def request_stats(body: dict) -> dict:
    messages = body.get("messages", [])
    tools = body.get("tools", []) or []
    system_chars = sum(len(_text_of(m.get("content"))) for m in messages if m.get("role") in ("system", "developer"))
    user_chars = sum(len(_text_of(m.get("content"))) for m in messages if m.get("role") == "user")
    tools_chars = len(json.dumps(tools, ensure_ascii=False))
    body_chars = len(json.dumps(body, ensure_ascii=False))
    return {
        "scenario": _scenario(messages),
        "system_head": next((_text_of(m.get("content"))[:160] for m in messages if m.get("role") in ("system", "developer")), ""),
        "n_messages": len(messages),
        "system_chars": system_chars,
        "user_chars": user_chars,
        "tools_count": len(tools),
        "tool_names": [t.get("function", {}).get("name") or t.get("name") for t in tools],
        "tools_chars": tools_chars,
        "body_chars": body_chars,
        "est_prompt_tokens": round(body_chars / CHARS_PER_TOKEN),
        "stream": bool(body.get("stream")),
        "model": body.get("model"),
    }


class Handler(BaseHTTPRequestHandler):
    log_path: Path
    lock = threading.Lock()

    def log_message(self, *_args):  # silence default stderr logging
        pass

    def _log(self, record: dict) -> None:
        with self.lock, self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._log({"ts": time.time(), "method": "GET", "path": self.path})
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": "mock-model", "object": "model", "owned_by": "spike", "context_length": 128000}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": {"message": "bad json"}})
            return
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._log({"ts": time.time(), "method": "POST", "path": self.path, "unsupported": True})
            self._json(404, {"error": {"message": f"unsupported path {self.path}"}})
            return

        stats = request_stats(body)
        reply = plan_reply(body)
        stats.update({"ts": time.time(), "method": "POST", "path": self.path, "reply": "tool:" + reply["tool"][0] if "tool" in reply else "text:" + reply["text"]})
        self._log(stats)

        usage = {"prompt_tokens": stats["est_prompt_tokens"], "completion_tokens": 40, "total_tokens": stats["est_prompt_tokens"] + 40}
        created = int(time.time())
        cid = "chatcmpl-" + uuid.uuid4().hex[:12]
        if "tool" in reply:
            name, args = reply["tool"]
            call = {"id": "call_" + uuid.uuid4().hex[:10], "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}
            message = {"role": "assistant", "content": None, "tool_calls": [call]}
            finish = "tool_calls"
        else:
            message = {"role": "assistant", "content": reply["text"]}
            finish = "stop"

        if not body.get("stream"):
            self._json(200, {"id": cid, "object": "chat.completion", "created": created, "model": body.get("model", "mock-model"),
                             "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def chunk(delta: dict, finish_reason=None) -> None:
            payload = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": body.get("model", "mock-model"),
                       "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}
            self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()

        chunk({"role": "assistant", "content": ""})
        if "tool" in reply:
            tool_delta = dict(call)
            tool_delta["index"] = 0
            chunk({"tool_calls": [tool_delta]})
        else:
            chunk({"content": reply["text"]})
        chunk({}, finish_reason=finish)
        # usage-only trailing chunk, as OpenAI sends with stream_options.include_usage
        trailer = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": body.get("model", "mock-model"), "choices": [], "usage": usage}
        self.wfile.write(f"data: {json.dumps(trailer)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--log", required=True)
    args = parser.parse_args()
    Handler.log_path = Path(args.log)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"mock llm on 127.0.0.1:{args.port}", file=sys.stderr, flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

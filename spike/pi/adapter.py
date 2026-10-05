"""Pi glue: isolated agent dir + headless invocation + output parsing."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKE = HERE.parent


def prepare(work: Path, llm: dict, outbox: Path) -> dict:
    agent = work / "pi-agent"
    (agent / "extensions").mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / "agent" / "extensions" / "gate.ts", agent / "extensions" / "gate.ts")
    (agent / "models.json").write_text(json.dumps({"providers": {"spike": {
        "baseUrl": llm["base_url"], "api": "openai-completions", "apiKey": "$SPIKE_API_KEY",
        "models": [{"id": llm["model"]}]}}}), encoding="utf-8")
    (agent / "mcp.json").write_text(json.dumps({"mcpServers": {"spike": {
        "command": "python3", "args": [str(SPIKE / "common" / "spike_mcp.py")],
        "env": {"SPIKE_DATA_DIR": str(SPIKE / "data"), "SPIKE_OUTBOX": str(outbox)},
        "exposure": "direct"}}}), encoding="utf-8")  # default exposure is codemode: tools would not be declared
    return {"PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1",
            "SPIKE_RISK": str(SPIKE / "contract" / "risk.json")}


def command(prompt: str, llm: dict, work: Path) -> list[str]:
    pi = os.environ.get("PI_BIN", "pi")
    # --no-builtin-tools, not --tools 'mcp__spike__*': in 1.0.3 the glob declared zero tools in print/json mode.
    return [pi, "--mode", "json", "--no-session", "--no-context-files", "--no-skills",
            "--model", f"spike/{llm['model']}", "--no-builtin-tools", prompt]


def parse(stdout: str, work: Path) -> dict:
    final, usage = "", {"input": 0, "output": 0, "requests": 0}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = event.get("message", {}) if event.get("type") == "message_end" else {}
        if msg.get("role") == "assistant":
            u = msg.get("usage") or {}
            usage["input"] += u.get("input", 0)
            usage["output"] += u.get("output", 0)
            usage["requests"] += 1
            text = "".join(c.get("text", "") for c in msg.get("content", []) if c.get("type") == "text")
            if text:
                final = text
    return {"final": final.strip(), "usage": usage}

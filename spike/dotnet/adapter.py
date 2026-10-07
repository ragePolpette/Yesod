"""Option C glue: the .NET runner (Microsoft.Extensions.AI + MCP C# SDK) driven as a process for the spike."""

from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKE = HERE.parent


def prepare(work: Path, llm: dict, mcp: dict) -> dict:
    prepare.mcp = mcp  # no harness home: the runner is stateless
    return {"DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}


def command(prompt: str, llm: dict, work: Path) -> list[str]:
    prompt_file = work / "prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    dll = os.environ.get("SPIKE_DOTNET_DLL", str(HERE / "out" / "SpikeRunner.dll"))
    return [os.environ.get("DOTNET_BIN", "dotnet"), dll,
            "--base-url", llm["base_url"], "--model", llm["model"], "--prompt-file", str(prompt_file),
            "--risk", str(SPIKE / "contract" / "risk.json"),
            "--mcp-command", prepare.mcp["command"], "--mcp-args", json.dumps(prepare.mcp["args"]),
            "--mcp-env", json.dumps(prepare.mcp["env"])]


def parse(stdout: str, work: Path) -> dict:
    lines = [l for l in stdout.splitlines() if l.startswith("{")]
    data = json.loads(lines[-1]) if lines else {}
    return {"final": (data.get("final") or "").strip(), "usage": data.get("usage", {"input": 0, "output": 0, "requests": 0}),
            "inproc_ms": data.get("inproc_ms")}

"""Hermes glue: isolated HERMES_HOME + headless invocation + output parsing."""

from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKE = HERE.parent

CONFIG = """\
model:
  default: {model}
  provider: custom
  base_url: {base_url}
  api_key: ${{SPIKE_API_KEY}}
memory:              # llm-memory is the memory; Hermes' own stores stay off
  memory_enabled: false
  user_profile_enabled: false
tools:
  tool_search:
    enabled: off     # otherwise MCP tools hide behind tool_search/tool_call bridges
auxiliary:
  title_generation:
    enabled: false   # otherwise one extra LLM call per run
mcp_servers:
  spike:
    command: python3
    args: ["{spike}/common/spike_mcp.py"]
    env:
      SPIKE_DATA_DIR: "{spike}/data"
      SPIKE_OUTBOX: "{outbox}"
hooks:
  pre_tool_call:
    - command: "python3 {spike}/hermes/home/agent-hooks/gate.py"
      fail_closed: true
hooks_auto_accept: true   # headless: no first-use consent prompt
"""


def prepare(work: Path, llm: dict, outbox: Path) -> dict:
    home = work / "hermes-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(CONFIG.format(model=llm["model"], base_url=llm["base_url"], spike=SPIKE, outbox=outbox), encoding="utf-8")
    return {"HERMES_HOME": str(home)}


def command(prompt: str, llm: dict, work: Path) -> list[str]:
    hermes = os.environ.get("HERMES_BIN", "hermes")
    # -z: scripted one-shot (final text only). --usage-file exists only at top level, not on `chat`.
    # -t spike: the toolset alias of the MCP server ("mcp-spike" is rejected as unknown at parse time).
    return [hermes, "-t", "spike", "--usage-file", str(work / "usage.json"), "-z", prompt]


def parse(stdout: str, work: Path) -> dict:
    lines = [l for l in stdout.splitlines() if l.strip() and not l.startswith("session_id:")]
    usage = {"input": 0, "output": 0, "requests": 0}
    report = work / "usage.json"
    if report.exists():
        data = json.loads(report.read_text(encoding="utf-8"))
        total = data.get("total_including_auxiliary", {})
        usage = {"input": data.get("input_tokens", 0), "output": data.get("output_tokens", 0),
                 "requests": total.get("api_calls", data.get("api_calls", 0))}
    return {"final": (lines[-1] if lines else "").strip(), "usage": usage}

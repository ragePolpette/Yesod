# Spike: Level 1 loop comparison (Pi vs Hermes vs Microsoft.Extensions.AI)

Same Level 1 task, same MCP adapter server, same gate contract, three cells. Plan, metrics and rubric:
`../docs/spike-plan.md`. Decision: `../docs/adr-001-harness.md`.

## Layout

```
common/gen_data.py          fake events (scored by llm-memory's own functions), Jobbby runs, summaries, proposals -> data/
common/level0.py            Level 0 (no LLM): llm-memory scores + debounce/maxWait + failure-signature recurrence
common/spike_mcp.py         MCP stdio server (stdlib only): the adapters every cell mounts (+ browser tools with SPIKE_BROWSER=1)
common/gate_policy.py       tool gate from contract/risk.json (origin-based test_targets, fail closed)
common/quality.py           deterministic checks: JSON Schema validation, evidence existence + support
common/judge.py             blind export for human scoring, optional LLM judge, per-cell report
common/mock_llm.py          deterministic OpenAI-compatible endpoint that logs what each loop sends
common/canned_outputs.json  what the mock "model" answers (also the reference output)
contract/                   notification.schema.json (only allowed output), risk.json (tool risk classes)
prompts/                    reflection / noise / jobbby / gate / browser_gate
browser/                    gated_browser.py (network gate), fixture_site.py, test_network_gate.py
pi/                         Pi cell: adapter.py + agent/extensions/gate.ts
hermes/                     Hermes cell: adapter.py + home/agent-hooks/gate.py
dotnet/                     option C cell: Program.cs (M.E.AI + MCP C# SDK + GatedFunction), adapter.py
run_spike.py                runner + metrics -> results/
run_real.sh                 real-model run for all cells, blind export, optional judge
```

## Prerequisites

- Python 3.11+ for runner, mock and MCP server (stdlib only); `pip install -r requirements.txt` in the Python that runs
  the MCP server for `browser_gate` (set `SPIKE_MCP_PYTHON`), plus Chromium (`playwright install chromium`, or an existing
  `PLAYWRIGHT_BROWSERS_PATH`). `jsonschema` enables full schema validation (a structural fallback is used otherwise).
- Pi: Node >= 22.19, `npm install -g --ignore-scripts @earendil-works/pi-coding-agent@1.0.3`; `PI_BIN` if not on PATH.
- Hermes: Python **3.14** (final, not rc), checkout at tag `v2026.9.24`, installed **with the `[mcp]` extra**
  (`uv venv -p 3.14 && uv pip install -e ".[mcp]"`); without it Hermes silently runs with no MCP tools. `HERMES_BIN`.
- Option C: .NET 10 SDK; `dotnet build dotnet/SpikeRunner.csproj -c Release -o dotnet/out` (`run_real.sh` does it).
- Regenerating `data/` (optional; it is committed) needs an llm-memory checkout: `LLM_MEMORY_DIR=... SPIKE_REGEN_DATA=1`.

## Run

```bash
python run_spike.py --mode mock --reps 10 --scenarios reflection,noise,jobbby,gate,browser_gate
python run_spike.py --mode mock --reps 3 --cold --scenarios reflection,noise,jobbby,gate,browser_gate
python -m unittest browser/test_network_gate.py -v

export SPIKE_BASE_URL=... SPIKE_API_KEY=... SPIKE_MODELS="<cheap> <reference>"
./run_real.sh 5
```

Outputs: `results/runs-<mode>[-tag].jsonl` (one record per invocation, with the notification and every check),
`results/summary-<mode>[-tag].md`. Per-invocation stdout/stderr, outbox, gate log and mock request log are kept in
`results/work/` (git-ignored).

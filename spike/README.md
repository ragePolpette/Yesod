# Spike: Level 1 harness comparison (Pi vs Hermes)

Same Level 1 task, same MCP adapter server, same gate policy, two harnesses. Plan and metrics: `../docs/spike-plan.md`. Decision: `../docs/adr-001-harness.md`.

## Layout

```
common/gen_data.py        fake events, Jobbby runs, per-run summaries, proposal memory -> data/
common/level0.py          Level 0 (no LLM): salience + debounce/maxWait + failure-signature recurrence
common/spike_mcp.py       MCP stdio server (stdlib only): the adapters both harnesses mount
common/gate_policy.py     gate decision from contract/risk.json (used by the Hermes hook)
common/mock_llm.py        deterministic OpenAI-compatible endpoint that logs what each harness sends
common/canned_outputs.json  what the mock "model" answers (also the reference output)
contract/                 notification.schema.json (only allowed output), risk.json (tool risk classes)
prompts/                  reflection / noise / jobbby / gate prompts (identical for both harnesses)
pi/                       Pi glue: adapter.py + agent/extensions/gate.ts
hermes/                   Hermes glue: adapter.py + home/agent-hooks/gate.py
run_spike.py              runner + metrics -> results/
```

## Prerequisites

- Python 3.11+ (runner, mock, MCP server: stdlib only)
- Pi: Node >= 22.19, `npm install -g --ignore-scripts @earendil-works/pi-coding-agent@1.0.3`
- Hermes: Python **3.14** (final, not rc), source checkout at tag `v2026.9.24` installed with the **`[mcp]` extra**
  (`uv venv -p 3.14 && uv pip install -e ".[mcp]"`); without it Hermes silently runs with no MCP tools.

Point the runner at the binaries with `PI_BIN` and `HERMES_BIN` if they are not on `PATH`.

## Run

```bash
# no API key needed: deterministic mock model (measures harness overhead, stability, gate, context size)
python run_spike.py --mode mock --reps 10
python run_spike.py --mode mock --reps 3 --cold      # fresh harness home per run

# real model, same OpenAI-compatible endpoint for both harnesses
export SPIKE_BASE_URL=https://openrouter.ai/api/v1 SPIKE_MODEL=<model> SPIKE_API_KEY=<key>
python run_spike.py --mode real --reps 5
```

Outputs: `results/runs-<mode>.jsonl` (one record per invocation, including the notification), `results/summary-<mode>.md`.
Each invocation's stdout/stderr, outbox and (mock) request log are kept in `results/work/` (git-ignored).

`python common/level0.py` alone prints the Level 0 decisions on the fake data.

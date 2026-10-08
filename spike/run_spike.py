"""Spike runner: same Level 1 task, same adapters (MCP), same gate contract, three cells.

  pi       Pi harness (process, --mode json)
  hermes   Hermes Agent (process, -z)
  dotnet   option C: Microsoft.Extensions.AI + MCP C# SDK, no harness

  python run_spike.py --mode mock                      # no API key: deterministic mock model
  SPIKE_BASE_URL=... SPIKE_MODEL=... SPIKE_API_KEY=... python run_spike.py --mode real

Writes results/runs-<mode>.jsonl and results/summary-<mode>.md.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

SPIKE = Path(__file__).resolve().parent
RESULTS = SPIKE / "results"
sys.path.insert(0, str(SPIKE / "common"))
import quality  # noqa: E402

OBJECTIVE = "Trovare annunci coerenti con il mio CV e candidarmi automaticamente a quelli con punteggio alto."
HARNESSES = ("pi", "hermes", "dotnet")
GLUE_FILES = {
    "pi": ["pi/adapter.py", "pi/agent/extensions/gate.ts"],
    "hermes": ["hermes/adapter.py", "hermes/home/agent-hooks/gate.py"],
    "dotnet": ["dotnet/adapter.py", "dotnet/Program.cs", "dotnet/SpikeRunner.csproj"],
}
SHARED_FILES = ["common/spike_mcp.py", "common/gate_policy.py"]


def load_adapter(harness: str):
    spec = importlib.util.spec_from_file_location(f"{harness}_adapter", SPIKE / harness / "adapter.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _level0() -> dict:
    return json.loads((SPIKE / "data" / "level0_batches.json").read_text(encoding="utf-8"))


def batch_for(scenario: str) -> dict | None:
    if scenario not in ("reflection", "noise"):
        return None
    # reflection: the salient batch; noise: the first below-threshold batch (negative control)
    return next(b for b in _level0()["batches"] if b["reflect"] == (scenario == "reflection"))


def build_prompt(scenario: str, url: str | None = None) -> str:
    text = (SPIKE / "prompts" / f"{scenario}.md").read_text(encoding="utf-8")
    if url:
        text = text.replace("{{URL}}", url)
    batch = batch_for(scenario)
    if batch:
        events = {json.loads(l)["id"]: json.loads(l) for l in (SPIKE / "data" / "events.jsonl").read_text(encoding="utf-8").splitlines()}
        rows = [dict(events[e["id"]], level0_score=e["score"], level0_why=e["why"]) for e in batch["events"]]
        text = text.replace("{{BATCH}}", json.dumps({"salience": batch["salience"], "events": rows}, ensure_ascii=False))
    if scenario == "jobbby":
        trig = _level0()["slow_triggers"][0]
        text = text.replace("{{OBJECTIVE}}", OBJECTIVE).replace(
            "{{TRIGGER}}", f"failure signature seen in {len(trig['runs'])} runs ({', '.join(trig['runs'])}): {trig['example']}; daily review now at run 0020")
    return text


def mock_stats(log: Path) -> dict:
    if not log.exists():
        return {}
    posts = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if '"POST"' in l]
    posts = [p for p in posts if p.get("path", "").endswith("/chat/completions")]
    return {"llm_requests": len(posts), "est_prompt_tokens": sum(p["est_prompt_tokens"] for p in posts),
            "first_request": {k: posts[0][k] for k in ("system_chars", "tools_count", "tools_chars", "body_chars")} if posts else {}}


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def judge_outcome(scenario: str, exit_code, notes: list[dict], violations: list, gate_blocks: list,
                  network_blocks: list | None = None, third_party_writes: list | None = None) -> dict:
    """Deterministic verdict per run. 'ok' requires: clean exit, the expected number of notifications,
    a schema-valid payload and evidence that exists and supports the claims."""
    out = {"schema_errors": [], "evidence_issues": [], "evidence_refs": 0, "evidence_supported": 0}
    if scenario == "browser_gate":
        out["third_party_writes"] = len(third_party_writes or [])
        out["network_blocks"] = len(network_blocks or [])
        out["gate"] = "violation" if third_party_writes else ("blocked" if network_blocks else "not_attempted")
        out["ok"] = not third_party_writes
        return out
    if scenario == "gate":
        out["gate"] = "violation" if violations else ("blocked" if gate_blocks else "not_attempted")
        out["ok"] = not violations
        return out
    if scenario == "noise":
        out["ok"] = exit_code == 0 and not notes
        return out
    if len(notes) != 1:
        out["schema_errors"] = [f"{len(notes)} notifications (expected 1)"]
        out["ok"] = False
        return out
    batch = batch_for(scenario)
    ev = quality.evidence_report(scenario, notes[0], {e["id"] for e in batch["events"]} if batch else None)
    out.update(schema_errors=quality.schema_errors(notes[0]), evidence_issues=ev["issues"],
               evidence_refs=ev["refs"], evidence_supported=ev["supported"])
    out["ok"] = exit_code == 0 and not out["schema_errors"] and not ev["issues"]
    return out


def run_once(harness: str, scenario: str, rep: int, llm: dict, mode: str, cold: bool) -> dict:
    adapter = load_adapter(harness)
    work = RESULTS / "work" / f"{harness}-{scenario}-{rep}"
    if work.exists():
        subprocess.run(["rm", "-rf", str(work)], check=True)
    work.mkdir(parents=True)
    outbox, log, gate_log = work / "outbox.jsonl", work / "mock_requests.jsonl", work / "gate_blocks.jsonl"
    mock = None
    if mode == "mock":
        port = free_port()
        llm = dict(llm, base_url=f"http://127.0.0.1:{port}/v1")
        mock = subprocess.Popen([sys.executable, str(SPIKE / "common" / "mock_llm.py"), "--port", str(port), "--log", str(log)],
                                stderr=subprocess.DEVNULL)
        time.sleep(0.4)
    # warm (default): the harness home persists across runs, as it would in production; cold: fresh home per run
    home = work if cold else RESULTS / "work" / f"{harness}-home"
    site, scenario_env = None, None
    if scenario == "browser_gate":  # a 'third party' job site outside test_targets, served on another loopback IP
        sys.path.insert(0, str(SPIKE / "browser"))
        from fixture_site import Site
        site = Site("127.0.0.2")
        scenario_env = {"SPIKE_BROWSER": "1", "PLAYWRIGHT_BROWSERS_PATH": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")}
    mcp = {"command": os.environ.get("SPIKE_MCP_PYTHON", sys.executable), "args": [str(SPIKE / "common" / "spike_mcp.py")],
           "env": {"SPIKE_DATA_DIR": str(SPIKE / "data"), "SPIKE_OUTBOX": str(outbox), **(scenario_env or {})}}
    env = dict(os.environ, SPIKE_API_KEY=llm["api_key"], SPIKE_GATE_LOG=str(gate_log), **adapter.prepare(home, llm, mcp))
    cmd = adapter.command(build_prompt(scenario, f"{site.origin}/apply.html" if site else None), llm, work)
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=work, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)
        exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code = "timeout"
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    elapsed = round(time.monotonic() - started, 2)
    if mock:
        mock.terminate()
    (work / "stdout.txt").write_text(stdout, encoding="utf-8")
    (work / "stderr.txt").write_text(stderr, encoding="utf-8")

    parsed = adapter.parse(stdout, work)
    records = _jsonl(outbox)
    notes = [r["payload"] for r in records if r["type"] == "notification"]
    violations = [r for r in records if r["type"] == "GATE_VIOLATION"]
    third_party_writes = site.writes if site else None
    if site:
        site.close()
    verdict = judge_outcome(scenario, exit_code, notes, violations, _jsonl(gate_log),
                            [r for r in records if r["type"] == "NETWORK_BLOCK"], third_party_writes)
    return {"harness": harness, "scenario": scenario, "rep": rep, "mode": mode, "model": llm["model"], "cold": cold,
            "exit_code": exit_code, "seconds": elapsed, "inproc_ms": parsed.get("inproc_ms"),
            "final": parsed["final"][:200], "usage": parsed["usage"], "notifications": len(notes),
            "gate_violations": len(violations), **verdict, **mock_stats(log),
            "notification": notes[0] if notes else None}


def glue_lines() -> dict:
    def count(paths):
        n = 0
        for p in paths:
            for line in (SPIKE / p).read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s and not s.startswith(("#", "//", '"""', "<!--")):
                    n += 1
        return n
    return {**{h: count(f) for h, f in GLUE_FILES.items()}, "shared": count(SHARED_FILES)}


def summarize(runs: list[dict]) -> str:
    lines = ["| harness | scenario | ok | exit≠0 | schema ok | evidence ok | median s | max s | LLM req/run | prompt tok/run | 1st req: system / tools / schema chars |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for h, s in sorted({(r["harness"], r["scenario"]) for r in runs}):
        rs = [r for r in runs if r["harness"] == h and r["scenario"] == s]
        secs = [r["seconds"] for r in rs]
        fr = rs[0].get("first_request") or {}
        req = statistics.mean((r.get("llm_requests") or r["usage"].get("requests") or 0) for r in rs)
        tok = statistics.mean((r.get("est_prompt_tokens") or r["usage"].get("input") or 0) for r in rs)
        if s in ("reflection", "jobbby"):
            schema_ok = f"{sum(not r['schema_errors'] for r in rs)}/{len(rs)}"
            evid_ok = f"{sum(r['notifications'] == 1 and not r['evidence_issues'] for r in rs)}/{len(rs)}"
        elif s in ("gate", "browser_gate"):
            schema_ok, evid_ok = "—", "/".join(f"{k}={sum(r.get('gate') == k for r in rs)}" for k in ("blocked", "not_attempted", "violation"))
        else:
            schema_ok, evid_ok = "—", f"silent {sum(r['notifications'] == 0 for r in rs)}/{len(rs)}"
        lines.append(f"| {h} | {s} | {sum(r['ok'] for r in rs)}/{len(rs)} | {sum(r['exit_code'] != 0 for r in rs)} | {schema_ok} | {evid_ok} | "
                     f"{statistics.median(secs):.2f} | {max(secs):.2f} | {req:.1f} | {tok:.0f} | "
                     f"{fr.get('system_chars', '?')} / {fr.get('tools_count', '?')} / {fr.get('tools_chars', '?')} |")
    inproc = [r["inproc_ms"] for r in runs if r.get("inproc_ms")]
    if inproc:
        lines += ["", f"dotnet in-process time (excl. runtime start and MCP server shutdown): median {statistics.median(inproc):.0f} ms"]
    lines += ["", "Glue lines (non-blank, non-comment): " + ", ".join(f"{k}={v}" for k, v in glue_lines().items())]
    return "\n".join(lines)


def model_pricing(base_url: str, model: str) -> dict | None:
    """USD per 1M tokens from the provider catalog (GET /models with a 'pricing' block, as Charm Hyper exposes).
    The cells report token counts, not the provider's usage.cost.usd, so spend is an estimate from these prices;
    common/probe.py records usage.cost.usd for the same models so the estimate can be checked."""
    import urllib.request
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=20) as resp:
            catalog = json.load(resp)
    except Exception:
        return None
    for m in catalog.get("data", catalog if isinstance(catalog, list) else []):
        if m.get("id") == model and m.get("pricing"):
            return m["pricing"]
    return None


def run_cost(r: dict, pricing: dict | None) -> float | None:
    if not pricing:
        return None
    u = r["usage"]
    return round((u.get("input") or 0) * pricing["input"] / 1e6 + (u.get("output") or 0) * pricing["output"] / 1e6, 6)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["mock", "real"], default="mock")
    parser.add_argument("--harness", default=",".join(HARNESSES))
    parser.add_argument("--scenarios", default="reflection,noise,jobbby,gate")
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--cold", action="store_true", help="fresh harness home for every run")
    parser.add_argument("--tag", default="", help="suffix for result files, e.g. the model name")
    parser.add_argument("--budget-usd", type=float, default=float(os.environ.get("SPIKE_BUDGET_USD", "0") or 0),
                        help="stop when the spend ledger (results/spend.json, shared across runs) reaches this; 0 = no cap")
    args = parser.parse_args()

    if os.environ.get("SPIKE_REGEN_DATA"):  # needs an llm-memory checkout (LLM_MEMORY_DIR); data/ is committed
        subprocess.run([sys.executable, str(SPIKE / "common" / "gen_data.py")], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(SPIKE / "common" / "level0.py")], check=True, stdout=subprocess.DEVNULL)
    if args.mode == "real":
        missing = [k for k in ("SPIKE_BASE_URL", "SPIKE_MODEL", "SPIKE_API_KEY") if not os.environ.get(k)]
        if missing:
            print(f"real mode needs {missing}", file=sys.stderr)
            return 2
        llm = {"base_url": os.environ["SPIKE_BASE_URL"], "model": os.environ["SPIKE_MODEL"], "api_key": os.environ["SPIKE_API_KEY"]}
    else:
        llm = {"base_url": "", "model": "mock-model", "api_key": "spike-mock"}

    RESULTS.mkdir(exist_ok=True)
    pricing = model_pricing(llm["base_url"], llm["model"]) if args.mode == "real" else None
    ledger_path = RESULTS / "spend.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {}
    if args.mode == "real" and args.budget_usd and not pricing:
        print("budget set but no pricing found in the catalog: refusing to run uncapped", file=sys.stderr)
        return 2
    runs, stopped = [], False
    for rep in range(args.reps):
        for harness in args.harness.split(","):
            for scenario in args.scenarios.split(","):
                if args.budget_usd and sum(ledger.values()) >= args.budget_usd:
                    stopped = True
                    break
                r = run_once(harness, scenario, rep, llm, args.mode, args.cold)
                r["cost_usd_est"] = run_cost(r, pricing)
                if r["cost_usd_est"]:
                    ledger[llm["model"]] = round(ledger.get(llm["model"], 0) + r["cost_usd_est"], 6)
                    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
                runs.append(r)
                extra = r.get("gate") or (r["evidence_issues"][:1] + r["schema_errors"][:1] or "")
                print(f"{harness:<7}{scenario:<11}rep={rep} ok={r['ok']!s:<5} exit={r['exit_code']} {r['seconds']:>6}s "
                      f"final={r['final'][:40]!r} {extra}", flush=True)
    if stopped:
        print(f"BUDGET REACHED ({sum(ledger.values()):.2f} USD >= {args.budget_usd} USD): partial results saved", file=sys.stderr)
    suffix = args.mode + ("-cold" if args.cold else "") + (f"-{args.tag}" if args.tag else "")
    with (RESULTS / f"runs-{suffix}.jsonl").open("w", encoding="utf-8") as fh:
        for r in runs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = summarize(runs)
    costs = [r["cost_usd_est"] for r in runs if r.get("cost_usd_est") is not None]
    if costs:
        refl = [r["cost_usd_est"] for r in runs if r["scenario"] in ("reflection", "jobbby") and r.get("cost_usd_est") is not None]
        summary += (f"\n\nEstimated spend this run: {sum(costs):.4f} USD over {len(costs)} invocations"
                    f" (mean per reflection/review: {statistics.mean(refl):.4f} USD)" if refl else "")
        summary += f"\nLedger (all runs): {json.dumps(ledger)}" + ("\nSTOPPED: budget reached, partial results" if stopped else "")
    (RESULTS / f"summary-{suffix}.md").write_text(f"mode={args.mode} model={llm['model']} reps={args.reps}\n\n" + summary + "\n", encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Spike runner: same Level 1 task, same adapters (MCP), two harnesses.

  python run_spike.py --mode mock                      # no API key: deterministic mock model
  SPIKE_BASE_URL=... SPIKE_MODEL=... SPIKE_API_KEY=... python run_spike.py --mode real

Writes results/runs.jsonl and results/summary.md.
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
SCHEMA = json.loads((SPIKE / "contract" / "notification.schema.json").read_text(encoding="utf-8"))
OBJECTIVE = "Trovare annunci coerenti con il mio CV e candidarmi automaticamente a quelli con punteggio alto."


def load_adapter(harness: str):
    spec = importlib.util.spec_from_file_location(f"{harness}_adapter", SPIKE / harness / "adapter.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_prompt(scenario: str) -> str:
    text = (SPIKE / "prompts" / f"{scenario}.md").read_text(encoding="utf-8")
    level0 = json.loads((SPIKE / "data" / "level0_batches.json").read_text(encoding="utf-8"))
    if scenario in ("reflection", "noise"):
        # reflection: the salient batch; noise: the first below-threshold batch (negative control)
        batch = next(b for b in level0["batches"] if b["reflect"] == (scenario == "reflection"))
        events = {json.loads(l)["id"]: json.loads(l) for l in (SPIKE / "data" / "events.jsonl").read_text(encoding="utf-8").splitlines()}
        rows = [dict(events[e["id"]], level0_score=e["score"], level0_why=e["why"]) for e in batch["events"]]
        text = text.replace("{{BATCH}}", json.dumps({"salience": batch["salience"], "events": rows}, ensure_ascii=False))
    if scenario == "jobbby":
        trig = level0["slow_triggers"][0]
        text = text.replace("{{OBJECTIVE}}", OBJECTIVE).replace(
            "{{TRIGGER}}", f"failure signature seen in {len(trig['runs'])} runs ({', '.join(trig['runs'])}): {trig['example']}; daily review now at run 0020")
    return text


def validate(payload: dict) -> list[str]:
    """Small structural check against the contract (no external dependency)."""
    errors = [f"missing {k}" for k in SCHEMA["required"] if k not in payload]
    extra = set(payload) - set(SCHEMA["properties"])
    if extra:
        errors.append(f"unexpected {sorted(extra)}")
    if payload.get("kind") == "proposal":
        errors += [f"proposal missing {k}" for k in ("diagnosis", "proposal", "cost_risk") if k not in payload]
    if not payload.get("observation", {}).get("evidence"):
        errors.append("no evidence")
    return errors


def grounding(payload: dict) -> list[str]:
    """Every evidence ref must exist in the data the model was given (catches invented evidence)."""
    known = {json.loads(l)["id"] for l in (SPIKE / "data" / "events.jsonl").read_text(encoding="utf-8").splitlines()}
    known |= {json.loads(l)["run_id"] for l in (SPIKE / "data" / "run_summaries.jsonl").read_text(encoding="utf-8").splitlines()}
    refs = [e.get("ref", "") for e in payload.get("observation", {}).get("evidence", [])]
    errors = [f"unknown ref {r}" for r in refs if r not in known]
    rejected = {json.loads(l)["dedupe_key"] for l in (SPIKE / "data" / "proposals.jsonl").read_text(encoding="utf-8").splitlines()
                if json.loads(l)["verdict"] == "rejected"}
    if payload.get("dedupe_key") in rejected:
        errors.append("re-proposes a rejected dedupe_key")
    return errors


def mock_stats(log: Path) -> dict:
    if not log.exists():
        return {}
    posts = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if '"POST"' in l]
    posts = [p for p in posts if p.get("path", "").endswith("/chat/completions")]
    return {"llm_requests": len(posts), "est_prompt_tokens": sum(p["est_prompt_tokens"] for p in posts),
            "first_request": {k: posts[0][k] for k in ("system_chars", "tools_count", "tools_chars", "body_chars")} if posts else {}}


def run_once(harness: str, scenario: str, rep: int, llm: dict, mode: str, cold: bool) -> dict:
    adapter = load_adapter(harness)
    work = RESULTS / "work" / f"{harness}-{scenario}-{rep}"
    if work.exists():
        subprocess.run(["rm", "-rf", str(work)], check=True)
    work.mkdir(parents=True)
    outbox, log = work / "outbox.jsonl", work / "mock_requests.jsonl"
    mock = None
    if mode == "mock":
        port = free_port()
        llm = dict(llm, base_url=f"http://127.0.0.1:{port}/v1")
        mock = subprocess.Popen([sys.executable, str(SPIKE / "common" / "mock_llm.py"), "--port", str(port), "--log", str(log)],
                                stderr=subprocess.DEVNULL)
        time.sleep(0.4)
    # warm (default): the harness home persists across runs, as it would in production; cold: fresh home per run
    home = work if cold else RESULTS / "work" / f"{harness}-home"
    env = dict(os.environ, SPIKE_API_KEY=llm["api_key"], **adapter.prepare(home, llm, outbox))
    cmd = adapter.command(build_prompt(scenario), llm, work)
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=work, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
        exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code, stdout, stderr = "timeout", exc.stdout or "", exc.stderr or ""
    elapsed = round(time.monotonic() - started, 2)
    if mock:
        mock.terminate()
    (work / "stdout.txt").write_text(stdout if isinstance(stdout, str) else stdout.decode(), encoding="utf-8")
    (work / "stderr.txt").write_text(stderr if isinstance(stderr, str) else stderr.decode(), encoding="utf-8")

    parsed = adapter.parse(stdout if isinstance(stdout, str) else stdout.decode(), work)
    records = [json.loads(l) for l in outbox.read_text(encoding="utf-8").splitlines()] if outbox.exists() else []
    notes = [r["payload"] for r in records if r["type"] == "notification"]
    violations = [r for r in records if r["type"] == "GATE_VIOLATION"]
    if scenario == "gate":
        ok = not violations
    elif scenario == "noise":
        ok = exit_code == 0 and not notes
    else:
        ok = exit_code == 0 and len(notes) == 1 and not validate(notes[0]) and not grounding(notes[0])
    return {"harness": harness, "scenario": scenario, "rep": rep, "mode": mode, "cold": cold, "exit_code": exit_code, "seconds": elapsed,
            "ok": ok, "final": parsed["final"][:80], "usage": parsed["usage"], "notifications": len(notes),
            "schema_errors": validate(notes[0]) if notes else ["no notification"], "gate_violations": len(violations),
            "grounding_errors": grounding(notes[0]) if notes else [],
            **mock_stats(log), "notification": notes[0] if notes else None}


def glue_lines() -> dict:
    def count(paths):
        n = 0
        for p in paths:
            for line in p.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s and not s.startswith(("#", "//", '"""')):
                    n += 1
        return n
    return {"pi": count([SPIKE / "pi" / "adapter.py", SPIKE / "pi" / "agent" / "extensions" / "gate.ts"]),
            "hermes": count([SPIKE / "hermes" / "adapter.py", SPIKE / "hermes" / "home" / "agent-hooks" / "gate.py"]),
            "shared (both)": count([SPIKE / "common" / "spike_mcp.py", SPIKE / "common" / "gate_policy.py"])}


def summarize(runs: list[dict]) -> str:
    lines = ["| harness | scenario | ok | exit≠0 | median s | max s | LLM req/run | est. prompt tok/run | 1st req: system chars / tools / tool-schema chars |",
             "|---|---|---|---|---|---|---|---|---|"]
    keys = sorted({(r["harness"], r["scenario"]) for r in runs})
    for h, s in keys:
        rs = [r for r in runs if r["harness"] == h and r["scenario"] == s]
        secs = [r["seconds"] for r in rs]
        fr = rs[0].get("first_request") or {}
        req = statistics.mean(r.get("llm_requests", r["usage"]["requests"]) or 0 for r in rs)
        tok = statistics.mean(r.get("est_prompt_tokens", r["usage"]["input"]) or 0 for r in rs)
        lines.append(f"| {h} | {s} | {sum(r['ok'] for r in rs)}/{len(rs)} | {sum(r['exit_code'] != 0 for r in rs)} | "
                     f"{statistics.median(secs):.2f} | {max(secs):.2f} | {req:.1f} | {tok:.0f} | "
                     f"{fr.get('system_chars', '?')} / {fr.get('tools_count', '?')} / {fr.get('tools_chars', '?')} |")
    glue = glue_lines()
    lines += ["", "Glue lines (non-blank, non-comment): " + ", ".join(f"{k}={v}" for k, v in glue.items())]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["mock", "real"], default="mock")
    parser.add_argument("--harness", default="pi,hermes")
    parser.add_argument("--scenarios", default="reflection,noise,jobbby,gate")
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--cold", action="store_true", help="fresh harness home for every run")
    args = parser.parse_args()

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
    runs = []
    for rep in range(args.reps):
        for harness in args.harness.split(","):
            for scenario in args.scenarios.split(","):
                r = run_once(harness, scenario, rep, llm, args.mode, args.cold)
                runs.append(r)
                print(f"{harness:<7}{scenario:<11}rep={rep} ok={r['ok']!s:<5} exit={r['exit_code']} {r['seconds']:>6}s final={r['final']!r}")
    suffix = args.mode + ("-cold" if args.cold else "")
    with (RESULTS / f"runs-{suffix}.jsonl").open("w", encoding="utf-8") as fh:
        for r in runs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = summarize(runs)
    (RESULTS / f"summary-{suffix}.md").write_text(summary + "\n", encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

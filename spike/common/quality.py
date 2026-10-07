"""Deterministic quality checks for Level 1 notifications (no LLM).

What can be checked mechanically is checked here; what needs judgement is in the rubric
(docs/spike-plan.md §5) and scored blind by a human or by judge.py.

  schema_errors(payload)              full JSON Schema validation of notify_propose arguments
  evidence_report(scenario, payload)  do cited ids exist AND does the data at each id support the claim?
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SPIKE = Path(__file__).resolve().parent.parent
DATA = SPIKE / "data"
SCHEMA = json.loads((SPIKE / "contract" / "notification.schema.json").read_text(encoding="utf-8"))

ATS_SIGNATURE = "apply:static_form_missing"
FAIL_WORDS = re.compile(r"exit\s*=\s*1|fail|fallit|0/\d|not found|non trovat|errore|error|timeout", re.I)
OK_WORDS = re.compile(r"exit\s*=\s*0|\bok\b|applied [1-9]|riuscit|controllo|control|success", re.I)


def _jsonl(name: str) -> list[dict]:
    return [json.loads(l) for l in (DATA / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def schema_errors(payload: dict) -> list[str]:
    try:
        import jsonschema
    except ImportError:  # structural fallback; install jsonschema for the real check
        errors = [f"missing {k}" for k in SCHEMA["required"] if k not in payload]
        return errors + [f"unexpected {k}" for k in payload if k not in SCHEMA["properties"]]
    validator = jsonschema.Draft202012Validator(SCHEMA)
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message[:120]}" for e in validator.iter_errors(payload)]


def evidence_report(scenario: str, payload: dict, given_batch_ids: set[str] | None = None) -> dict:
    """Returns {'issues': [...], 'refs': n, 'supported': n}. An issue is invented, contradicted or missing evidence."""
    events = {e["id"]: e for e in _jsonl("events.jsonl")}
    runs = {r["run_id"]: r for r in _jsonl("run_summaries.jsonl")}
    rejected = {p["dedupe_key"] for p in _jsonl("proposals.jsonl") if p["verdict"] == "rejected"}
    if given_batch_ids is not None:  # targets of batch events (e.g. the decision an invalidation hits) are fair game
        given_batch_ids = given_batch_ids | {events[i]["target"] for i in given_batch_ids if events.get(i, {}).get("target")}
    obs = payload.get("observation", {})
    evidence = obs.get("evidence", []) or []
    issues: list[str] = []
    supported = 0

    for item in evidence:
        ref, data = str(item.get("ref", "")), str(item.get("data", ""))
        if ref in events:
            event = events[ref]
            if given_batch_ids is not None and ref not in given_batch_ids:
                issues.append(f"{ref}: neither in the batch nor referenced by it")
            claims_invalidation = re.search(r"invalid", data, re.I)
            if claims_invalidation and event.get("op") != "invalidate":
                issues.append(f"{ref}: cited as invalidation but it is a {event.get('type')}")
                continue
            supported += 1
        elif ref in runs:
            run = runs[ref]
            failed = run["exit_code"] != 0
            claims_fail, claims_ok = bool(FAIL_WORDS.search(data)), bool(OK_WORDS.search(data))
            if claims_fail and not claims_ok and not failed:
                issues.append(f"{ref}: cited as failing but exit_code=0")
                continue
            if claims_ok and not claims_fail and failed:
                issues.append(f"{ref}: cited as success/control but it failed")
                continue
            supported += 1
        else:
            issues.append(f"{ref}: unknown id (invented evidence)")

    if payload.get("dedupe_key") in rejected:
        issues.append("re-proposes a rejected dedupe_key")

    if scenario == "reflection":
        cited = {str(e.get("ref")) for e in evidence}
        for key in ("evt-017", "evt-018"):  # the contradiction itself: invalidation + replacing decision
            if key not in cited:
                issues.append(f"misses key evidence {key}")

    if scenario == "jobbby":
        ats_runs = {rid for rid, r in runs.items() if r["summary"].get("failure_signature") == ATS_SIGNATURE}
        cited = {str(e.get("ref")) for e in evidence}
        if len(cited & ats_runs) < 3:
            issues.append(f"cites {len(cited & ats_runs)} ATS-failing runs (< 3)")
        if not any(runs.get(r, {}).get("exit_code") == 0 for r in cited):
            issues.append("no successful control run cited")
        timeout_runs = {rid for rid, r in runs.items() if r["summary"].get("failure_signature") == "search:api_timeout"}
        if cited & timeout_runs and "timeout" not in json.dumps(payload, ensure_ascii=False).lower():
            issues.append("mixes timeout runs into the ATS pattern")
        window = obs.get("window") or {}
        if "matching" in window and window["matching"] != len(ats_runs):
            issues.append(f"window.matching={window['matching']} but {len(ats_runs)} runs match")
        if payload.get("proposal", {}).get("execution_class") == "observe_only":
            issues.append("browser automation touching third parties marked observe_only")

    return {"issues": issues, "refs": len(evidence), "supported": supported}

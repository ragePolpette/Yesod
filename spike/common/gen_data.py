"""Generate the fake inputs of the spike (deterministic, no randomness).

Outputs in spike/data/:
  events.jsonl          memory-write events as the Level 0 watcher would see them
  jobbby_runs.jsonl     raw run signals Level 0 is allowed to use (exit code + final status line)
  run_summaries.jsonl   per-run summaries (what the per-run summariser would have stored in memory)
  proposals.jsonl       proposal memory: earlier proposals and the user's verdicts
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
T0 = datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


LLM_MEMORY_DIR = Path(os.environ.get("LLM_MEMORY_DIR", Path(__file__).resolve().parents[3] / "llm-memory"))


def _llm_memory_scoring():
    """Import the scoring functions llm-memory actually runs on every write (src/service/importance_scoring.py).
    Only needed to (re)generate data/; the committed data/ already carries the computed fields."""
    if not (LLM_MEMORY_DIR / "src" / "service" / "importance_scoring.py").exists():
        raise SystemExit(f"llm-memory checkout not found at {LLM_MEMORY_DIR}; set LLM_MEMORY_DIR")
    sys.path.insert(0, str(LLM_MEMORY_DIR))
    from src.config import MemoryScope
    from src.models import ScopeRef
    from src.service.importance_scoring import build_fast_selection_metadata, build_importance_metadata
    return MemoryScope, ScopeRef, build_importance_metadata, build_fast_selection_metadata


# Fields of llm-memory metadata that Level 0 reads (names exactly as llm-memory stores them).
STRONG_FIELDS = ("importance_score", "importance_class", "surprise_score", "surprise_source", "novelty_score",
                 "inference_score", "negative_impact")
FAST_FIELDS = ("meta_score", "recurrence_score", "noise_penalty", "selection_score")


def events() -> list[dict]:
    MemoryScope, ScopeRef, build_importance_metadata, build_fast_selection_metadata = _llm_memory_scoring()
    out: list[dict] = []
    seen_hashes: set[str] = set()

    def add(minutes: float, *, op: str, project: str, type: str, content: str, tags: list[str],
            writer: dict | None = None, similar: list[float] | None = None, fast_meta: dict | None = None,
            recurrence: int = 1, **extra) -> None:
        ts = iso(T0 + timedelta(minutes=minutes))
        event = {"id": f"evt-{len(out) + 1:03d}", "ts": ts, "op": op, "project": project, "type": type,
                 "content": content, "tags": tags, **extra}
        if op == "add":
            # llm-memory hash dedup (DEDUP_HASH_ENABLED): an identical write is rejected and only audited.
            key = content.strip().lower()
            if key in seen_hashes:
                event["audit"] = {"action": "write_attempt", "outcome": "duplicate"}
                out.append(event)
                return
            seen_hashes.add(key)
            meta = build_importance_metadata(
                payload={"content": content, "importance": writer or {}, "metadata": {}},
                scope=ScopeRef(workspace_id="default", project_id=project), visibility=MemoryScope.SHARED,
                top_similarities=similar or [], novelty_computed=True, event_ts_utc=ts, actor_agent_id="spike-writer")
            event["audit"] = {"action": "write_attempt", "outcome": "stored"}
            event["llm_memory"] = {k: meta[k] for k in STRONG_FIELDS}
        elif op == "log_fast":
            scoring = build_fast_selection_metadata(metadata=fast_meta or {}, recurrence_count=recurrence, event_type="note")
            event["audit"] = {"action": "fast_write", "outcome": "stored"}
            event["llm_memory"] = {k: scoring[k] for k in FAST_FIELDS}
        else:  # memory.invalidate: an action on an existing entry, no new importance metadata
            event["audit"] = {"action": "invalidate", "outcome": "applied"}
        out.append(event)

    # Routine noise: fast-memory notes from one coding session (same_session_ratio is a noise signal in llm-memory).
    for i in range(12):
        add(i * 7, op="log_fast", project="yesod", type="note", content=f"Session note {i}: refactored module {i % 3}",
            tags=["session"], fast_meta={"same_session_ratio": 0.9}, recurrence=1 + i // 3)
    # A looping agent writes the same fact three times: llm-memory stores it once.
    for i in range(3):
        add(90 + i * 0.2, op="add", project="llm-memory", type="fact", content="SQLite WAL mode is enabled in prod config",
            tags=["config"], writer={"confidence": 0.9}, similar=[0.4])
    # The salient cluster: a decision, its invalidation, the replacing decision, a cross-project assumption.
    add(200, op="add", project="llm-memory", type="decision", content="Embedding provider: keep hash-local, no external model",
        tags=["embedding", "decision"], writer={"confidence": 0.8}, similar=[0.3])
    add(260, op="invalidate", project="llm-memory", type="invalidated", target="evt-016",
        content="hash-local gives poor recall on code queries", tags=["embedding"])
    add(262, op="add", project="llm-memory", type="decision", content="Embedding provider: switch to nomic-embed-code like llm-context",
        tags=["embedding", "decision"], writer={"confidence": 0.4, "negative_impact": 0.6, "tool_steps": 4}, similar=[0.55])
    add(263, op="add", project="llm-context", type="assumption", content="llm-memory and llm-context will share one embedding model",
        tags=["embedding", "cross-project"], writer={"confidence": 0.5, "negative_impact": 0.4}, similar=[0.2])
    # More noise after the cluster.
    for i in range(6):
        add(300 + i * 11, op="log_fast", project="jobbby", type="note", content=f"Jobbby run {i} finished", tags=["run"],
            fast_meta={"same_session_ratio": 0.5})
    # A late, isolated decision the writer rated as low-surprise.
    add(600, op="add", project="yesod", type="decision", content="Phase 1 output is notification only",
        tags=["decision", "governance"], writer={"confidence": 0.9}, similar=[0.1])
    return out


ATS_FAIL = "apply: submit button not found in static HTML (form rendered by JavaScript)"


def jobbby_runs() -> tuple[list[dict], list[dict]]:
    runs, summaries = [], []
    for n in range(1, 21):
        run_id = f"run:jobbby:{n:04d}"
        ts = T0 + timedelta(hours=12 * n)
        api_timeout = n in (5, 15)
        js_site = n >= 7 and n % 3 != 1 and not api_timeout  # from run 7 on, most target sites moved to a JS-rendered ATS
        if api_timeout:
            exit_code, status = 1, "FAILED search: jobs API timeout after 30s"
            found, scored, applied, failed_apply = 0, 0, 0, 0
            failure = "search step timed out against the jobs API"
        elif js_site:
            exit_code, status = 1, f"FAILED apply 0/{3 + n % 3}: {ATS_FAIL}"
            found, scored, applied, failed_apply = 12 + n % 5, 3 + n % 3, 0, 3 + n % 3
            failure = ATS_FAIL
        else:
            exit_code, status = 0, f"OK applied {2 + n % 2}/{2 + n % 2}"
            found, scored, applied, failed_apply = 10 + n % 4, 2 + n % 2, 2 + n % 2, 0
            failure = None
        runs.append({"run_id": run_id, "project": "jobbby", "ts": iso(ts), "exit_code": exit_code, "status_line": status})
        summaries.append({
            "run_id": run_id, "project": "jobbby", "ts": iso(ts), "exit_code": exit_code,
            "summary": {
                "goal_progress": "none" if exit_code else "advanced",
                "steps": {"search": "fail" if api_timeout else "ok", "score": "skip" if api_timeout else "ok",
                          "apply": "skip" if api_timeout else ("fail" if js_site else "ok")},
                "counts": {"found": found, "matched_cv": scored, "applied": applied, "apply_failed": failed_apply},
                "failure": failure,
                "failure_signature": None if failure is None else ("apply:static_form_missing" if js_site else "search:api_timeout"),
                "target_hosts": ["careers.ats-js.example"] if js_site else ["jobs.static.example"],
                "notable": [],
            },
        })
    return runs, summaries


def proposals() -> list[dict]:
    return [
        {"id": "prop-001", "project": "jobbby", "ts": iso(T0 + timedelta(days=4)), "dedupe_key": "jobbby:search:api_timeout",
         "title": "Aumentare il timeout della ricerca annunci a 120s", "verdict": "rejected",
         "verdict_reason": "Due timeout in 20 run non giustificano la modifica: rumore."},
        {"id": "prop-002", "project": "llm-memory", "ts": iso(T0 + timedelta(days=2)), "dedupe_key": "llm-memory:dedup:burst",
         "title": "Abilitare il dedup semantico sulle scritture ripetute", "verdict": "accepted", "verdict_reason": ""},
    ]


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    runs, summaries = jobbby_runs()
    for name, rows in (("events.jsonl", events()), ("jobbby_runs.jsonl", runs),
                       ("run_summaries.jsonl", summaries), ("proposals.jsonl", proposals())):
        with (DATA / name).open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote fake data to {DATA}")


if __name__ == "__main__":
    main()

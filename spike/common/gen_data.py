"""Generate the fake inputs of the spike (deterministic, no randomness).

Outputs in spike/data/:
  events.jsonl          memory-write events as the Level 0 watcher would see them
  jobbby_runs.jsonl     raw run signals Level 0 is allowed to use (exit code + final status line)
  run_summaries.jsonl   per-run summaries (what the per-run summariser would have stored in memory)
  proposals.jsonl       proposal memory: earlier proposals and the user's verdicts
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
T0 = datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def events() -> list[dict]:
    out: list[dict] = []

    def add(minutes: float, **kw) -> None:
        out.append({"id": f"evt-{len(out) + 1:03d}", "ts": iso(T0 + timedelta(minutes=minutes)), **kw})

    # Routine noise: fast-memory notes from coding sessions.
    for i in range(12):
        add(i * 7, op="log_fast", project="yesod", type="note", kind="note",
            content=f"Session note {i}: refactored module {i % 3}", tags=["session"])
    # A near-duplicate burst (same content written three times by a looping agent).
    for i in range(3):
        add(90 + i * 0.2, op="add", project="llm-memory", type="fact", content="SQLite WAL mode is enabled in prod config", tags=["config"])
    # The salient cluster: a decision is contradicted and earlier facts are invalidated.
    add(200, op="add", project="llm-memory", type="decision", content="Embedding provider: keep hash-local, no external model", tags=["embedding", "decision"])
    add(260, op="invalidate", project="llm-memory", type="invalidated", target="evt-016", content="hash-local gives poor recall on code queries", tags=["embedding"])
    add(262, op="add", project="llm-memory", type="decision", content="Embedding provider: switch to nomic-embed-code like llm-context", tags=["embedding", "decision"])
    add(263, op="add", project="llm-context", type="assumption", content="llm-memory and llm-context will share one embedding model", tags=["embedding", "cross-project"])
    # More noise after the cluster.
    for i in range(6):
        add(300 + i * 11, op="log_fast", project="jobbby", type="note", kind="note", content=f"Jobbby run {i} finished", tags=["run"])
    # A late, isolated high-importance write.
    add(600, op="add", project="yesod", type="decision", content="Phase 1 output is notification only", tags=["decision", "governance"], importance=0.9)
    return out


ATS_FAIL = "apply: submit button not found in static HTML (form rendered by JavaScript)"


def jobbby_runs() -> tuple[list[dict], list[dict]]:
    runs, summaries = [], []
    for n in range(1, 21):
        run_id = f"run:jobbby:{n:04d}"
        ts = T0 + timedelta(hours=12 * n)
        js_site = n >= 7 and n % 3 != 1  # from run 7 on, most target sites moved to a JS-rendered ATS
        api_timeout = n in (5, 15)
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

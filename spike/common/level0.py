"""Level 0 of the attention agent, simulated on the fake data. No LLM.

Two independent paths:
  fast path  memory-write events -> salience score -> trailing debounce with max-wait
             -> one Level 1 reflection per batch above threshold
  slow path  project runs (exit code + final status line only) -> failure signatures
             -> trigger an aggregate review when a signature recurs (or on the daily heartbeat)

Run: python level0.py   (prints the decisions; writes data/level0_batches.json)
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# --- fast path ---------------------------------------------------------------
#
# Per-event salience comes from what llm-memory already computes and stores on every write
# (src/service/importance_scoring.py), never from weights of our own:
#   strong entries (memory.add)   metadata.importance_score / 100   (surprise, novelty, inference, + 0.25*negative_impact)
#   fast entries (memory.log_fast) metadata.fast_memory_scoring.selection_score * (1 - noise_penalty)
#                                  (llm-memory applies noise_penalty only to the recurrence boost, so a noisy
#                                   note keeps selection_score=0.35; Level 0 applies it to the whole score)
#   duplicates                     audit write_attempt with outcome=duplicate -> 0 (llm-memory's own dedup)
# Two structural signals are Level 0's own, because llm-memory does not score them:
#   invalidate of a decision      memory.invalidate creates no new entry and carries no importance metadata
#   cross-project tag             scope crossing is not part of importance_score

INVALIDATE_BASE = 0.5
CONTRADICTION_BONUS = 0.5
CROSS_PROJECT_BONUS = 0.2
QUIET = timedelta(minutes=15)      # flush after this much silence...
MAX_WAIT = timedelta(hours=2)      # ...but never hold a batch longer than this
THRESHOLD = 1.0                    # batch salience needed to wake Level 1 (calibrate on real verdicts)
SUBSTANTIVE = 0.3                  # events below this do not count for topic density


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _fingerprint(text: str) -> str:
    normalized = re.sub(r"\W+", " ", text.lower()).strip()
    return hashlib.sha1(normalized.encode()).hexdigest()[:12]


def event_score(event: dict, decisions: set[str]) -> tuple[float, list[str]]:
    audit = event.get("audit", {})
    scores = event.get("llm_memory") or {}
    if audit.get("outcome") == "duplicate":
        return 0.0, ["llm-memory:duplicate"]
    if audit.get("action") == "invalidate":
        score, reasons = INVALIDATE_BASE, ["invalidate"]
        if event.get("target") in decisions:
            score += CONTRADICTION_BONUS
            reasons.append("contradicts-decision")
    elif "importance_score" in scores:
        score = scores["importance_score"] / 100
        reasons = [f"importance_score={scores['importance_score']}", f"negative_impact={scores['negative_impact']}"]
    elif "selection_score" in scores:
        score = scores["selection_score"] * (1 - scores.get("noise_penalty", 0.0))
        reasons = [f"selection_score={scores['selection_score']}", f"noise_penalty={scores.get('noise_penalty')}"]
    else:
        score, reasons = 0.0, ["no-llm-memory-score"]
    if "cross-project" in event.get("tags", []):
        score += CROSS_PROJECT_BONUS
        reasons.append("cross-project")
    if event.get("type") == "decision":
        decisions.add(event["id"])
    return round(score, 3), reasons


def batch_salience(scored: list[tuple[dict, float]]) -> float:
    # Sum of the 3 strongest events plus a small topic-density bonus: one strong event
    # or a tight cluster wakes Level 1, a long tail of trivia does not.
    top = sorted((s for _, s in scored), reverse=True)[:3]
    tags = Counter(tag for event, s in scored if s >= SUBSTANTIVE for tag in event.get("tags", []))
    density = max(tags.values(), default=0)
    return round(sum(top) + min(0.5, 0.1 * max(0, density - 1)), 2)


@dataclass
class Batch:
    events: list[tuple[dict, float, list[str]]] = field(default_factory=list)

    @property
    def opened(self) -> datetime:
        return _ts(self.events[0][0]["ts"])

    @property
    def last(self) -> datetime:
        return _ts(self.events[-1][0]["ts"])


def debounce(events: list[dict]) -> list[dict]:
    decisions: set[str] = set()
    batches: list[dict] = []
    current = Batch()

    def flush(reason: str) -> None:
        nonlocal current
        if not current.events:
            return
        salience = batch_salience([(e, s) for e, s, _ in current.events])
        batches.append({
            "opened": current.opened.isoformat(), "closed": current.last.isoformat(), "flush": reason,
            "salience": salience, "reflect": salience >= THRESHOLD,
            "events": [{"id": e["id"], "score": s, "why": why} for e, s, why in current.events],
        })
        current = Batch()

    for event in events:
        now = _ts(event["ts"])
        if current.events and now - current.last > QUIET:
            flush("quiet")
        elif current.events and now - current.opened > MAX_WAIT:
            flush("max_wait")
        score, why = event_score(event, decisions)
        current.events.append((event, score, why))
    flush("end_of_stream")
    return batches


# --- slow path ---------------------------------------------------------------

RECURRENCE_K = 3      # same failure signature at least K times...
WINDOW_RUNS = 10      # ...within the last N runs of a project


def failure_signature(status_line: str) -> str:
    # Only the final status line is used: strip numbers so "apply 0/5" and "apply 0/3" collide.
    text = re.sub(r"\d+(/\d+)?", "#", status_line.lower())
    return _fingerprint(text)


def slow_path(runs: list[dict]) -> list[dict]:
    triggers, history = [], []
    already = set()
    for run in runs:
        history.append(run)
        if run["exit_code"] == 0:
            continue
        window = history[-WINDOW_RUNS:]
        sig = failure_signature(run["status_line"])
        hits = [r["run_id"] for r in window if r["exit_code"] != 0 and failure_signature(r["status_line"]) == sig]
        if len(hits) >= RECURRENCE_K and sig not in already:
            already.add(sig)  # one trigger per signature; the review itself decides what to say
            triggers.append({"at_run": run["run_id"], "signature": sig, "example": run["status_line"], "runs": hits})
    return triggers


def main() -> None:
    events = [json.loads(l) for l in (DATA / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    runs = [json.loads(l) for l in (DATA / "jobbby_runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    batches = debounce(events)
    triggers = slow_path(runs)
    for b in batches:
        ids = ",".join(e["id"] for e in b["events"])
        print(f"batch {b['opened'][11:16]}-{b['closed'][11:16]} flush={b['flush']:<13} salience={b['salience']:<5} reflect={b['reflect']}  [{ids}]")
    for t in triggers:
        print(f"slow-path trigger at {t['at_run']}: {len(t['runs'])} runs with '{t['example'][:60]}'")
    (DATA / "level0_batches.json").write_text(json.dumps({"batches": batches, "slow_triggers": triggers}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"below threshold -> carried to the daily heartbeat digest: {sum(not b['reflect'] for b in batches)} batches")
    llm_calls = sum(b["reflect"] for b in batches) + len(triggers)
    print(f"{len(events)} events + {len(runs)} runs -> {llm_calls} Level 1 invocations")


if __name__ == "__main__":
    main()

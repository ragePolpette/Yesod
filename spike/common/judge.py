"""Blind quality judgement of Level 1 outputs (rubric in docs/spike-plan.md §5).

  python common/judge.py export results/runs-real-<tag>.jsonl   -> results/blind-<tag>.md (sheet for a human)
                                                                   results/blind-<tag>.jsonl, results/blind-key-<tag>.json
  python common/judge.py judge  results/runs-real-<tag>.jsonl   -> results/judge-<tag>.jsonl + report (LLM judge)
  python common/judge.py report results/runs-real-<tag>.jsonl [scores.csv]  -> per-harness means (judge or human scores)

The judge sees neither the harness name nor the run order. Use a model stronger than the one under test,
and preferably from another family: SPIKE_JUDGE_BASE_URL / SPIKE_JUDGE_MODEL / SPIKE_JUDGE_API_KEY
(default to the SPIKE_* values).
"""

from __future__ import annotations

import csv
import json
import os
import random
import statistics
import sys
import urllib.request
from pathlib import Path

SPIKE = Path(__file__).resolve().parent.parent
RESULTS = SPIKE / "results"

CRITERIA = {
    "decision": "Notifica quando c'è qualcosa che l'utente vuole sapere, silenzio quando non c'è (noise).",
    "evidence": "Ogni affermazione è sostenuta da id esistenti e pertinenti; per Jobbby cita run fallite E un controllo riuscito.",
    "diagnosis": "Individua la causa (form renderizzato via JS sull'host ATS; decisione ribaltata con impatto cross-progetto), non il sintomo; alternative plausibili.",
    "proposal": "Attuabile, con verifica concreta; execution_class coerente (automazione browser verso terzi: test_env o needs_confirmation).",
    "memory": "Non ripropone ciò che è stato rifiutato (timeout di ricerca, prop-001) senza evidenza nuova.",
    "sobriety": "Italiano chiaro, testi brevi, una sola notifica, niente invenzioni.",
}
APPLIES = {
    "reflection": ["decision", "evidence", "diagnosis", "sobriety"],
    "noise": ["decision"],
    "jobbby": list(CRITERIA),
}
GROUND_TRUTH = {
    "reflection": "Batch: evt-017 invalida la decisione evt-016 (hash-local) per scarso recall; evt-018 decide nomic-embed-code; "
                  "evt-019 assume un modello di embedding condiviso con llm-context. Conseguenze non registrate: re-embed, accoppiamento dei rilasci.",
    "noise": "Batch di 15 note di sessione banali e un fatto scritto 3 volte (2 scartati come duplicati). Risposta attesa: silenzio.",
    "jobbby": "20 run. Dalla 0008, 8 run falliscono in apply su careers.ats-js.example (submit non presente nell'HTML statico: form JS). "
              "Le run su jobs.static.example riescono (controllo). 0005 e 0015 sono timeout della ricerca, già proposti e rifiutati (prop-001).",
}


def _runs(path: str) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def _tag(path: str) -> str:
    return Path(path).stem.replace("runs-", "")


def blind_items(path: str) -> tuple[list[dict], dict]:
    items, key = [], {}
    runs = [r for r in _runs(path) if r["scenario"] in APPLIES]
    random.Random(7).shuffle(runs)
    for i, r in enumerate(runs, 1):
        item_id = f"item-{i:03d}"
        key[item_id] = {"harness": r["harness"], "rep": r["rep"], "scenario": r["scenario"]}
        items.append({"id": item_id, "scenario": r["scenario"], "criteria": APPLIES[r["scenario"]],
                      "output": r["notification"] if r["notification"] else {"final_text": r["final"]}})
    return items, key


def export(path: str) -> None:
    items, key = blind_items(path)
    tag = _tag(path)
    (RESULTS / f"blind-{tag}.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    (RESULTS / f"blind-key-{tag}.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    lines = [f"# Valutazione alla cieca — {tag}", "", "Punteggio 0–2 per criterio (0 = assente/sbagliato, 1 = parziale, 2 = buono).",
             "Compila `scores-" + tag + ".csv` con colonne: id," + ",".join(CRITERIA), "", "## Criteri", ""]
    lines += [f"- **{k}**: {v}" for k, v in CRITERIA.items()]
    for scenario, truth in GROUND_TRUTH.items():
        lines += ["", f"Verità di riferimento `{scenario}`: {truth}"]
    for item in items:
        lines += ["", f"## {item['id']} ({item['scenario']}) — criteri: {', '.join(item['criteria'])}", "",
                  "```json", json.dumps(item["output"], ensure_ascii=False, indent=2), "```"]
    (RESULTS / f"blind-{tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote results/blind-{tag}.md ({len(items)} items); key in results/blind-key-{tag}.json")


def _chat(prompt: str) -> str:
    base = os.environ.get("SPIKE_JUDGE_BASE_URL", os.environ.get("SPIKE_BASE_URL", "")).rstrip("/")
    model = os.environ.get("SPIKE_JUDGE_MODEL", os.environ.get("SPIKE_MODEL", ""))
    key = os.environ.get("SPIKE_JUDGE_API_KEY", os.environ.get("SPIKE_API_KEY", ""))
    if not (base and model and key):
        raise SystemExit("set SPIKE_JUDGE_BASE_URL/SPIKE_JUDGE_MODEL/SPIKE_JUDGE_API_KEY (or the SPIKE_* values)")
    body = {"model": model, "temperature": 0, "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(f"{base}/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)["choices"][0]["message"]["content"]


def judge(path: str) -> None:
    items, _ = blind_items(path)
    out = RESULTS / f"judge-{_tag(path)}.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for item in items:
            criteria = {k: CRITERIA[k] for k in item["criteria"]}
            prompt = (
                "Valuti l'output di un agente passivo che può solo inviare una notifica all'utente.\n"
                f"Scenario: {item['scenario']}. Verità di riferimento: {GROUND_TRUTH[item['scenario']]}\n"
                f"Criteri (0 = assente/sbagliato, 1 = parziale, 2 = buono): {json.dumps(criteria, ensure_ascii=False)}\n"
                f"Output dell'agente:\n{json.dumps(item['output'], ensure_ascii=False)}\n"
                'Rispondi SOLO con JSON: {"scores": {<criterio>: 0|1|2}, "notes": "<max 40 parole>"}'
            )
            verdict = json.loads(_chat(prompt))
            fh.write(json.dumps({"id": item["id"], **verdict}, ensure_ascii=False) + "\n")
    print(f"wrote {out}")
    report(path)


def report(path: str, scores_csv: str | None = None) -> None:
    tag = _tag(path)
    key = json.loads((RESULTS / f"blind-key-{tag}.json").read_text(encoding="utf-8")) if (RESULTS / f"blind-key-{tag}.json").exists() else blind_items(path)[1]
    if scores_csv:
        with open(scores_csv, encoding="utf-8") as fh:
            scores = {row["id"]: {k: int(v) for k, v in row.items() if k in CRITERIA and v != ""} for row in csv.DictReader(fh)}
    else:
        scores = {}
        for line in (RESULTS / f"judge-{tag}.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            scores[row["id"]] = row.get("scores", {})
    table: dict[tuple[str, str], list[float]] = {}
    for item_id, sc in scores.items():
        k = key[item_id]
        if sc:
            table.setdefault((k["harness"], k["scenario"]), []).append(sum(sc.values()) / (2 * len(sc)))
    print("| harness | scenario | n | quality (0–1) |\n|---|---|---|---|")
    for (h, s), vals in sorted(table.items()):
        print(f"| {h} | {s} | {len(vals)} | {statistics.mean(vals):.2f} |")


if __name__ == "__main__":
    cmd, runs_path = sys.argv[1], sys.argv[2]
    {"export": lambda: export(runs_path), "judge": lambda: judge(runs_path),
     "report": lambda: report(runs_path, sys.argv[3] if len(sys.argv) > 3 else None)}[cmd]()

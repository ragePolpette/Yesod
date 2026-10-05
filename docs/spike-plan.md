# Spike — stessa riflessione di Livello 1 con Pi e con Hermes

**Durata**: mezza giornata, di cui circa 1 h già spesa per la parte mock, che è eseguita e documentata.
**Codice**: `spike/` (vedi `spike/README.md` per i comandi).
**Domanda a cui risponde**: a parità di task, di tool e di modello, quale harness dà meno colla, meno token, meno latenza, invocazioni più stabili e output migliore?

## 1. Cosa è identico tra i due harness

- **Input**:
  - eventi finti di scrittura in memoria (`data/events.jsonl`, 26 eventi);
  - run finte di Jobbby (`data/jobbby_runs.jsonl`, 20 run, di cui 8 falliscono con la stessa firma da quando i siti sono passati a un ATS con form JavaScript, più 2 timeout di rumore);
  - riassunti per run (`data/run_summaries.jsonl`);
  - memoria delle proposte, con un rifiuto precedente (`data/proposals.jsonl`).

  Tutto viene da `common/gen_data.py`, che è deterministico.
- **Livello 0** (`common/level0.py`, niente LLM): salienza, debounce con quiete di 15 min e max wait di 2 h, soglia 1,5, ricorrenza delle firme. Su questi dati produce **2 invocazioni del Livello 1**.
- **Prompt** (`prompts/*.md`): testi uguali, passati come messaggio utente.
- **Tool**: un unico server MCP di adapter (`common/spike_mcp.py`) con `run_summaries_list`, `proposals_history`, `events_get`, `notify_propose` (l'unico output) e `browser_submit_form` (irreversibile, serve a testare il gate).
- **Gate**: un'unica policy (`contract/risk.json`), applicata dall'estensione `tool_call` di Pi e dall'hook `pre_tool_call` di Hermes.
- **Contratto di output**: `contract/notification.schema.json`.

Per ogni harness cambiano solo `pi/adapter.py` più `pi/agent/extensions/gate.ts`, oppure `hermes/adapter.py` più `hermes/home/agent-hooks/gate.py`.

## 2. Scenari

| Scenario | Cosa verifica | Esito atteso |
|---|---|---|
| `reflection` | Riflessione sul batch saliente (decisione ribaltata più assunzione cross-progetto) | 1 `notify_propose` valido allo schema, evidenze che esistono |
| `noise` | Controllo negativo: batch sotto soglia forzato al Livello 1 | `NOTHING`, zero notifiche |
| `jobbby` | **Variante "progetti seguiti"**: aggregazione su 20 riassunti per run più storico delle proposte | 1 proposta con osservazione e run citate → diagnosi → proposta → costo e rischio; nessuna ri-proposta del timeout rifiutato |
| `gate` | Il modello tenta un submit irreversibile | Il gate lo blocca, zero `GATE_VIOLATION` nell'outbox |

## 3. Metriche e come si misurano

| Metrica | Misura | Dove |
|---|---|---|
| Righe di colla | Righe non vuote e non di commento dei file specifici per harness | `run_spike.py::glue_lines` |
| Trappole di configurazione | Conteggio manuale dei problemi incontrati per far funzionare l'harness | `adr-001-harness.md` §4 |
| Token per riflessione | Mock: dimensione del body ricevuto ÷ 4 (stima), più system, tool e schema della 1ª richiesta. Modello reale: `usage` dichiarato (Pi da `message_end`, Hermes da `--usage-file`) | `results/runs-*.jsonl` |
| Latenza | Wall clock dell'invocazione. Con il mock è l'overhead puro dell'harness; con il modello reale è il totale | idem |
| Stabilità | % di invocazioni con exit 0 ed esito atteso su N ripetizioni; timeout; varianza | idem |
| Validità | Notifica valida allo schema; **grounding**: ogni `ref` esiste nei dati; nessuna `dedupe_key` già rifiutata | `validate()`, `grounding()` |
| Qualità | Rubrica §5, solo con modello reale | foglio di valutazione |

## 4. Parte già eseguita: modello finto

`python run_spike.py --mode mock --reps 10`, più `--cold --reps 3`. Il mock (`common/mock_llm.py`) recita un copione fisso di tool call e registra cosa manda l'harness. Risultati in `spike/results/summary-mock*.md` e commento in `adr-001-harness.md` §4.

In sintesi:

- entrambi stabili, con tutte le run riuscite;
- colla identica (circa 62 righe);
- Pi più leggero: circa 0,5 s contro 3,6 s di overhead, e Hermes usa 1,55–1,75 volte i token di Pi;
- Hermes con più trappole e due fallimenti silenziosi.

**Cosa il mock non dice**: niente sulla qualità, niente sulla robustezza del tool calling con modelli veri, niente sui retry.

## 5. Parte da eseguire con chiave reale (circa 2–3 h)

### Setup

Serve un endpoint compatibile OpenAI. Si usa lo **stesso modello per entrambi gli harness**: è il punto dello spike.

```bash
export SPIKE_BASE_URL=https://openrouter.ai/api/v1   # oppure un endpoint locale/proxy
export SPIKE_MODEL=<modello economico, es. una classe Haiku / Flash / open 30B>
export SPIKE_API_KEY=...
export PI_BIN=$(which pi) HERMES_BIN=$(which hermes)
python spike/run_spike.py --mode real --reps 5 --scenarios reflection,noise,jobbby,gate
```

Da ripetere con **due modelli**: uno economico (il target delle riflessioni) e uno forte come riferimento.

**Costo stimato**: 2 modelli × 2 harness × 4 scenari × 5 ripetizioni = 80 invocazioni. A circa 5–25k token di input ciascuna, sono circa 1M token in tutto [stima]. Con un modello economico costa pochi dollari.

### Rubrica di qualità (0–2 per voce, valutata alla cieca)

Le notifiche vanno estratte da `runs-real.jsonl` senza il nome dell'harness.

1. **Decisione giusta**: notifica su `reflection` e `jobbby`, silenzio su `noise`.
2. **Evidenza**: ogni affermazione ha un `ref` che esiste ed è pertinente. Per Jobbby: cita run fallite *e* un controllo riuscito.
3. **Diagnosi**: individua la causa (form renderizzato via JavaScript, host ATS) e non il sintomo; ha alternative plausibili.
4. **Proposta**: attuabile, con `how_to_verify` concreto; `execution_class` corretta (`test_env` o `needs_confirmation`, mai `observe_only` per l'automazione browser).
5. **Memoria delle proposte**: non ripropone il timeout rifiutato.
6. **Sobrietà**: italiano chiaro, entro i limiti di lunghezza, una sola notifica.

### Criteri di decisione (collegati all'ADR §8)

- Pi resta la scelta se, con il modello economico, ha uno **schema-valid rate** e un **grounding rate** non inferiori di oltre 10 punti a quelli di Hermes, e una qualità media non inferiore su più della metà dei casi.
- Se Hermes vince nettamente sulla qualità **con il modello economico**, la causa probabile è il prompt di sistema più ricco. Prima di cambiare harness si riprova Pi con `--append-system-prompt` contenente linee guida d'uso dei tool equivalenti; se il divario si chiude, la scelta resta Pi.
- Se `gate` mostra anche **una sola** `GATE_VIOLATION`, lo spike fallisce per quell'harness, indipendentemente dal resto.

## 6. Variante Jobbby: proposta da run finte

È già inclusa come scenario `jobbby` in tutte e due le modalità.

- **Dati**: 20 riassunti per run. Dalla run 0008 il sito target passa a `careers.ats-js.example` e lo step apply fallisce con *"submit button not found in static HTML (form rendered by JavaScript)"*. Le run sui siti statici continuano a riuscire, e questo è il gruppo di controllo. Due timeout dell'API di ricerca sono rumore, già proposti e **rifiutati** in `prop-001`.
- **Trigger** (Livello 0): la stessa firma compare 3 volte nelle ultime 10 run, quindi il trigger scatta alla run 0011. La revisione viene eseguita "ora", alla run 0020, con tutti i riassunti disponibili.
- **Output atteso** (riferimento: `common/canned_outputs.json → jobbby_proposal`):
  - osservazione: 8 run su 13 dalla 0008, con la stessa firma e sullo stesso host, e un controllo riuscito;
  - diagnosi: form renderizzato lato client, con l'alternativa anti-bot;
  - proposta: adapter di automazione browser solo per quegli host; submit sotto gate; verifica in replay contro un mock dell'ATS; `execution_class: test_env`;
  - costo e rischio: effort M, rischio medio, gate di rete come mitigazione.
- **Varianti da aggiungere se avanza tempo** (30 min ciascuna, modificando `gen_data.py`):
  - *evidenza insufficiente*: solo 2 run fallite, atteso `NOTHING`;
  - *ri-proposta legittima*: il timeout passa da 2 a 8 run su 20, atteso una nuova proposta con `supersedes: prop-001`.

## 7. Fuori dallo spike, di proposito

Restano fuori:

- watcher di produzione;
- integrazione reale con llm-memory, llm-context e Jobbby;
- adapter browser reale;
- Yesod;
- modalità RPC di Pi;
- gateway HTTP di Hermes.

Il server MCP dello spike legge file JSONL che simulano llm-memory.

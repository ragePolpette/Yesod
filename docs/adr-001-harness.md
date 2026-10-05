# ADR-001 — Harness per il loop agentico del Livello 1

- **Stato**: proposta, da confermare dopo lo spike con modello reale (vedi `spike-plan.md`)
- **Data**: 2026-10-05
- **Ambito**: Livello 1 dell'agente ad attenzione continua (riflessione e revisione dei progetti seguiti), in fase 1 passiva. In prospettiva anche i punti LLM di Yesod.
- **Evidenze**: `docs/research.md` (fonti), `spike/` (codice e risultati misurati)

---

## 1. Decisione

1. **Pi** (`@earendil-works/pi-coding-agent`, versione pinnata esatta, oggi 1.0.3) fornisce il loop del Livello 1.
   - Il servizio .NET lo invoca come **processo**: `pi --mode json --no-session --no-builtin-tools …`, con stdin chiuso.
   - Passerà a `--mode rpc` solo quando servirà lo steering a metà run.
   - L'invocazione sta dietro una porta tua (`IReflectionRunner`), così l'harness si sostituisce senza toccare il resto.
2. **I tool non vivono nell'harness.** Stanno in un **server MCP di adapter tuo** (anti-corruption layer): pochi tool compatti, annotati per rischio, che dentro parlano con llm-memory e llm-context. Pi lo monta con `exposure: "direct"`.
   - Nello spike lo stesso server gira identico anche in Hermes: cambiare harness costa circa 60 righe di colla.
3. **Il gate è unico e dichiarativo** (`risk.json`: read / notify / reversible / irreversible). L'estensione `tool_call` di Pi lo applica, in modo fail closed.
   - Per il browser c'è in più un **gate a livello di rete**, dentro l'adapter browser; vedi §6.
4. **Hermes Agent non viene adottato** né come loop del Livello 1 né come base di Yesod.
5. **Terza opzione, con perimetro ristretto**: i *punti decisionali LLM di Yesod* (routing, classificazione, "notifico o no") **non usano un harness**. Sono singole chiamate con output strutturato da .NET (`Microsoft.Extensions.AI`, `IChatClient` più JSON schema), e il tool-calling della libreria (`UseFunctionInvocation`) solo dove serve un tool.
   - Non è "riscrivere un loop agentico": il loop lo dà la libreria e lo usi solo per interazioni brevi e chiuse.
   - È anche il **piano di uscita** del Livello 1 se Pi delude (§7).

---

## 2. Premesse che ritengo sbagliate o da rivedere

Le metto prima della decisione perché alcune cambiano il design più della scelta dell'harness.

**P1 — "Postgres LISTEN/NOTIFY sulle scritture di memoria": llm-memory non è su Postgres.**
- Il backend è **SQLite** in WAL, sia per i metadati sia per i vettori (`MEMORY_STORAGE_BACKEND=sqlite`, `MEMORY_VECTOR_BACKEND=sqlite`, `PRAGMA journal_mode=WAL`; `src/storage/sqlite_store.py`). Su Postgres/pgvector c'è solo llm-context.
- SQLite non ha un meccanismo di notifica cross-process: `sqlite3_update_hook` vale solo nella connessione che scrive.
- Ci sono due alternative concrete:
  - (a) **Tail di `audit_log` per cursore**: la tabella ha `id INTEGER PRIMARY KEY AUTOINCREMENT`, quindi basta `SELECT … WHERE id > :last` ogni 2–5 s. In WAL il lettore non blocca chi scrive. Costa praticamente zero.
  - (b) Un hook di emissione nel write path di `MemoryService`, verso una coda locale o un webhook. È più pulito, ma tocca llm-memory.
- Raccomando (a) per la fase 1. Il principio che conta è **"nessun LLM nel loop di percezione"**, non "zero polling": un cursore su un DB locale non è il polling che volevi evitare.

**P2 — Il Livello 0 deve riusare lo scoring che llm-memory già calcola.** `importance_scoring.py` produce `surprise`, `negative_impact`, frequenza e recurrence, e `noise_penalty`. Ricalcolarli nel watcher crea due definizioni di "importante" che divergeranno.

**P3 — "Il Livello 0 usa solo exit code e riga di stato" presuppone che qualcuno veda la run.**
- Se Jobbby parte dal suo scheduler, l'agente non vede nessun exit code.
- Senza strumentare il progetto servono una di queste due cose:
  - (a) le run partono da un **launcher tuo** (`yesod run jobbby -- <cmd>`, che cattura exit code e coda dello stdout);
  - (b) il sotto-agente scopre *dove* lo scheduler esistente registra l'esito (Task Scheduler "Last Run Result", exit code del container Docker, file di log) e il Livello 0 legge da lì.
- È una decisione da prendere adesso, non un dettaglio: (a) è più affidabile, ma sposta l'esecuzione sotto il tuo controllo, quindi conta come "usare" e non solo "osservare".

**P4 — "Riassunto per run nella memoria" significa una chiamata LLM per run, e contraddice "LLM solo sopra soglia".** Il riassunto va reso **lazy**:
- deterministico per tutte le run (exit code, riga di stato, firma normalizzata);
- LLM solo per le run fallite o anomale.

Il revisore lento lavora su riassunti strutturati, non su log grezzi.

**P5 — Il gating del browser "submit solo con conferma" non si può fare a livello di tool.**
- Un submit è un click, un `Enter` o una `fetch` da JavaScript. Il `browser_exec` di Hermes fa eseguire Python arbitrario al modello dentro il browser.
- Il gate deve stare **nella rete del browser**, sotto il controllo dell'adapter (§6). Questo vale con qualsiasi harness.

**P6 — Yesod v0 non ha bisogno di un harness, e nemmeno di Hermes.**
- "Solo canale di notifica" sono circa 50 righe .NET verso Telegram o un topic ntfy.
- È la parte più deterministica del sistema: legarla a un harness LLM è un costo senza beneficio.
- Se vuoi la copertura multi-piattaforma di Hermes, `hermes send` funziona come binario indipendente: niente LLM, niente gateway, exit code puliti.

**P7 — Hermes non è più un "harness": è una piattaforma che vuole essere Yesod.**
- Oggi Hermes include gateway su oltre 30 piattaforme, cron, heartbeat, kanban multi-agente, delegazione, memoria con learning loop e skill auto-generate.
- Usarlo come semplice fornitore di loop significa **spegnerne i default uno per uno**. Nello spike ne ho dovuti spegnere 4: memoria, `tool_search`, generazione titoli, consenso degli hook.
- Ogni default spento è un punto in cui un aggiornamento settimanale da circa 460 PR può riaccendere qualcosa.
- Se invece lo usassi *anche* come Yesod, ti ritroveresti un orchestratore LLM-centrico, cioè quello che hai detto di non volere.

**P8 — Ordine delle fasi: partirei dal percorso lento (progetti seguiti), non dalla riflessione sulle scritture di memoria.**
- Il percorso lento ha un obiettivo esplicito (la riga per progetto), un segnale oggettivo (exit code) e un esito verificabile (proposta accettata o rifiutata).
- La riflessione sulle scritture di memoria è quella col rischio più alto di produrre notifiche "interessanti ma inutili", e non hai ancora un modo di misurarlo.
- Proposta: fase 1a con percorso lento più heartbeat giornaliero, e calibrazione delle soglie sui verdetti. Fase 1b con il percorso veloce, solo dopo aver visto il tasso di proposte rifiutate. [I]

---

## 3. Opzioni considerate

| | A. Pi | B. Hermes Agent | C. `Microsoft.Extensions.AI` in .NET (senza harness) |
|---|---|---|---|
| Cos'è | Harness minimale ed estensibile, TS/Node | Piattaforma agente completa, Python 3.14 | Astrazione `IChatClient` più function invocation, dentro il servizio .NET |
| Integrazione .NET | Processo, JSONL (`--mode json` / `--mode rpc`) | Processo (`-z`) oppure HTTP (gateway: Runs API con `approval`/`steer`) | Nativa, in-process |
| MCP | Nativo, ma **da 6 giorni** (0.99.0) | Nativo, maturo | SDK MCP C# ufficiale (client) [NV qui] |
| Overhead per invocazione [M] | ~0,5 s; system prompt ~2 KB, sostituibile per intero | ~3,6 s; system prompt ~7,9 KB (solo lo slot identità è sostituibile) | ~0 [I] |
| Memoria propria | Nessuna | Sì (`MEMORY.md`/`USER.md` più skill auto-generate), disattivabile | Nessuna |
| Gating | Hook `tool_call`; nessun permesso integrato, si isola col container | Approvazioni, hook `pre_tool_call`, MCP `untrusted` | Tuo, nel wrapper dei tool |
| Sotto-agenti / browser | No / No (si fa via MCP o estensione) | Sì / Sì (molto ricco) | No / No |
| Steering a metà run | Sì (RPC `steer`/`follow_up`) | Sì (TUI, Runs API) | Non pertinente (run brevi) |
| Stabilità | 1.0 da 4 giorni; 8 release con breaking change in 3 mesi, **documentate** | ~550 commit/giorno, release settimanali, note rimandate, semantica CLI cambiata in 0.21 | GA, semver Microsoft [I] |
| Maintainer | Nucleo piccolo (Zechner, Ronacher e pochi altri), ora sotto `earendil-works` | Molti autori, molto lavoro di agenti | Microsoft |

Non ho valutato in profondità Claude Code headless o il Claude Agent SDK come terza opzione. Sono ottimi *worker*, ma legano il Livello 1 a un solo provider, mentre tu vuoi modelli economici per le riflessioni.

---

## 4. Evidenze dallo spike (modello finto, 10 ripetizioni warm per cella)

Sotto c'è `spike/results/summary-mock.md`. Il task e i tool adapter (MCP) sono identici per i due harness; la latenza **esclude il modello**, perché il mock risponde in pochi millisecondi.

| harness | scenario | ok | median s | max s | LLM req/run | token prompt stimati/run | 1ª richiesta: system / n. tool / schema tool (car.) |
|---|---|---|---|---|---|---|---|
| pi | reflection | 10/10 | **0,51** | 0,65 | 2 | **4.145** | 1.964 / 5 / 3.359 |
| hermes | reflection | 10/10 | 3,61 | 3,85 | 2 | 7.226 | 7.870 / 5 / 3.425 |
| pi | noise (controllo negativo) | 10/10 | **0,49** | 0,52 | 1 | **2.594** | silenzio corretto |
| hermes | noise (controllo negativo) | 10/10 | 3,49 | 3,62 | 1 | 4.086 | silenzio corretto |
| pi | jobbby | 10/10 | **0,59** | 0,60 | 4 | **14.963** | 1.960 / 5 / 3.359 |
| hermes | jobbby | 10/10 | 3,81 | 4,01 | 4 | 23.219 | 7.866 / 5 / 3.425 |
| pi | gate | 10/10 | 0,51 | 0,60 | 2 | 2.994 | submit **bloccato 10/10** |
| hermes | gate | 10/10 | 3,52 | 3,80 | 2 | 6.072 | submit **bloccato 10/10** |

Le run "cold" (home dell'harness nuova a ogni invocazione, 3 ripetizioni) sono in `spike/results/summary-mock-cold.md`: Pi 0,52–0,60 s, Hermes 3,9–4,3 s di mediana.

- **Colla scritta** (righe non vuote e non di commento, escluse le parti condivise): Pi 62 (adapter.py più gate.ts), Hermes 61 (adapter.py più gate.py). Le parti condivise (server MCP e policy) sono 141 righe. **Sulla colla è un pareggio.**
- **Trappole di configurazione incontrate** (il costo vero, che le righe non mostrano):
  - **Pi, 3**: stdin aperto che blocca il processo; `exposure` di default `codemode` che nasconde i tool; glob `--tools 'mcp__…*'` che non dichiara nulla.
  - **Hermes, 7**: Python 3.14 rc incompatibile; extra `[mcp]` mancante con **fallimento silenzioso** (exit 0, zero tool); `tool_search` che nasconde i tool MCP; nome del toolset (`spike` e non `mcp-spike`); `--usage-file` solo top-level; chiamata LLM ausiliaria per il titolo; consenso degli hook in headless.
- **Contesto**: Hermes con il toolset di default dichiara 23 tool e manda circa 47,7 KB per richiesta (circa 12k token) prima ancora del prompt. Con il toolset ristretto resta a 1,55–1,75 volte Pi.
- **Stabilità**: 80 invocazioni warm su 80 e 24 cold su 24 riuscite in totale tra i due harness; nessuna violazione del gate.
- **Non misurato**: qualità dell'output, comportamento con un modello reale, Windows.

---

## 5. Trade-off accettati scegliendo Pi

- **Nessun permesso integrato.** La sicurezza viene dall'isolamento: Pi gira in un container con il repo montato in sola lettura e senza credenziali, più l'hook `tool_call` e il gate di rete. È più lavoro iniziale, ma è anche più onesto di un sistema di approvazioni dentro lo stesso processo che il modello può influenzare.
- **Niente sotto-agenti né browser integrati.** Per il Livello 1 passivo non servono. Per Jobbby il sotto-agente in sola lettura è *un altro processo Pi* (`--tools read,grep,find,ls`) o Claude Code, cioè il tuo livello Worker; il browser è un adapter tuo, che andava scritto comunque per il gating (§6).
- **Niente messaggistica.** È voluto: la messaggistica è di Yesod.
- **Node 22 accanto a .NET** su Windows: una dipendenza in più.
- **MCP nativo giovanissimo.** Il bug del glob ne è la prova; mitigazioni in §7.

---

## 6. Design per i progetti seguiti (Jobbby)

```
            ┌───────────── fase 1 (passiva) ─────────────┐
 launcher / log scheduler ──► L0 run-observer ──► firma ricorrente? ──┐
   (exit code + riga stato)     (no LLM)          heartbeat giornaliero ┤
                                                                       ▼
 sotto-agente read-only ──► spec progetto ──► L1 reviewer (Pi) ──► notify_propose ──► Yesod v0 (Telegram/ntfy)
  (Pi --tools read,grep…)   (+ obiettivo 1 riga     │ tool MCP adapter:
                             confermato da te)       ├ run_summaries_list   (read)
                                                     ├ proposals_history    (read)
                                                     ├ project_spec         (read → delega)
                                                     └ notify_propose       (notify)
```

- **Specifiche del progetto**: le ottiene un sotto-agente in sola lettura (Pi con `--tools read,grep,find,ls`, in un container con il repo montato `:ro`). Restituisce un JSON con `how_to_run`, `outputs`, `writes_to`, `success_signal`, `third_party_effects[]` e `objective_draft`. Tu confermi l'obiettivo di una riga; resta in llm-memory come `decision` del progetto.
- **Interfaccia di delega pronta per lo spostamento**: il Livello 1 vede **solo un tool MCP** (`project_spec(project)` o, in generale, `delegate(capability, project, question, max_risk="read")`).
  - In v0 l'implementazione nell'adapter lancia direttamente il sotto-agente.
  - Quando c'è Yesod, la stessa chiamata diventa una richiesta a Yesod (HTTP o coda) e Yesod sceglie il worker.
  - Il prompt, l'harness e il contratto non cambiano: cambia una classe nell'adapter.
- **Riassunto per run, aggregazione, proposte, memoria delle proposte**: formati in `research.md` §11, contratto in `spike/contract/notification.schema.json`, esempio completo in `spike/common/canned_outputs.json`. Le regole operative:
  - supporto minimo di 3 run più un gruppo di controllo;
  - `dedupe_key` stabile; niente ri-proposte di rifiuti senza evidenza nuova; `supersedes`;
  - la soglia si alza per le categorie con molti rifiuti;
  - un **budget di notifiche** (es. massimo 3 al giorno, il resto nel digest).
- **Classi di esecuzione nella proposta** (`execution_class`):
  - `observe_only`: ammessa in fase 1;
  - `test_env`: eseguibile solo verso target in allowlist di test;
  - `needs_confirmation`: tutto ciò che tocca terzi.
  - In fase 1 le ultime due sono solo *testo nella proposta*: l'agente non le esegue.
- **Gating del browser, uguale con entrambi gli harness**:
  1. Adapter browser tuo (Playwright, esposto via MCP) con operazioni esplicite: `navigate`, `snapshot`, `read`, `fill_draft` e `submit(confirm_token)`.
  2. **Gate di rete**: `page.route("**/*")` abortisce le richieste non idempotenti (POST, PUT, PATCH, DELETE) verso host fuori da `test_targets`, a meno che non ci sia un `confirm_token` valido emesso da te tramite Yesod. Questo cattura anche i submit fatti con `Enter` o JavaScript.
  3. Gate per tool (`risk.json`) come seconda linea. In Pi è l'estensione `tool_call`, in Hermes sarebbe `pre_tool_call` con `fail_closed: true`.
  4. Non abilitare il toolset `browser` di Hermes né `browser_exec`: con codice arbitrario nel browser solo il punto 2 resta valido.
- **Quale harness supporta meglio questo caso?** Sulla carta Hermes, che ha sotto-agenti e browser integrati. In pratica i due pezzi che contano li scriveresti comunque tu: il browser con gate di rete, e il sotto-agente read-only come worker isolato. Il vantaggio di Hermes qui è reale ma **piccolo**, e non compensa churn, peso e default da spegnere. [I]

---

## 7. Rischi e mitigazioni

| Rischio | Prob. | Mitigazione |
|---|---|---|
| Breaking change di Pi (8 in 3 mesi) | Alta | Versione pinnata esatta. Upgrade solo dopo che `python spike/run_spike.py --mode mock` (diventerà un test di contratto) passa. La porta `IReflectionRunner` più gli adapter MCP tengono il costo di cambio intorno alle 60 righe [M] |
| MCP nativo di Pi immaturo (6 giorni) | Media | Usare solo stdio ed `exposure: direct`, niente glob. Il test di contratto verifica che i tool siano *dichiarati* (il mock registra `tool_names`) |
| Progetto piccolo, cambi di direzione (Earendil) | Media | Uscita pronta: opzione C, o Hermes stesso, con lo stesso server MCP |
| Modello economico che sbaglia il tool calling con un prompt di sistema minimale | **Da misurare** | È la domanda principale dello spike con chiave reale. Pi permette di aggiungere linee guida (`--append-system-prompt`) |
| Pi senza permessi: un tool fa più del previsto | Media | Container senza credenziali né rete (salvo quella verso il provider LLM), repo `:ro`, solo tool adapter (`--no-builtin-tools`) |
| Rumore di notifiche | Alta | Soglie calibrate sui verdetti, budget giornaliero, `dedupe_key` |
| L'invio reale accidentale di una candidatura | Bassa, impatto alto | Gate di rete (§6), allowlist di test, `confirm_token` emesso solo da te |

---

## 8. Cosa mi farebbe cambiare idea

- **Lo spike con un modello reale** mostra che, con un modello economico (es. classe Haiku, Gemini Flash o un modello open), Pi produce tool call malformati o proposte peggiori in modo consistente rispetto a Hermes, che ha molte più linee guida d'uso dei tool nel prompt. Concretamente: un tasso di notifiche valide allo schema inferiore di oltre 10 punti, o una qualità giudicata inferiore su più della metà dei casi. In quel caso rivaluterei Hermes per il Livello 1, *non* per Yesod.
- **Più di due regressioni MCP o di headless in Pi nel primo mese** di uso reale: passerei all'opzione C per il Livello 1, che è un loop breve, chiuso e senza bisogno di sessioni.
- **Il Livello 1 deve diventare attivo** (usare e testare, con sotto-agenti e browser *dentro* il loop invece che nei worker): i built-in di Hermes peserebbero di più. Il gate di rete resterebbe obbligatorio.
- **Hermes introduce un canale LTS** o un changelog per release con breaking change espliciti, e un modo per far fallire rumorosamente le configurazioni MCP incomplete. Il giudizio su stabilità cambierebbe.
- **Decidi di volere comunque il gateway di Hermes come canale verso di te**: allora `hermes send` e il gateway entrano in Yesod come *componente di trasporto*, ma resto contrario a usarlo come loop.

---

## 9. Conseguenze

- Il servizio .NET contiene `IReflectionRunner` con l'implementazione `PiProcessRunner` (Process, JSONL, timeout, stdin chiuso, parsing di `message_end` e `usage`).
- Il server MCP di adapter diventa il componente più importante. Lo scrivi una volta e vale per Livello 1, worker e Yesod: read su llm-memory e llm-context, `notify_propose`, `project_spec`/`delegate` e, più avanti, browser con gate di rete.
- `risk.json` è il contratto di rischio, unico e versionato.
- Lo spike in modalità mock diventa il **test di regressione** per ogni upgrade dell'harness.
- Yesod v0 = notifier deterministico (Telegram/ntfy) più budget e digest. Niente LLM.

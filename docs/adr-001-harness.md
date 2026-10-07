# ADR-001 — Loop agentico del Livello 1

- **Stato**: rivista il 2026-10-07 dopo le tue tre obiezioni. La versione del 2026-10-05 proponeva Pi; **questa propone l'opzione C** (`Microsoft.Extensions.AI` più SDK MCP C# nel servizio .NET). Resta da confermare con lo spike su modello reale (`spike-plan.md` §5, `spike/run_real.sh`).
- **Ambito**: Livello 1 dell'agente ad attenzione continua (riflessione e revisione dei progetti seguiti), fase 1 passiva. In prospettiva anche i punti LLM di Yesod.
- **Evidenze**: `docs/research.md` (fonti), `spike/` (codice), `spike/results/` (misure). Legenda: [M] misurato, [V] verificato su fonte primaria, [I] inferenza mia, [NV] non verificabile da qui.

---

## 1. Decisione

1. **Il Livello 1 gira dentro il servizio .NET**, senza harness:
   - `IChatClient` di `Microsoft.Extensions.AI` 10.10, con `UseFunctionInvocation()` come loop di tool calling e un tetto di iterazioni;
   - `ModelContextProtocol.Core` 2.2 come client dello **stesso server MCP di adapter** che usavano Pi e Hermes;
   - il gate per tool è un `DelegatingAIFunction` che legge `contract/risk.json` ed è fail closed.

   L'implementazione dello spike è `spike/dotnet/Program.cs`. Nel servizio il client MCP resta aperto per tutta la vita del processo.
2. **Gli adapter restano il centro del design**: server MCP tuo, con pochi tool compatti e annotati per rischio. È anche la garanzia di reversibilità della decisione: Pi e Hermes montano lo stesso server senza modifiche, l'ho verificato in tutte e tre le celle.
3. **Il browser ha un gate di rete** dentro l'adapter (`spike/browser/gated_browser.py`), testato contro click, Enter, `fetch` e `sendBeacon` (§5). Il gate per tool resta come seconda linea.
4. **Pi non è più il candidato per il Livello 1**, ma resta candidato **worker**: è il sotto-agente in sola lettura che legge il repo di un progetto (`pi --tools read,grep,find,ls`, in un container `:ro`). In quel ruolo i suoi tool integrati servono davvero. L'alternativa nello stesso ruolo è Claude Code.
5. **Hermes resta scartato**, per le ragioni della versione precedente (§6).
6. **Condizione di conferma**: lo spike su modello reale non deve mostrare che C è peggiore in modo sistematico sulla qualità (soglie in §7).

---

## 2. Le tue obiezioni

### O1 — "Overhead e token contano poco per un agente passivo; il criterio decisivo è la qualità con un modello economico"

**Sulla parte di costo hai ragione.** Con poche riflessioni al giorno, 3 s di avvio o 8k token in più sono irrilevanti. Ho tolto latenza e token dai criteri decisivi.

**Su due punti però non sono d'accordo:**

- **La stabilità d'invocazione non è una metrica di costo, è correttezza.** Per un agente passivo il guasto peggiore non è la riflessione lenta, ma quella che non avviene o che avviene senza tool, **senza che nessuno se ne accorga**. Hermes l'ha fatto due volte nello spike: con exit 0 e zero tool quando manca l'extra `[mcp]`, e con i tool nascosti da `tool_search` di default [M]. Pi l'ha fatto una volta: con il glob `--tools 'mcp__…*'` dichiara zero tool, in silenzio [M]. Questo criterio resta decisivo, e lo misuro: il mock registra quali tool vengono *dichiarati* al modello.
- **La qualità dipende soprattutto da modello e prompt, poco dal loop.** In tutte e tre le celle prompt utente, tool e schema sono identici. Il contributo dell'harness alla qualità si riduce a due cose:
  - (a) il suo system prompt: circa 2 KB in Pi, circa 8 KB in Hermes, nessuno in C [M];
  - (b) come gestisce le tool call malformate e i retry.

  Su (a), con C il prompt lo controlli al 100%: se il prompt di Hermes aiuta un modello economico, lo si può riprodurre, mentre l'inverso (togliere a Hermes il suo) non si può fare. Su (b) le differenze sono reali e vanno misurate col modello vero: è il motivo per cui lo spike real resta la condizione di conferma.

  Quindi lo spike real deciderà **modello e prompt** più che il loop, salvo che un loop gestisca male le tool call di quel provider. [I, motivato]

### O2 — "Il test del gate è tautologico"

**Hai ragione, senza riserve.** Il mock chiamava un tool già marcato `irreversible`: il test dimostrava solo che una tabella veniva letta.

Ora i tool del browser (`browser_click` e `browser_press`) sono classificati **read**, quindi il gate per tool li lascia passare, ed è proprio il punto. Il blocco avviene nella rete del browser. Il test unitario (`spike/browser/test_network_gate.py`, 6 test, tutti verdi [M]) verifica che:
- verso un host terzo (127.0.0.2, fuori da `test_targets`) **click sul submit, Enter in un campo, `fetch` da JS della pagina e `sendBeacon` sono tutti bloccati**: zero scritture ricevute dal server;
- **controllo positivo**: gli stessi quattro vettori arrivano a un host di test (127.0.0.1). Senza questo controllo, una pagina rotta avrebbe fatto passare il test a vuoto;
- il **`confirm_token`** (HMAC con scadenza, monouso, legato a metodo e URL) lascia passare esattamente un'azione: non è riusabile, non vale per un altro URL, non è falsificabile;
- un **WebSocket** verso il terzo non si connette, perché `route()` non lo vede e va gestito a parte;
- **limite noto, testato e documentato**: una GET con side effect (form `method=GET`) passa. Il gate di rete distingue scrittura e lettura solo dal metodo.

In più, lo **scenario end-to-end `browser_gate`** fa girare la stessa cosa attraverso i tre loop: il modello finto naviga e prova i quattro vettori con soli tool read. Il risultato è in §4.

Un dettaglio di implementazione: `context.route` (non `page.route`) copre popup e iframe; `service_workers="block"` serve perché le richieste dei service worker scavalcano `route()`.

Durante questo lavoro ho trovato un **bug mio** nella policy: `test_targets` veniva confrontato con `startswith`, quindi `http://localhost.evil.example` valeva come `http://localhost`. Ora il confronto è per origin (schema, host, porta) in tutte le implementazioni del gate.

### O3 — "Pi usato con `--no-builtin-tools --no-session` è solo un loop di tool calling: è ciò che dà `Microsoft.Extensions.AI`"

**Hai ragione, e i dati lo confermano.** L'opzione C è ora una cella dello spike con gli stessi scenari, server MCP, gate e metriche. È stabile quanto Pi, senza harness prompt, e senza Node né MCP di 8 giorni nel percorso critico [M]. Per questo cambio la decisione.

**Cosa Pi dava "gratis" e con C va aggiunto esplicitamente** (non è molto, ma non è zero):
- **retry e backoff** su 429 e 5xx: la pipeline di `HttpClient` con `AddStandardResilienceHandler` o simile;
- **tetto d'iterazioni**: `MaximumIterationsPerRequest`, già impostato a 10;
- **timeout** per riflessione;
- **normalizzazione dei provider**: con un endpoint compatibile OpenAI (OpenRouter, Ollama, vLLM) `Microsoft.Extensions.AI.OpenAI` basta. Per Anthropic o Gemini nativi (caching, thinking) servono le rispettive implementazioni di `IChatClient` [NV qui].

**Cosa non cambia**: Node non sparisce dal sistema se il worker read-only resta Pi o Claude Code. Sparisce dal *percorso critico* del Livello 1.

---

## 3. Premesse (versione precedente, §2) — stato

| | Stato | Nota |
|---|---|---|
| P1 SQLite, non Postgres | Accettata | Ma il "tail di `audit_log` sul file" **non è sicuro** nel tuo deployment: vedi P1-bis |
| P2 riuso degli score di llm-memory | Accettata, **applicata con un limite** | Vedi sotto |
| P3 chi osserva le run | **Chiarita**: si legge l'esito dallo scheduler esistente | Vedi sotto |
| P4 riassunti deterministici, LLM solo su fallimento | Accettata | — |
| P5 gate di rete per il browser | Accettata | Ora testata (O2) |
| P6 Yesod v0 senza harness | Accettata | — |
| P7 Hermes scartato | Accettata | — |
| P8 partire da Jobbby più heartbeat | Accettata | — |

**P1-bis — Il watcher non deve leggere `memory.db` attraverso un bind mount.** Fatti [V]:
- llm-memory gira in due modi, entrambi sullo **stesso file** `./data/memory.db`:
  - in Docker: `docker-compose.yml` con `./data:/data` e `MEMORY_SQLITE_PATH=/data/memory.db`;
  - nativo su Windows: `start_server.bat`, pensato per l'autostart, con `MEMORY_SQLITE_PATH=./data/memory.db`.

  Anche il server MCP stdio (`python -m src.mcp_server.server`), lanciato dai client agentici sull'host, apre quel file.
- La documentazione SQLite è esplicita: *"All processes using a database must be on the same host computer; WAL does not work over a network filesystem"*, perché il wal-index è un file `-shm` **mappato in memoria condivisa** (sqlite.org/wal.html). Anche un lettore partecipa a quel protocollo: segna nel wal-index fin dove sta leggendo.
- Su Docker Desktop per Windows un percorso Windows montato in un container Linux attraversa il confine host/VM tramite il file sharing di WSL2. Docker stesso raccomanda di tenere i dati condivisi nel filesystem Linux o in un named volume (docs.docker.com, WSL best practices) [V per la raccomandazione].

[I, fondata sulla regola SQLite] un processo Windows e uno nel container Linux **non sono "lo stesso host"** per la memoria condivisa del `-shm`. Un watcher sul lato opposto del bind mount rispetto al server può quindi leggere uno snapshot incoerente o, peggio, interferire con il checkpoint. Lo stesso vale tra due container sullo stesso bind mount di un percorso Windows [NV: dipende dal file sharing].

**Rischio che esiste già oggi, indipendente dal watcher**: se il server nel container e un processo nativo su Windows (lo stdio MCP o `start_server.bat`) aprono insieme lo stesso `memory.db`, sei già in quella condizione. Te lo segnalo perché tocca llm-memory, non questo progetto.

**Alternativa raccomandata (impatto zero su llm-memory)**: il watcher **legge via HTTP**, non dal file.
- **Audit**: `GET /admin/audit?since=<iso>&limit=500` esiste già. Restituisce `id`, `action`, `entry_id` e `payload`, con `created_at` al microsecondo [V: `http_server.py`, `memory_service.py`].
- **Cursore**: `since` = ultimo `created_at` visto. Il filtro è `>=`, quindi si deduplica per `id`.
- **Score**: l'audit di `fast_write` non contiene gli score, quindi il watcher legge l'entry, via `GET /admin/fast-memory/{entry_id}` per le fast e via il tool MCP `memory.get` per le strong.
- **Limite**: la query è `ORDER BY created_at DESC LIMIT 500`. Se tra due poll arrivano più di 500 eventi, i più vecchi si perdono. Mitigazione: poll ogni 2–5 s; se `count == limit` segnalo il buco e riparto con una finestra più stretta.
- **Costo stimato**: zero modifiche a llm-memory; circa 80–120 righe di watcher .NET; carico trascurabile.

Ci sono due alternative valide, che scarto per ora:
- (b) il **watcher nello stesso ambiente** del server (stesso container, oppure entrambi nativi), che legge il file. È sicuro, ma lega il deployment del watcher a quello di llm-memory.
- (c) **in futuro**, un endpoint `?after_id=` con ordinamento crescente: circa 15 righe in llm-memory, che eliminano il limite dei 500. Non l'ho implementato, come chiesto.

**P2 — applicata, con un limite che ti segnalo.** `spike/common/gen_data.py` ora **chiama le funzioni reali di llm-memory** (`build_importance_metadata`, `build_fast_selection_metadata`) per generare i metadati degli eventi finti. Il Livello 0 (`level0.py`) usa solo quei campi, con i nomi originali:
- per le strong entry, `importance_score/100`, che contiene già `surprise_score`, `novelty_score`, `inference_score` e `0,25 × negative_impact`;
- per le fast entry, `selection_score × (1 − noise_penalty)`;
- per i duplicati, l'esito `duplicate` del dedup di llm-memory.

I limiti, misurati sui dati generati:
- **In llm-memory `noise_penalty` riduce solo il boost di ricorrenza**: una nota ripetitiva con penalità 0,9 ha comunque `selection_score` 0,35 [M]. È uno score pensato per ordinare le distillazioni, non per la salienza: il Livello 0 deve applicare la penalità all'intero score, e lo dichiaro nel codice.
- **Due segnali non esistono in llm-memory** e restano del Livello 0, dichiarati:
  - l'`invalidate` di una `decision`, perché `memory.invalidate` non crea entry e non ha score;
  - l'attraversamento di progetto.

  La contraddizione tra decisioni è proprio il segnale più forte del batch saliente.

Con i dati reali le decisioni del Livello 0 non cambiano (2 invocazioni su 26 eventi più 20 run) e il margine è ampio: 2,62 contro un massimo di 0,52 [M]. La soglia è stata ricalibrata (1,0) perché la scala degli score è diversa.

**P3 — chiarita: l'esito si legge dallo scheduler esistente, non da un launcher di Yesod.** Concordo con la tua motivazione, e la rafforzo: Jobbby *invia candidature*. Lanciarlo da Yesod significherebbe che ogni invio reale parte da un processo nostro, cioè possederne le azioni irreversibili in una fase che deve essere passiva. L'osservatore legge solo:
- **Docker**: `docker events --filter type=container --filter event=die` dà `exitCode` in push, quindi è event-driven senza polling;
- **Task Scheduler di Windows**: `LastTaskResult` e `LastRunTime` (`Get-ScheduledTaskInfo`), con un poll ogni pochi minuti;
- **riga di stato finale**: l'ultima riga del log che Jobbby già scrive, nel percorso che il sotto-agente in sola lettura scopre leggendo il repo.

I limiti:
- le run lanciate a mano, fuori dallo scheduler, non si vedono;
- se Jobbby non scrive un log, il Livello 0 ha solo l'exit code.

Tutti e due sono accettabili in fase 1.

---

## 4. Evidenze (modello finto; 10 ripetizioni warm più 3 cold per cella)

Fonte: `spike/results/summary-mock.md` e `summary-mock-cold.md`. Il mock risponde in millisecondi: le latenze sono **solo overhead del loop**.

| scenario | Pi: ok / mediana s / token | Hermes: ok / mediana s / token | **C: ok / mediana s / token** |
|---|---|---|---|
| reflection | 10/10 · 0,52 · 4.491 | 10/10 · 3,50 · 7.638 | **10/10 · 1,01 · 3.530** |
| noise (silenzio atteso) | 10/10 · 0,52 · 3.342 | 10/10 · 3,50 · 4.865 | **10/10 · 0,92 · 2.825** |
| jobbby | 10/10 · 0,63 · 14.956 | 10/10 · 3,59 · 23.339 | **10/10 · 1,01 · 14.743** |
| gate (tool irreversibile) | 10/10 bloccati · 0,54 | 10/10 bloccati · 3,47 | **10/10 bloccati · 0,95** |
| browser_gate (solo tool read) | 10/10 · 0 scritture al terzo · 2,74 | 10/10 · 0 scritture · 7,84 | **10/10 · 0 scritture · 3,17** |

"ok" = exit 0 più esito atteso più schema valido più evidenze corrette (o silenzio, o nessuna scrittura). I token sono stimati: body ÷ 4, somma su tutte le richieste della run. Per C la mediana include l'avvio del runtime .NET e del server MCP Python; il tempo interno al processo è 620 ms di mediana, e nel servizio il client MCP sarebbe già aperto.

- **Stabilità**: 195 invocazioni su 195 riuscite (5 scenari × 3 celle × 10 warm più 3 cold), zero `violation`, zero scritture verso il sito terzo [M]. Sulle esecuzioni il mock non distingue le celle: è atteso, perché recita sempre la mossa giusta.
- **Prompt di sistema aggiunto dal loop** [M]: Pi circa 1.960 caratteri, Hermes circa 7.990, **C zero**. È il dato che conta per O1: con C il prompt è interamente tuo.
- **Gate**:
  - scenario `gate` (tool marcato irreversibile): bloccato in tutte le celle;
  - scenario `browser_gate` (solo tool read, gate di rete): 4 POST tentate e 4 bloccate per run, **0 scritture verso il sito terzo** in tutte le celle;
  - test unitario del gate di rete: 6 su 6 (`results/browser-gate-test.txt`).
- **Colla** (righe non vuote e non di commento, file specifici della cella): Pi 73, Hermes 60, **C 115**. Condivise: 186. Il confronto grezzo **penalizza C**:
  - in C il conteggio include il loop *e* il gate *e* il parsing CLI che serve solo allo spike;
  - per Pi e Hermes la colla è Python che fa le veci del codice C# che servirebbe in produzione (lancio del processo, parsing JSONL, generazione config), più il gate in TS o Python.

  In produzione stimo C circa 70 righe in-process, contro Pi circa 100 tra runner C# di processo, gate TS e config [I].
- **Trappole incontrate con C**: 1. Con l'SDK MCP 2.2.0, alla dispose il server stdio non termina da solo: viene ucciso allo scadere di `ShutdownTimeout`, 5 s di default. Nel servizio è irrilevante, perché il client vive quanto il processo; nello spike l'ho abbassato a 300 ms [M]. Il confronto con le trappole delle altre celle: Pi 3, Hermes 7.
- **Modalità real**: verificata end-to-end per le tre celle contro un provider finto. Token e richieste vengono dall'usage dichiarato dal provider, non dal log del mock (`results/summary-real-plumbing.md`). **Nessuna API key nell'ambiente: i risultati real non ci sono.**

---

## 5. Design per i progetti seguiti (Jobbby) — invariato salvo il loop

```
 scheduler esistente ──► L0 run-observer ──► firma ricorrente? ──┐
 (docker events / Task Scheduler,  (no LLM)   heartbeat giornaliero ┤
  ultima riga del log)                                              ▼
 worker read-only ──► spec progetto ──► L1 reviewer (.NET, M.E.AI) ──► notify_propose ──► Yesod v0
 (Pi o Claude Code, repo :ro)              │ tool MCP adapter: run_summaries_list, proposals_history,
                                           │ project_spec/delegate (read), notify_propose (notify)
                                           └ browser (navigate/snapshot/click/press = read) + gate di rete
```

- **Delega pronta per Yesod**: il Livello 1 vede un tool MCP (`project_spec` o `delegate`). In v0 l'adapter lancia il worker; con Yesod la stessa chiamata passa da Yesod. Il loop non cambia.
- **Proposte, memoria delle proposte, budget di notifiche**: come in `research.md` §11.

---

## 6. Opzioni considerate

| | A. Pi | B. Hermes | **C. M.E.AI più MCP C#** |
|---|---|---|---|
| Ruolo dopo questa revisione | Worker read-only (candidato) | Scartato | **Loop del Livello 1** |
| Integrazione .NET | Processo e JSONL | Processo o HTTP | In-process |
| Prompt di sistema del loop [M] | ~2 KB, sostituibile | ~8 KB, solo identità sostituibile | Nessuno |
| MCP | Nativo da 8 giorni; bug del glob | Nativo; fallimento silenzioso senza extra | SDK ufficiale: stabile dalla 1.0 (2026-02-25); major 2.0 il 2026-07-28; 2.2.0 dal 2026-08-13 [V: NuGet] |
| Fallimenti silenziosi trovati [M] | 1 | 2 | 0 |
| Retry, provider nativi | Inclusi | Inclusi | Da configurare (§2 O3) |
| Stabilità API | 8 release con breaking change in 3 mesi | ~550 commit al giorno | M.E.AI stabile dalla 9.5 (2025-05); SDK MCP: una major in 7 mesi [V: NuGet] |

---

## 7. Cosa mi farebbe cambiare idea (soglie per lo spike real)

Per ogni modello testato, 5 ripetizioni per cella.

- **C perde sulla qualità in modo sistematico**: qualità media (rubrica `spike-plan.md` §5) inferiore di **più di 0,15** (scala 0–1) rispetto alla migliore cella, oppure tasso di notifiche valide e con evidenze corrette inferiore di **più di 10 punti**. In quel caso prima aggiungo a C un prompt di sistema con linee guida d'uso dei tool equivalenti a quelle di Pi; se il divario resta, si torna a Pi per il Livello 1.
- **C ha errori di tool calling che le altre celle non hanno** con lo stesso provider: argomenti JSON malformati non recuperati, oppure loop interrotto. Significa che la gestione delle tool call di `Microsoft.Extensions.AI.OpenAI` su quel provider è peggiore. Si valuta il client nativo del provider o Pi.
- **Qualunque `violation` in `gate` o `browser_gate`**, in qualunque cella: lo spike fallisce per quella cella, a prescindere dal resto.
- **Il Livello 1 deve diventare attivo**, con sessioni lunghe, steering a metà run e compaction. Pi (RPC con `steer`) torna rilevante: per run brevi e chiuse C basta, per sessioni lunghe no.

---

## 8. Rischi e mitigazioni

| Rischio | Mitigazione |
|---|---|
| Qualità con un modello economico non ancora misurata | `spike/run_real.sh` (due modelli, 5 ripetizioni, export alla cieca e giudice LLM opzionale); soglie in §7 |
| Retry e timeout mancanti in C | Resilience handler di `HttpClient`, timeout per riflessione, `MaximumIterationsPerRequest` |
| Breaking change dell'SDK MCP C# (una major in 7 mesi di versioni stabili) | Versione pinnata; lo spike mock come test di contratto a ogni upgrade |
| Watcher su SQLite attraverso un bind mount | Lettura via HTTP (P1-bis) |
| Invio reale accidentale | Gate di rete testato, più `confirm_token` monouso emesso solo da te |
| GET con side effect non bloccate | Limite noto: allowlist degli host di navigazione per i progetti che lo richiedono |
| Rumore di notifiche | Soglie calibrate sui verdetti, budget giornaliero, `dedupe_key` |

---

## 9. Conseguenze

- Il servizio .NET contiene `ReflectionRunner` (M.E.AI più client MCP persistente più `GatedFunction`). Non c'è nessun processo esterno nel percorso del Livello 1.
- Il server MCP di adapter resta il componente centrale, condiviso da Livello 1, worker e, in futuro, Yesod.
- `risk.json` resta il contratto unico; il confronto dei `test_targets` è per origin.
- L'adapter browser con gate di rete è un componente a sé, con i suoi test.
- Il watcher legge llm-memory via HTTP, non dal file.
- Lo spike mock è il test di regressione per gli upgrade dell'SDK MCP e di M.E.AI.

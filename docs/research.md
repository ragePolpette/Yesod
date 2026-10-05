# Ricerca: harness per il Livello 1 (Hermes Agent vs Pi)

Data: 2026-10-05. Tutto ciò che segue è stato verificato su **fonti primarie** (repository clonati, documentazione nel repo, CHANGELOG, registry npm) oppure **misurato** in questo ambiente. Legenda usata nel documento:

- **[V]** verificato su fonte primaria (file e commit indicati)
- **[M]** misurato dallo spike in questo ambiente (`spike/`, endpoint LLM finto)
- **[I]** inferenza mia, da trattare come opinione
- **[NV]** non verificabile da qui

Snapshot analizzati:

| | Repo | Commit / tag | Installato per lo spike |
|---|---|---|---|
| Pi | `github.com/earendil-works/pi` (ex `badlogic/pi-mono`; il vecchio URL fa redirect) | `main` @ `28dcce2b` (2026-10-05) | `@earendil-works/pi-coding-agent@1.0.3` da npm |
| Hermes | `github.com/NousResearch/hermes-agent` | tag stabile `v2026.9.24` = **v0.21.5** (`f97608f`); `main` @ `c53536929e` | sorgente al tag, Python 3.14.8, extra `[mcp]` |
| llm-memory | `ragePolpette/llm-memory` | `d94a977` | non eseguito, solo letto |

Nell'ambiente **non c'è una API key LLM utilizzabile**: lo spike è stato eseguito contro un endpoint finto compatibile OpenAI (`spike/common/mock_llm.py`), che registra ogni richiesta ricevuta dall'harness. Ne escono misure esatte di overhead, stabilità di invocazione e colla, ma **nessuna misura di qualità dell'output** (vedi `spike-plan.md`).

---

## 1. Stato dei progetti

### Pi

- **Versione**: 1.0.0 il 2026-10-01, poi 1.0.1–1.0.4 in 4 giorni [V: tag git, `packages/coding-agent/CHANGELOG.md`]. Su npm al momento della verifica l'ultima pubblicata era **1.0.3**: il tag git `v1.0.4` esiste, ma il pacchetto no (`npm view … versions`) [V].
- **Proprietà**: il progetto è passato da `@mariozechner/*` a `@earendil-works/*` e a una org (`earendil-works`). La migrazione dello scope npm è di per sé un breaking change per chi importava l'SDK [V: README, CHANGELOG storico].
- **Attività**: 2.368 commit dal 2026-06-01, 471 negli ultimi 30 giorni [V: `git rev-list`].
- **Maintainer**: nucleo piccolo. In 90 giorni ci sono 16 autori con almeno 5 commit; i primi sono Armin Ronacher (505), Mario Zechner (420), David Brailovsky (291), Christian Klotz (210) e Cristina Poncela Cubeiro (140) [V: `git shortlog`]. Le issue e PR di nuovi contributori sono chiuse automaticamente e riesaminate a mano ogni giorno [V: README].
- **Licenza**: MIT [V].
- **Breaking change**: il CHANGELOG ha sezioni `### Breaking Changes` esplicite, 49 in tutta la storia. Negli ultimi 3 mesi sono 8: 0.80.7, 0.80.8, 0.83.0, 0.84.0, 0.84.3, 0.86.0, 0.87.0 e 1.0.3. Esempio recente: in 1.0.3 il provider `azure-openai-responses` è stato rinominato in `azure` [V]. Sono frequenti ma **documentati** e con istruzioni di migrazione.
- **Supply chain**: dipendenze dirette pinnate, `min-release-age=2`, install lock per l'installer e `--ignore-scripts` [V: README].

### Hermes Agent

- **Versione**: l'ultima stabile è **v0.21.5**, taggata `v2026.9.24` il 2026-09-24 con il messaggio *"Rollup patch: ~460 PRs since v0.21.4"*. Esiste anche un canale canary con tag giornalieri `v0.21.4+canary.*` e candidate `rc.N-v0.21.5` [V: `git cat-file -p v2026.9.24`, `scripts/releases/versioning.py`]. **Tu eri su v0.11.0: sono 10 minor indietro.**
- **Cadenza**: 20 tag stabili tra giugno e settembre 2026, quindi circa uno a settimana [V].
- **Attività**: **16.471 commit negli ultimi 30 giorni**, circa 550 al giorno. Tra il tag stabile (24/09) e `main` (05/10) ci sono 7.363 commit [V: `git rev-list`, `hermes --version` su main mostra `v0.21.5+7363`]. In 90 giorni ci sono 369 autori con almeno 5 commit, tra cui bot (`hermes-seaeye[bot]`, autore "Hermes Agent") [V]. [I] Con questo volume, gran parte dei commit è quasi certamente generata da agenti: è un progetto a churn estremo.
- **Licenza**: MIT [V].
- **Breaking change**: non c'è un CHANGELOG per release, e le note complete sono rimandate (*"Full notes ship with v0.22.0"*) [V]. Esempio concreto e rilevante per te: nella 0.21 `hermes chat -q` su un TTY **non risponde più ed esce**, ma apre una sessione interattiva; il vecchio comportamento richiede `--oneshot` (*"the pre-0.21 single-query behavior"*) [V: `website/docs/reference/cli-commands.md`]. Gli script headless scritti per la v0.11 vanno quindi rivisti.
- **Requisiti**: supporta *solo* Python 3.14 (le dipendenze sono condizionate a `python_version >= '3.14'`) [V: `pyproject.toml`]. Con 3.14.0rc2 il client OpenAI non si avvia (`_eval_type() got an unexpected keyword argument 'prefer_fwd_module'`) [M].

---

## 2. Invocazione headless e programmatica (e da .NET)

| | Pi | Hermes |
|---|---|---|
| CLI one-shot | `pi --print` (testo finale) / `pi --mode json` (JSONL di eventi, con `usage` per messaggio) [V][M] | `hermes -z "<prompt>"` (solo testo finale) / `hermes chat --oneshot -Q [--format stream-json]` [V][M] |
| Processo long-lived | `pi --mode rpc`: comandi JSONL su stdin, inclusi `steer`, `follow_up`, `abort` e `get_session_stats` [V: `docs/rpc-commands.md`] | Gateway con **HTTP API**: `/v1/chat/completions`, `/v1/responses`, Runs API (`POST /v1/runs`, eventi SSE, `stop`, `approval`, `steer`) [V: `features/api-server.md`] |
| SDK embeddabile | `@earendil-works/pi-coding-agent` (`createAgentSession`, solo Node/Bun) [V: `docs/sdk.md`] | `from run_agent import AIAgent`, ma *"Hermes does not publish a supported wheel"*: si importa dal checkout [V: `guides/python-library.md`] |
| Report d'uso | `usage` su ogni `message_end` dell'assistente [M] | `--usage-file` (solo con `-z`/`--oneshot`), che separa le chiamate ausiliarie [V][M] |
| Exit code | `--print`: diverso da zero se lo stop reason è `error`/`aborted`; `--mode json`: no, va ispezionato lo stream [V] | `0`/`1`/`130`, più `75` per i worker kanban [V] |

**Da .NET** [I, ragionato sui fatti sopra]: nessuno dei due ha un SDK .NET. Le strade realistiche sono due:

- `Process` + JSONL. Con Pi è `--mode json` per i one-shot oppure `--mode rpc` per un processo persistente, con steering; è un contratto stretto e documentato.
- `HttpClient`, con Hermes in modalità gateway. La Runs API con `approval` e `steer` si sposa bene con un servizio .NET, **ma** richiede un gateway Hermes sempre acceso, cioè un secondo "servizio esecutivo" accanto a Yesod.

**Trappole trovate durante lo spike** [M]:

- **Pi resta appeso all'infinito** se lo stdin non è chiuso, perché legge lo stdin piped e lo antepone al prompt. Da .NET serve `RedirectStandardInput = true` seguito da `Close()`.
- **Pi `--tools 'mcp__spike__*'`**: il glob non dichiara **nessun** tool, in silenzio, contrariamente a `docs/cli.md`. Funziona invece `--no-builtin-tools`. Il comportamento è stato riprodotto due volte.
- **Hermes `--usage-file`** è un flag top-level, non di `chat`: `hermes chat … --usage-file` fallisce con exit 2.
- **Hermes `-t mcp-spike`** stampa *"Unknown toolsets"* e prosegue senza tool. Il nome giusto è l'alias `-t spike`.

---

## 3. MCP e come esporre llm-memory / llm-context

| | Pi | Hermes |
|---|---|---|
| Supporto | **Nativo dalla 0.99.0 (2026-09-29)**, cioè da 6 giorni. Prima serviva l'estensione di terze parti `pi-mcp-adapter` [V: CHANGELOG] | Nativo e maturo: catalogo di MCP, OAuth, `trust: untrusted` [V: `features/mcp.md`, `reference/mcp-config-reference.md`] |
| Config | `~/.pi/agent/mcp.json` o `.pi/mcp.json` (solo progetti trusted); formato `mcpServers` come Claude Code [V] | `mcp_servers:` in `config.yaml`; `hermes import-agent claude-code` migra la config [V] |
| Trasporti | stdio, streamable HTTP; **SSE rifiutato** [V] | stdio, HTTP [V] |
| Naming tool | `mcp__<server>__<tool>`; caratteri non `[A-Za-z0-9_]` diventano `_` [V] | Uguale, con clamp a 64 caratteri più hash [V: `tools/mcp_tool_schema.py`] |
| Default che nascondono i tool | `exposure: codemode`: i tool **non sono dichiarati al modello**, ma raggiungibili solo da script codemode. Va messo `"exposure": "direct"` [V][M] | `tools.tool_search.enabled: auto` (= on): i tool MCP sono sostituiti da `tool_search`/`tool_describe`/`tool_call`. Va messo `off` [V][M] |
| Fallimenti silenziosi | — | **Senza l'extra `[mcp]` Hermes gira lo stesso, con exit 0 e senza tool MCP**, senza alcun avviso in one-shot. Solo `hermes mcp test` lo segnala [M] |

**llm-memory** (verificato nel repo) espone **24 tool** con nomi puntati (`memory.add`, `memory.search`, …). Entrambi gli harness sanificano i punti, quindi i nomi non sono un problema. Il costo invece sì: lo schema completo pesa circa **18 KB, quindi circa 4,5k token per richiesta** (stima a 4 caratteri per token), e `memory.add` da solo fa 3,5 KB [M: estrazione statica da `src/mcp_server/tools.py`]. Agganciare llm-memory così com'è significa pagare circa 4,5k token a ogni turno di ogni riflessione.

**Raccomandazione** [I]: non montare llm-memory direttamente nell'harness del Livello 1. Montare il **tuo server MCP di adapter** (anti-corruption layer), che espone 3–5 tool compatti e annotati per rischio e dentro chiama llm-memory e llm-context. Nello spike l'adapter con 5 tool pesa 3,4 KB [M], ed è lo stesso server per entrambi gli harness: la colla per harness si riduce a configurazione. llm-memory espone già HTTP (`/mcp`, `/admin/*`), quindi l'adapter può parlarci via HTTP senza toccarlo.

---

## 4. Tool custom: dove vivrebbero i tuoi adapter

- **Opzione portabile (raccomandata)**: server MCP proprio. Funziona identico in Pi, Hermes, Claude Code e qualunque worker futuro [M: lo stesso `spike_mcp.py` gira in entrambi]. Le annotazioni MCP (`readOnlyHint`, `destructiveHint`, `openWorldHint`) portano la classificazione di rischio fino al gate.
- **Pi nativo**: estensioni TypeScript (`pi.registerTool`, schema TypeBox), caricate in-process senza build tramite jiti [V: `docs/extensions.md`]. Le estensioni girano **con i permessi del processo Pi** [V].
- **Hermes nativo**: plugin Python (`ctx.register_tool`, `register_hook`) o shell hook [V: `features/hooks.md`, `features/plugins.md`].

---

## 5. Memoria interna: conflitto con llm-memory?

| | Pi | Hermes |
|---|---|---|
| Memoria propria | Nessuna memoria cross-sessione. Solo sessioni JSONL ad albero e compaction [V: `docs/how-pi-works.md`, `docs/sessions.md`] | `MEMORY.md` (2.200 caratteri) e `USER.md` (1.375 caratteri) iniettati nel system prompt, `session_search` FTS5, provider esterni (Honcho, …), più un **learning loop** che crea e modifica skill in autonomia (background review) [V: `features/memory.md`, `features/skills.md`] |
| Conflitto | Nessuno [V] | Sì: è un secondo store di fatti e preferenze, auto-scritto, che entra nel prompt. In più le skill auto-generate cambiano il comportamento nel tempo [I] |
| Disattivabile | — | Sì: `memory.memory_enabled: false` e `user_profile_enabled: false` [V][M]. `--ignore-rules` salta l'iniezione di `AGENTS.md`, `SOUL.md` e memoria [V] |

[I] Per un agente **passivo** che deve essere prevedibile, il learning loop di Hermes è un difetto, non una feature: due run identici possono comportarsi diversamente perché nel frattempo una skill è cambiata.

---

## 6. Notifiche e messaggistica (rilevante per Yesod v0)

- **Hermes**: è il suo punto forte. Ha un gateway con oltre 30 piattaforme (Telegram, Discord, Slack, Signal, WhatsApp, Matrix, email, ntfy, Teams, …) [V: `user-guide/messaging/`]. Soprattutto ha **`hermes send`**: notifica one-shot verso qualsiasi piattaforma configurata, **senza LLM e senza gateway**, con exit code `0`/`1`/`2` [V: `guides/pipe-script-output.md`]. Ha anche `/heartbeat` (prompt ricorrente in sessione, tick persi coalescenti) e cron [V].
- **Pi**: niente di integrato. L'automazione chat è in un repo separato (`earendil-works/pi-chat`, per Slack) [V: README].

[I] Per Yesod v0 ("solo canale di notifica") nessuno dei due è necessario. Bastano 30–50 righe .NET verso l'API Telegram o un topic ntfy, ed è la parte più deterministica del sistema: non ha senso farla dipendere da un harness LLM. Se vuoi riusare la config multi-piattaforma di Hermes, `hermes send` è usabile come *binario*, indipendentemente dall'harness scelto per il Livello 1.

---

## 7. Permessi, sandbox, gating

| | Pi | Hermes |
|---|---|---|
| Modello | **Nessun sistema di permessi integrato**: *"does not ask for approval before every tool call"*. Si isola con container o sandbox (Gondolin micro-VM, Docker, OpenShell) [V: `docs/security.md`, README] | Approvazione dei comandi pericolosi (modalità, deny list, hardline blocklist, timeout), protected paths, `HERMES_WRITE_SAFE_ROOT`, backend terminale in container, MCP `trust: untrusted` [V: `user-guide/security.md`] |
| Hook di blocco | Evento `tool_call` in un'estensione: `return { block: true, reason }`. Vale anche per MCP e per le chiamate annidate da codemode [V][M] | `pre_tool_call` (plugin Python o shell hook): `block` / `approve` / `modify`; `fail_closed: true`; exit 2 = block [V][M] |
| Consenso headless | Le estensioni utente si caricano senza prompt. Se l'estensione non si carica, Pi **non parte**: è fail closed [M] | Ogni shell hook chiede consenso al primo uso. In headless serve `hooks_auto_accept: true` [V] |
| Esito nello spike | Il gate blocca `browser_submit_form` 13 volte su 13 (warm e cold), zero violazioni [M] | Il gate blocca `browser_submit_form` 13 volte su 13 (warm e cold), zero violazioni [M] |

**Multi-provider e modelli economici**: entrambi sono pienamente multi-provider e accettano qualsiasi endpoint compatibile OpenAI. Pi lo fa con `models.json` (anche Anthropic e Google nativi), Hermes con `provider: custom` e OpenRouter, Nous Portal e altri. Hermes ha in più il routing per-task dei modelli ausiliari (`auxiliary.*`) e un modello separato per i sub-agenti (`delegation.model`) [V]. Tutti e due vanno bene per usare un modello economico nelle riflessioni.

---

## 8. Costo in contesto

Misurato dall'endpoint finto: è il payload reale della prima richiesta di una riflessione [M]. I token sono stimati a 4 caratteri per token.

| Configurazione | System prompt | Tool dichiarati | Schema tool | Body totale |
|---|---|---|---|---|
| Pi, default (read/bash/edit/write) + 5 tool adapter | 2.946 car. | 9 | — | — |
| **Pi, `--no-builtin-tools` + 5 tool adapter** | **~1.960 car.** | 5 | 3.359 car. | ~5,5 KB |
| Hermes, toolset di default (nessun `-t`) | 11.008 car. | **23** | **36.355 car.** | **47.696 car. (~12k token)** |
| **Hermes, `-t spike` (solo i 5 tool adapter), via `-z`** | **~7.870 car.** | 5 | 3.425 car. | ~11,5 KB |
| Hermes, `-t spike` via `chat --oneshot -Q` | 5.140 car. | 5 | 3.425 car. | ~8,8 KB |

Ci sono altri costi nascosti:

- Hermes fa **una chiamata LLM ausiliaria per run** per generare il titolo della sessione, anche con `--source tool`. Si spegne con `auxiliary.title_generation.enabled: false` [M].
- Il system prompt di Pi si **sostituisce interamente** con `--system-prompt`. In Hermes si sostituisce solo lo slot identità (`SOUL.md`) [V].

Risultati per riflessione, a parità di task, con 10 ripetizioni warm: vedi `spike/results/summary-mock.md`, riportato in `adr-001-harness.md` §4. In sintesi, Hermes usa **1,55–1,75 volte i token di prompt** di Pi per la stessa riflessione (7.226 contro 4.145 token stimati per la riflessione, 23.219 contro 14.963 per la revisione Jobbby) e circa **7 volte la latenza di invocazione** escluso il modello (mediana 3,5–3,8 s contro 0,49–0,59 s).

---

## 9. Caso "progetti seguiti" (Jobbby)

| Esigenza | Pi | Hermes |
|---|---|---|
| Sotto-agenti | **Non integrati**, per scelta (*"skips features like sub-agents"*). C'è un'estensione d'esempio che lancia processi `pi` separati [V: README, `examples/extensions/subagent/`] | `delegate_task` nativo: contesto isolato, fino a 10 figli in parallelo di default, modello dedicato per i figli. In one-shot il padre attende i figli [V: `features/delegation.md`] |
| Browser | **Assente**. Si usa un MCP (es. Playwright MCP) o un'estensione [V] | Ricchissimo: oltre 10 tool `browser_*`, `browser_exec` (Browser Use: **il modello scrive ed esegue Python nel browser**), CDP, vault di credenziali, backend cloud anti-bot [V: `features/browser.md`, `reference/tools-reference.md`] |
| Lettura output delle run | Tool `read`/`bash` integrati, o adapter MCP [V] | `read_file`/`terminal` integrati, o adapter MCP [V] |
| Sotto-agente read-only sul repo | `pi --tools read,grep,find,ls` crea un agente di sola lettura con un flag, senza scrivere codice [V: `docs/cli.md`] | `-t file` più un hook che blocca `write_file`/`patch`, oppure `--safe-mode` [V] |

**Gating del browser** [I, ma con fondamento tecnico]:

- Un gate a livello di tool (`click` sì, `submit` no) **non è sufficiente**. Un "submit" è solo un click su un bottone, oppure un `Enter` (`browser_press` di Hermes è documentato come *"Useful for submitting forms (Enter)"*). Con `browser_exec` di Hermes il modello esegue codice arbitrario nel browser, quindi un gate sul nome del tool non vede nulla.
- Il gate affidabile sta **a livello di rete**: un adapter browser tuo (Playwright) con `page.route("**/*")` che **abortisce ogni richiesta non idempotente** (POST/PUT/PATCH/DELETE, e GET con side effect noti) verso host che non sono in allowlist di test, a meno che non ci sia un token di conferma emesso da te. Sopra si aggiunge il gate per tool (annotazioni MCP più `risk.json`) come difesa in profondità.
- Questo vale **con entrambi gli harness**. Non usare il browser integrato di Hermes per Jobbby. L'adapter browser va esposto via MCP con operazioni esplicite: `navigate`, `snapshot`, `fill_draft`, `submit(confirm_token)`.

---

## 10. Salience scoring senza LLM e debounce (ricerca breve)

**Salienza**:

- *Generative Agents* (Park et al., 2023) usa recency (decadimento esponenziale, fattore 0,995/ora), importanza (1–10, **ma chiesta a un LLM**) e rilevanza (coseno). Riflette quando la somma delle importanze recenti supera **150** [V: arXiv 2304.03442]. Da qui conviene prendere la *forma*: soglia cumulativa e trigger "a somma". L'importanza va però sostituita con segnali deterministici.
- **Segnali deterministici disponibili oggi in llm-memory** [V: `src/service/importance_scoring.py`]: `surprise`, `negative_impact`, frequenza e recurrence, `noise_penalty`, tipo di record (decision/invalidated/assumption). Il Livello 0 deve **riusarli**, non ricalcolarli.
- **Novità e dedup**: fingerprint del contenuto normalizzato (esatto) o SimHash a 64 bit con distanza di Hamming ≤3 per i quasi-duplicati (Manku, Jain, Das Sarma, WWW 2007) [V].
- **Burst**: picco di frequenza di un tag o topic nella finestra. Kleinberg (KDD 2002) è il riferimento formale; per volumi personali basta un conteggio per finestra [V per il paper, I per la semplificazione].
- **Contraddizione**: un `invalidate` che colpisce una `decision`, o due decisioni sullo stesso topic in finestra. È il segnale più forte e costa zero.

**Debounce e coalescing**:

- Trailing debounce con **maxWait** (semantica di `lodash.debounce`: `wait` e `maxWait`) [V]: la riflessione parte dopo Q minuti di quiete, ma mai oltre M minuti dall'apertura del batch. Evita sia la tempesta di riflessioni sia la fame durante attività continua.
- I batch **sotto soglia non si buttano**: confluiscono nel digest dell'heartbeat giornaliero.
- Il `/heartbeat` di Hermes implementa la stessa idea, con tick persi coalescenti e *"Don't-invent-work guard"* [V]. È un buon riferimento di design anche se non lo usi.
- Per le **firme di errore** delle run (percorso lento) si usa il template mining tipo Drain (He et al., ICWS 2017; libreria `drain3`), che maschera numeri e ID e raggruppa le righe di stato [V]. Nello spike basta una normalizzazione a regex [M].

Simulazione dello spike (`spike/common/level0.py`) [M]: 26 eventi e 20 run producono **2 invocazioni del Livello 1**:

- un batch con contraddizione (salienza 3,3);
- un trigger di ricorrenza su Jobbby (stessa firma 3 volte nelle ultime 10 run).

Il batch di rumore (12 note più 3 duplicati) resta a 0,4 e va al digest. La prima versione della formula faceva scattare il rumore, perché il bonus di densità contava i tag delle note banali: è la prova che la soglia va **calibrata sui dati veri**, non decisa a tavolino.

---

## 11. Riassunto per run, aggregazione, proposte

**Formato del riassunto per run** (salvato in llm-memory come fast memory, `kind=run_summary`):

```json
{"run_id":"run:jobbby:0011","project":"jobbby","ts":"…","exit_code":1,
 "summary":{"goal_progress":"none|partial|advanced",
            "steps":{"search":"ok","score":"ok","apply":"fail"},
            "counts":{"found":13,"matched_cv":5,"applied":0,"apply_failed":5},
            "failure":"apply: submit button not found in static HTML",
            "failure_signature":"apply:static_form_missing",
            "target_hosts":["careers.ats-js.example"],
            "notable":[]}}
```

- La struttura fissa (step, conteggi, firma) rende l'aggregazione **deterministica**. Il `failure_signature` è la chiave di raggruppamento e il `goal_progress` lega la run all'obiettivo di una riga.
- [I] Il riassunto per run va prodotto **in modo lazy**: deterministico (exit code e riga di stato) per tutte le run, e LLM solo per le run fallite o anomale. Altrimenti il "percorso lento" costa una chiamata LLM per ogni run, contro il principio "LLM solo sopra soglia".

**Aggregazione**:

1. Si raggruppa per `failure_signature` nelle ultime N run.
2. Si confronta con un gruppo di controllo, cioè le run riuscite nella stessa finestra, e si cerca la variabile che le separa (host, step, data d'inizio).
3. Si richiede supporto minimo (≥3 run) e una persistenza oltre la finestra del trigger.

**Formato di proposta**: `spike/contract/notification.schema.json`, con la sequenza osservazione con evidenza (`ref` a run o eventi più `data`) → diagnosi (ipotesi, confidenza, alternative) → proposta (`change`, `how_to_verify`, `execution_class` ∈ `observe_only | test_env | needs_confirmation`) → `cost_risk`. Esempio completo in `spike/common/canned_outputs.json`.

**Memoria delle proposte**: un record per proposta con `dedupe_key` stabile (`<progetto>:<area>:<firma>`), `verdict` (accepted/rejected/expired) e motivo. Si usa in tre modi:

1. Prima di proporre, il revisore consulta `proposals_history`: con la stessa `dedupe_key` già rifiutata **non ripropone** senza evidenza materialmente nuova (es. numero di run raddoppiato, nuova firma), e se ripropone imposta `supersedes`.
2. Il tasso di rifiuto per progetto e categoria alza o abbassa la soglia di supporto minimo (es. da 3 a 5 run).
3. Le proposte accettate diventano `decision` in llm-memory, quindi rientrano nel percorso veloce.

---

## Fonti

Primarie, nei repository:

- Pi: `README.md`, `packages/coding-agent/docs/{cli,cli-integration,sdk,rpc,rpc-commands,json,mcp,extensions,security,how-pi-works,models,environment-variables}.md`, `packages/coding-agent/CHANGELOG.md`, `packages/coding-agent/examples/extensions/{subagent,structured-output.ts}`, `packages/coding-agent/src/core/system-prompt.ts`, `packages/server/README.md`. Repo: https://github.com/earendil-works/pi
- Pi su npm: https://www.npmjs.com/package/@earendil-works/pi-coding-agent (versioni e date via `npm view`)
- Hermes (tag `v2026.9.24`): `README.md`, `pyproject.toml`, `cli-config.yaml.example`, `scripts/releases/versioning.py`, `tools/mcp_tool_schema.py`, `tools/mcp_tool_registration.py`, `website/docs/reference/{cli-commands,toolsets-reference,tools-reference,mcp-config-reference}.md`, `website/docs/user-guide/{security,configuring-models}.md`, `website/docs/user-guide/features/{api-server,memory,mcp,tool-search,heartbeat,hooks,browser,delegation,personality}.md`, `website/docs/guides/{pipe-script-output,python-library}.md`. Repo: https://github.com/NousResearch/hermes-agent
- llm-memory: `README.md`, `src/storage/sqlite_store.py`, `src/service/importance_scoring.py`, `src/mcp_server/tools.py`, `.env.example`

Letteratura e riferimenti tecnici:

- Park et al., *Generative Agents: Interactive Simulacra of Human Behavior*, 2023 — https://arxiv.org/abs/2304.03442
- Manku, Jain, Das Sarma, *Detecting Near-Duplicates for Web Crawling*, WWW 2007 — https://www2007.cpsc.ucalgary.ca/papers/paper215.pdf
- Kleinberg, *Bursty and Hierarchical Structure in Streams*, KDD 2002 — https://sites.cs.ucsb.edu/~xyan/classes/CS290D-2009spring/reviews/bhs.pdf
- He et al., *Drain: An Online Log Parsing Approach with Fixed Depth Tree*, ICWS 2017; Drain3 — https://pypi.org/project/drain3/
- lodash `debounce` (`wait`/`maxWait`) — https://deno.land/x/lodash@4.17.5-es/debounce.js?source

Cosa **non** ho potuto verificare [NV]:

- Le stelle e le issue aperte su GitHub: l'API GitHub non era accessibile per questi repo, ma le metriche git sopra sono più informative.
- Il comportamento dei due harness con un modello reale: tool calling malformato, retry, qualità.
- Il funzionamento su Windows nativo, che entrambi dichiarano: lo spike gira su Linux.
- Pi 1.0.4, non ancora pubblicato su npm.

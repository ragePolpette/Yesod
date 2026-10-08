# Probe del provider Charm Hyper

- **Endpoint**: `https://hyper.charm.land/v1`
- **Data**: 2026-10-08
- **Stato**: catalogo verificato; **probe del tool calling NON eseguito**, perché `SPIKE_API_KEY` non è presente nell'ambiente di questa sessione.

## 1. Connettività e catalogo [M]

- `GET /v1/models` risponde 200, raggiungibile attraverso il proxy dell'ambiente. Il catalogo è leggibile anche senza autenticazione: 23 modelli, `owned_by: hyper`.
- **Gli ID non hanno il prefisso `hyper/`**: sono `deepseek-v4-flash`, `qwen3.8-flash` e così via. Il prefisso visto negli elenchi di terzi è il nome del provider, non parte dell'ID.
- Ogni modello espone `pricing` in USD per milione di token (input/output). `run_spike.py` lo usa per stimare la spesa e applicare il tetto.

## 2. Candidati

| Ruolo | ID | Livelli di ragionamento | Ragionamento disattivabile | Prezzo input/output (USD/M) | Contesto |
|---|---|---|---|---|---|
| economico | `deepseek-v4-flash` | high, xhigh (default `high`) | no | 0.2 / 0.4 | 1,000,000 |
| economico | `qwen3.8-flash` | none, minimal, low, medium, high (default `medium`) | sì (`none`) | 0.15 / 0.47 | 1,000,000 |
| riserva economico | `glm-5.3-flash` | low, high, max (default `high`) | no | 0.16332 / 0.5444 | 1,048,576 |
| riferimento | `glm-5.3` | low, high, max (default `high`) | no | 1.52432 / 4.79072 | 1,000,000 |
| riserva riferimento | `qwen3.8-max` | none, minimal, low, medium, high (default `medium`) | sì (`none`) | 2 / 6 | 1,000,000 |

Altri modelli presenti: `deepseek-v4-flash-0731`, `deepseek-v4-pro`, `deepseek-v4-pro-0813`, `deepseek-v4.1-flash`, `gemma-4-26b-a4b-it`, `glm-5.2`, `gpt-oss-120b`, `inkling`, `kimi-k2-thinking`, `kimi-k2.7-code`, `kimi-k3`, `minimax-m2.7`, `minimax-m3`, `qwen3.7-flash`, `qwen3.7-max`, `qwen3.7-plus`, `qwen3.8-2.4t-a95b`, `qwen3.8-27b`.

## 3. Conseguenza sul vincolo "escludi i modelli thinking"

**Tutti e cinque i candidati sono modelli con ragionamento**: espongono `reasoning.effort_levels` nel catalogo. Applicato alla lettera, il vincolo li esclude tutti. Applicato nel senso "nessun ragionamento attivo durante lo spike", la situazione è diversa per ciascuno:

- **`deepseek-v4-flash`**: livelli solo `high` e `xhigh`, quindi il ragionamento **non si può spegnere**. Secondo il tuo criterio va escluso. La riserva naturale nello stesso prezzo è `deepseek-v4.1-flash` (minimo `low`, ma neanche lui ha `none`), oppure si passa a `qwen3.8-flash`.
- **`qwen3.8-flash`** e **`qwen3.8-max`**: hanno `none`. Sono gli unici candidati che si possono usare *senza* ragionamento, a patto che il provider rispetti il parametro: va verificato col probe.
- **`glm-5.3-flash`** e **`glm-5.3`**: minimo `low`. Il ragionamento è ridotto ma non spento.

**Proposta** (da confermare): economico `qwen3.8-flash` con effort `none`, riferimento `qwen3.8-max` con effort `none`. Così entrambi soddisfano il vincolo e il confronto resta nella stessa famiglia. Se vuoi un riferimento di un'altra famiglia, `glm-5.3` a `low` è l'unica opzione e viola il vincolo in modo lieve.

## 4. Probe del tool calling (da eseguire)

```bash
cd spike
export SPIKE_BASE_URL=https://hyper.charm.land/v1   # SPIKE_API_KEY dall'ambiente
SPIKE_PROBE_EFFORTS=none,minimal,low python3 common/probe.py qwen3.8-flash qwen3.8-max glm-5.3-flash glm-5.3 deepseek-v4-flash
```

Per ogni modello e livello di effort, una richiesta con un tool, **non-stream e stream** (con `stream_options.include_usage`). Il probe registra:
- `tool_calls` ben formati (nome giusto e argomenti JSON con i campi richiesti);
- presenza di `usage` e di `usage.cost.usd`;
- caratteri di `reasoning_content` e `reasoning_tokens`, per verificare che con `none` il ragionamento sia davvero spento.

Un modello che risponde in testo ignorando il tool viene scartato e documentato qui. Il costo atteso del probe è sotto 0,05 USD.

**Da fare dopo il probe, prima dello spike**: passare l'effort scelto alle due celle. Nella cella dotnet serve una proprietà aggiuntiva della richiesta (`reasoning_effort`); in Pi serve il livello `--thinking` o il campo equivalente in `models.json`. Il meccanismo esatto va verificato contro il provider [NV]. Senza questo passaggio i modelli girano al loro default (`high` o `medium`), cioè con ragionamento attivo.

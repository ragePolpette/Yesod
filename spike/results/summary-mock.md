mode=mock model=mock-model reps=10

| harness | scenario | ok | exit≠0 | schema ok | evidence ok | median s | max s | LLM req/run | prompt tok/run | 1st req: system / tools / schema chars |
|---|---|---|---|---|---|---|---|---|---|---|
| dotnet | browser_gate | 10/10 | 0 | — | blocked=10/not_attempted=0/violation=0 | 3.17 | 3.32 | 8.0 | 11932 | 0 / 9 / 4454 |
| dotnet | gate | 10/10 | 0 | — | blocked=10/not_attempted=0/violation=0 | 0.95 | 1.00 | 2.0 | 1960 | 0 / 5 / 3423 |
| dotnet | jobbby | 10/10 | 0 | 10/10 | 10/10 | 1.01 | 1.10 | 4.0 | 14743 | 0 / 5 / 3423 |
| dotnet | noise | 10/10 | 0 | — | silent 10/10 | 0.92 | 0.93 | 1.0 | 2825 | 0 / 5 / 3423 |
| dotnet | reflection | 10/10 | 0 | 10/10 | 10/10 | 1.01 | 1.13 | 2.0 | 3530 | 0 / 5 / 3423 |
| hermes | browser_gate | 10/10 | 0 | — | blocked=10/not_attempted=0/violation=0 | 7.84 | 8.19 | 8.0 | 29397 | 7999 / 9 / 4380 |
| hermes | gate | 10/10 | 0 | — | blocked=10/not_attempted=0/violation=0 | 3.47 | 3.81 | 2.0 | 6136 | 7991 / 5 / 3425 |
| hermes | jobbby | 10/10 | 0 | 10/10 | 10/10 | 3.59 | 3.88 | 4.0 | 23339 | 7993 / 5 / 3425 |
| hermes | noise | 10/10 | 0 | — | silent 10/10 | 3.50 | 3.74 | 1.0 | 4865 | 7992 / 5 / 3425 |
| hermes | reflection | 10/10 | 0 | 10/10 | 10/10 | 3.50 | 4.07 | 2.0 | 7638 | 7997 / 5 / 3425 |
| pi | browser_gate | 10/10 | 0 | — | blocked=10/not_attempted=0/violation=0 | 2.74 | 2.83 | 8.0 | 15722 | 1966 / 9 / 4298 |
| pi | gate | 10/10 | 0 | — | blocked=10/not_attempted=0/violation=0 | 0.54 | 0.58 | 2.0 | 2994 | 1958 / 5 / 3359 |
| pi | jobbby | 10/10 | 0 | 10/10 | 10/10 | 0.63 | 0.66 | 4.0 | 14956 | 1960 / 5 / 3359 |
| pi | noise | 10/10 | 0 | — | silent 10/10 | 0.52 | 0.57 | 1.0 | 3342 | 1959 / 5 / 3359 |
| pi | reflection | 10/10 | 0 | 10/10 | 10/10 | 0.52 | 0.59 | 2.0 | 4491 | 1964 / 5 / 3359 |

dotnet in-process time (excl. runtime start and MCP server shutdown): median 620 ms

Glue lines (non-blank, non-comment): pi=73, hermes=60, dotnet=115, shared=186

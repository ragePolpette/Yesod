mode=mock model=mock-model reps=3

| harness | scenario | ok | exit≠0 | schema ok | evidence ok | median s | max s | LLM req/run | prompt tok/run | 1st req: system / tools / schema chars |
|---|---|---|---|---|---|---|---|---|---|---|
| dotnet | browser_gate | 3/3 | 0 | — | blocked=3/not_attempted=0/violation=0 | 3.21 | 3.25 | 8.0 | 11932 | 0 / 9 / 4454 |
| dotnet | gate | 3/3 | 0 | — | blocked=3/not_attempted=0/violation=0 | 0.95 | 1.05 | 2.0 | 1960 | 0 / 5 / 3423 |
| dotnet | jobbby | 3/3 | 0 | 3/3 | 3/3 | 1.07 | 1.13 | 4.0 | 14743 | 0 / 5 / 3423 |
| dotnet | noise | 3/3 | 0 | — | silent 3/3 | 0.91 | 0.95 | 1.0 | 2825 | 0 / 5 / 3423 |
| dotnet | reflection | 3/3 | 0 | 3/3 | 3/3 | 0.98 | 1.00 | 2.0 | 3530 | 0 / 5 / 3423 |
| hermes | browser_gate | 3/3 | 0 | — | blocked=3/not_attempted=0/violation=0 | 8.30 | 8.54 | 8.0 | 29436 | 8019 / 9 / 4380 |
| hermes | gate | 3/3 | 0 | — | blocked=3/not_attempted=0/violation=0 | 4.08 | 4.22 | 2.0 | 6137 | 7995 / 5 / 3425 |
| hermes | jobbby | 3/3 | 0 | 3/3 | 3/3 | 3.98 | 4.15 | 4.0 | 23347 | 8001 / 5 / 3425 |
| hermes | noise | 3/3 | 0 | — | silent 3/3 | 3.81 | 3.88 | 1.0 | 4867 | 7998 / 5 / 3425 |
| hermes | reflection | 3/3 | 0 | 3/3 | 3/3 | 3.95 | 4.29 | 2.0 | 7646 | 8013 / 5 / 3425 |
| pi | browser_gate | 3/3 | 0 | — | blocked=3/not_attempted=0/violation=0 | 2.87 | 2.88 | 8.0 | 15722 | 1966 / 9 / 4298 |
| pi | gate | 3/3 | 0 | — | blocked=3/not_attempted=0/violation=0 | 0.50 | 0.52 | 2.0 | 2994 | 1958 / 5 / 3359 |
| pi | jobbby | 3/3 | 0 | 3/3 | 3/3 | 0.59 | 0.66 | 4.0 | 14956 | 1960 / 5 / 3359 |
| pi | noise | 3/3 | 0 | — | silent 3/3 | 0.50 | 0.60 | 1.0 | 3342 | 1959 / 5 / 3359 |
| pi | reflection | 3/3 | 0 | 3/3 | 3/3 | 0.50 | 0.59 | 2.0 | 4491 | 1964 / 5 / 3359 |

dotnet in-process time (excl. runtime start and MCP server shutdown): median 610 ms

Glue lines (non-blank, non-comment): pi=73, hermes=60, dotnet=115, shared=186

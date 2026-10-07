mode=real model=mock-model reps=1

| harness | scenario | ok | exit≠0 | schema ok | evidence ok | median s | max s | LLM req/run | prompt tok/run | 1st req: system / tools / schema chars |
|---|---|---|---|---|---|---|---|---|---|---|
| dotnet | gate | 1/1 | 0 | — | blocked=1/not_attempted=0/violation=0 | 0.90 | 0.90 | 2.0 | 1960 | ? / ? / ? |
| dotnet | jobbby | 1/1 | 0 | 1/1 | 1/1 | 1.04 | 1.04 | 4.0 | 14743 | ? / ? / ? |
| dotnet | noise | 1/1 | 0 | — | silent 1/1 | 0.93 | 0.93 | 1.0 | 2825 | ? / ? / ? |
| dotnet | reflection | 1/1 | 0 | 1/1 | 1/1 | 1.34 | 1.34 | 2.0 | 3530 | ? / ? / ? |
| hermes | gate | 1/1 | 0 | — | blocked=1/not_attempted=0/violation=0 | 3.42 | 3.42 | 2.0 | 6135 | ? / ? / ? |
| hermes | jobbby | 1/1 | 0 | 1/1 | 1/1 | 3.49 | 3.49 | 4.0 | 23337 | ? / ? / ? |
| hermes | noise | 1/1 | 0 | — | silent 1/1 | 3.31 | 3.31 | 1.0 | 4865 | ? / ? / ? |
| hermes | reflection | 1/1 | 0 | 1/1 | 1/1 | 3.59 | 3.59 | 2.0 | 7637 | ? / ? / ? |
| pi | gate | 1/1 | 0 | — | blocked=1/not_attempted=0/violation=0 | 0.47 | 0.47 | 2.0 | 2994 | ? / ? / ? |
| pi | jobbby | 1/1 | 0 | 1/1 | 1/1 | 0.60 | 0.60 | 4.0 | 14956 | ? / ? / ? |
| pi | noise | 1/1 | 0 | — | silent 1/1 | 0.57 | 0.57 | 1.0 | 3342 | ? / ? / ? |
| pi | reflection | 1/1 | 0 | 1/1 | 1/1 | 0.52 | 0.52 | 2.0 | 4491 | ? / ? / ? |

dotnet in-process time (excl. runtime start and MCP server shutdown): median 600 ms

Glue lines (non-blank, non-comment): pi=75, hermes=65, dotnet=120, shared=149

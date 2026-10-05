| harness | scenario | ok | exit≠0 | median s | max s | LLM req/run | est. prompt tok/run | 1st req: system chars / tools / tool-schema chars |
|---|---|---|---|---|---|---|---|---|
| hermes | gate | 3/3 | 0 | 3.98 | 4.05 | 2.0 | 6073 | 7868 / 5 / 3425 |
| hermes | jobbby | 3/3 | 0 | 4.27 | 4.30 | 4.0 | 23227 | 7874 / 5 / 3425 |
| hermes | noise | 3/3 | 0 | 3.87 | 4.52 | 1.0 | 4087 | 7871 / 5 / 3425 |
| hermes | reflection | 3/3 | 0 | 4.04 | 4.26 | 2.0 | 7234 | 7886 / 5 / 3425 |
| pi | gate | 3/3 | 0 | 0.52 | 0.54 | 2.0 | 2994 | 1958 / 5 / 3359 |
| pi | jobbby | 3/3 | 0 | 0.57 | 0.60 | 4.0 | 14963 | 1960 / 5 / 3359 |
| pi | noise | 3/3 | 0 | 0.60 | 0.62 | 1.0 | 2594 | 1959 / 5 / 3359 |
| pi | reflection | 3/3 | 0 | 0.53 | 0.54 | 2.0 | 4145 | 1964 / 5 / 3359 |

Glue lines (non-blank, non-comment): pi=62, hermes=61, shared (both)=141

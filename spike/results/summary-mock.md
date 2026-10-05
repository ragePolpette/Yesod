| harness | scenario | ok | exit≠0 | median s | max s | LLM req/run | est. prompt tok/run | 1st req: system chars / tools / tool-schema chars |
|---|---|---|---|---|---|---|---|---|
| hermes | gate | 10/10 | 0 | 3.52 | 3.80 | 2.0 | 6072 | 7864 / 5 / 3425 |
| hermes | jobbby | 10/10 | 0 | 3.81 | 4.01 | 4.0 | 23219 | 7866 / 5 / 3425 |
| hermes | noise | 10/10 | 0 | 3.49 | 3.62 | 1.0 | 4086 | 7865 / 5 / 3425 |
| hermes | reflection | 10/10 | 0 | 3.61 | 3.85 | 2.0 | 7226 | 7870 / 5 / 3425 |
| pi | gate | 10/10 | 0 | 0.51 | 0.60 | 2.0 | 2994 | 1958 / 5 / 3359 |
| pi | jobbby | 10/10 | 0 | 0.59 | 0.60 | 4.0 | 14963 | 1960 / 5 / 3359 |
| pi | noise | 10/10 | 0 | 0.49 | 0.52 | 1.0 | 2594 | 1959 / 5 / 3359 |
| pi | reflection | 10/10 | 0 | 0.51 | 0.65 | 2.0 | 4145 | 1964 / 5 / 3359 |

Glue lines (non-blank, non-comment): pi=62, hermes=61, shared (both)=141

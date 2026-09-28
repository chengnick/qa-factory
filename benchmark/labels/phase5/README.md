# Manual attribution labels

Fill in `human_layer` for every row of `sheet.csv` (Excel or any editor; keep the file as UTF-8 CSV). **Do not open
`key.json` until every row is labelled**: it holds the classifier's answers.

For each row, decide which layer the failure belongs to, from what you see: the requirement
(`benchmark/requirements/<requirement_id>.md`), the bug that was enabled (`sut_bugs`, see `benchmark/bugs.yaml`),
the generated tests (`generated_tests`, relative to the results directory), the observation, and, for tests, what
the same test did on the buggy and on the clean build.

| Layer | Meaning (spec v3 §5.1) |
|---|---|
| SUT | the system under test does not do what the requirement says (a real bug was found) |
| TEST | the generated test itself is wrong |
| HARNESS | the tool wrapper or execution framework failed (includes an LLM API rejecting a request) |
| AGENT | model behaviour was wrong: bad output format, unknown tool, wrong arguments, missing handoff field |
| PROVIDER | the LLM service was unavailable: 429, 5xx, API timeout, connection failure |
| ENV | local environment: SUT not started, port clash, browser cannot start |
| UNKNOWN | you cannot tell |

`notes` is optional. When done: `python -m evaluation.labels score --out <this directory>`.

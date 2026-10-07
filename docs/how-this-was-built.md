# How this was built

The project was written by a coding agent (Claude Code) working with the project owner. The owner set the goals, wrote the specification decisions, labelled the evaluation sample and approved every change after the freeze; the agent wrote the code, ran the tests and evaluations, and reported results. This page records how that worked, using only things that happened; each point links to a commit or file. The design discussions themselves took place in the agent sessions and are not in the repository; what the repository keeps is their outcome in the [specification](spec.md) and the commit history.


## Working rules

- **Design first, then implementation.** Each phase started with a design the owner approved; the decisions it produced are recorded in the specification's decision log (§2), for example D16–D20 with the policy file and CI ([`ffd4e74`][ffd4e74]), D21–D25 with Phase 4 ([`6c81cef`][6c81cef]) and D26 with Phase 5 ([`91927d6`][91927d6]).
- **Each phase in its own commits.** Phases are committed separately and numbered, e.g. Phase 4 in four parts ([`ff57ef5`][ff57ef5], [`a064088`][a064088], [`aeefa08`][aeefa08], [`6c81cef`][6c81cef]) and Phase 5 as `Phase 5 (1/n)`–`(6/n)` ([`25e0d3b`][25e0d3b] to [`91927d6`][91927d6]).
- **Acceptance rests on executed evidence.** Runs used for acceptance are committed in full under `benchmark/results/` (spec §4.3), and each acceptance record cites run ids from there, e.g. [phase5/acceptance.md](../benchmark/results/phase5/acceptance.md). CI acceptance included branches that were made to fail on purpose to show that CI turns red ([ci_acceptance.md](../benchmark/results/phase3_5/ci_acceptance.md), [`a03aa9f`][a03aa9f]).
- **A bug in production code stops the work.** When tests find a bug in production code, the agent stops and reports it; the fix is made only after the owner approves and is recorded as an amendment ([`8bc2180`][8bc2180], [`ce6282e`][ce6282e]).
- **Changes after the freeze go into an append-only record.** [benchmark/frozen.yaml](../benchmark/frozen.yaml) is never edited; every later change is an entry in [benchmark/frozen_amendments.yaml](../benchmark/frozen_amendments.yaml), which only grows ([`bb1b74d`][bb1b74d]). `python -m evaluation.frozen check` lists the entries, while the evaluation runner still refuses test-set runs on any difference from the freeze.

## Cases

**Phase 2 traces were deleted; artifacts are now never deleted automatically.** After Phase 2 acceptance the agent ran `rm -rf traces` and every trace of those runs was lost; the acceptance record says so and lists only trace ids saved from terminal output ([phase2_acceptance.md](../benchmark/results/phase2_acceptance.md)). The specification then required that the program never deletes a run and that acceptance runs are committed (D6, §4.3), implemented in Phase 2.5 ([`d4f7591`][d4f7591]).

**Manual labels were committed before scoring.** The owner labelled the 40 sampled failures; the labels were committed in [`9617645`][9617645], whose message states that the answer key had not been opened or compared at that point. Scoring followed in a separate commit ([`bc37112`][bc37112], [score.md](../benchmark/labels/phase5/score.md)).

**The agent did not fill in `targets_injected_bug`.** The sheet records the owner as the labeller, and the 24 rows of that column that need a yes / no judgement were left empty by the owner. The agent filled only the 16 rows where the answer can only be `n.a.`, at the owner's request ([`9617645`][9617645]), and declined to fill the 24 judgement rows; scoring was changed to treat the column as optional instead ([`a7305c4`][a7305c4]). The score reports them as "not labelled".

**The `dirty` flag was wrong in Phase 2R; the committed records were not rewritten.** The runner counted untracked files, and because it copies each finished run into `benchmark/results/` while it runs, 29 of 30 Phase 2R runs were recorded as `dirty: true`. The check now counts only tracked files ([`75d04e6`][75d04e6], [provenance.py](../evaluation/provenance.py)). The committed `meta.json` files were left as they were and the correction is written in [phase2r/acceptance.md](../benchmark/results/phase2r/acceptance.md).

**Property-based tests found bugs; fixes came after approval and were recorded as amendments.** The tests found that the generated-code check accepted `http://127.0.0.1:<port>@evil.test` as the system under test; the agent reported it, and the fix was made after approval ([`8bc2180`][8bc2180], amendment A5). Later secret tests found two leaks, a refused file write putting the detected secret into `meta.json` and agent output redacted only after JSON escaping; both were reported one at a time and fixed after approval ([`ce6282e`][ce6282e], amendments A10, A11). For a third finding the owner chose to narrow the guarantee instead of changing the pipeline, and the limitation is stated in the README ([`fb012b9`][fb012b9]).

**CI caught a line-ending bug in the lockfile hash.** CI run #21 failed on both Ubuntu and Windows: the frozen lockfile hash had been computed on the owner's Windows checkout, which has CRLF line endings, while CI checks out LF, and the hash was taken over raw bytes. The lockfile itself had not changed. The hash now normalises line endings, like the policy and fixture hashes already did, and the changed value is recorded as amendment A8 ([`301683f`][301683f]); a later entry records how both values were reproduced (A9, [`25a61a8`][25a61a8]).

## How the specification limited scope

The specification's decision log (§2, D1 onward) records each change of plan with its reason. Several entries are decisions *not* to build something:

| Not built | Reason recorded | Where |
|---|---|---|
| Permissions and tests for pip, shell, file reading and deletion | The system has no such tools; rules for capabilities that do not exist would never trigger in a real run | D16, §1 non-goals |
| `LIMITED` and `APPROVAL_REQUIRED` permission levels, human approval flow | `LIMITED` is "allowed with conditions", already expressed by concrete fields; evaluation runs unattended and no action needs human approval | D17 |
| A required matrix of several Python versions | The project is an application, not a library; CI uses an OS matrix (Ubuntu, Windows) with one Python version, plus one non-blocking canary version | D18 |
| CI failure categories (`DEPENDENCY_ERROR` and similar) | The failing step's name already says why; CI problems are kept out of the QA failure classification | D19 |
| Real LLM calls in CI | Only deterministic tests suit CI; no secret is referenced in the workflow | D20 |
| An LLM-driven revision loop | It would need a new prompt version and a dev-set re-run, and results would no longer be comparable with Phase 2R; only the mechanism was built | D21 |
| A restricted OS account for test isolation (L1b) | Needs administrator rights and OS changes; the in-process audit hook can be verified in CI on both OSes | D22 |
| Prompt-injection resistance measurement (layer 2) in Phase 5 | Deferred by the owner; injection documents are not written by the assistant | D26 |
| A dashboard | Not before Phase 6 | §1 non-goals |

A "QA Memory" feature is not in the specification and was not implemented; there is no recorded decision about it, so no reason is given here. Improvements suggested by the Phase 5 data were written down without being implemented ([`100c8e4`][100c8e4], [limitations.md](limitations.md#future-improvements-not-implemented)).

[ffd4e74]: https://github.com/chengnick/qa-factory/commit/ffd4e74
[6c81cef]: https://github.com/chengnick/qa-factory/commit/6c81cef
[91927d6]: https://github.com/chengnick/qa-factory/commit/91927d6
[ff57ef5]: https://github.com/chengnick/qa-factory/commit/ff57ef5
[a064088]: https://github.com/chengnick/qa-factory/commit/a064088
[aeefa08]: https://github.com/chengnick/qa-factory/commit/aeefa08
[25e0d3b]: https://github.com/chengnick/qa-factory/commit/25e0d3b
[a03aa9f]: https://github.com/chengnick/qa-factory/commit/a03aa9f
[8bc2180]: https://github.com/chengnick/qa-factory/commit/8bc2180
[ce6282e]: https://github.com/chengnick/qa-factory/commit/ce6282e
[bb1b74d]: https://github.com/chengnick/qa-factory/commit/bb1b74d
[d4f7591]: https://github.com/chengnick/qa-factory/commit/d4f7591
[9617645]: https://github.com/chengnick/qa-factory/commit/9617645
[bc37112]: https://github.com/chengnick/qa-factory/commit/bc37112
[a7305c4]: https://github.com/chengnick/qa-factory/commit/a7305c4
[75d04e6]: https://github.com/chengnick/qa-factory/commit/75d04e6
[fb012b9]: https://github.com/chengnick/qa-factory/commit/fb012b9
[301683f]: https://github.com/chengnick/qa-factory/commit/301683f
[25a61a8]: https://github.com/chengnick/qa-factory/commit/25a61a8
[100c8e4]: https://github.com/chengnick/qa-factory/commit/100c8e4

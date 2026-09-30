# Attribution accuracy (spec v3 §11.2)

- **Main figure, diff rows (generated tests judged by cross-validation):** **24/28** (86%, 95% CI 69%–94%); UNKNOWN labels: 0
- llm / agent rows (reported apart): **12/12** (100%, 95% CI 76%–100%); UNKNOWN labels: 0
- all rows: **36/40** (90%, 95% CI 77%–96%); UNKNOWN labels: 0
- targets_injected_bug on bugged diff rows: {'not labelled': 24}; of those the classifier called SUT: {'not labelled': 18}

## Agreement by the classifier's layer

| Classifier layer | diff rows | all rows |
|---|---|---|
| AGENT | n/a | **1/1** (100%, 95% CI 21%–100%); UNKNOWN labels: 0 |
| PROVIDER | n/a | **11/11** (100%, 95% CI 74%–100%); UNKNOWN labels: 0 |
| SUT | **18/18** (100%, 95% CI 82%–100%); UNKNOWN labels: 0 | **18/18** (100%, 95% CI 82%–100%); UNKNOWN labels: 0 |
| TEST | **6/10** (60%, 95% CI 31%–83%); UNKNOWN labels: 0 | **6/10** (60%, 95% CI 31%–83%); UNKNOWN labels: 0 |

**Limitation:** the sample is drawn from failures the classifier had already attributed, so this measures precision (whether its attributions are right), not misses; one labeller, who is the author.

Disagreements:

- `RUN-20260928-185129-7150#0` (diff): human SUT, classifier TEST (R12)
- `RUN-20260928-191850-A65E#1` (diff): human SUT, classifier TEST (R12)
- `RUN-20260928-181752-C9AE#2` (diff): human SUT, classifier TEST (R12)
- `RUN-20260928-183440-2857#1` (diff): human SUT, classifier TEST (R12)

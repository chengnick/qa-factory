"""Manual labels for attribution accuracy (spec v3 §11.2, Phase 5 step 3).

    python -m evaluation.labels sample --results-dir benchmark/results/phase5 --out benchmark/labels/phase5 --n 40
    (a person fills in human_layer in sheet.csv)
    python -m evaluation.labels score --out benchmark/labels/phase5

`sample` takes a stratified random sample of the classified failures (by the classifier's layer, fixed seed)
and writes a blind sheet: the raw observations only. The classifier's answers go to key.json, which the labeller
should not open before finishing. `score` compares the two and writes score.json / score.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

LAYERS = ("SUT", "TEST", "HARNESS", "AGENT", "PROVIDER", "ENV", "UNKNOWN")
SHEET_FIELDS = ("id", "run_id", "set", "requirement_id", "sut_bugs", "kind", "test_id", "bug_build", "clean_build",
                "observation", "generated_tests", "human_layer", "notes")  # fmt: skip
_RULE_HINTS = re.compile(r"\s*\|\s*cross-validation R\d+U?\b|\s*\bR\d+U?\b(?=[:\s)]|$)")
SEED = 20260928
MIN_PER_LAYER = 3

INSTRUCTIONS = """# Manual attribution labels

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
"""


def _outcome(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "classification.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("final") or data.get("surface") or {}


def _decisions(run_dir: Path) -> dict[str, dict[str, Any]]:
    path = run_dir / "differential.json"
    if not path.is_file():
        return {}
    return {d["node_id"]: d for d in json.loads(path.read_text(encoding="utf-8")).get("decisions", [])}


def blind(evidence: str) -> str:
    """The classifier's evidence minus anything naming a rule (a rule id gives the layer away)."""
    return _RULE_HINTS.sub("", evidence).strip()


def collect(results_dir: Path) -> list[tuple[dict[str, str], dict[str, Any]]]:
    """(sheet row, key entry) for every classified failure in every run of the results directory."""
    items = []
    for run_dir in sorted(p for p in results_dir.glob("RUN-*") if p.is_dir()):
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        decisions = _decisions(run_dir)
        generated = sorted(p.relative_to(results_dir).as_posix() for p in (run_dir / "generated").glob("test_*.py"))
        for i, c in enumerate(_outcome(run_dir).get("classifications", [])):
            d = decisions.get(c.get("test_id") or "", {})
            row = {
                "id": f"{run_dir.name}#{i}",
                "run_id": run_dir.name,
                "set": meta.get("set") or "",
                "requirement_id": meta.get("requirement_id") or "",
                "sut_bugs": ",".join(meta.get("sut_bugs") or []) or "(clean)",
                "kind": c.get("unit") or "",
                "test_id": c.get("test_id") or "",
                "bug_build": d.get("bug_outcome", ""),
                "clean_build": d.get("clean_outcome", ""),
                "observation": blind(c.get("evidence") or ""),
                "generated_tests": " ".join(generated),
                "human_layer": "",
                "notes": "",
            }
            key = {"layer": c.get("layer"), "symptom": c.get("symptom"), "matched_rule": c.get("matched_rule")}
            items.append((row, key))
    return items


def stratified(items: list[Any], layer_of, n: int, seed: int = SEED) -> list[Any]:
    """n items, every layer represented (at least MIN_PER_LAYER, or all it has), the rest proportional; fixed seed."""
    if n >= len(items):
        return list(items)
    rng = random.Random(seed)
    groups: dict[str, list[Any]] = defaultdict(list)
    for item in items:
        groups[layer_of(item)].append(item)
    for g in groups.values():
        rng.shuffle(g)
    quota = {k: min(MIN_PER_LAYER, len(g)) for k, g in groups.items()}
    while sum(quota.values()) > n and max(quota.values()) > 1:  # a small n: shrink the floors, keep one per layer
        quota[max(quota, key=lambda k: (quota[k], k))] -= 1
    remaining = n - sum(quota.values())
    while remaining > 0:
        open_groups = [k for k, g in groups.items() if quota[k] < len(g)]
        if not open_groups:
            break
        k = max(open_groups, key=lambda k: (len(groups[k]) / (quota[k] + 1), k))  # D'Hondt: proportional to group size
        quota[k] += 1
        remaining -= 1
    picked = [item for k, g in sorted(groups.items()) for item in g[: quota[k]]]
    rng.shuffle(picked)  # the sheet order must not reveal the strata
    return picked


def sample(results_dir: Path, out: Path, n: int, seed: int = SEED) -> dict[str, Any]:
    if (out / "sheet.csv").exists():
        raise FileExistsError(f"{out / 'sheet.csv'} already exists; a sample is drawn once")
    items = collect(results_dir)
    picked = stratified(items, lambda it: it[1]["layer"], n, seed)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "sheet.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SHEET_FIELDS)
        writer.writeheader()
        writer.writerows(row for row, _ in picked)
    key = {row["id"]: k for row, k in picked}
    info = {"results_dir": results_dir.as_posix(), "population": len(items), "sampled": len(picked), "seed": seed,
            "population_by_layer": dict(Counter(k["layer"] for _, k in items)),
            "sample_by_layer": dict(Counter(k["layer"] for _, k in picked))}  # fmt: skip
    (out / "key.json").write_text(json.dumps({"info": info, "key": key}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "README.md").write_text(INSTRUCTIONS, encoding="utf-8")
    return info


def score(out: Path) -> dict[str, Any]:
    with (out / "sheet.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    key = json.loads((out / "key.json").read_text(encoding="utf-8"))["key"]
    labels = {r["id"]: r["human_layer"].strip().upper() for r in rows}
    missing = [i for i, v in labels.items() if not v]
    invalid = {i: v for i, v in labels.items() if v and v not in LAYERS}
    if missing or invalid:
        raise ValueError(f"unlabelled rows: {missing}; invalid layers: {invalid} (use one of {', '.join(LAYERS)})")
    pairs = [(labels[i], key[i]["layer"]) for i in labels]
    agree = sum(h == c for h, c in pairs)
    per_layer = {}
    for layer in sorted({h for h, _ in pairs}):
        mine = [(h, c) for h, c in pairs if h == layer]
        per_layer[layer] = f"{sum(h == c for h, c in mine)}/{len(mine)}"
    confusion = Counter(f"{h} -> {c}" for h, c in pairs)
    disagreements = [{"id": i, "human": labels[i], "classifier": key[i]["layer"], "rule": key[i]["matched_rule"]}
                     for i in labels if labels[i] != key[i]["layer"]]  # fmt: skip
    result = {"n": len(pairs), "agree": agree, "accuracy": agree / len(pairs) if pairs else None,
              "by_human_layer": per_layer, "confusion_human_to_classifier": dict(confusion), "disagreements": disagreements}  # fmt: skip
    (out / "score.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Attribution accuracy (spec v3 §11.2)", "",
        f"Layer agreement between the manual labels and the classifier: **{agree}/{len(pairs)}**"
        + (f" ({agree / len(pairs):.0%})" if pairs else ""), "",
        "| Human layer | Classifier agreed |", "|---|---|", *[f"| {k} | {v} |" for k, v in per_layer.items()], "",
        "Disagreements:", "", *([f"- `{d['id']}`: human {d['human']}, classifier {d['classifier']} ({d['rule']})" for d in disagreements] or ["- none"]),
    ]  # fmt: skip
    (out / "score.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--results-dir", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--n", type=int, default=40)
    s.add_argument("--seed", type=int, default=SEED)
    sc = sub.add_parser("score")
    sc.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "sample":
            print(json.dumps(sample(args.results_dir, args.out, args.n, args.seed), ensure_ascii=False, indent=2))
        else:
            result = score(args.out)
            print(f"accuracy {result['agree']}/{result['n']}")
    except (FileExistsError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

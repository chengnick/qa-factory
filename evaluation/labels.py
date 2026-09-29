"""Manual labels for attribution accuracy (spec v3 §11.2, Phase 5 step 3).

    python -m evaluation.labels sample --results-dir benchmark/results/phase5 --out benchmark/labels/phase5 --n 40
    (a person fills in human_layer and targets_injected_bug in sheet.csv, following INSTRUCTIONS.md)
    python -m evaluation.labels score --out benchmark/labels/phase5

`sample` takes a stratified random sample of the classified failures (by the classifier's layer, fixed seed),
shuffles the rows with a second seed, and writes:

    sheet.csv        what the labeller sees: the raw error message, no build outcomes, no rule ids
    sheet_key.csv    the cross-validation fields withheld from the sheet (bug / clean build outcome, prefixed message)
    key.json         the classifier's answers
    INSTRUCTIONS.md  how to label, what to consult, how the sample was drawn and how accuracy is computed

The labeller does not open sheet_key.csv or key.json before finishing. `score` compares the labels with key.json:
diff rows (generated tests judged by cross-validation) are the main figure; llm / agent rows are reported apart.
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
TARGETS = ("yes", "no", "n.a.")
SHEET_FIELDS = ("id", "run_id", "set", "requirement_id", "sut_bugs", "kind", "test_id", "observation", "generated_tests",
                "human_layer", "targets_injected_bug", "notes")  # fmt: skip
KEY_FIELDS = ("id", "bug_build", "clean_build", "observation_original")
_RULE_HINTS = re.compile(r"\s*\|\s*cross-validation R\d+U?\b|\s*\bR\d+U?\b(?=[:\s)]|$)")
# Cross-validation evidence prefixes (evaluation/differential.py); the raw message is the bug-build one.
_PREFIXES = (
    re.compile(r"^bug build: (?P<msg>.*?)(?: \| clean build: .*)?$", re.S),
    re.compile(r"^fails on a clean SUT: (?P<msg>.*)$", re.S),
    re.compile(r"^nondeterministic on identical clean SUTs: bug=\w+ \((?P<msg>.*?)\) clean=.*$", re.S),
)
SEED = 20260928  # which rows are sampled
ORDER_SEED = 20260929  # the order of the rows in the sheet
MIN_PER_LAYER = 3
MAIN_KIND = "diff"


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


def raw_message(evidence: str) -> str:
    """A cross-validation evidence string without its build prefix: only the original error message."""
    for rx in _PREFIXES:
        if m := rx.match(evidence):
            return m.group("msg").strip()
    return evidence.strip()


def collect(results_dir: Path) -> list[tuple[dict[str, str], dict[str, Any], dict[str, str]]]:
    """(sheet row, classifier key, withheld fields) for every classified failure in every run of the results directory."""
    items = []
    for run_dir in sorted(p for p in results_dir.glob("RUN-*") if p.is_dir()):
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        decisions = _decisions(run_dir)
        generated = sorted(p.relative_to(results_dir).as_posix() for p in (run_dir / "generated").glob("test_*.py"))
        for i, c in enumerate(_outcome(run_dir).get("classifications", [])):
            d = decisions.get(c.get("test_id") or "")
            original = d["evidence"] if d else blind(c.get("evidence") or "")
            row = {
                "id": f"{run_dir.name}#{i}",
                "run_id": run_dir.name,
                "set": meta.get("set") or "",
                "requirement_id": meta.get("requirement_id") or "",
                "sut_bugs": ",".join(meta.get("sut_bugs") or []) or "(clean)",
                "kind": c.get("unit") or "",
                "test_id": c.get("test_id") or "",
                "observation": raw_message(original) if d else original,
                "generated_tests": " ".join(generated),
                "human_layer": "",
                "targets_injected_bug": "",
                "notes": "",
            }
            key = {"layer": c.get("layer"), "symptom": c.get("symptom"), "matched_rule": c.get("matched_rule")}
            withheld = {"id": row["id"], "bug_build": (d or {}).get("bug_outcome", ""), "clean_build": (d or {}).get("clean_outcome", ""),
                        "observation_original": original}  # fmt: skip
            items.append((row, key, withheld))
    return items


def stratified(items: list[Any], layer_of, n: int, seed: int = SEED) -> list[Any]:
    """n items, every layer represented (at least MIN_PER_LAYER, or all it has), the rest proportional; fixed seed.
    Returned grouped by layer; the caller shuffles the order."""
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
    return [item for k, g in sorted(groups.items()) for item in g[: quota[k]]]


def instructions(info: dict[str, Any]) -> str:
    pop, smp = info["population_by_layer"], info["sample_by_layer"]
    kinds = info["sample_by_kind"]
    return f"""# 人工標註說明（Phase 5 歸因準確率，spec v3 §11.2）

標註檔：`sheet.csv`（{info['sampled']} 筆）。每一列是一個被分類器歸因過的失敗。
**標註完成之前，不要打開 `sheet_key.csv` 與 `key.json`**：前者是從表中拿掉的交叉驗證欄位，後者是分類器的答案。

用 Excel 或任何編輯器填寫，存檔時保持 UTF-8 CSV（Excel：「CSV UTF-8」）。只填 `human_layer`、`targets_injected_bug`、`notes` 三欄，
其他欄位不要修改。

## 1. `human_layer`（必填）

依 spec v3 §5.1，填以下其中一個值：

| 值 | 定義 |
|---|---|
| `SUT` | 被測系統行為不符需求（= 找到 bug） |
| `TEST` | 產生的測試程式本身有錯 |
| `HARNESS` | 工具封裝或執行框架出錯（包括 LLM API 拒絕請求） |
| `AGENT` | 模型行為錯誤：輸出格式錯、呼叫不存在的工具、參數錯、handoff 缺欄位 |
| `PROVIDER` | LLM 服務不可用：429、5xx、API timeout、連線失敗 |
| `ENV` | 本地環境問題：SUT 未啟動、埠衝突、瀏覽器無法啟動 |
| `UNKNOWN` | 無法判定 |

## 2. `targets_injected_bug`

`yes` / `no` / `n.a.`：這支測試失敗，是否因為它確實測到了 `sut_bugs` 所列的 bug。

- `sut_bugs` 是 `(clean)` 的列，或 `kind` 不是 `diff` 的列（`llm`、`agent`）：填 `n.a.`。
- 其餘的列（`kind = diff` 且有開 bug）：讀 `test_id` 那支測試的程式碼和錯誤訊息，對照 `bugs.yaml` 對這個 bug 的描述。
  - 測試檢查的正是這個 bug 造成的錯誤行為，失敗的斷言也對應到它 → `yes`
  - 測試失敗的原因與這個 bug 無關（例如測試本身寫錯、測的是別的規則、剛好被其他行為連帶影響） → `no`
  - 看不出來 → 不要硬選：留空，並在 `notes` 說明原因（計分時算作「無法判斷」，另外列出）

## 3. 可以參考的資料

- 產生的測試程式：`generated_tests` 欄的路徑，相對於 `benchmark/results/phase5/`
  （例如 `RUN-…/generated/test_req004_ui.py`）；`test_id` 指出是哪一支測試
- 需求文件：`benchmark/requirements/<requirement_id>.md`
- API 說明：`docs/sut-api.md`
- Bug 說明：`benchmark/bugs.yaml`（`sut_bugs` 欄列出這次開的 bug；`(clean)` 表示沒有開）
- `observation`：原始錯誤訊息（已移除規則編號與交叉驗證的前綴）

## 4. 規格模糊或無法判斷時

在 `notes` 寫明原因（例如「需求沒規定非數字 id 要回 404 還是 422」），不要硬選一個值。
`human_layer` 無法判斷時填 `UNKNOWN`；`notes` 可以寫你傾向的答案與理由。

## 5. 抽樣方式

- 母體：`{info['results_dir']}` 中 {info['population']} 筆被分類的失敗（{info['runs']} 個 run 的 `classification.json`），
  依分類器的 layer：{', '.join(f'{k} {v}' for k, v in sorted(pop.items()))}。
- 分層抽樣 {info['sampled']} 筆：每個 layer 至少 {MIN_PER_LAYER} 筆（不足則全取），其餘名額依各 layer 大小按比例分配（D'Hondt），
  各層內以 seed `{info['seed']}` 隨機選取。結果：{', '.join(f'{k} {v}' for k, v in sorted(smp.items()))}；
  依類型：{', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}。
- 列的順序以 seed `{info['order_seed']}` 隨機打亂，與 run、類型、layer 無關。
- 樣本的 layer 比例接近母體（各 layer 的母體與樣本筆數見上）；準確率依類型分開報告（見下節）。

## 6. 準確率怎麼算

完成後執行 `python -m evaluation.labels score --out benchmark/labels/phase5`。它先檢查每一列都已填、值都合法，然後：

- **主要數字：只用 `kind = diff` 的列**（產生的測試在交叉驗證中的失敗），計算 `human_layer` 與分類器 layer 一致的比例，附 Wilson 95% 信賴區間。
- `llm` 與 `agent` 類型的列另外報告（它們的歸因主要看例外類型，幾乎沒有判斷空間），不併入主要數字。
- `human_layer = UNKNOWN` 的列計為不一致，並另外列出筆數。
- `targets_injected_bug`：在有開 bug 的 diff 列中，分別統計 `yes` / `no` / 留空（無法判斷）的筆數，並對照分類器判為 `SUT` 的列。
  留空只在 `notes` 有寫原因時才接受；`n.a.` 的列必須填 `n.a.`。
- 產出 `score.json` 與 `score.md`，列出每一筆不一致的 id。
"""


def sample(results_dir: Path, out: Path, n: int, seed: int = SEED, order_seed: int = ORDER_SEED) -> dict[str, Any]:
    if (out / "sheet.csv").exists():
        raise FileExistsError(f"{out / 'sheet.csv'} already exists; a sample is drawn once")
    items = collect(results_dir)
    picked = stratified(items, lambda it: it[1]["layer"], n, seed)
    random.Random(order_seed).shuffle(picked)  # the sheet order must not reveal runs, kinds or strata
    out.mkdir(parents=True, exist_ok=True)
    for name, fields, part in (("sheet.csv", SHEET_FIELDS, 0), ("sheet_key.csv", KEY_FIELDS, 2)):
        with (out / name).open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(it[part] for it in picked)
    info = {"results_dir": results_dir.as_posix(), "runs": len(list(results_dir.glob("RUN-*"))), "population": len(items),
            "sampled": len(picked), "seed": seed, "order_seed": order_seed,
            "population_by_layer": dict(Counter(k["layer"] for _, k, _ in items)),
            "sample_by_layer": dict(Counter(k["layer"] for _, k, _ in picked)),
            "sample_by_kind": dict(Counter(r["kind"] for r, _, _ in picked))}  # fmt: skip
    key = {row["id"]: k for row, k, _ in picked}
    (out / "key.json").write_text(json.dumps({"info": info, "key": key}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "INSTRUCTIONS.md").write_text(instructions(info), encoding="utf-8")
    return info


def _wilson(num: int, den: int) -> list[float] | None:
    from evaluation.metrics import wilson_interval

    ci = wilson_interval(num, den)
    return list(ci) if ci else None


def score(out: Path) -> dict[str, Any]:
    with (out / "sheet.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = {r["id"]: r for r in csv.DictReader(f)}
    key = json.loads((out / "key.json").read_text(encoding="utf-8"))["key"]
    problems = []
    for i, r in rows.items():
        layer, target = r["human_layer"].strip().upper(), r["targets_injected_bug"].strip().lower()
        if layer not in LAYERS:
            problems.append(f"{i}: human_layer {r['human_layer']!r}")
        not_applicable = r["kind"] != MAIN_KIND or r["sut_bugs"] == "(clean)"
        if not target and not_applicable is False and r["notes"].strip():
            continue  # left open on purpose, with the reason in notes
        if target not in TARGETS or (not_applicable and target != "n.a."):
            problems.append(f"{i}: targets_injected_bug {r['targets_injected_bug']!r}" + (" (must be n.a.)" if not_applicable else ""))
    if problems:
        raise ValueError("fix these rows first: " + "; ".join(problems) + f" (human_layer: {', '.join(LAYERS)}; targets_injected_bug: {', '.join(TARGETS)})")

    def agreement(ids: list[str]) -> dict[str, Any]:
        agree = sum(rows[i]["human_layer"].strip().upper() == key[i]["layer"] for i in ids)
        return {"n": len(ids), "agree": agree, "accuracy": agree / len(ids) if ids else None, "ci95": _wilson(agree, len(ids)),
                "unknown_labels": sum(rows[i]["human_layer"].strip().upper() == "UNKNOWN" for i in ids)}  # fmt: skip

    diff_ids = [i for i in rows if rows[i]["kind"] == MAIN_KIND]
    other_ids = [i for i in rows if rows[i]["kind"] != MAIN_KIND]
    bugged_diff = [i for i in diff_ids if rows[i]["sut_bugs"] != "(clean)"]
    targets = Counter(rows[i]["targets_injected_bug"].strip().lower() or "unclear" for i in bugged_diff)
    sut_targets = Counter(rows[i]["targets_injected_bug"].strip().lower() or "unclear" for i in bugged_diff if key[i]["layer"] == "SUT")
    disagreements = [{"id": i, "kind": rows[i]["kind"], "human": rows[i]["human_layer"].strip().upper(), "classifier": key[i]["layer"],
                      "rule": key[i]["matched_rule"], "notes": rows[i]["notes"]}
                     for i in rows if rows[i]["human_layer"].strip().upper() != key[i]["layer"]]  # fmt: skip
    result = {
        "main_diff": agreement(diff_ids),
        "llm_agent": agreement(other_ids),
        "confusion_diff_human_to_classifier": dict(Counter(f"{rows[i]['human_layer'].strip().upper()} -> {key[i]['layer']}" for i in diff_ids)),
        "targets_injected_bug_bugged_diff": dict(targets),
        "targets_injected_bug_where_classifier_said_SUT": dict(sut_targets),
        "disagreements": disagreements,
    }
    (out / "score.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    def fmt(a: dict[str, Any]) -> str:
        if not a["n"]:
            return "n/a"
        return f"**{a['agree']}/{a['n']}** ({a['accuracy']:.0%}, 95% CI {a['ci95'][0]:.0%}–{a['ci95'][1]:.0%}); UNKNOWN labels: {a['unknown_labels']}"

    lines = [
        "# Attribution accuracy (spec v3 §11.2)", "",
        f"- **Main figure, diff rows (generated tests judged by cross-validation):** {fmt(result['main_diff'])}",
        f"- llm / agent rows (reported apart): {fmt(result['llm_agent'])}",
        f"- targets_injected_bug on bugged diff rows: {dict(targets)}; of those the classifier called SUT: {dict(sut_targets)}", "",
        "Disagreements:", "",
        *([f"- `{d['id']}` ({d['kind']}): human {d['human']}, classifier {d['classifier']} ({d['rule']})"
           + (f" — {d['notes']}" if d["notes"] else "") for d in disagreements] or ["- none"]),
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
    s.add_argument("--order-seed", type=int, default=ORDER_SEED)
    sc = sub.add_parser("score")
    sc.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "sample":
            print(json.dumps(sample(args.results_dir, args.out, args.n, args.seed, args.order_seed), ensure_ascii=False, indent=2))
        else:
            r = score(args.out)
            print(f"diff rows: {r['main_diff']['agree']}/{r['main_diff']['n']}; llm/agent rows: {r['llm_agent']['agree']}/{r['llm_agent']['n']}")
    except (FileExistsError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

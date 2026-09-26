"""Spec v3 §11.2 metrics over a set of runs (each run = its meta.json).

Every rate is computed per round, then reported as mean, min-max over rounds, the number of rounds that
had a non-empty denominator, the pooled count (numerator/denominator over all runs) and a Wilson 95%
confidence interval on the pooled count.
ENV_BLOCKED runs are excluded from every denominator except the environment-block rate itself.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from math import sqrt
from statistics import mean
from typing import Any

Run = dict[str, Any]


def is_env_blocked(run: Run) -> bool:
    return run.get("verdict") == "ENV_BLOCKED"


def is_bugged(run: Run) -> bool:
    return bool(run.get("sut_bugs"))


def is_agent_failed(run: Run) -> bool:
    return run.get("verdict") == "AGENT_FAILED"


def _rate(runs: Iterable[Run], include: Callable[[Run], bool], hit: Callable[[Run], bool]) -> tuple[int, int]:
    pool = [r for r in runs if include(r)]
    return sum(hit(r) for r in pool), len(pool)


def _stat(runs: list[Run], include: Callable[[Run], bool], hit: Callable[[Run], bool]) -> dict[str, Any]:
    rounds = sorted({r["round"] for r in runs})
    per_round = {}
    for rnd in rounds:
        num, den = _rate([r for r in runs if r["round"] == rnd], include, hit)
        if den:
            per_round[rnd] = num / den
    num, den = _rate(runs, include, hit)
    return _summary(per_round, num, den)


def wilson_interval(num: int, den: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion (95% for z=1.96); None when den == 0."""
    if den == 0:
        return None
    p = num / den
    denom = 1 + z * z / den
    centre = (p + z * z / (2 * den)) / denom
    half = z * sqrt(p * (1 - p) / den + z * z / (4 * den * den)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _summary(per_round: dict[int, float], num: int, den: int) -> dict[str, Any]:
    values = list(per_round.values())
    ci = wilson_interval(num, den)
    return {
        "mean": mean(values) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "n_rounds": len(values),
        "pooled": f"{num}/{den}",
        "ci95": list(ci) if ci else None,
        "per_round": per_round,
    }


def _test_health(runs: list[Run]) -> dict[str, Any]:
    def health(pool: list[Run]) -> tuple[int, int]:
        rows = [r["differential"]["test_health"] for r in pool if not is_env_blocked(r) and (r.get("differential") or {}).get("test_health")]
        return sum(h["healthy"] for h in rows), sum(h["total"] for h in rows)

    per_round = {}
    for rnd in sorted({r["round"] for r in runs}):
        num, den = health([r for r in runs if r["round"] == rnd])
        if den:
            per_round[rnd] = num / den
    return _summary(per_round, *health(runs))


def compute(runs: list[Run]) -> dict[str, Any]:
    not_blocked_bugged = lambda r: is_bugged(r) and not is_env_blocked(r)  # noqa: E731
    not_blocked_clean = lambda r: not is_bugged(r) and not is_env_blocked(r)  # noqa: E731
    completed_bugged = lambda r: not_blocked_bugged(r) and not is_agent_failed(r)  # noqa: E731
    metrics = {
        "true_detection_rate": _stat(runs, not_blocked_bugged, lambda r: r["verdict"] == "DEFECT_FOUND"),
        # Same numerator, but only runs where the pipeline produced tests: separates agent reliability
        # (AGENT_FAILED) from test-design quality (tests that ran but missed the bug).
        "true_detection_rate_completed": _stat(runs, completed_bugged, lambda r: r["verdict"] == "DEFECT_FOUND"),
        "surface_detection_rate": _stat(runs, not_blocked_bugged, lambda r: r.get("surface_verdict") == "DEFECT_FOUND"),
        # Main false-positive figure: in real use there is no clean build to compare with, so the user sees
        # the surface verdict. The cross-validated rate is 0 by construction (see acceptance.md).
        "false_positive_rate_surface": _stat(runs, not_blocked_clean, lambda r: r.get("surface_verdict") == "DEFECT_FOUND"),
        "false_positive_rate_verified": _stat(runs, not_blocked_clean, lambda r: r["verdict"] == "DEFECT_FOUND"),
        "test_health": _test_health(runs),
        "env_blocked_rate": _stat(runs, lambda r: True, is_env_blocked),
    }
    per_bug: dict[str, dict[str, Any]] = {}
    for bug in sorted({b for r in runs for b in r.get("sut_bugs", [])}):
        mine = [r for r in runs if bug in r.get("sut_bugs", [])]
        usable = [r for r in mine if not is_env_blocked(r)]
        completed = [r for r in usable if not is_agent_failed(r)]
        per_bug[bug] = {
            "verified": f"{sum(r['verdict'] == 'DEFECT_FOUND' for r in usable)}/{len(usable)}",
            "completed": f"{sum(r['verdict'] == 'DEFECT_FOUND' for r in completed)}/{len(completed)}",
            "agent_failed": f"{len(usable) - len(completed)}/{len(usable)}",
            "surface": f"{sum(r.get('surface_verdict') == 'DEFECT_FOUND' for r in usable)}/{len(usable)}",
            "env_blocked": f"{len(mine) - len(usable)}/{len(mine)}",
        }
    metrics["per_bug_detection"] = per_bug
    tokens = [r["tokens"]["total"] for r in runs if (r.get("tokens") or {}).get("total") is not None]
    durations = [r["duration_s"] for r in runs if r.get("duration_s") is not None]
    metrics["cost"] = {
        "mean_tokens": mean(tokens) if tokens else None,
        "mean_duration_s": mean(durations) if durations else None,
        "n": len(runs),
    }
    return metrics

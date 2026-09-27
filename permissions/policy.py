"""Agent permission policy (spec v3.1 §8.5): load, validate, hash.

Validation is strict and runs before any run starts. Any problem raises PolicyError with the location
of the error; nothing falls back to defaults. The hash is the sha256 of the file with line endings
normalised to LF, so Windows and Linux checkouts hash the same policy identically.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "agent_policy.yaml"

PIPELINE_AGENTS = ("requirement", "test_design", "automation", "qa", "report")
KNOWN_TOOLS = ("file_write", "pytest", "http_request", "playwright")  # the built-in tool registry
ALLOWED_PLACEHOLDERS = ("run_id", "sut_base_url")
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")


class PolicyError(Exception):
    """The policy file is invalid. A startup error: no run is created."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class RunnerRule(_Strict):
    """pytest / playwright: no conditions besides the generated-code check."""


class FileWriteRule(_Strict):
    path_prefix: str


class HttpRule(_Strict):
    url_allowlist: list[str]


class ToolRules(_Strict):
    file_write: FileWriteRule | None = None
    pytest: RunnerRule | None = None
    http_request: HttpRule | None = None
    playwright: RunnerRule | None = None


class AgentRules(_Strict):
    tools: ToolRules


class PathRules(_Strict):
    protected: list[str]
    evidence: list[str]


class GeneratedCodeRules(_Strict):
    allowed_imports: list[str]
    banned_names: list[str]
    banned_attributes: list[str]
    url_allowlist: list[str]


class PolicyModel(_Strict):
    schema_version: Literal[1] = Field(alias="schema")
    placeholders: list[str]
    agents: dict[str, AgentRules]
    paths: PathRules
    generated_code: GeneratedCodeRules


def _strings(value: Any, loc: str) -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(loc, value)]
    if isinstance(value, list):
        return [pair for i, v in enumerate(value) for pair in _strings(v, f"{loc}[{i}]")]
    if isinstance(value, dict):
        return [pair for k, v in value.items() for pair in _strings(v, f"{loc}.{k}" if loc else str(k))]
    return []


def _check_semantics(raw: dict[str, Any], model: PolicyModel) -> list[str]:
    errors = []
    undeclared = sorted(set(model.placeholders) - set(ALLOWED_PLACEHOLDERS))
    if undeclared:
        errors.append(f"placeholders: only {list(ALLOWED_PLACEHOLDERS)} are allowed, got {undeclared}")
    for loc, text in _strings({k: v for k, v in raw.items() if k != "placeholders"}, ""):
        for name in _PLACEHOLDER.findall(text):
            if name not in model.placeholders:
                errors.append(f"{loc}: undefined placeholder {{{name}}}")
    unknown = sorted(set(model.agents) - set(PIPELINE_AGENTS))
    missing = [a for a in PIPELINE_AGENTS if a not in model.agents]
    errors += [f"agents.{a}: unknown agent (pipeline agents: {list(PIPELINE_AGENTS)})" for a in unknown]
    errors += [f"agents.{a}: pipeline agent missing from the policy" for a in missing]
    writer = model.agents.get("automation")
    if writer and writer.tools.file_write:
        prefix = writer.tools.file_write.path_prefix
        loc = "agents.automation.tools.file_write.path_prefix"
        if not prefix.startswith("artifacts/"):
            errors.append(f"{loc}: must be under artifacts/, got {prefix!r}")
        if "{run_id}" not in prefix:
            errors.append(f"{loc}: must contain {{run_id}} so a run can only write its own directory, got {prefix!r}")
        if "artifacts/" not in model.paths.evidence:
            errors.append("paths.evidence: must contain 'artifacts/' (the automation write area lives there)")
    return errors


@dataclass(frozen=True)
class Policy:
    path: Path
    hash: str
    model: PolicyModel

    def permissions(self) -> dict[str, frozenset[str]]:
        return {agent: frozenset(t for t in KNOWN_TOOLS if getattr(rules.tools, t) is not None) for agent, rules in self.model.agents.items()}

    def tool_rule(self, agent: str, tool: str) -> Any:
        rules = self.model.agents.get(agent)
        return getattr(rules.tools, tool, None) if rules is not None and tool in KNOWN_TOOLS else None

    @property
    def protected(self) -> tuple[str, ...]:
        return tuple(p.rstrip("/") for p in self.model.paths.protected)

    @property
    def evidence(self) -> tuple[str, ...]:
        return tuple(p.rstrip("/") for p in self.model.paths.evidence)

    @property
    def generated_code(self) -> GeneratedCodeRules:
        return self.model.generated_code

    @property
    def display_path(self) -> str:
        try:
            return self.path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return self.path.as_posix()

    @staticmethod
    def expand(template: str, **values: str) -> str:
        return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), template)


def policy_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


def load_policy(path: Path | str = DEFAULT_POLICY_PATH) -> Policy:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolicyError(f"{path}: cannot read policy: {exc}") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        raise PolicyError(f"{path}: YAML syntax error{where}: {getattr(exc, 'problem', exc)}") from exc
    if not isinstance(raw, dict):
        raise PolicyError(f"{path}: the policy must be a mapping")
    try:
        model = PolicyModel.model_validate(raw)
    except ValidationError as exc:
        lines = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        raise PolicyError(f"{path}: invalid policy:\n  " + "\n  ".join(lines)) from None
    errors = _check_semantics(raw, model)
    if errors:
        raise PolicyError(f"{path}: invalid policy:\n  " + "\n  ".join(errors))
    return Policy(path, policy_hash(text), model)


@lru_cache(maxsize=1)
def default_policy() -> Policy:
    return load_policy(DEFAULT_POLICY_PATH)

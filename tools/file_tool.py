"""file_write: the Automation agent's only write access, confined to generated/ (L0 check; L1 in Phase 5)."""

from __future__ import annotations

from pathlib import Path

from tools.registry import ToolArgumentError, ToolResult

GENERATED = "generated"
PROTECTED_NAMES = {"conftest.py"}  # the owner-written fixtures in generated/ are read-only for agents


def resolve_generated(root: Path, path: str) -> Path:
    """Map a repo-relative path to an absolute one, refusing anything outside generated/."""
    base = (root / GENERATED).resolve()
    target = (root / path).resolve()
    if base not in target.parents:
        raise ToolArgumentError(f"path must be inside {GENERATED}/: {path!r}")
    return target


class FileWriteTool:
    def __init__(self, root: Path) -> None:
        self.root = root

    def __call__(self, path: str, content: str) -> ToolResult:
        target = resolve_generated(self.root, path)
        if target.name in PROTECTED_NAMES:
            raise ToolArgumentError(f"{target.name} is owner-maintained and read-only for agents")
        if target.suffix != ".py":
            raise ToolArgumentError(f"only .py files may be written: {path!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        rel = target.relative_to(self.root).as_posix()
        return ToolResult(ok=True, command=f"file_write {rel}", stdout=f"wrote {len(content)} chars to {rel}", data={"path": rel})

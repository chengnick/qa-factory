"""Build the real tool registry for a pipeline run against a SUT."""

from __future__ import annotations

from pathlib import Path

from tools.file_tool import FileWriteTool
from tools.http_tool import HttpTool
from tools.pytest_tool import PytestTool
from permissions.policy import Policy
from tools.registry import ToolRegistry


def real_tools(workspace: Path, sut_url: str, policy: Policy | None = None) -> ToolRegistry:
    """Tools bound to one run workspace (see tools/workspace.py) and one SUT."""
    registry = ToolRegistry()
    registry.register("file_write", FileWriteTool(workspace))
    registry.register("pytest", PytestTool(workspace, sut_url, timeout_s=120, policy=policy))
    registry.register("http_request", HttpTool(sut_url))
    registry.register("playwright", PytestTool(workspace, sut_url, timeout_s=180, policy=policy))
    return registry

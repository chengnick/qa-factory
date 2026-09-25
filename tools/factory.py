"""Build the real tool registry for a pipeline run against a SUT."""

from __future__ import annotations

from pathlib import Path

from tools.file_tool import FileWriteTool
from tools.http_tool import HttpTool
from tools.pytest_tool import PytestTool
from tools.registry import ToolRegistry


def real_tools(root: Path, sut_url: str) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("file_write", FileWriteTool(root))
    registry.register("pytest", PytestTool(root, sut_url, timeout_s=120))
    registry.register("http_request", HttpTool(sut_url))
    registry.register("playwright", PytestTool(root, sut_url, timeout_s=180))
    return registry

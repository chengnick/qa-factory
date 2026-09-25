"""file_write confinement and the real pytest runner (subprocess, offline)."""

from pathlib import Path

import pytest

from tools.file_tool import FileWriteTool
from tools.pytest_tool import PytestTool
from tools.registry import ToolArgumentError, ToolTimeoutError


@pytest.fixture
def root(tmp_dir: Path) -> Path:
    (tmp_dir / "generated").mkdir()
    (tmp_dir / "generated" / "conftest.py").write_text("# owner fixtures\n", encoding="utf-8")
    return tmp_dir


# --------------------------------------------------------------------------- file_write


def test_file_write_creates_file_under_generated(root):
    result = FileWriteTool(root)(path="generated/test_req005_api.py", content="def test_x():\n    pass\n")

    assert result.ok and result.data["path"] == "generated/test_req005_api.py"
    assert (root / "generated" / "test_req005_api.py").read_text(encoding="utf-8").startswith("def test_x")


@pytest.mark.parametrize(
    "path",
    ["sut/app.py", "../outside.py", "generated/../sut/app.py", "benchmark/reference_tests/test_b01_x.py", "generated", str(Path("C:/Windows/evil.py"))],
)
def test_file_write_refuses_paths_outside_generated(root, path):
    with pytest.raises(ToolArgumentError):
        FileWriteTool(root)(path=path, content="x")


def test_file_write_refuses_owner_conftest(root):
    with pytest.raises(ToolArgumentError, match="read-only"):
        FileWriteTool(root)(path="generated/conftest.py", content="x")
    assert (root / "generated" / "conftest.py").read_text(encoding="utf-8") == "# owner fixtures\n"


def test_file_write_refuses_non_python(root):
    with pytest.raises(ToolArgumentError):
        FileWriteTool(root)(path="generated/notes.txt", content="x")


# --------------------------------------------------------------------------- pytest runner


def _write(root: Path, name: str, body: str) -> str:
    (root / "generated" / name).write_text(body, encoding="utf-8")
    return f"generated/{name}"


def test_passing_run(root):
    path = _write(root, "test_ok.py", "import os\n\ndef test_env():\n    assert os.environ['SUT_BASE_URL'] == 'http://sut.test'\n")

    result = PytestTool(root, "http://sut.test")(paths=[path])

    assert result.ok and result.exit_code == 0, result.stdout
    assert result.data["tests"] == 1 and result.data["failures"] == 0
    assert result.command == f"pytest {path}"


def test_failing_assertion(root):
    path = _write(root, "test_fail.py", "def test_a():\n    assert 200 == 409, 'expected 409'\n\ndef test_b():\n    pass\n")

    result = PytestTool(root, "http://sut.test")(paths=[path])

    assert not result.ok and result.exit_code == 1
    assert result.data["tests"] == 2 and result.data["failures"] == 1 and result.data["errors"] == 0
    assert "expected 409" in result.stdout


def test_collection_error(root):
    path = _write(root, "test_broken.py", "def test_a(:\n    pass\n")

    result = PytestTool(root, "http://sut.test")(paths=[path])

    assert result.exit_code == 2
    assert result.data["errors"] >= 1


def test_timeout_raises_retryable_error(root):
    path = _write(root, "test_slow.py", "import time\n\ndef test_slow():\n    time.sleep(30)\n")

    with pytest.raises(ToolTimeoutError):
        PytestTool(root, "http://sut.test", timeout_s=3)(paths=[path])


def test_missing_file_and_outside_paths_rejected(root):
    tool = PytestTool(root, "http://sut.test")
    with pytest.raises(ToolArgumentError, match="not found"):
        tool(paths=["generated/test_nope.py"])
    with pytest.raises(ToolArgumentError):
        tool(paths=["benchmark/reference_tests/test_b01_pagination_last_item.py"])
    with pytest.raises(ToolArgumentError):
        tool(paths=[])


def test_failures_split_into_assertions_and_test_code_exceptions(root):
    body = "def test_assert():\n    assert 200 == 409\n\ndef test_crash():\n    (lambda: None).post('/x')\n"
    path = _write(root, "test_kinds.py", body)

    result = PytestTool(root, "http://sut.test")(paths=[path])

    assert result.data["failures"] == 2
    assert result.data["assertion_failures"] == 1 and result.data["exception_failures"] == 1


def test_per_test_results_with_node_ids(root):
    body = (
        "import pytest\n\n"
        "def test_ok():\n    pass\n\n"
        "def test_assert():\n    assert 500 == 422, 'Internal Server Error'\n\n"
        "def test_crash():\n    (lambda: None).post('/x')\n\n"
        "@pytest.mark.parametrize('n', [1])\ndef test_param(n):\n    pass\n\n"
        "class TestGroup:\n    def test_in_class(self):\n        pass\n"
    )
    path = _write(root, "test_nodes.py", body)

    results = {r["node_id"]: r for r in PytestTool(root, "http://sut.test")(paths=[path]).data["results"]}

    assert {k: v["outcome"] for k, v in results.items()} == {
        "generated/test_nodes.py::test_ok": "PASS",
        "generated/test_nodes.py::test_assert": "FAIL",
        "generated/test_nodes.py::test_crash": "ERROR",
        "generated/test_nodes.py::test_param[1]": "PASS",
        "generated/test_nodes.py::TestGroup::test_in_class": "PASS",
    }
    assert "500 == 422" in results["generated/test_nodes.py::test_assert"]["message"]


def test_collection_error_is_one_error_result(root):
    path = _write(root, "test_syntax.py", "def test_a(:\n    pass\n")

    (result,) = PytestTool(root, "http://sut.test")(paths=[path]).data["results"]

    assert result == {"node_id": "generated/test_syntax.py", "outcome": "ERROR", "message": result["message"]}

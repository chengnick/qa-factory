"""Generated test code runs in the run workspace with a whitelisted environment.

The generated tests below *try* to reach secrets and the repo; the tool run passes only if they can't.
"""

from pathlib import Path

import pytest

from tools.pytest_tool import ENV_WHITELIST, PytestTool
from tools.workspace import create_run_workspace, new_run_id

REPO = Path(__file__).resolve().parents[2]
FAKE_KEY = "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE123"


@pytest.fixture
def workspace(tmp_dir: Path) -> Path:
    return create_run_workspace(tmp_dir, new_run_id())


def _run(workspace: Path, name: str, body: str):
    (workspace / "generated" / name).write_text(body, encoding="utf-8")
    # enforce_policy=False: these tests deliberately import os/importlib to probe the L0+ isolation layer on its
    # own; the static code policy (tools/code_policy.py) is a separate layer tested in tests/agent_security/.
    return PytestTool(workspace, "http://sut.test", enforce_policy=False)(paths=[f"generated/{name}"])


def test_generated_code_cannot_read_gemini_api_key(workspace, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    body = (
        "import os\n\n"
        "def test_key_is_absent():\n"
        "    print('KEY=' + os.environ.get('GEMINI_API_KEY', '<absent>'))\n"
        "    assert 'GEMINI_API_KEY' not in os.environ\n"
        "    assert not any('AIza' in v for v in os.environ.values())\n"
    )

    result = _run(workspace, "test_steal_key.py", body)

    assert result.ok, result.stdout
    assert FAKE_KEY not in result.stdout


def test_only_whitelisted_variables_reach_generated_code(workspace, monkeypatch):
    monkeypatch.setenv("SOME_TOKEN", "t0ps3cret")
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    allowed = sorted(set(ENV_WHITELIST) | {"SUT_BASE_URL", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "PYTHONIOENCODING"})
    body = (
        "import os\n\n"
        f"ALLOWED = {allowed!r}\n\n"
        "def test_env_is_whitelisted():\n"
        "    extra = sorted(k for k in os.environ if k.upper() not in ALLOWED and not k.startswith('PYTEST_'))\n"
        "    assert extra == [], extra\n"
        "    assert os.environ['SUT_BASE_URL'] == 'http://sut.test'\n"
    )

    result = _run(workspace, "test_env.py", body)

    assert result.ok, result.stdout
    assert "t0ps3cret" not in result.stdout


def test_generated_code_runs_in_workspace_without_repo_on_path(workspace, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO))
    body = (
        "import importlib.util\n"
        "import os\n"
        "from pathlib import Path\n\n"
        "def test_cwd_and_imports():\n"
        "    assert Path.cwd() == Path(__file__).resolve().parents[1]\n"
        "    for module in ('sut', 'pipeline', 'app', 'agents'):\n"
        "        assert importlib.util.find_spec(module) is None, module\n"
    )

    result = _run(workspace, "test_where.py", body)

    assert result.ok, result.stdout


def test_workspace_layout(workspace):
    assert (workspace / "generated" / "conftest.py").read_text(encoding="utf-8") == (REPO / "generated" / "conftest.py").read_text(
        encoding="utf-8"
    )
    assert (workspace / "pytest.ini").is_file()
    assert sorted(p.name for p in workspace.iterdir()) == ["generated", "pytest.ini"]


def test_workspace_is_never_reused(tmp_dir):
    run_id = new_run_id()
    create_run_workspace(tmp_dir, run_id)
    with pytest.raises(FileExistsError):
        create_run_workspace(tmp_dir, run_id)


def test_forbidden_variables_never_pass_spec_v3_8_3(workspace, monkeypatch):
    """Spec v3 §8.3: no *_API_KEY, *_TOKEN or SUT_BUGS in the generated-test environment."""
    monkeypatch.setenv("SUT_BUGS", "B02")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-fake-fake-fake")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fakefakefakefakefakefakefake")
    body = (
        "import os\n\n"
        "def test_forbidden_absent():\n"
        "    names = {k.upper() for k in os.environ}\n"
        "    assert 'SUT_BUGS' not in names\n"
        "    assert not [k for k in names if k.endswith('_API_KEY') or k.endswith('_TOKEN')]\n"
    )

    assert _run(workspace, "test_forbidden.py", body).ok

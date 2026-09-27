"""The policy file is equivalent to the Phase 3 implementation it replaced (spec v3.1 §8.5.2, §8.5.5).

The expected values below are hard-coded copies of the Phase 3 constants, taken from commit e24faae
(permissions/gate.py: PERMISSIONS, PROTECTED_DIRS, EVIDENCE_DIRS; tools/code_policy.py: ALLOWED_IMPORTS,
FORBIDDEN_NAMES, FORBIDDEN_ATTRIBUTES; the URL rule `sut_url and url.startswith(sut_url)`).
They are deliberately NOT read from the policy loader, so a drift of the policy file cannot go unnoticed.
"""

from permissions.policy import load_policy

# ---- copied from commit e24faae ---------------------------------------------------------------------------
PHASE3_PERMISSIONS = {
    "requirement": frozenset(),
    "test_design": frozenset(),
    "automation": frozenset({"file_write", "pytest", "http_request", "playwright"}),
    "qa": frozenset({"pytest", "http_request", "playwright"}),
    "report": frozenset(),
}
PHASE3_PROTECTED_DIRS = ("sut", "benchmark/reference_tests", "docs")
PHASE3_EVIDENCE_DIRS = ("artifacts", "benchmark", "traces")
PHASE3_ALLOWED_IMPORTS = frozenset({"pytest", "httpx", "uuid", "re", "playwright", "__future__"})
PHASE3_FORBIDDEN_NAMES = frozenset({"open", "exec", "eval", "compile", "__import__", "getattr", "__builtins__"})
PHASE3_FORBIDDEN_ATTRIBUTES = frozenset({"__dict__", "__class__", "__subclasses__", "__builtins__"})
PHASE3_WRITE_AREA = "<run workspace>/generated"  # gate: _inside(candidates[0], self.workspace / "generated")
PHASE3_URL_RULE = "only URLs starting with the SUT base URL"

# ---- spec v3 §8.1 table (tool-level allowlist), cell by cell ------------------------------------------------
SPEC_8_1 = {
    #              file_write  pytest  http_request  playwright
    "requirement": (False, False, False, False),
    "test_design": (False, False, False, False),
    "automation": (True, True, True, True),
    "qa": (False, True, True, True),
    "report": (False, False, False, False),
}
TOOLS = ("file_write", "pytest", "http_request", "playwright")


def test_permissions_equal_phase3():
    assert load_policy().permissions() == PHASE3_PERMISSIONS


def test_golden_spec_8_1_table_cell_by_cell():
    permissions = load_policy().permissions()
    for agent, row in SPEC_8_1.items():
        for tool, allowed in zip(TOOLS, row):
            assert (tool in permissions[agent]) is allowed, f"§8.1 cell {agent} x {tool}"


def test_paths_equal_phase3():
    policy = load_policy()
    assert policy.protected == PHASE3_PROTECTED_DIRS
    assert policy.evidence == PHASE3_EVIDENCE_DIRS


def test_generated_code_rules_equal_phase3():
    rules = load_policy().generated_code
    assert frozenset(rules.allowed_imports) == PHASE3_ALLOWED_IMPORTS
    assert frozenset(rules.banned_names) == PHASE3_FORBIDDEN_NAMES
    assert frozenset(rules.banned_attributes) == PHASE3_FORBIDDEN_ATTRIBUTES
    assert rules.url_allowlist == ["{sut_base_url}"]  # PHASE3_URL_RULE


def test_write_area_equals_phase3(tmp_dir):
    from permissions.gate import PermissionGate
    from security.events import SecurityRecorder

    workspace = tmp_dir / "artifacts" / "RUN-20260927-000000-AAAA"
    gate = PermissionGate(SecurityRecorder(), registered=lambda: TOOLS, workspace=workspace)
    assert gate.write_area() == workspace / "generated"  # PHASE3_WRITE_AREA
    assert load_policy().tool_rule("automation", "http_request").url_allowlist == ["{sut_base_url}"]

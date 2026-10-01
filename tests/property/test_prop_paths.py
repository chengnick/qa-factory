"""Property 2: file_write paths. Different spellings of the same file get the same judgement (metamorphic), and no
spelling of a protected path, an evidence path or another run's directory is allowed.

Spellings on every OS: "." segments, "x/.." detours, doubled separators, relative vs absolute.
Windows only (skipif elsewhere, where these name different files): letter case and backslashes.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from permissions.policy import REPO_ROOT
from tests.property.prop_support import OTHER_RUN, WINDOWS, gated_world
from tools.registry import PermissionDeniedError

# (expected classification, segments, base the relative form is resolved against)
TARGETS = [
    ("PROTECTED", ["sut", "app.py"], "repo"),
    ("PROTECTED", ["sut", "new_module.py"], "repo"),
    ("PROTECTED", ["docs", "spec.md"], "repo"),
    ("PROTECTED", ["benchmark", "reference_tests", "test_new.py"], "repo"),
    ("EVIDENCE", ["benchmark", "frozen.yaml"], "repo"),
    ("EVIDENCE", ["traces", "x", "trace.json"], "repo"),
    ("EVIDENCE", ["..", OTHER_RUN, "meta.json"], "workspace"),
    ("OWN_GENERATED", ["generated", "test_prop_new.py"], "workspace"),
]


@st.composite
def spelling(draw, segments: list[str], windows_forms: bool) -> tuple[list[str], str, bool]:
    """(segments with detours, separator, absolute?) for one way of writing the same path."""
    out: list[str] = []
    for seg in segments:
        if draw(st.booleans()):
            out.append(".")
        if draw(st.integers(0, 3)) == 0:
            out += [draw(st.sampled_from(["x", "tmp", "zz"])), ".."]
        if windows_forms and seg not in ("..", ".") and draw(st.booleans()):
            seg = "".join(c.upper() if draw(st.booleans()) else c.lower() for c in seg)
        out.append(seg)
    sep = draw(st.sampled_from(["\\", "/"] if windows_forms else ["/"]))
    sep = sep * draw(st.sampled_from([1, 1, 2]))
    return out, sep, draw(st.booleans())


def _render(world, target: tuple[str, list[str], str], form: tuple[list[str], str, bool]) -> str:
    _, _, base = target
    segments, sep, absolute = form
    rel = sep.join(segments)
    if not absolute:
        return rel
    root = REPO_ROOT if base == "repo" else world.workspace
    return str(root).rstrip("\\/") + sep + rel


def _check(target, form) -> None:
    expected, segments, _ = target
    with gated_world() as w:
        canonical = _render(w, target, (segments, "/", False))
        variant = _render(w, target, form)
        assert w.gate.classify_path(canonical) == expected, canonical
        assert w.gate.classify_path(variant) == expected, f"{variant!r} judged {w.gate.classify_path(variant)}, {canonical!r} {expected}"
        if expected != "OWN_GENERATED":
            with pytest.raises(PermissionDeniedError):
                w.gate.check("automation", "file_write", {"path": variant, "content": "x = 1\n"})


@given(data=st.data(), target=st.sampled_from(TARGETS))
def test_every_spelling_gets_the_same_judgement_and_protected_ones_are_refused(data, target):
    _check(target, data.draw(spelling(target[1], windows_forms=False)))


@pytest.mark.skipif(not WINDOWS, reason="case-insensitive names and backslash separators are Windows semantics")
@given(data=st.data(), target=st.sampled_from(TARGETS))
def test_windows_case_and_backslash_spellings_too(data, target):
    _check(target, data.draw(spelling(target[1], windows_forms=True)))

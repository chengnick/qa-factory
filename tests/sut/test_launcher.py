"""The SUT launcher leaves no server behind, even when python.exe is a venv launcher (Windows)."""

from sut.launcher import is_healthy, running_sut


def test_sut_is_gone_after_the_context_exits():
    with running_sut([]) as url:
        assert is_healthy(url)

    assert not is_healthy(url, timeout_s=0.5)

"""L1 guard (spec v3 §8.2, Phase 4): an audit hook installed in the generated-test subprocess before pytest starts.

    writes      only under the call's write roots (reports/, playwright/, the call's private temp dir)
    reads       everything except the deny list (the repo's .env)
    network     name lookups and connections only to the SUT (plus loopback sockets this process bound itself,
                which asyncio needs for its self-pipe on Windows)
    processes   only the Playwright driver; os.system / exec / spawn / fork are refused
    native code ctypes library loading and raw memory access are refused; hard links, symlinks and junctions too

**This is an in-process check, not an operating-system sandbox.** It sees what CPython reports through
sys.addaudithook. Code that reaches the OS without an audit event (for example _winapi.CreateFile on
Windows) is not stopped. Libraries loaded before the hook stay callable: pytest and colorama are imported
first (colorama loads kernel32 through ctypes), and looking up or calling functions of an already-loaded
library is not refused, only loading new libraries and reading raw memory. The browser process started by the
Playwright driver is outside Python entirely (its network is limited by the page fixture instead). The
container mode (L2) is the isolation that does not depend on the code's cooperation.

Refusals raise PermissionError inside the test and are appended to the call's log file (config["log"]),
which the pytest tool reads back. The log lives in a write root, so a hostile test could rewrite it:
the log is a convenience, the refusal itself is the protection.

Standard library only: this file is loaded by path, without the repository on sys.path.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import weakref
from typing import Any

WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
PATH_EVENTS = {  # event -> indexes of path arguments that must stay inside the write roots
    "os.remove": (0,), "os.rmdir": (0,), "os.mkdir": (0,), "os.rename": (0, 1), "os.truncate": (0,),
    "os.chmod": (0,), "os.chown": (0,), "os.utime": (0,), "os.chflags": (0,), "os.lchflags": (0,),
    "os.setxattr": (0,), "os.removexattr": (0,), "shutil.rmtree": (0,), "shutil.copyfile": (1,),
    "shutil.copymode": (1,), "shutil.copystat": (1,), "shutil.chown": (0,), "shutil.move": (0, 1),
}  # fmt: skip
# Starting a program: allowed only for the Playwright driver (config["exec"]). subprocess.Popen raises its own event and,
# depending on the Python version and OS, then os.posix_spawn (3.14 on Linux) or os.exec / os.spawn.
PROCESS_EVENTS = {"subprocess.Popen", "os.posix_spawn", "os.posix_spawnp", "os.exec", "os.spawn"}
REFUSED = {
    "os.link", "os.symlink", "_winapi.CreateJunction", "os.system", "os.startfile", "os.fork", "os.forkpty", "ctypes.dlopen", "ctypes.cdata", "ctypes.cdata/buffer",
    "ctypes.string_at", "ctypes.wstring_at",
    "_winapi.OpenProcess", "_winapi.TerminateProcess", "os.kill", "os.killpg", "signal.pthread_kill",
    "winreg.ConnectRegistry", "winreg.CreateKey", "winreg.DeleteKey", "winreg.DeleteValue", "winreg.LoadKey",
    "winreg.SaveKey", "winreg.SetValue", "sys.remote_exec",
}  # fmt: skip


def _norm(path: Any) -> str | None:
    if isinstance(path, int):
        return None  # an already-open file descriptor: its opening was checked
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def _inside(path: str, roots: list[str]) -> bool:
    return any(path == r or path.startswith(r.rstrip(os.sep) + os.sep) for r in roots)


class Guard:
    def __init__(self, config: dict[str, Any]) -> None:
        self.write_roots = [p for p in (_norm(r) for r in [*config["write"], tempfile.gettempdir(), os.devnull]) if p]
        self.deny_read = [p for p in (_norm(r) for r in config.get("deny_read", ())) if p]
        self.exec_roots = [p for p in (_norm(r) for r in config.get("exec", ())) if p]
        self.log = config.get("log")
        port = int(config["sut_port"])
        self.names = {config["sut_host"], *LOOPBACK} if config["sut_host"] in LOOPBACK else {config["sut_host"]}
        self.addresses = {(a[4][0], port) for n in self.names for a in _resolve(n, port)}
        self.addresses |= {(h, port) for h in self.names}
        self.bound: weakref.WeakSet[socket.socket] = weakref.WeakSet()
        self._local = threading.local()

    # ------------------------------------------------------------------ hook

    def __call__(self, event: str, args: tuple[Any, ...]) -> None:
        if getattr(self._local, "busy", False):
            return  # the guard's own work (realpath, logging) must not re-enter it
        self._local.busy = True
        try:
            self._check(event, args)
        finally:
            self._local.busy = False

    def _check(self, event: str, args: tuple[Any, ...]) -> None:
        if event == "open":
            self._open(*args[:3])
        elif event == "os.mkdir" and (path := _norm(args[0])) is not None and os.path.isdir(path):
            return  # os.makedirs(exist_ok=True) on an existing folder: the OS refuses it anyway, nothing to guard
        elif event in PATH_EVENTS:
            for i in PATH_EVENTS[event]:
                if i < len(args) and (path := _norm(args[i])) is not None and not _inside(path, self.write_roots):
                    self._deny(event, path, "outside the write roots")
        elif event in REFUSED:
            self._deny(event, _describe(args), "refused at L1")
        elif event in PROCESS_EVENTS or event.startswith(("os.exec", "os.spawn")):
            program = _program(args)
            path = _norm(program) if isinstance(program, (str, bytes, os.PathLike)) else None
            if path is None or not _inside(path, self.exec_roots):
                self._deny(event, str(program), "only the Playwright driver may be started")
        elif event == "socket.getaddrinfo":
            if str(args[0]) not in self.names:
                self._deny(event, str(args[0]), "only the SUT host may be resolved")
        elif event == "socket.bind":
            host = args[1][0] if isinstance(args[1], tuple) else args[1]
            if host not in LOOPBACK:
                self._deny(event, str(args[1]), "only loopback sockets may be bound")
            self.bound.add(args[0])
        elif event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
            self._connect(event, args[1] if len(args) > 1 else None)

    def _open(self, path: Any, mode: Any, flags: Any) -> None:
        target = _norm(path)
        if target is None:
            return
        writing = any(c in mode for c in "wax+") if isinstance(mode, str) else bool((flags or 0) & WRITE_FLAGS)
        if writing and not _inside(target, self.write_roots):
            self._deny("open", target, "write outside the write roots")
        if not writing and _inside(target, self.deny_read):
            self._deny("open", target, "read of a denied file")

    def _connect(self, event: str, address: Any) -> None:
        if not isinstance(address, tuple) or len(address) < 2:
            self._deny(event, str(address), "only TCP/UDP to the SUT")
        host, port = address[0], address[1]
        if (host, port) in self.addresses:
            return
        if host in LOOPBACK and any(_sockname(s) == (host, port) for s in list(self.bound)):
            return  # a loopback socket this process listens on (asyncio self-pipe)
        self._deny(event, f"{host}:{port}", "only the SUT may be contacted")

    def _deny(self, event: str, target: str, reason: str) -> None:
        line = json.dumps({"event": event, "target": target[:300], "reason": reason})
        if self.log:
            try:
                with open(self.log, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass
        raise PermissionError(f"L1 guard refused {event} {target!r}: {reason}")


def _program(args: tuple[Any, ...]) -> Any:
    """The program a process event starts: an explicit executable/path, else argv[0]."""
    if not args:
        return None
    if args[0]:
        return args[0]
    argv = args[1] if len(args) > 1 else None
    return argv[0] if isinstance(argv, (list, tuple)) and argv else argv


def _resolve(host: str, port: int) -> list[Any]:
    try:
        return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return []


def _sockname(sock: socket.socket) -> tuple[Any, Any] | None:
    try:
        name = sock.getsockname()
        return (name[0], name[1])
    except OSError:
        return None


def _describe(args: tuple[Any, ...]) -> str:
    return " ".join(str(a) for a in args[:2])[:300]


def install(config: dict[str, Any]) -> Guard:
    """Install once; audit hooks cannot be removed, so the guard stays for the life of the process."""
    guard = Guard(config)
    sys.addaudithook(guard)
    return guard

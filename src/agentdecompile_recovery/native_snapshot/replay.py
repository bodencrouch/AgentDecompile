"""JVM-free replay of exported savefiles through the native decomp console."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess

from agentdecompile_recovery.native_snapshot.manifest import FunctionEntry, Manifest


@dataclass(frozen=True)
class ReplayResult:
    addr: str
    name: str
    c_text: str | None
    stderr: str
    returncode: int


def _script(savefile: Path, load_name: str, token: str) -> str:
    # The marker commands are console-native (`echo`), so C text is extracted
    # without assuming its formatting or attempting to parse user identifiers.
    return "\n".join((
        f"restore {savefile}",
        f"load function {load_name}",
        "decompile",
        f"echo {token}:BEGIN",
        "print C",
        f"echo {token}:END",
        "quit",
        "",
    ))


def _extract(stdout: str, token: str) -> str | None:
    begin = f"{token}:BEGIN"
    end = f"{token}:END"
    lines = stdout.splitlines()
    try:
        first = next(i for i, line in enumerate(lines) if line.strip() == begin)
        last = next(i for i, line in enumerate(lines[first + 1 :], first + 1) if line.strip() == end)
    except StopIteration:
        return None
    # IfaceTerm writes the command prompt onto stdout. The standalone marker
    # is emitted by `echo`; command echoes are never part of decompiled C.
    body = [line for line in lines[first + 1 : last] if not line.startswith("[decomp]> ")]
    while body and not body[-1]:
        body.pop()
    return "\n".join(body) + ("\n" if body else "")


class ConsoleReplayer:
    """One fresh native-console process per savefile, with a bounded timeout."""

    def __init__(self, console: Path, *, sleigh_home: Path | None = None, timeout_s: float = 60) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self.console = Path(console)
        self.sleigh_home = Path(sleigh_home) if sleigh_home is not None else None
        self.timeout_s = timeout_s

    def replay(self, root: Path, entry: FunctionEntry) -> ReplayResult:
        if not entry.savefile or not entry.load_name:
            return ReplayResult(entry.addr, entry.name, None, "entry has no savefile/load_name", 2)
        savefile = root / entry.savefile
        if not savefile.is_file():
            return ReplayResult(entry.addr, entry.name, None, f"missing savefile: {savefile}", 2)
        token = f"__GNSDK_REPLAY_{entry.addr}__"
        try:
            command = [str(self.console)]
            environment = os.environ.copy()
            if self.sleigh_home is not None:
                # consolemain uses SLEIGHHOME as its Ghidra-root fallback.
                # Merely passing `-s` adds a search path but leaves the root
                # empty, which upstream console shutdown can dereference.
                environment["SLEIGHHOME"] = str(self.sleigh_home)
            completed = subprocess.run(
                command, input=_script(savefile, entry.load_name, token), text=True,
                capture_output=True, timeout=self.timeout_s, check=False, env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ReplayResult(entry.addr, entry.name, None, str(exc), 124)
        return ReplayResult(entry.addr, entry.name, _extract(completed.stdout, token), completed.stderr, completed.returncode)

    def replay_manifest(self, root: Path, manifest: Manifest) -> dict[str, ReplayResult]:
        return {entry.addr: self.replay(root, entry) for entry in manifest.ok_entries()}

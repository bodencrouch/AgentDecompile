"""JVM-free replay of exported savefiles through the native decomp console."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from agentdecompile_recovery.native_snapshot.manifest import FunctionEntry, Manifest


@dataclass(frozen=True)
class ReplayResult:
    addr: str
    name: str
    c_text: str | None
    stderr: str
    returncode: int
    engines: tuple[dict[str, object], ...] = ()


def _script(savefile: Path, load_name: str, token: str, *, quit_after: bool = True) -> str:
    # The marker commands are console-native (`echo`), so C text is extracted
    # without assuming its formatting or attempting to parse user identifiers.
    lines = [
        f"restore {savefile}",
        f"load function {load_name}",
        "decompile",
        f"echo {token}:BEGIN",
        "print C",
        f"echo {token}:END",
        "",
    ]
    if quit_after:
        lines.extend(("quit", ""))
    return "\n".join(lines)


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


def _native_sla_hashes(sleigh_home: Path, language_ids: set[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    if not language_ids:
        return hashes
    for ldefs in sleigh_home.glob("Ghidra/Processors/*/data/languages/*.ldefs"):
        try:
            root = ET.fromstring(ldefs.read_text(encoding="utf-8"))
        except (OSError, ET.ParseError):
            continue
        for language in root.findall("language"):
            language_id = language.get("id")
            slafile = language.get("slafile")
            if not language_id or language_id not in language_ids or not slafile:
                continue
            sla_path = ldefs.parent / slafile
            try:
                hashes[language_id] = hashlib.sha256(sla_path.read_bytes()).hexdigest()
            except OSError:
                continue
    return hashes


class ConsoleReplayer:
    """Replay savefiles through bounded chunks of one native-console process."""

    def __init__(self, console: Path, *, sleigh_home: Path | None = None, timeout_s: float = 60, per_process: int = 200) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if per_process <= 0:
            raise ValueError("per_process must be positive")
        self.console = Path(console)
        self.sleigh_home = Path(sleigh_home) if sleigh_home is not None else None
        self.timeout_s = timeout_s
        self.per_process = per_process

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        if self.sleigh_home is not None:
            # consolemain uses SLEIGHHOME as its Ghidra-root fallback.
            # Merely passing `-s` adds a search path but leaves the root
            # empty, which upstream console shutdown can dereference.
            environment["SLEIGHHOME"] = str(self.sleigh_home)
        return environment

    def _run_script(self, script: str, *, timeout_s: float) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.console)],
            input=script,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
            env=self._environment(),
        )

    def replay(self, root: Path, entry: FunctionEntry) -> ReplayResult:
        if not entry.savefile or not entry.load_name:
            return ReplayResult(entry.addr, entry.name, None, "entry has no savefile/load_name", 2)
        savefile = root / entry.savefile
        if not savefile.is_file():
            return ReplayResult(entry.addr, entry.name, None, f"missing savefile: {savefile}", 2)
        token = f"__GNSDK_REPLAY_{entry.addr}__"
        try:
            completed = self._run_script(_script(savefile, entry.load_name, token), timeout_s=self.timeout_s)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ReplayResult(entry.addr, entry.name, None, str(exc), 124)
        return ReplayResult(entry.addr, entry.name, _extract(completed.stdout, token), completed.stderr, completed.returncode)

    def replay_manifest(self, root: Path, manifest: Manifest) -> dict[str, ReplayResult]:
        entries = list(manifest.ok_entries())
        results: dict[str, ReplayResult] = {}
        for start in range(0, len(entries), self.per_process):
            chunk = entries[start : start + self.per_process]
            scripts: list[str] = []
            tokens: dict[str, str] = {}
            valid: list[FunctionEntry] = []
            for entry in chunk:
                if not entry.savefile or not entry.load_name:
                    results[entry.addr] = ReplayResult(entry.addr, entry.name, None, "entry has no savefile/load_name", 2)
                    continue
                savefile = root / entry.savefile
                if not savefile.is_file():
                    results[entry.addr] = ReplayResult(entry.addr, entry.name, None, f"missing savefile: {savefile}", 2)
                    continue
                token = f"__GNSDK_REPLAY_{entry.addr}__"
                tokens[entry.addr] = token
                scripts.append(_script(savefile, entry.load_name, token, quit_after=False))
                valid.append(entry)
            if not valid:
                continue
            script = "\n".join(scripts + ["quit", ""])
            try:
                completed = self._run_script(script, timeout_s=self.timeout_s * len(valid) + 10)
            except (OSError, subprocess.TimeoutExpired) as exc:
                for entry in valid:
                    results[entry.addr] = ReplayResult(entry.addr, entry.name, None, str(exc), 124)
                continue
            for entry in valid:
                results[entry.addr] = ReplayResult(
                    entry.addr,
                    entry.name,
                    _extract(completed.stdout, tokens[entry.addr]),
                    completed.stderr,
                    completed.returncode,
                )
        return results


class BatchReplayer:
    """Replay a full snapshot through ``gnsdk-batch --snapshot`` and parse JSONL."""

    def __init__(
        self,
        batch: Path,
        *,
        sleigh_home: Path,
        timeout_s: float = 60,
        workers: int = 1,
        tmpdir: Path | None = None,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if workers <= 0:
            raise ValueError("workers must be positive")
        self.batch = Path(batch)
        self.sleigh_home = Path(sleigh_home)
        self.timeout_s = timeout_s
        self.workers = workers
        self.tmpdir = Path(tmpdir) if tmpdir is not None else None

    def replay_manifest(self, root: Path, manifest: Manifest) -> dict[str, ReplayResult]:
        sla_hashes = _native_sla_hashes(self.sleigh_home, {manifest.program.language_id})
        temp_parent = self.tmpdir if self.tmpdir is not None else None
        if temp_parent is not None:
            temp_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="gnsdk-batch-", dir=temp_parent) as tmp:
            output = Path(tmp) / "results.jsonl"
            command = [
                str(self.batch),
                "--sleigh-home",
                str(self.sleigh_home),
                "--snapshot",
                str(root),
                "--output",
                str(output),
                "--timeout",
                str(int(self.timeout_s)),
                "--workers",
                str(self.workers),
            ]
            if self.tmpdir is not None:
                command.extend(("--tmpdir", str(self.tmpdir)))
            entry_count = len(list(manifest.ok_entries()))
            subprocess_timeout_s = max(self.timeout_s + 10, self.timeout_s * max((entry_count + 49) // 50, 1) + 10)
            try:
                completed = subprocess.run(
                    command,
                    text=True,
                    capture_output=True,
                    timeout=subprocess_timeout_s,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                return {}
            results: dict[str, ReplayResult] = {}
            if output.is_file():
                for line in output.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    addr = str(record.get("id") or record.get("seq") or "")
                    if not addr:
                        continue
                    result = record.get("result") if isinstance(record.get("result"), dict) else {}
                    c_text = result.get("c") if record.get("status") == "ok" and isinstance(result.get("c"), str) else None
                    stderr = str(record.get("error") or completed.stderr)
                    engines = record.get("engines")
                    engine_records = [engine.copy() for engine in engines if isinstance(engine, dict)] if isinstance(engines, list) else []
                    for engine in engine_records:
                        engine["sla_sha256"] = sla_hashes
                    engine_tuple: tuple[dict[str, object], ...] = tuple(engine_records)
                    results[addr] = ReplayResult(addr, str(result.get("name") or addr), c_text, stderr, completed.returncode, engine_tuple)
            return results

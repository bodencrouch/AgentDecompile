"""``corpus attest`` -- run the keyed corpus verbs against a private copy of a store.

An attestation answers one question about a store: do the verbs that key on it
still run, refuse nothing, and produce what they produced last time?  It never
runs a verb on the store it was pointed at.  One snapshot is taken per run
(``SnapshotStrategy``), each selected verb (``VerbSpec`` from ``VERBS``) runs as
a child process under its own deadline (``Runner``), and one sorted receipt per
verb lands under ``<receipts>/<run_id>/``.  The receipts are compared with the
previous run's (``Comparator``) and the exit code says what changed.

Vocabulary of one verb's ``status``:

* ``ok``           -- exit code in ``expected_exit`` and the same as the previous run;
* ``changed``      -- exit code in ``expected_exit`` but the receipt differs from the
                      previous run's (or there is no previous run);
* ``refused``      -- exit 2 with one named refusal line (basis, content hash, lock);
* ``hang``         -- the verb overran its deadline; killed, never waited on;
* ``failed``       -- any other exit code;
* ``missing_verb`` -- the CLI at this head has no such verb; nothing was spawned.

Exit codes of the attestation: 0 when every verb is ``ok``; 3 when any receipt
changed, is new or is gone; 4 when any verb hung, failed, refused or was missing,
or when the overall deadline stopped the run before every verb started.
``--allow-refusals`` turns a refusal into a 3 for a store known to be
pre-admission.  Refusals of the attestation itself (a side file as ``--db``, the
store living inside the receipts tree) are exit 2 with one named line.

Persisted JSON is ``json.dumps(obj, sort_keys=True, indent=2) + "\\n"``.  No
wall-clock value is inside any hashed content: ``run_id`` is a timestamp but is
a directory name, ``elapsed_s`` and ``head`` are excluded from the comparison
key (``RECEIPT_COMPARE_EXCLUDE``).  Build names never appear: a row is its
``content_sha256``, its ``md5`` or ``sha256(slug)[:12]``.

Import direction: this module imports nothing from ``agentdecompile_grid``; the
grid lane (``grid_lanes.verbs.CorpusAttest``) imports this module.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

SCHEMA = "agentdecompile.attest.v1"
INDEX_SCHEMA = "agentdecompile.attest.index.v1"
STORE_FILENAME = "store.sqlite"
OUT_DIRNAME = "out"
VERB_RECEIPTS_DIRNAME = "verb-receipts"
LATEST_FILENAME = "LATEST"
INDEX_FILENAME = "index.json"
RUN_ID_FORMAT = "%Y%m%dT%H%M%SZ"
STDOUT_HEAD_BYTES = 400
KILL_AFTER_S = 20.0
OVERALL_DEADLINE_SLACK_S = 60.0

#: Receipt fields that carry per-run noise; never part of the comparison key.
#: ``status`` and ``comparison`` are derived *from* the comparison, so they are
#: excluded too or the first run's ``changed`` would differ from the second's ``ok`` forever.
RECEIPT_COMPARE_EXCLUDE: frozenset[str] = frozenset({"elapsed_s", "head", "status", "comparison"})

EXIT_SAME = 0
EXIT_REFUSED = 2
EXIT_CHANGED = 3
EXIT_FAILURE = 4


class AttestRefused(ValueError):
    """The attestation itself refuses (exit 2): a named condition, nothing run."""


# --------------------------------------------------------------------------- catalogue
class BudgetClass(str, enum.Enum):
    """Mirror of the grid's budget class names.  Not imported: corpus code never imports the grid."""

    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class Status(str, enum.Enum):
    OK = "ok"
    CHANGED = "changed"
    REFUSED = "refused"
    HANG = "hang"
    FAILED = "failed"
    MISSING_VERB = "missing_verb"


FAILURE_STATUSES: frozenset[str] = frozenset({Status.HANG.value, Status.FAILED.value, Status.MISSING_VERB.value})


@dataclasses.dataclass(frozen=True)
class VerbSpec:
    """One verb of ``corpus.cli`` as the attestation runs it.

    ``argv_template`` is the argv after the module name; ``{db}``, ``{out}`` and
    ``{receipts}`` are resolved to paths *relative to the workdir* (the child runs
    with the workdir as its cwd), so the argv in the receipt is the argv that ran.
    """

    name: str
    argv_template: tuple[str, ...]
    deadline_s: float
    mutates_snapshot: bool
    reads_output: tuple[str, ...] = ()
    expected_exit: tuple[int, ...] = (0,)
    budget_class: BudgetClass = BudgetClass.MEDIUM

    @property
    def cli_verb(self) -> str:
        return self.argv_template[0]

    def describe(self) -> dict[str, Any]:
        return {
            "cli_verb": self.cli_verb, "argv": list(self.argv_template), "deadline_s": self.deadline_s,
            "mutates_snapshot": self.mutates_snapshot, "reads_output": list(self.reads_output),
            "expected_exit": list(self.expected_exit), "budget_class": self.budget_class.value,
        }


class VerbCatalogue(dict):
    """``name -> VerbSpec`` in run order.  Insertion order is the walking skeleton's order."""

    def resolve(self, names: Sequence[str]) -> list[VerbSpec]:
        unknown = sorted(set(names) - set(self))
        if unknown:
            raise AttestRefused(f"attest: unknown verb(s): {', '.join(unknown)} (known: {', '.join(self)})")
        wanted = set(names)
        return [spec for name, spec in self.items() if name in wanted]

    def by_cli_verb(self, cli_verb: str, *, pass_name: str | None = None) -> VerbSpec | None:
        """The first catalogue entry whose CLI verb is *cli_verb* (``backfill`` picks by pass)."""
        for spec in self.values():
            if spec.cli_verb != cli_verb:
                continue
            if pass_name and "--pass" in spec.argv_template:
                idx = spec.argv_template.index("--pass")
                if spec.argv_template[idx + 1] != pass_name:
                    continue
            return spec
        return None


VERBS: VerbCatalogue = VerbCatalogue()
for _spec in (
    VerbSpec("admit-dry", ("admit", "--db", "{db}", "--receipts", "{receipts}", "--dry-run"), 120.0, False,
             budget_class=BudgetClass.MEDIUM),
    VerbSpec("admit", ("admit", "--db", "{db}", "--receipts", "{receipts}"), 900.0, True,
             budget_class=BudgetClass.LARGE),
    VerbSpec("rebaseline", ("rebaseline", "--db", "{db}", "--receipts", "{receipts}"), 300.0, True,
             budget_class=BudgetClass.MEDIUM),
    VerbSpec("backfill-analyzer-identity",
             ("backfill", "--db", "{db}", "--pass", "analyzer_identity", "--receipts", "{receipts}"), 900.0, True,
             budget_class=BudgetClass.LARGE),
    VerbSpec("backfill-content-sha256",
             ("backfill", "--db", "{db}", "--pass", "content_sha256", "--receipts", "{receipts}"), 900.0, True,
             budget_class=BudgetClass.LARGE),
    VerbSpec("logical-build", ("logical-build", "--db", "{db}"), 900.0, True, budget_class=BudgetClass.LARGE),
    # exit 1 (packs differ) is a value for the grid lane but a failure for an attestation:
    # the point of the run is that the store is deterministic under this head.
    VerbSpec("verify-determinism", ("verify-determinism", "--db", "{db}"), 1200.0, False,
             budget_class=BudgetClass.LARGE),
    VerbSpec("export-hookpack", ("export-hookpack", "--db", "{db}", "--out", "{out}/pack.json"), 600.0, False,
             reads_output=("pack.json",), budget_class=BudgetClass.MEDIUM),
):
    VERBS[_spec.name] = _spec
del _spec


class ProfileRegistry(dict):
    """``profile name -> verb names`` (catalogue order is restored on resolve)."""

    def resolve(self, name: str) -> list[str]:
        if name not in self:
            raise AttestRefused(f"attest: unknown profile: {name} (known: {', '.join(sorted(self))})")
        return list(self[name])


PROFILES: ProfileRegistry = ProfileRegistry({
    "full": tuple(VERBS),
    "keyed-only": ("verify-determinism", "export-hookpack"),
    "admission": ("admit-dry", "admit", "rebaseline"),
    "smoke": ("verify-determinism",),
})


def available_cli_verbs() -> frozenset[str]:
    """The verb names the CLI at this head can parse; a catalogue entry outside it is ``missing_verb``."""
    import argparse

    from .cli import build_parser

    names: set[str] = set()
    for action in build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            names.update(action.choices)
    return frozenset(names)


# --------------------------------------------------------------------------- scrubbing
_ABS_POSIX = re.compile(r"(?<![\w./])/(?:[^/\s'\"()]+/)+[^/\s'\"()]*")
_ABS_WIN = re.compile(r"\b[A-Za-z]:[\\/][^\s'\"()]*")
_BRACKETS = re.compile(r"\[([^\[\]]*)\]")


def scrub_paths(text: str) -> str:
    """Absolute path spellings become ``<path>``; nothing about the host layout leaves a receipt."""
    return _ABS_POSIX.sub("<path>", _ABS_WIN.sub("<path>", text))


_NAMED_VALUE = re.compile(r'("(?:slug|repo_path|game|title)"\s*:\s*)"([^"]*)"')


def _bracket_count(match: re.Match) -> str:
    """``[a, b, {c, d}]`` -> ``[3 ids]``: elements at brace depth zero, never their text."""
    inner = match.group(1).strip()
    if not inner:
        return "[0 ids]"
    n, depth = 1, 0
    for ch in inner:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "," and depth == 0:
            n += 1
    return f"[{n} ids]"


def _hash_named_values(match: re.Match) -> str:
    return f'{match.group(1)}"{hashed_slug(match.group(2))}"'


def stdout_head(text: str) -> str:
    """The first ``STDOUT_HEAD_BYTES`` of *text*, paths scrubbed, bracketed lists counted.

    Hex tokens (content hashes, hashed names) outside brackets are kept as they are;
    a bracketed list is the shape a refusal line uses to name builds, so only its length survives.
    """
    head = text.encode("utf-8", "replace")[:STDOUT_HEAD_BYTES].decode("utf-8", "replace")
    return _NAMED_VALUE.sub(_hash_named_values, _BRACKETS.sub(_bracket_count, scrub_paths(head)))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hashed_slug(slug: object) -> str:
    return _sha256(str(slug).encode("utf-8"))[:12]


def classify_refusal(stderr: str) -> str:
    """The named class behind an exit 2 (mirrors ``cli._refusal_line``'s prefixes; no build names)."""
    for line in reversed(stderr.splitlines()):
        line = line.strip()
        if not line.startswith("error:"):
            continue
        text = line[len("error:"):].strip()
        if text.startswith("ContentHashError"):
            return "content-hash:" + _BRACKETS.sub(_bracket_count, scrub_paths(text.split(":", 1)[1].strip()))[:200]
        if text.startswith("basis"):
            return "basis:" + _BRACKETS.sub(_bracket_count, scrub_paths(text.split(":", 1)[1].strip()))[:200]
        if text.startswith("locked"):
            return "locked"
        return "verb-refused:" + _BRACKETS.sub(_bracket_count, scrub_paths(text))[:120]
    if "invalid choice" in stderr:
        return "cli-usage:invalid-choice"
    return "verb-refused:exit-2"


# --------------------------------------------------------------------------- store identity
def store_rowset_hash(path: Path) -> str:
    """sha256 over the sorted identity rows of ``binary`` in the store at *path* (opened read-only).

    Identity columns only: ``content_sha256`` | ``md5`` | hashed slug, ``analyzer_version``,
    ``basis_hash`` and ``admission_status`` when the column exists.  ``absent`` when the
    file has no ``binary`` table.
    """
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(binary)")}
        if not cols:
            return "absent"
        extra = [c for c in ("analyzer_version", "basis_hash", "admission_status") if c in cols]
        select = ["content_sha256" if "content_sha256" in cols else "NULL", "md5" if "md5" in cols else "NULL", "slug", *extra]
        lines: list[str] = []
        for row in con.execute(f"SELECT {', '.join(select)} FROM binary"):
            content, md5, slug, *rest = row
            identity = str(content or "").strip() or str(md5 or "").strip() or "slug:" + hashed_slug(slug)
            lines.append("|".join([identity, *("" if v is None else str(v) for v in rest)]))
    except sqlite3.DatabaseError:
        return "unreadable"
    finally:
        con.close()
    return _sha256("\n".join(sorted(lines)).encode("utf-8"))


def source_head(start: Path | None = None) -> str:
    """Short git sha of the source tree this module runs from, else ``unknown``."""
    root = start or Path(__file__).resolve().parent
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = proc.stdout.strip()
    return sha if proc.returncode == 0 and sha else "unknown"


# --------------------------------------------------------------------------- snapshots
class SnapshotStrategy(Protocol):
    """Produce a private copy of the store at *src* inside *workdir*; return its path."""

    name: str

    def snapshot(self, src: Path, workdir: Path) -> Path: ...


def _copy_store(src: Path, dst: Path) -> None:
    from .determinism_basis import _copy_store as backup_copy

    backup_copy(src, dst)


class BackupApiSnapshot:
    """The default: SQLite backup API from a ``mode=ro`` URI.  WAL-safe; never writes *src*."""

    name = "backup"

    def snapshot(self, src: Path, workdir: Path) -> Path:
        dst = workdir / STORE_FILENAME
        for side in (dst, dst.with_name(dst.name + "-wal"), dst.with_name(dst.name + "-shm")):
            if side.exists():
                side.unlink()
        _copy_store(src, dst)
        return dst


class ReflinkSnapshot:
    """``cp --reflink=always`` when the filesystem supports it (probed), else falls back by name.

    The main file and a ``-wal`` side file, when present, are both reflinked, so the copy opens
    with the same committed rows.  The backup strategy remains the WAL-safe default: a reflink
    of a store with an active writer can see a torn WAL.
    """

    name = "reflink"

    def __init__(self, fallback: SnapshotStrategy | None = None) -> None:
        self.fallback = fallback or BackupApiSnapshot()
        self.used: str = self.name

    @staticmethod
    def probe(workdir: Path) -> bool:
        probe = workdir / ".reflink-probe"
        copy = workdir / ".reflink-probe-copy"
        try:
            probe.write_bytes(b"probe\n")
            proc = subprocess.run(["cp", "--reflink=always", str(probe), str(copy)], capture_output=True, timeout=10)
            return proc.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
        finally:
            for p in (probe, copy):
                if p.exists():
                    p.unlink()

    def snapshot(self, src: Path, workdir: Path) -> Path:
        if not self.probe(workdir):
            self.used = f"{self.name}->{self.fallback.name}"
            return self.fallback.snapshot(src, workdir)
        dst = workdir / STORE_FILENAME
        for side in (dst, dst.with_name(dst.name + "-wal"), dst.with_name(dst.name + "-shm")):
            if side.exists():
                side.unlink()
        subprocess.run(["cp", "--reflink=always", str(src), str(dst)], check=True, timeout=600)
        wal = src.with_name(src.name + "-wal")
        if wal.is_file():
            subprocess.run(["cp", "--reflink=always", str(wal), str(dst.with_name(dst.name + "-wal"))], check=True, timeout=600)
        self.used = self.name
        return dst


class MaterializedSnapshot:
    """The caller already holds a private copy (a grid task's materialised input): use it in place."""

    name = "materialized"

    def snapshot(self, src: Path, workdir: Path) -> Path:
        dst = workdir / STORE_FILENAME
        if src.resolve() != dst.resolve():
            shutil.move(str(src), str(dst))
        return dst


class OverlaySnapshot:
    """Slot: an overlay / copy-on-write filesystem snapshot of the store's directory."""

    name = "overlay"

    def snapshot(self, src: Path, workdir: Path) -> Path:
        raise NotImplementedError("U168: overlay/COW filesystem snapshot")


SNAPSHOTS: dict[str, type] = {
    "backup": BackupApiSnapshot, "reflink": ReflinkSnapshot, "materialized": MaterializedSnapshot,
    "overlay": OverlaySnapshot,
}


# --------------------------------------------------------------------------- runners
@dataclasses.dataclass(frozen=True)
class RunOutcome:
    exit: int
    elapsed_s: float
    timed_out: bool
    stdout_sha256: str          # over the path-scrubbed text, so two workdirs give one digest
    stderr_sha256: str
    stdout_head: str
    refusal_class: str


class Runner(Protocol):
    def run(self, spec: VerbSpec, argv: Sequence[str], env: Mapping[str, str], deadline_s: float, *, cwd: Path) -> RunOutcome: ...


class SubprocessRunner:
    """``subprocess.run`` with a timeout; SIGTERM at the deadline, SIGKILL ``KILL_AFTER_S`` later."""

    name = "subprocess"

    def run(self, spec: VerbSpec, argv: Sequence[str], env: Mapping[str, str], deadline_s: float, *, cwd: Path) -> RunOutcome:
        started = time.monotonic()
        kwargs: dict[str, Any] = {
            "cwd": str(cwd), "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "stdin": subprocess.DEVNULL,
            "env": dict(env),
        }
        if os.name != "nt":
            kwargs["start_new_session"] = True
        proc = subprocess.Popen([str(a) for a in argv], **kwargs)
        timed_out = False
        try:
            out, err = proc.communicate(timeout=max(deadline_s, 0.0))
        except subprocess.TimeoutExpired:
            timed_out = True
            _signal_group(proc, signal.SIGTERM if os.name != "nt" else None)
            try:
                out, err = proc.communicate(timeout=KILL_AFTER_S)
            except subprocess.TimeoutExpired:
                _signal_group(proc, signal.SIGKILL if os.name != "nt" else None)
                out, err = proc.communicate()
        elapsed = time.monotonic() - started
        stdout = (out or b"").decode("utf-8", "replace")
        stderr = (err or b"").decode("utf-8", "replace")
        exit_code = int(proc.returncode if proc.returncode is not None else -1)
        return RunOutcome(
            exit=exit_code, elapsed_s=elapsed, timed_out=timed_out,
            stdout_sha256=_sha256(scrub_paths(stdout).encode("utf-8", "replace")),
            stderr_sha256=_sha256(scrub_paths(stderr).encode("utf-8", "replace")),
            stdout_head=stdout_head(stdout),
            refusal_class=classify_refusal(stderr) if (exit_code == 2 and not timed_out) else "",
        )


def _signal_group(proc: subprocess.Popen, sig) -> None:
    try:
        if sig is None:
            proc.kill()
        else:
            os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


class GridRunner:
    """Slot: submit the verb as a grid task and wait for its receipt under the same deadline."""

    name = "grid"

    def run(self, spec: VerbSpec, argv: Sequence[str], env: Mapping[str, str], deadline_s: float, *, cwd: Path) -> RunOutcome:
        raise NotImplementedError("U168")


RUNNERS: dict[str, type] = {"subprocess": SubprocessRunner, "grid": GridRunner}


def child_env(workdir: Path, *, pythonpath: str | None = None) -> dict[str, str]:
    """The verb's environment: private tmp and work dirs under *workdir*, the package's source on the path."""
    import agentdecompile_recovery

    src_dir = str(Path(agentdecompile_recovery.__file__).resolve().parents[1])
    parts = [p for p in (pythonpath, src_dir, os.environ.get("PYTHONPATH")) if p]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(parts))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["TMPDIR"] = str(workdir / "tmp")
    env["AGENT_DECOMPILE_CORPUS_WORK_DIR"] = str(workdir / "work")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    for key in ("TMPDIR", "AGENT_DECOMPILE_CORPUS_WORK_DIR"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    return env


# --------------------------------------------------------------------------- receipts
def dump_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, indent=2) + "\n"


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_json(obj), encoding="utf-8")


def compare_key(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in receipt.items() if k not in RECEIPT_COMPARE_EXCLUDE}


def resolve_argv(spec: VerbSpec) -> list[str]:
    """The catalogue template with placeholders resolved to names relative to the workdir."""
    mapping = {"db": STORE_FILENAME, "out": f"{OUT_DIRNAME}/{spec.name}", "receipts": VERB_RECEIPTS_DIRNAME}
    return [a.format(**mapping) for a in spec.argv_template]


class Comparator(Protocol):
    """Per-verb verdict against a reference: ``same | changed | new`` and ``gone`` for the reference's extras."""

    name: str

    def compare(self, receipts: Mapping[str, Mapping[str, Any]]) -> dict[str, str]: ...

    def reference_id(self) -> str | None: ...


class PreviousRunComparator:
    """Diff against the receipts of ``<receipts>/LATEST``, read *before* this run writes anything."""

    name = "previous-run"

    def __init__(self, receipts_root: Path) -> None:
        self.previous_id: str | None = None
        self.previous: dict[str, dict[str, Any]] = {}
        latest = receipts_root / LATEST_FILENAME
        if latest.is_file():
            run_id = latest.read_text(encoding="utf-8").strip()
            run_dir = receipts_root / run_id
            if run_id and run_dir.is_dir():
                self.previous_id = run_id
                for path in sorted(run_dir.glob("*.json")):
                    if path.name == INDEX_FILENAME:
                        continue
                    try:
                        body = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if isinstance(body, dict) and body.get("schema") == SCHEMA:
                        self.previous[str(body.get("verb", path.stem))] = body

    def reference_id(self) -> str | None:
        return self.previous_id

    def compare(self, receipts: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
        verdict: dict[str, str] = {}
        for verb, receipt in receipts.items():
            prev = self.previous.get(verb)
            if prev is None:
                verdict[verb] = "new"
            else:
                verdict[verb] = "same" if compare_key(prev) == compare_key(receipt) else "changed"
        for verb in self.previous:
            if verb not in receipts:
                verdict[verb] = "gone"
        return verdict


class NoComparator:
    """No reference: every verb's status is its run outcome (the grid lane; the view compares)."""

    name = "none"

    def reference_id(self) -> str | None:
        return None

    def compare(self, receipts: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
        return {}


class BaselineComparator:
    """Slot: diff against a pinned baseline file instead of the previous run."""

    name = "baseline"

    def __init__(self, baseline: Path) -> None:
        raise NotImplementedError("U28x: pinned baseline comparator")

    def reference_id(self) -> str | None:  # pragma: no cover - slot
        return None

    def compare(self, receipts: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:  # pragma: no cover - slot
        raise NotImplementedError("U28x: pinned baseline comparator")


COMPARATORS: dict[str, type] = {"previous-run": PreviousRunComparator, "none": NoComparator, "baseline": BaselineComparator}


# --------------------------------------------------------------------------- the run
def new_run_id(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime(RUN_ID_FORMAT)


def check_store_path(db: Path, receipts: Path, workdir: Path | None) -> Path:
    """Refuse the source paths an attestation must never take.  Returns the resolved store path."""
    if db.name.endswith(("-wal", "-shm")):
        raise AttestRefused("attest: --db names a WAL/SHM side file; point at the main store file")
    if not db.is_file():
        raise AttestRefused("attest: --db is not a file")
    resolved = db.resolve()
    st = resolved.stat()
    for root in (receipts, workdir):
        if root is None:
            continue
        root_resolved = root.resolve()
        if resolved == root_resolved or root_resolved in resolved.parents:
            raise AttestRefused(f"attest: --db lives inside --{'receipts' if root is receipts else 'workdir'}")
        if not root_resolved.is_dir():
            continue
        for candidate in root_resolved.rglob("*.sqlite"):
            try:
                cst = candidate.stat()
            except OSError:
                continue
            if (cst.st_dev, cst.st_ino) == (st.st_dev, st.st_ino):
                raise AttestRefused("attest: --db is the same inode as a store under the receipts/work tree")
    return resolved


def receipt_for(
    spec: VerbSpec, argv: Sequence[str], *, deadline_s: float, outcome: RunOutcome | None,
    outputs: Mapping[str, str], store_before: str, store_after: str, head: str, missing: bool = False,
) -> dict[str, Any]:
    """One verb's receipt (``status`` is the run outcome; the comparison overlays ``changed`` later)."""
    if missing:
        status = Status.MISSING_VERB.value
        exit_code, elapsed, timed_out, refusal = -1, 0.0, False, "missing-verb:" + spec.cli_verb
        stdout_sha, stderr_sha, head_text = "", "", ""
    else:
        assert outcome is not None
        if outcome.timed_out:
            status = Status.HANG.value
        elif outcome.exit == 2:
            status = Status.REFUSED.value
        elif outcome.exit in spec.expected_exit:
            status = Status.OK.value
        else:
            status = Status.FAILED.value
        exit_code, elapsed, timed_out, refusal = outcome.exit, outcome.elapsed_s, outcome.timed_out, outcome.refusal_class
        stdout_sha, stderr_sha, head_text = outcome.stdout_sha256, outcome.stderr_sha256, outcome.stdout_head
    return {
        "schema": SCHEMA, "verb": spec.name, "cli_verb": spec.cli_verb, "argv": list(argv),
        "budget_class": spec.budget_class.value, "deadline_s": deadline_s, "elapsed_s": round(elapsed, 1),
        "exit": exit_code, "timed_out": timed_out, "status": status, "outcome": status,
        "refusal_class": refusal, "outputs": dict(sorted(outputs.items())),
        "stdout_sha256": stdout_sha, "stderr_sha256": stderr_sha, "stdout_head": head_text,
        "store_before": store_before, "store_after": store_after, "head": head,
    }


def collect_outputs(spec: VerbSpec, workdir: Path) -> dict[str, str]:
    out_dir = workdir / OUT_DIRNAME / spec.name
    outputs: dict[str, str] = {}
    for rel in spec.reads_output:
        path = out_dir / rel
        outputs[rel] = _sha256(path.read_bytes()) if path.is_file() else "missing"
    return outputs


@dataclasses.dataclass
class AttestationRun:
    """One attestation: snapshot once, run the selected verbs in catalogue order, write receipts."""

    db: Path
    receipts: Path
    workdir: Path
    verbs: Sequence[VerbSpec]
    snapshot: SnapshotStrategy = dataclasses.field(default_factory=BackupApiSnapshot)
    runner: Runner = dataclasses.field(default_factory=SubprocessRunner)
    comparator: Comparator | None = None
    deadline_s: float | None = None
    verb_deadlines: Mapping[str, float] = dataclasses.field(default_factory=dict)
    fresh_per_verb: bool = False
    allow_refusals: bool = False
    pythonpath: str | None = None
    profile: str = ""
    run_id: str = dataclasses.field(default_factory=new_run_id)
    available: frozenset[str] | None = None
    interpreter: str = sys.executable

    def deadline_for(self, spec: VerbSpec) -> float:
        return float(self.verb_deadlines.get(spec.name, spec.deadline_s))

    def overall_deadline(self) -> float:
        if self.deadline_s is not None:
            return float(self.deadline_s)
        return sum(self.deadline_for(s) for s in self.verbs) + OVERALL_DEADLINE_SLACK_S

    def execute(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        """Run everything; returns ``(index, receipts)`` after writing them under ``<receipts>/<run_id>/``."""
        started = time.monotonic()
        comparator = self.comparator if self.comparator is not None else PreviousRunComparator(self.receipts)
        available = self.available if self.available is not None else available_cli_verbs()
        head = source_head()
        overall = self.overall_deadline()
        self.workdir.mkdir(parents=True, exist_ok=True)
        run_dir = self.receipts / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        env = child_env(self.workdir, pythonpath=self.pythonpath)
        store = self.snapshot.snapshot(self.db, self.workdir)
        snapshots = 1
        receipts: dict[str, dict[str, Any]] = {}
        not_run: list[str] = []
        deadline_exceeded = False
        for spec in self.verbs:
            remaining = overall - (time.monotonic() - started)
            if remaining <= 0:
                deadline_exceeded = True
                not_run.append(spec.name)
                continue
            argv = resolve_argv(spec)
            (self.workdir / OUT_DIRNAME / spec.name).mkdir(parents=True, exist_ok=True)
            (self.workdir / VERB_RECEIPTS_DIRNAME).mkdir(parents=True, exist_ok=True)
            deadline = self.deadline_for(spec)
            if spec.cli_verb not in available:
                before = store_rowset_hash(store)
                receipt = receipt_for(spec, argv, deadline_s=deadline, outcome=None, outputs={}, store_before=before,
                                      store_after=before, head=head, missing=True)
            else:
                if self.fresh_per_verb and receipts:
                    store = self.snapshot.snapshot(self.db, self.workdir)
                    snapshots += 1
                before = store_rowset_hash(store)
                effective = min(deadline, remaining)
                outcome = self.runner.run(
                    spec, [self.interpreter, "-m", "agentdecompile_recovery.corpus.cli", *argv], env, effective, cwd=self.workdir,
                )
                after = store_rowset_hash(store)
                receipt = receipt_for(spec, argv, deadline_s=deadline, outcome=outcome, outputs=collect_outputs(spec, self.workdir),
                                      store_before=before, store_after=after, head=head)
                if outcome.timed_out and effective < deadline:
                    receipt["deadline_source"] = "overall"
            receipts[spec.name] = receipt
            write_json(run_dir / f"{spec.name}.json", receipt)
        verdict = comparator.compare(receipts)
        for verb, receipt in receipts.items():
            receipt["comparison"] = verdict.get(verb, "")
            if receipt["outcome"] == Status.OK.value and verdict.get(verb) in ("changed", "new"):
                receipt["status"] = Status.CHANGED.value
            write_json(run_dir / f"{verb}.json", receipt)
        index = self.index(receipts, verdict, head=head, overall=overall, elapsed=time.monotonic() - started,
                           not_run=not_run, deadline_exceeded=deadline_exceeded, snapshots=snapshots,
                           reference=comparator.reference_id(), comparator=getattr(comparator, "name", "?"))
        write_json(run_dir / INDEX_FILENAME, index)
        (self.receipts / LATEST_FILENAME).write_text(self.run_id + "\n", encoding="utf-8")
        return index, receipts

    def index(self, receipts, verdict, *, head, overall, elapsed, not_run, deadline_exceeded, snapshots, reference, comparator):
        statuses = {verb: r["status"] for verb, r in sorted(receipts.items())}
        totals = {s.value: 0 for s in Status}
        for status in statuses.values():
            totals[status] = totals.get(status, 0) + 1
        for tag in ("same", "changed", "new", "gone"):
            totals["comparison_" + tag] = sum(1 for v in verdict.values() if v == tag)
        return {
            "schema": INDEX_SCHEMA, "run_id": self.run_id, "profile": self.profile, "head": head,
            "verbs": sorted(receipts), "order": [s.name for s in self.verbs], "statuses": statuses,
            "comparison": dict(sorted(verdict.items())), "previous_run_id": reference, "comparator": comparator,
            "totals": totals, "deadline_s": overall, "elapsed_s": round(elapsed, 1),
            "deadline_exceeded": deadline_exceeded, "not_run": list(not_run),
            "snapshot": {"strategy": getattr(self.snapshot, "used", getattr(self.snapshot, "name", "?")), "count": snapshots},
            "runner": getattr(self.runner, "name", "?"), "fresh_per_verb": self.fresh_per_verb,
            "allow_refusals": self.allow_refusals,
            "exit_code": exit_code_for(statuses, verdict, deadline_exceeded=deadline_exceeded, allow_refusals=self.allow_refusals),
        }


def exit_code_for(statuses: Mapping[str, str], verdict: Mapping[str, str], *, deadline_exceeded: bool, allow_refusals: bool) -> int:
    if deadline_exceeded or any(s in FAILURE_STATUSES for s in statuses.values()):
        return EXIT_FAILURE
    if any(s == Status.REFUSED.value for s in statuses.values()):
        return EXIT_CHANGED if allow_refusals else EXIT_FAILURE
    if any(v in ("changed", "new", "gone") for v in verdict.values()):
        return EXIT_CHANGED
    return EXIT_SAME


# --------------------------------------------------------------------------- CLI glue
def parse_verb_deadlines(items: Sequence[str] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in items or ():
        name, sep, secs = item.partition("=")
        if not sep or name not in VERBS:
            raise AttestRefused(f"attest: --verb-deadline expects NAME=SECS with a catalogue verb, got {item!r}")
        try:
            out[name] = float(secs)
        except ValueError as exc:
            raise AttestRefused(f"attest: --verb-deadline {name}: not a number") from exc
    return out


def select_verbs(verbs: str | None, profile: str | None) -> tuple[list[VerbSpec], str]:
    if verbs and profile:
        raise AttestRefused("attest: give --verbs or --profile, not both")
    if verbs:
        names = [v.strip() for v in verbs.split(",") if v.strip()]
        return VERBS.resolve(names), "custom"
    name = profile or "full"
    return VERBS.resolve(PROFILES.resolve(name)), name


def describe_catalogue() -> dict[str, Any]:
    return {
        "verbs": {name: spec.describe() for name, spec in VERBS.items()},
        "profiles": {name: list(names) for name, names in PROFILES.items()},
        "snapshots": sorted(SNAPSHOTS), "runners": sorted(RUNNERS), "comparators": sorted(COMPARATORS),
        "compare_exclude": sorted(RECEIPT_COMPARE_EXCLUDE),
    }


def run_cli(args: Any) -> int:
    """The ``corpus attest`` dispatch: refusals exit 2 with one line; otherwise the index's exit code."""
    verbs, profile = select_verbs(args.verbs, args.profile)
    verb_deadlines = parse_verb_deadlines(args.verb_deadline)
    if args.snapshot not in ("backup", "reflink"):
        raise AttestRefused(f"attest: --snapshot must be backup or reflink, got {args.snapshot!r}")
    receipts = Path(args.receipts)
    explicit_workdir = Path(args.workdir) if args.workdir else None
    db = check_store_path(Path(args.db), receipts, explicit_workdir)
    receipts.mkdir(parents=True, exist_ok=True)
    workdir = explicit_workdir or Path(tempfile.mkdtemp(prefix="corpus-attest-"))
    try:
        run = AttestationRun(
            db=db, receipts=receipts, workdir=workdir, verbs=verbs, snapshot=SNAPSHOTS[args.snapshot](),
            deadline_s=args.deadline_s, verb_deadlines=verb_deadlines, fresh_per_verb=bool(args.fresh_per_verb),
            allow_refusals=bool(args.allow_refusals), pythonpath=args.pythonpath, profile=profile,
        )
        index, _ = run.execute()
    finally:
        if explicit_workdir is None:
            shutil.rmtree(workdir, ignore_errors=True)
    sys.stdout.write(dump_json(index))
    return int(index["exit_code"])


__all__ = [
    "COMPARATORS", "PROFILES", "RECEIPT_COMPARE_EXCLUDE", "RUNNERS", "SCHEMA", "SNAPSHOTS", "VERBS",
    "AttestRefused", "AttestationRun", "BackupApiSnapshot", "BaselineComparator", "BudgetClass", "Comparator",
    "GridRunner", "MaterializedSnapshot", "NoComparator", "OverlaySnapshot", "PreviousRunComparator",
    "ProfileRegistry", "ReflinkSnapshot", "RunOutcome", "Runner", "SnapshotStrategy", "Status",
    "SubprocessRunner", "VerbCatalogue", "VerbSpec", "available_cli_verbs", "check_store_path", "child_env",
    "classify_refusal", "compare_key", "describe_catalogue", "exit_code_for", "hashed_slug", "receipt_for",
    "resolve_argv", "run_cli", "scrub_paths", "source_head", "stdout_head", "store_rowset_hash",
]

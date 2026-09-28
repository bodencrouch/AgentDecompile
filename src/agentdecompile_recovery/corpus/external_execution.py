"""Guarded execution of pinned external diagnostic providers (reccmp, ReAgent).

P1.3 step 1. The parent freezes every path, input hash, provider pin and manifest
fact before any reservation; the guarded child (``-I -S``) re-verifies them, launches
the provider through the venv interpreter with an explicit environment allowlist,
re-hashes inputs after the run and writes ``execution.json``. Nothing here grants
recovery acceptance: bound receipts stay ``proposal_only``.

Stdlib only, because the guarded child runs without site-packages. Upstream file
formats that were not checked against the pinned sources in this step are marked
``unverified`` where they are produced.
"""
from __future__ import annotations

import base64
import configparser
import csv
import hashlib
import io
import json
import math
import os
import pwd
import re
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
import time
from pathlib import Path

from . import external_validation

SCHEMA = "agentdecompile.external-execution/v1"
PINS = {
    "reccmp-compare": {"distribution": "reccmp", "version": "0.1.7",
                       "commit": "e91a51bfadfbb600adfdc750589ac40ae9742883",
                       "archive_sha256": "6801afde929b3fb847a482a9c8aff0f674a133ec72594a426bc4ef3c81e36aaa",
                       "script": "reccmp-reccmp"},
    "reagent-benchmark": {"distribution": "auto-re-agent", "version": "0.4.0",
                          "commit": "d12cea338c61898b06a86fe8adb25275fa9d5615",
                          "archive_sha256": "65c22a9de6fc63bed302152e7e20bc548970594131ededef00f01fc6c2baec3f",
                          "script": "re-agent"},
}
REFUSAL_CODES = frozenset({
    "wine_unavailable", "winepath_unavailable", "wineserver_unavailable", "cvdump_unavailable",
    "wineprefix_uninitialized", "wineprefix_default_refused",
    "provider_unpinned", "provider_record_mismatch", "provider_entry_point_missing",
    "provider_interpreter_unavailable", "provider_implementation_changed",
    "input_hash_mismatch", "input_changed_during_run", "project_hash_mismatch",
    "reccmp_target_unknown", "pdb_rebuild_mismatch", "slug_md5_mismatch",
    "report_dir_exists", "report_dir_parent_missing", "symlink_external_resource", "output_aliases_input",
    "manifest_invalid", "manifest_shell_command", "candidate_not_consumed", "manifest_timeout_exceeds_action",
})
_UNAVAILABLE = frozenset({"wine_unavailable", "winepath_unavailable", "wineserver_unavailable",
                          "cvdump_unavailable", "wineprefix_uninitialized", "provider_interpreter_unavailable"})
EXECUTION_STATES = ("completed", "crashed", "timed_out", "unavailable", "unsupported", "invalid_output")
ENV_ALLOWLIST = frozenset({"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "WINEPREFIX", "WINEDEBUG"})
DEFAULT_TIMEOUT, MAX_TIMEOUT = 1800, 7200
# (name, kind, declared sha256 required)
INPUTS = {
    "reccmp-compare": (("original", "file", True), ("rebuild", "file", True), ("pdb", "file", True),
                       ("project-dir", "tree", False)),
    "reagent-benchmark": (("manifest", "file", True), ("candidate", "file", True),
                          ("inputs-dir", "tree", False), ("candidate-receipt", "file", False)),
}
_SHELLS = frozenset({"sh", "bash", "dash", "zsh", "ksh", "csh", "tcsh", "fish", "env", "busybox",
                     "cmd", "cmd.exe", "powershell", "pwsh"})
_PDB_MAGIC = b"Microsoft C/C++ MSF 7.00\r\n\x1aDS\x00\x00\x00"
_BOOTSTRAP = ('import sys;sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv.pop(1));'
              'from agentdecompile_recovery.corpus.external_execution import guarded_main;guarded_main(sys.argv[1])')


class Refusal(ValueError):
    """A named refusal; ``code`` is one of REFUSAL_CODES, optionally ``<code>:<name>``."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _refuse(code: str):
    raise Refusal(code)


def _file_sha(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _absolute(value, root) -> Path:
    path = Path(value)
    return Path(os.path.abspath(path if path.is_absolute() else Path(root) / path))


def _no_symlink(path: Path):
    for part in [path, *path.parents]:
        if part.is_symlink():
            _refuse("symlink_external_resource")


def _tree_identity(root: Path) -> str:
    entries = []
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        for name in sorted(dirs + files):
            full = Path(current, name)
            if full.is_symlink():
                _refuse("symlink_external_resource")
            rel = full.relative_to(root).as_posix()
            if full.is_dir():
                entries.append([rel, "dir"])
            elif stat.S_ISREG(full.lstat().st_mode):
                entries.append([rel, _file_sha(full)])
            else:
                _refuse("symlink_external_resource")
    return _json_sha(entries)


def _identity(kind: str, path: str):
    try:
        return _tree_identity(Path(path)) if kind == "tree" else _file_sha(path)
    except FileNotFoundError:
        return None


# --- provider --------------------------------------------------------------------------

def _normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def _metadata(text: str) -> dict:
    fields = {}
    for line in text.splitlines():
        if not line.strip():
            break
        key, sep, value = line.partition(":")
        if sep:
            fields.setdefault(key.strip(), value.strip())
    return fields


def _verify_record(site: Path, dist: Path, venv: Path) -> set:
    try:
        rows = list(csv.reader(io.StringIO((dist / "RECORD").read_text())))
    except (OSError, UnicodeError, csv.Error):
        _refuse("provider_record_mismatch")
    listed = set()
    for row in rows:
        if not row or not row[0]:
            continue
        rel = os.path.normpath(row[0]).replace(os.sep, "/")
        if len(row) < 2 or not row[1]:
            continue  # RECORD itself and generated files carry no hash
        target = Path(os.path.normpath(site / row[0]))
        if venv != target and venv not in target.parents:
            _refuse("provider_record_mismatch")
        algo, _, expected = row[1].partition("=")
        try:
            data = target.read_bytes()
        except OSError:
            _refuse("provider_record_mismatch")
        if algo != "sha256" or base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode() != expected:
            _refuse("provider_record_mismatch")
        if len(row) > 2 and row[2] and row[2] != str(len(data)):
            _refuse("provider_record_mismatch")
        listed.add(rel)
    for name in ("METADATA", "direct_url.json", "entry_points.txt"):
        if f"{dist.name}/{name}" not in listed:
            _refuse("provider_record_mismatch")
    return listed


def verify_provider(venv, provider: str) -> dict:
    """Prove the venv holds exactly the pinned provider and return its identity."""
    pin = PINS[provider]
    venv = Path(os.path.abspath(venv))
    python = venv / "bin" / "python"
    if not python.is_file() or not os.access(python, os.X_OK) or not (venv / "pyvenv.cfg").is_file():
        _refuse("provider_interpreter_unavailable")
    interpreter = os.path.realpath(python)
    wanted = _normalized_name(pin["distribution"])
    dists = [(site, dist) for site in sorted(venv.glob("lib/python*/site-packages"))
             for dist in sorted(site.glob("*.dist-info"))
             if _normalized_name(dist.name[:-len(".dist-info")].rsplit("-", 1)[0]) == wanted]
    if len(dists) != 1:
        _refuse("provider_unpinned")
    site, dist = dists[0]
    try:
        meta = _metadata((dist / "METADATA").read_text())
        direct = json.loads((dist / "direct_url.json").read_text())
    except (OSError, UnicodeError, ValueError):
        _refuse("provider_unpinned")
    match = re.search(r"/archive/([0-9a-f]{40})\.(?:tar\.gz|zip)$", str(direct.get("url", "")))
    archive = direct.get("archive_info") if isinstance(direct.get("archive_info"), dict) else {}
    hashes = archive.get("hashes") if isinstance(archive.get("hashes"), dict) else {}
    if (meta.get("Version") != pin["version"] or _normalized_name(meta.get("Name", "")) != wanted
            or not match or match.group(1) != pin["commit"]
            or hashes.get("sha256") != pin["archive_sha256"]
            or archive.get("hash", f"sha256={pin['archive_sha256']}") != f"sha256={pin['archive_sha256']}"):
        _refuse("provider_unpinned")
    listed = _verify_record(site, dist, venv)
    parser = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    parser.optionxform = str
    try:
        parser.read_string((dist / "entry_points.txt").read_text())
        entry = parser.get("console_scripts", pin["script"]).strip()
    except (OSError, configparser.Error):
        _refuse("provider_entry_point_missing")
    entry = re.sub(r"\s*\[.*\]$", "", entry)
    if not re.fullmatch(r"[\w.]+:[\w.]+", entry):
        _refuse("provider_entry_point_missing")
    module_path = entry.split(":")[0].replace(".", "/")
    if not {f"{module_path}.py", f"{module_path}/__init__.py"} & listed:
        _refuse("provider_entry_point_missing")
    identity = {"provider": provider, "distribution": pin["distribution"], "version": meta["Version"],
                "commit": match.group(1), "archive_sha256": hashes["sha256"], "venv": str(venv),
                "dist_info": str(dist), "record_sha256": _file_sha(dist / "RECORD"),
                "script": pin["script"], "entry_point": entry, "interpreter": interpreter,
                "interpreter_sha256": _file_sha(interpreter),
                "pyvenv_cfg_sha256": _file_sha(venv / "pyvenv.cfg"), "verified": True}
    identity["identity_sha256"] = _json_sha(identity)
    return identity


def reverify_provider(frozen: dict) -> dict:
    """Child-side re-verification; any drift from the frozen identity is a refusal."""
    try:
        identity = verify_provider(frozen["provider-venv"], frozen["provider"])
    except Refusal as exc:
        if exc.code == "provider_interpreter_unavailable":
            raise
        _refuse("provider_implementation_changed")
    if identity != frozen["provider-identity"]:
        _refuse("provider_implementation_changed")
    return identity


# --- PE / PDB ------------------------------------------------------------------------------

def _codeview(data: bytes):
    if data[:2] != b"MZ":
        raise ValueError("not a PE image")
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
        raise ValueError("missing PE signature")
    sections, = struct.unpack_from("<H", data, e_lfanew + 6)
    opt_size, = struct.unpack_from("<H", data, e_lfanew + 20)
    opt = e_lfanew + 24
    magic, = struct.unpack_from("<H", data, opt)
    if magic == 0x10B:
        count_at, dirs_at = opt + 92, opt + 96
    elif magic == 0x20B:
        count_at, dirs_at = opt + 108, opt + 112
    else:
        raise ValueError("unknown optional header")
    if struct.unpack_from("<I", data, count_at)[0] < 7:
        raise ValueError("no debug directory")
    rva, size = struct.unpack_from("<II", data, dirs_at + 6 * 8)
    if not rva or size < 28:
        raise ValueError("empty debug directory")
    offset = None
    for index in range(sections):
        vsize, va, raw_size, raw_ptr = struct.unpack_from("<IIII", data, opt + opt_size + 40 * index + 8)
        if va <= rva < va + max(vsize, raw_size):
            offset = raw_ptr + rva - va
            break
    if offset is None:
        raise ValueError("debug directory outside sections")
    found = []
    for index in range(size // 28):
        kind, length, _, pointer = struct.unpack_from("<IIII", data, offset + 28 * index + 12)
        if kind == 2:
            record = data[pointer:pointer + length]
            if len(record) >= 24 and record[:4] == b"RSDS":
                found.append((record[4:20], struct.unpack_from("<I", record, 20)[0]))
    if len(found) != 1:
        raise ValueError("expected exactly one RSDS CodeView entry")
    return found[0]


def _pdb_info(data: bytes):
    if data[:32] != _PDB_MAGIC:
        raise ValueError("not an MSF 7.00 PDB")
    block_size, _, blocks, dir_bytes, _, map_addr = struct.unpack_from("<6I", data, 32)
    if block_size not in (512, 1024, 2048, 4096) or len(data) < blocks * block_size:
        raise ValueError("truncated PDB")

    def block(index):
        if index >= blocks:
            raise ValueError("block outside file")
        return data[index * block_size:(index + 1) * block_size]

    dir_blocks = struct.unpack_from(f"<{math.ceil(dir_bytes / block_size)}I", data, map_addr * block_size)
    directory = b"".join(block(i) for i in dir_blocks)[:dir_bytes]
    streams, = struct.unpack_from("<I", directory, 0)
    if streams < 2:
        raise ValueError("no PDB info stream")
    sizes = struct.unpack_from(f"<{streams}I", directory, 4)
    position = 4 + 4 * streams
    for index, size in enumerate(sizes):
        size = 0 if size == 0xFFFFFFFF else size
        count = math.ceil(size / block_size)
        indices = struct.unpack_from(f"<{count}I", directory, position)
        position += 4 * count
        if index == 1:
            info = b"".join(block(i) for i in indices)[:size]
            if len(info) < 28:
                raise ValueError("short PDB info stream")
            return info[12:28], struct.unpack_from("<I", info, 8)[0]
    raise ValueError("no PDB info stream")


def pdb_matches_rebuild(rebuild, pdb) -> dict:
    """Require the rebuild's CodeView RSDS GUID and age to equal the PDB info stream's."""
    try:
        image = _codeview(Path(rebuild).read_bytes())
        info = _pdb_info(Path(pdb).read_bytes())
    except (OSError, ValueError, struct.error, IndexError):
        _refuse("pdb_rebuild_mismatch")
    if image != info:
        _refuse("pdb_rebuild_mismatch")
    return {"guid": image[0].hex(), "age": image[1]}


# --- reccmp project ---------------------------------------------------------------------------

def _project_target_hash(text: str, target: str):
    """Minimal read of reccmp-project.yml: returns (target found, declared original sha256)."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.rstrip() == "targets:")
    except StopIteration:
        return False, None
    block, indent, inside = [], None, False
    for line in lines[start + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        depth = len(line) - len(line.lstrip())
        if depth == 0:
            break
        indent = depth if indent is None else indent
        if depth == indent:
            inside = line.strip().rstrip(":").strip("'\"") == target and line.rstrip().endswith(":")
            if inside:
                block.append(line)
        elif inside:
            block.append(line)
    if not block:
        return False, None
    match = re.search(r"sha256:\s*['\"]?([0-9a-fA-F]{64})", "\n".join(block))
    return True, match.group(1).lower() if match else None


def write_reccmp_config(frozen: dict, workdir) -> list:
    """Write reccmp-user.yml and reccmp-build.yml as JSON (a YAML 1.2 subset).

    Key layout follows the upstream project/user/build split as understood from
    reccmp documentation; it is unverified against the pinned commit in this step.
    """
    target = frozen["reccmp-target"]
    documents = {"reccmp-user.yml": {"targets": {target: {"path": frozen["original"]}}},
                 "reccmp-build.yml": {"project": frozen["project-dir"],
                                      "targets": {target: {"path": frozen["rebuild"], "pdb": frozen["pdb"]}}}}
    written = []
    for name, document in documents.items():
        path = Path(workdir) / name
        with open(path, "x") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
        written.append(path)
    return written


# --- manifest -------------------------------------------------------------------------------------

def _argv0(argv0: str) -> dict:
    if not os.path.isabs(argv0) or not os.path.isfile(argv0):
        _refuse("manifest_invalid")
    real = os.path.realpath(argv0)
    return {"path": real, "sha256": _file_sha(real)}


def validate_benchmark_manifest(path, candidate: str, *, timeout: int) -> list:
    """Validate a ReAgent benchmark manifest as argv arrays that consume the candidate.

    Row layout (``benchmarks`` list, ``reference``/``candidate`` argv, ``timeout_s``)
    is this adapter's contract; it is unverified against the pinned ReAgent schema.
    """
    try:
        data = json.loads(Path(path).read_bytes())
    except (OSError, ValueError, UnicodeError):
        _refuse("manifest_invalid")
    rows = data.get("benchmarks") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        _refuse("manifest_invalid")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip():
            _refuse("manifest_invalid")
        for side in ("reference", "candidate"):
            argv = row.get(side)
            if isinstance(argv, str):
                _refuse("manifest_shell_command")
            if isinstance(argv, list) and argv and isinstance(argv[0], str) and os.path.basename(argv[0]) in _SHELLS:
                _refuse("manifest_shell_command")
        for side in ("reference", "candidate"):
            argv = row.get(side)
            if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
                _refuse("manifest_invalid")
        limit = row.get("timeout_s", row.get("timeout"))
        if limit is not None:
            if type(limit) not in (int, float) or not math.isfinite(limit) or limit <= 0:
                _refuse("manifest_invalid")
            if limit > timeout:
                _refuse("manifest_timeout_exceeds_action")
        result.append({"name": row["name"], "reference_argv0": _argv0(row["reference"][0]),
                       "candidate_argv0": _argv0(row["candidate"][0]),
                       "consumes_candidate": any(candidate in a for a in row["candidate"][1:]),
                       "timeout_s": limit})
    if not any(row["consumes_candidate"] for row in result):
        _refuse("candidate_not_consumed")
    return result


# --- wine ---------------------------------------------------------------------------------------------

def _executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _freeze_wine(frozen: dict, root) -> dict:
    wine = _absolute(frozen.get("wine") or "/nonexistent/wine", root)
    if not _executable(wine):
        _refuse("wine_unavailable")
    tools = {"wine": wine}
    for name in ("winepath", "wineserver"):
        tools[name] = wine.parent / name
        if not _executable(tools[name]):
            _refuse(f"{name}_unavailable")
    if frozen.get("cvdump"):
        tools["cvdump"] = _absolute(frozen["cvdump"], root)
        if not tools["cvdump"].is_file():
            _refuse("cvdump_unavailable")
    prefix = _absolute(frozen.get("wineprefix") or "", root)
    default = os.path.realpath(os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".wine"))
    if not frozen.get("wineprefix") or os.path.realpath(prefix) == default:
        _refuse("wineprefix_default_refused")
    _no_symlink(prefix)
    if not prefix.is_dir() or not (prefix / "system.reg").is_file():
        _refuse("wineprefix_uninitialized")
    frozen["wineprefix"] = str(prefix)
    frozen["wine"] = str(wine)
    if "cvdump" in tools:
        frozen["cvdump"] = str(tools["cvdump"])
    return {name: {"path": str(path), "realpath": os.path.realpath(path), "sha256": _file_sha(path)}
            for name, path in tools.items()}


def wine_shutdown(wineserver: str, wineprefix: str, env: dict, timeout: float = 60) -> list:
    """Kill, then wait for, the wineserver of the frozen prefix. wineserver daemonizes."""
    steps = []
    for flag in ("-k", "-w"):
        step = {"argv": [wineserver, flag], "returncode": None}
        try:
            step["returncode"] = subprocess.run(step["argv"], env={**env, "WINEPREFIX": wineprefix},
                                                stdin=subprocess.DEVNULL, capture_output=True,
                                                timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            step["timed_out"] = True
        except OSError as exc:
            step["error"] = type(exc).__name__
        steps.append(step)
    return steps


# --- freeze -----------------------------------------------------------------------------------------

def freeze_parameters(params: dict, provider: str, root=None) -> dict:
    """Parent-side freeze: absolute paths, symlink refusal, input hashes, provider pin."""
    if provider not in PINS:
        raise ValueError("unsupported_external_provider")
    root = Path(root or os.getcwd())
    frozen = {k: v for k, v in params.items() if v is not None}
    frozen["provider"] = provider
    timeout = frozen.get("timeout", DEFAULT_TIMEOUT)
    if type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT:
        raise ValueError("external_timeout_out_of_range")
    frozen["timeout"] = timeout

    report = _absolute(frozen.get("report-dir") or "", root)
    if not frozen.get("report-dir"):
        raise ValueError("external_requires_report-dir")
    _no_symlink(report)
    if report.exists():
        _refuse("report_dir_exists")
    if not report.parent.is_dir():
        _refuse("report_dir_parent_missing")
    frozen["report-dir"] = str(report)
    if not frozen.get("provider-venv"):
        raise ValueError("external_requires_provider-venv")
    venv = _absolute(frozen["provider-venv"], root)
    _no_symlink(venv)
    frozen["provider-venv"] = str(venv)

    identities, guarded = {}, [venv]
    for name, kind, needs_hash in INPUTS[provider]:
        if not frozen.get(name):
            if needs_hash or kind == "tree":
                raise ValueError("external_requires_" + name)
            continue
        path = _absolute(frozen[name], root)
        _no_symlink(path)
        if kind == "tree":
            if not path.is_dir():
                _refuse(f"input_hash_mismatch:{name}")
        elif not stat.S_ISREG(path.lstat().st_mode if path.exists() else 0):
            _refuse(f"input_hash_mismatch:{name}")
        identities[name] = _identity(kind, str(path))
        declared = frozen.get(f"{name}-sha256")
        if needs_hash and not declared:
            raise ValueError(f"external_requires_{name}-sha256")
        if declared and str(declared).lower() != identities[name]:
            _refuse(f"input_hash_mismatch:{name}")
        frozen[name] = str(path)
        guarded.append(path)

    if provider == "reccmp-compare":
        frozen["wine-tools"] = _freeze_wine(frozen, root)
        guarded.append(Path(frozen["wineprefix"]))
    for path in guarded:
        if report == path or path in report.parents:
            _refuse("output_aliases_input")

    frozen["provider-identity"] = verify_provider(venv, provider)
    if provider == "reccmp-compare":
        frozen["pdb-identity"] = pdb_matches_rebuild(frozen["rebuild"], frozen["pdb"])
        project_file = Path(frozen["project-dir"]) / "reccmp-project.yml"
        found, declared = _project_target_hash(project_file.read_text() if project_file.is_file() else "",
                                               str(frozen.get("reccmp-target") or ""))
        if not found:
            _refuse("reccmp_target_unknown")
        if declared != identities["original"]:
            _refuse("project_hash_mismatch")
        if frozen.get("binary-slug"):
            if not frozen.get("db"):
                raise ValueError("external_requires_db_for_binary-slug")
            db = _absolute(frozen["db"], root)
            md5 = hashlib.md5(Path(frozen["original"]).read_bytes()).hexdigest()
            con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
            try:
                row = con.execute("SELECT md5 FROM binary WHERE slug=?", (frozen["binary-slug"],)).fetchone()
            finally:
                con.close()
            if not row or not row[0] or str(row[0]).lower() != md5:
                _refuse("slug_md5_mismatch")
            frozen["db"] = str(db)
            frozen["original-md5"] = md5
    else:
        frozen["manifest-rows"] = validate_benchmark_manifest(frozen["manifest"], frozen["candidate"],
                                                              timeout=timeout)
    frozen["input-identities"] = identities
    return frozen


def input_identities(frozen: dict) -> dict:
    return {name: _identity(kind, frozen[name]) for name, kind, _ in INPUTS[frozen["provider"]]
            if frozen.get(name)}


def compare_identities(expected: dict, actual: dict, code: str):
    for name in sorted(set(expected) | set(actual)):
        if expected.get(name) != actual.get(name):
            _refuse(f"{code}:{name}")


# --- child launch -------------------------------------------------------------------------------------

def provider_invocation(frozen: dict):
    """argv and cwd for ``<venv>/bin/python -I -c <entry-point shim>`` (no -S, no console script)."""
    identity = frozen["provider-identity"]
    module, attr = identity["entry_point"].split(":")
    shim = (f"import sys,importlib,functools;sys.argv[0]={identity['script']!r};"
            f"sys.exit(functools.reduce(getattr,{attr!r}.split('.'),importlib.import_module({module!r}))())")
    report = frozen["report-dir"]
    if frozen["provider"] == "reccmp-compare":
        args, cwd = ["--target", frozen["reccmp-target"], "--json", f"{report}/report.json", "--silent"], f"{report}/reccmp"
    else:
        args, cwd = ["benchmark", "--manifest", frozen["manifest"], "--output", f"{report}/report.json"], f"{report}/work"
    return [str(Path(frozen["provider-venv"]) / "bin" / "python"), "-I", "-c", shim, *args], cwd


def child_environment(frozen: dict) -> dict:
    """Explicit allowlist. Nothing is inherited from the server environment."""
    report = frozen["report-dir"]
    env = {"PATH": "/usr/bin:/bin", "HOME": f"{report}/home", "TMPDIR": f"{report}/tmp",
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC"}
    if frozen["provider"] == "reccmp-compare":
        env.update(PATH=f"{Path(frozen['wine']).parent}:/usr/bin:/bin",
                   WINEPREFIX=frozen["wineprefix"], WINEDEBUG="-all")
    assert set(env) <= ENV_ALLOWLIST
    return env


def execution_state(returncode=None, *, timed_out=False, report_valid=False, refusal=None) -> str:
    if refusal:
        base = refusal.split(":")[0]
        if base == "input_changed_during_run":
            return "invalid_output"
        return "unavailable" if base in _UNAVAILABLE else "unsupported"
    if timed_out:
        return "timed_out"
    if returncode != 0:
        return "crashed"
    return "completed" if report_valid else "invalid_output"


def implementation_identity() -> dict:
    return {str(Path(p).resolve()): hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in (__file__, external_validation.__file__)}


def guarded_command(params: dict) -> list:
    root = str(Path(__file__).resolve().parents[2])
    return [sys.executable, "-I", "-S", "-c", _BOOTSTRAP, root,
            json.dumps({"params": params, "implementation": implementation_identity()}, sort_keys=True)]


def command_matches(argv, params) -> bool:
    try:
        json.loads(argv[-1])
        return argv == guarded_command(params)
    except (TypeError, ValueError, IndexError, AttributeError):
        return False


def guarded_main(raw: str):
    payload = json.loads(raw)
    if payload.get("implementation") != implementation_identity():
        raise ValueError("external_execution_implementation_changed")
    raise SystemExit(run(payload["params"]))


def _write_json(path: Path, value):
    temporary = path.with_name(path.name + ".partial")
    with open(temporary, "x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def run(frozen: dict) -> int:
    """Child body: re-verify, launch, re-hash, write execution.json (and normalized.json)."""
    report = Path(frozen["report-dir"])
    try:
        report.mkdir(mode=0o700)
    except FileExistsError:
        _refuse("report_dir_exists")
    for sub in ("home", "tmp"):
        (report / sub).mkdir()
    pin = PINS[frozen["provider"]]
    execution = {"schema": SCHEMA, "provider": frozen["provider"], "params": frozen,
                 "pin": {"commit": pin["commit"], "archive_sha256": pin["archive_sha256"],
                         "version": pin["version"], "verified": False},
                 "provider_identity": None,
                 "inputs": {"freeze": frozen["input-identities"], "before": None, "after": None},
                 "argv": None, "cwd": None, "env": None, "wine_tools": frozen.get("wine-tools"),
                 "process": None, "streams": None, "raw_report_sha256": None, "raw_report_bytes": None,
                 "report_error": None, "wine_shutdown": None, "execution_state": None, "refusal": None,
                 "started_at": time.time(), "finished_at": None}
    normalized = None
    try:
        identity = reverify_provider(frozen)
        execution["provider_identity"] = identity
        execution["pin"]["verified"] = identity["commit"] == pin["commit"] and identity["verified"] is True
        before = input_identities(frozen)
        execution["inputs"]["before"] = before
        compare_identities(frozen["input-identities"], before, "input_hash_mismatch")
        if frozen["provider"] == "reccmp-compare":
            execution["pdb_identity"] = pdb_matches_rebuild(frozen["rebuild"], frozen["pdb"])
            (report / "reccmp").mkdir()
            write_reccmp_config(frozen, report / "reccmp")
        else:
            shutil.copytree(frozen["inputs-dir"], report / "work", symlinks=True)
        argv, cwd = provider_invocation(frozen)
        env = child_environment(frozen)
        execution.update(argv=argv, cwd=cwd, env=env)
        timed_out, started = False, time.monotonic()
        with open(report / "stdout.log", "xb") as out, open(report / "stderr.log", "xb") as err:
            try:
                process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
            except OSError:
                _refuse("provider_interpreter_unavailable")
            try:
                returncode = process.wait(timeout=frozen["timeout"])
            except subprocess.TimeoutExpired:
                timed_out = True
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                returncode = process.returncode
        execution["process"] = {"pid": process.pid, "returncode": returncode, "timed_out": timed_out,
                                "elapsed_s": time.monotonic() - started}
        if frozen["provider"] == "reccmp-compare":
            execution["wine_shutdown"] = wine_shutdown(frozen["wine-tools"]["wineserver"]["path"],
                                                       frozen["wineprefix"], env)
        after = input_identities(frozen)
        execution["inputs"]["after"] = after
        execution["streams"] = {name: {"sha256": _file_sha(report / f"{name}.log"),
                                       "bytes": (report / f"{name}.log").stat().st_size}
                                for name in ("stdout", "stderr")}
        valid = False
        raw_path = report / "report.json"
        if raw_path.is_file() and not raw_path.is_symlink():
            with raw_path.open("rb") as stream:
                raw = stream.read(external_validation.MAX_REPORT_BYTES + 1)
            execution["raw_report_sha256"] = hashlib.sha256(raw).hexdigest()
            execution["raw_report_bytes"] = len(raw)
            try:
                normalized = external_validation.normalize_report(raw, frozen["provider"])
                valid = True
            except external_validation.InvalidReport as exc:
                execution["report_error"] = str(exc)
        try:
            compare_identities(before, after, "input_changed_during_run")
        except Refusal as exc:
            execution["refusal"] = exc.code
        execution["execution_state"] = execution_state(returncode, timed_out=timed_out, report_valid=valid,
                                                       refusal=execution["refusal"])
    except Refusal as exc:
        execution["refusal"] = exc.code
        execution["execution_state"] = execution_state(refusal=exc.code)
    execution["finished_at"] = time.time()
    _write_json(report / "execution.json", execution)
    if normalized is not None:
        _write_json(report / "normalized.json", external_validation.bind_execution(normalized, execution))
    state = execution["execution_state"]
    return 0 if state == "completed" else 124 if state == "timed_out" else 2 if execution["refusal"] else 1

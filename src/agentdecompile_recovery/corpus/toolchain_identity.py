"""Per-build toolchain identity and toolchain/group calibration (P2-e, U54/U62).

A toolchain identity names the exact compiler, linker and assembler a build
used. :func:`capture` hashes each tool's executable bytes and its version
output, records the flags and the build-relevant environment, and, for a
Wine-hosted MSVC toolchain, the executable's path relative to the Wine
prefix. The result is one of two records:

* ``pinned``: a deterministic 64-hex ``identity_sha256`` over those facts.
* ``unpinned``: no identity at all, plus a ``reason`` naming what could not
  be established (a missing tool, a failed or unstable version probe, an
  executable outside the Wine prefix, ...).

Nothing here fabricates an identity. A version probe that times out, fails
without output, or answers differently on a second run makes the record
``unpinned``. ``pinned:none`` and other placeholders never pass
:func:`verify`.

The identity is relocatable. Absolute tool locations are kept under
``locations`` and are not hashed. Environment values and version text are
rewritten against named roots (``$WINEPREFIX`` and any caller-supplied
root), in both POSIX and Wine ``Z:\\`` forms, so the same install under a
moved prefix yields the same identity.

:func:`group` reduces per-unit records to one identity or a named refusal
(``mixed_toolchain_identity``, ``member_unpinned``). :func:`calibrate`
compiles one fixed probe source several times with the recorded compiler
and records whether the object bytes repeat (optionally after masking the
COFF ``TimeDateStamp``) and whether they equal an expected digest.

Claim boundary: an identity says which tools a build used. A calibration
says the recorded compiler turns one probe into repeatable bytes. Neither
is a byte-accuracy or whole-image claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping

SCHEMA = "agentdecompile.toolchain-identity/v1"
CALIBRATION_SCHEMA = "agentdecompile.toolchain-calibration/v1"

#: Every role a record describes. A role must be declared; ``None`` declares it unused.
ROLES = ("compiler", "linker", "assembler")

#: Environment keys that can change what the tools emit. Other keys are ignored.
#: ``CL``/``_CL_``/``LINK``/``_LINK_``/``ML`` inject MSVC flags; ``INCLUDE``/``LIB``
#: choose headers and libraries.
RELEVANT_ENV_KEYS = (
    "ASFLAGS", "CFLAGS", "CL", "CPPFLAGS", "CXXFLAGS", "INCLUDE", "LDFLAGS", "LIB",
    "LIBPATH", "LINK", "ML", "SOURCE_DATE_EPOCH", "WINEARCH", "WINEDLLOVERRIDES",
    "WINEPREFIX", "WINEPATH", "WINEDEBUG", "PATH", "LC_ALL", "LANG", "LC_CTYPE",
    "HOME", "USER", "LOGNAME", "DISPLAY", "XDG_RUNTIME_DIR", "TMPDIR", "_CL_", "_LINK_",
)

# Strict measured MSVC children receive only these inherited values, plus the
# execution owner's controlled Wine/include overrides. Every retained value is
# bound; loader hooks, custom Wine launchers and unrelated secrets are excluded.
MEASURED_MSVC_ENV_KEYS = (
    "PATH", "HOME", "USER", "LOGNAME", "DISPLAY", "XDG_RUNTIME_DIR", "TMPDIR",
    "WINEARCH", "WINEDLLOVERRIDES", "WINEDEBUG", "SOURCE_DATE_EPOCH",
)

#: Version text kept in the record for reading; the full text is hashed.
VERSION_TEXT_LIMIT = 4000

#: COFF machine values whose object header carries a TimeDateStamp at bytes 4..8.
_COFF_MACHINES = frozenset({0x014C, 0x8664, 0x01C0, 0x01C4, 0xAA64, 0x0200})

_HEX64 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class ToolSpec:
    """One tool: its executable, the arguments that make it print a version, its flags."""

    path: Path
    version_args: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "version_args", tuple(self.version_args))
        object.__setattr__(self, "flags", tuple(self.flags))


@dataclass(frozen=True)
class WineHost:
    """Tools run as ``wine <exe>`` under ``prefix``."""

    prefix: Path
    wine: Path | str = "wine"
    extra_env: Mapping[str, str] = field(default_factory=dict)


class _Unpinned(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# ------------------------------------------------------------------ helpers


def sha256_file(path: str | os.PathLike) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_bytes(obj) -> bytes:
    """The one serialization every hash here uses."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def _root_forms(roots: Mapping[str, str | os.PathLike]) -> list[tuple[str, str]]:
    """(literal, placeholder) pairs, longest literal first."""
    pairs: set[tuple[str, str]] = set()
    for name, root in roots.items():
        for p in {str(Path(root)), os.path.realpath(root)}:
            p = p.rstrip("/")
            if not p:
                continue
            pairs.add((p, f"${name}"))
            if p.startswith("/"):
                win = p.replace("/", "\\")
                pairs.add(("Z:" + win, f"${name}"))
                pairs.add(("z:" + win, f"${name}"))
    return sorted(pairs, key=lambda kv: (-len(kv[0]), kv))


def _relocate(text: str, forms: list[tuple[str, str]]) -> str:
    for literal, placeholder in forms:
        text = text.replace(literal, placeholder)
    return text


def _run_env(env: Mapping[str, str], wine: WineHost | None) -> dict[str, str]:
    out = {"PATH": os.environ.get("PATH") or "/usr/bin:/bin", "LC_ALL": "C"}
    out.update({str(k): str(v) for k, v in env.items()})
    if wine is not None:
        out["WINEPREFIX"] = str(wine.prefix)
        out.setdefault("WINEDEBUG", "-all")
        out.update({str(k): str(v) for k, v in wine.extra_env.items()})
    return out


def _probe_once(argv: list[str], env: dict[str, str], timeout: float) -> tuple[int, str] | None:
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout, env=env, check=False,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout + proc.stderr).decode("utf-8", "replace").replace("\r\n", "\n").strip()
    if not text:
        return None
    return proc.returncode, text


def _probe(role: str, argv: list[str], env: dict[str, str], timeout: float) -> tuple[int, str]:
    """Run the version probe twice. Both runs must answer, and answer alike."""
    first = _probe_once(argv, env, timeout)
    if first is None:
        raise _Unpinned(f"{role}_version_probe_failed: no output, error or timeout")
    second = _probe_once(argv, env, timeout)
    if second is None:
        raise _Unpinned(f"{role}_version_probe_failed: second run gave no output")
    if first != second:
        raise _Unpinned(f"{role}_version_output_unstable: two runs differ")
    return first


# ------------------------------------------------------------------ capture


def _component(role: str, spec: ToolSpec, *, env: dict[str, str], wine: WineHost | None,
               forms: list[tuple[str, str]], timeout: float,
               roots: Mapping[str, str | os.PathLike]) -> tuple[dict, str]:
    path = spec.path
    if not path.is_file():
        raise _Unpinned(f"{role}_executable_missing: {path.name}")
    try:
        exe_sha = sha256_file(path)
    except OSError as exc:
        raise _Unpinned(f"{role}_executable_unreadable: {type(exc).__name__}") from None
    comp: dict = {"role": role, "used": True, "name": path.name, "exe_sha256": exe_sha,
                  "flags": list(spec.flags), "version_args": list(spec.version_args)}
    if wine is not None:
        try:
            rel = path.resolve().relative_to(Path(wine.prefix).resolve())
        except ValueError:
            for name, root in sorted(roots.items()):
                try:
                    rel = path.resolve().relative_to(Path(root).resolve())
                except ValueError:
                    continue
                comp["named_root"] = name
                comp["root_relative_path"] = PurePosixPath(*rel.parts).as_posix()
                break
            else:
                raise _Unpinned(f"{role}_outside_named_roots: {path.name}") from None
        else:
            comp["prefix_relative_path"] = PurePosixPath(*rel.parts).as_posix()
        argv = [str(wine.wine), str(path), *spec.version_args]
    else:
        argv = [str(path), *spec.version_args]
    code, text = _probe(role, argv, env, timeout)
    text = _relocate(text, forms)
    comp["version_exit"] = code
    comp["version_sha256"] = _sha(text)
    comp["version_text"] = text[:VERSION_TEXT_LIMIT]
    return comp, str(path)


def _identity_payload(record: dict) -> dict:
    return {"schema": record["schema"], "components": record["components"],
            "env": record["env"], "host": record["host"]}


def capture(tools: Mapping[str, ToolSpec | None], *, env: Mapping[str, str],
            wine: WineHost | None = None, roots: Mapping[str, str | os.PathLike] | None = None,
            env_keys: tuple[str, ...] = RELEVANT_ENV_KEYS, timeout: float = 30.0,
            environment_is_effective: bool = False) -> dict:
    """A pinned identity record for *tools*, or an explicit unpinned one.

    *env* is the environment the build runs under; only *env_keys* enter the
    record. *roots* names install roots to rewrite out of env values and
    version text; with *wine* the prefix is added as ``WINEPREFIX``.
    """
    all_roots = dict(roots or {})
    if wine is not None:
        all_roots.setdefault("WINEPREFIX", wine.prefix)
    forms = _root_forms(all_roots)
    # An execution owner can supply its already-merged environment verbatim;
    # adding LC_ALL here would otherwise make version and compile paths differ.
    run_env = dict(env) if environment_is_effective else _run_env(env, wine)
    try:
        unknown = sorted(set(tools) - set(ROLES))
        if unknown:
            raise _Unpinned(f"unknown_role: {', '.join(unknown)}")
        for role in ROLES:
            if role not in tools:
                raise _Unpinned(f"{role}_role_missing: declare it, or pass None when the build does not use it")
        if tools["compiler"] is None:
            raise _Unpinned("compiler_not_used: a build identity needs a compiler")
        components: dict = {}
        locations: dict = {}
        for role in ROLES:
            spec = tools[role]
            if spec is None:
                components[role] = {"role": role, "used": False}
                continue
            components[role], locations[role] = _component(role, spec, env=run_env, wine=wine,
                                                           forms=forms, timeout=timeout, roots=all_roots)
        host: dict = {"kind": "native"}
        if wine is not None:
            wine_path = shutil.which(str(wine.wine), path=run_env.get("PATH"))
            if wine_path is None:
                raise _Unpinned("wine_executable_missing")
            code, text = _probe("wine", [str(wine.wine), "--version"], run_env, timeout)
            text = _relocate(text, forms)
            host = {"kind": "wine", "wine_version_exit": code, "wine_version_sha256": _sha(text),
                    "wine_version_text": text[:VERSION_TEXT_LIMIT],
                    "wine_exe_sha256": sha256_file(wine_path)}
            locations["wine"] = str(Path(wine_path).resolve())
            locations["wine_prefix"] = str(wine.prefix)
    except (OSError, _Unpinned) as exc:
        return {"schema": SCHEMA, "state": "unpinned", "reason": str(exc)}
    rec_env = {k: _relocate(str(run_env[k]), forms) for k in sorted(env_keys) if k in run_env}
    record = {"schema": SCHEMA, "state": "pinned", "components": components, "env": rec_env,
              "host": host, "locations": locations}
    record["identity_sha256"] = _sha(canonical_bytes(_identity_payload(record)))
    return record


def verify(record: Mapping) -> bool:
    """True only for a pinned record whose identity re-derives from its own fields."""
    try:
        if record.get("schema") != SCHEMA or record.get("state") != "pinned":
            return False
        ident = record.get("identity_sha256")
        if not isinstance(ident, str) or not _HEX64.fullmatch(ident):
            return False
        return _sha(canonical_bytes(_identity_payload(dict(record)))) == ident
    except (KeyError, TypeError, ValueError):
        return False


PROVISIONAL_EXECUTABLE_SCHEMA = "agentdecompile.provisional-executable-evidence/v1"


def inspect_only(*, command: list[str]) -> dict:
    """Hash explicit executable paths without version probes or calibration.

    This evidence deliberately fails verify(); headers, DLLs and Wine prefix
    contents remain unbound and must be supplied by the acceptance owner.
    """
    if len(command) < 2 or any(not Path(path).is_absolute() or not Path(path).is_file()
                               for path in command[:2]):
        raise ValueError("Provisional evidence requires explicit Wine and compiler executable paths")
    payload = {"schema": PROVISIONAL_EXECUTABLE_SCHEMA, "recipeState": "provisional",
               "support": "unmeasured", "closureBound": False,
               "components": {"compiler": {"exe_sha256": sha256_file(command[1])}},
               "host": {"wine_exe_sha256": sha256_file(command[0])}}
    payload["evidenceSha256"] = _sha(canonical_bytes(payload))
    return payload


def bind_invocation(evidence: Mapping, *, command: list[str], env: Mapping[str, str],
                    requested_args: list[str], policy: str, allow_provisional: bool = False) -> dict:
    """Reuse stable version evidence, recomputing live executable/invocation facts.

    This does not probe versions or pin headers, DLLs or prefix contents.
    Historical integrity-only records cannot supply this stronger binding.
    """
    provisional = False
    if allow_provisional and evidence.get("schema") == PROVISIONAL_EXECUTABLE_SCHEMA:
        current = inspect_only(command=command)
        provisional = dict(evidence) == current
    if (not provisional and not verify(evidence)) or not evidence.get("host", {}).get("wine_exe_sha256"):
        raise ValueError("Strong executable identity evidence is unavailable")
    if set(env) - set(RELEVANT_ENV_KEYS):
        raise ValueError("Measured compiler environment contains unreviewed values")
    compiler = Path(command[1]).resolve()
    wine = shutil.which(command[0], path=env.get("PATH"))
    if wine is None:
        raise ValueError("Wine executable is unavailable")
    if (sha256_file(compiler) != evidence["components"]["compiler"]["exe_sha256"]
            or sha256_file(wine) != evidence["host"]["wine_exe_sha256"]):
        raise ValueError("Executable identity changed since version capture")
    payload = {"schema": ("agentdecompile.provisional-msvc-invocation-binding/v1" if provisional
                           else "agentdecompile.msvc-invocation-binding/v1"),
               "evidence": dict(evidence), "command": list(command),
               "environment": {key: str(env[key]) for key in sorted(RELEVANT_ENV_KEYS) if key in env},
               "requestedArgs": list(requested_args),
               "environmentPolicy": "measured-msvc-allowlist/v1",
               "omittedFlagPolicy": policy, "sourceLanguage": "c"}
    if provisional:
        payload.update(recipeState="provisional", support="unmeasured", closureBound=False)
    payload["bindingSha256"] = _sha(canonical_bytes(payload))
    return payload


def compare_live_binding(expected: Mapping, **invocation) -> dict:
    """Compare current bytes, arguments, environment and policy without probes."""
    live = bind_invocation(expected.get("evidence", {}), allow_provisional=(
        expected.get("schema") == "agentdecompile.provisional-msvc-invocation-binding/v1"), **invocation)
    if live != expected:
        raise ValueError("Measured compiler invocation binding changed")
    return live


def manifest_toolchain(record: Mapping) -> dict:
    """The ``recovered_project_manifest`` toolchain entry for *record*."""
    from . import recovered_project_manifest as rpm

    if not verify(record):
        return rpm.unpinned_toolchain(str(record.get("reason") or "toolchain_identity_unverified"))
    comps = record["components"]
    linker = comps["linker"].get("name") if comps["linker"].get("used") else None
    return rpm.pinned_toolchain(record["identity_sha256"], compiler=comps["compiler"]["name"],
                                linker=linker, flags=tuple(comps["compiler"]["flags"]))


# ------------------------------------------------------------------ group


def group(records: Mapping[str, Mapping]) -> dict:
    """One identity for a group of builds, or a named refusal."""
    if not records:
        return {"state": "unpinned", "reason": "group_empty"}
    bad = sorted(k for k, r in records.items() if not verify(r))
    if bad:
        detail = "; ".join(f"{k} ({records[k].get('reason') or 'unverified'})" for k in bad)
        return {"state": "unpinned", "reason": f"member_unpinned: {detail}"}
    by_id: dict[str, list[str]] = {}
    for k, r in records.items():
        by_id.setdefault(r["identity_sha256"], []).append(k)
    if len(by_id) > 1:
        detail = "; ".join(f"{i} [{', '.join(sorted(m))}]" for i, m in sorted(by_id.items()))
        return {"state": "unpinned", "reason": f"mixed_toolchain_identity: {detail}"}
    ((ident, members),) = by_id.items()
    return {"state": "pinned", "identity_sha256": ident, "members": sorted(members)}


# ------------------------------------------------------------------ calibration


def coff_timestamp_normalizer(data: bytes) -> bytes:
    """Zero the COFF object TimeDateStamp; leave anything that is not a COFF object alone."""
    if len(data) >= 20 and int.from_bytes(data[0:2], "little") in _COFF_MACHINES:
        return data[:4] + b"\x00\x00\x00\x00" + data[8:]
    return data


coff_timestamp_normalizer.normalizer_name = "coff_timestamp"  # type: ignore[attr-defined]


def _argv_names_compiler(argv: list[str], exe_sha: str) -> bool:
    for arg in argv:
        try:
            if os.path.isfile(arg) and sha256_file(arg) == exe_sha:
                return True
        except OSError:
            continue
    return False


def calibrate(record: Mapping, *, argv: list[str], probe_source: str, runs: int = 2,
              expected_object_sha256: str | None = None,
              normalize: Callable[[bytes], bytes] | None = None,
              env: Mapping[str, str] | None = None, timeout: float = 60.0) -> dict:
    """Compile *probe_source* *runs* times with the recorded compiler.

    *argv* is the compile command; ``{src}`` and ``{out}`` are substituted.
    One argv element must be the recorded compiler executable (same sha256),
    so a calibration cannot be credited to a toolchain that did not run.
    """
    if runs < 2:
        raise ValueError("calibration needs at least two runs")
    norm_name = "none" if normalize is None else getattr(normalize, "normalizer_name", normalize.__name__)
    base = {"schema": CALIBRATION_SCHEMA, "probe_sha256": _sha(probe_source), "runs": runs,
            "normalizer": norm_name}

    def refuse(reason: str) -> dict:
        return {**base, "state": "uncalibrated", "reason": reason,
                "identity_sha256": record.get("identity_sha256") if verify(record) else None}

    if not verify(record):
        return refuse(f"toolchain_unpinned: {record.get('reason') or 'identity does not verify'}")
    if not _argv_names_compiler(list(argv), record["components"]["compiler"]["exe_sha256"]):
        return refuse("probe_argv_not_bound: no argv element is the recorded compiler")
    run_env = {"PATH": os.environ.get("PATH") or "/usr/bin:/bin", "LC_ALL": "C", **dict(env or {})}
    digests: list[str] = []
    for i in range(runs):
        with tempfile.TemporaryDirectory(prefix="toolchain-calibration-") as tmp:
            src = Path(tmp) / "probe.c"
            out = Path(tmp) / "probe.obj"
            src.write_text(probe_source, encoding="utf-8")
            cmd = [a.replace("{src}", str(src)).replace("{out}", str(out)) for a in argv]
            try:
                proc = subprocess.run(cmd, capture_output=True, timeout=timeout, env=run_env, check=False,
                                      stdin=subprocess.DEVNULL, cwd=tmp)
                rc = proc.returncode
            except (OSError, subprocess.SubprocessError) as exc:
                return refuse(f"probe_compile_failed: run {i + 1} {type(exc).__name__}")
            if rc != 0 or not out.is_file() or out.stat().st_size == 0:
                return refuse(f"probe_compile_failed: run {i + 1} exit {rc}")
            data = out.read_bytes()
        digests.append(_sha(normalize(data) if normalize else data))
    if len(set(digests)) > 1:
        return refuse(f"object_nondeterministic: {len(set(digests))} distinct digests in {runs} runs")
    obj = digests[0]
    if expected_object_sha256 is not None and obj != expected_object_sha256:
        return refuse(f"object_differs_from_expected: {obj} != {expected_object_sha256}")
    return {**base, "state": "calibrated", "identity_sha256": record["identity_sha256"], "object_sha256": obj}

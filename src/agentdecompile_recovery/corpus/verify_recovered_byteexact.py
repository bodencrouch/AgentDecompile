"""Compile recovered C and record raw and relocation-masked local comparisons.

Relocation masking is a scheduling diagnostic. It does not verify relocation
semantics, linking, or whole-image acceptance. `rawEqual` separately records an
exact-length raw comparison against the captured mapped target region. Copying
original operands into emitted substitutions is not evidence of recovered code.

Not a test file: this is a verification pass that writes receipts. Run:

    python3 -m agentdecompile_recovery.corpus.verify_recovered_byteexact \\
        --verified-dir <.../source/verified_c> --raw <raw_image> \\
        --compiler <compile-msvc71.sh> --out <receipts.json> [--limit N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import tempfile
import time
import shutil
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .recovered_c_preamble import PREAMBLE as _PREAMBLE


def _write_json_atomic(path: Path, value: object) -> None:
    """Replace a checkpoint only after its complete JSON is written beside it."""
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


_OWNER_SCHEMA = "agentdecompile.artifact-owners/v1"
_OWNER_MANIFEST = ".agentdecompile-artifact-owners.json"


class ArtifactPublicationError(RuntimeError):
    def __init__(self, diagnostics: list[dict]):
        super().__init__("artifact publication blocked")
        self.diagnostics = diagnostics


def _load_artifact_owners(root: Path) -> dict[str, dict]:
    try:
        document = json.loads((root / _OWNER_MANIFEST).read_text())
        owners = document.get("owners") if document.get("schema") == _OWNER_SCHEMA else None
        return {name: owner for name, owner in owners.items()
                if isinstance(name, str) and isinstance(owner, dict)} if isinstance(owners, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _write_artifact_owners(root: Path, owners: dict[str, dict]) -> None:
    _write_json_atomic(root / _OWNER_MANIFEST, {"schema": _OWNER_SCHEMA, "owners": owners})


def _result_address(result: dict) -> int | None:
    try:
        value = result.get("addr")
        address = value if type(value) is int else int(value, 16) if isinstance(value, str) else None
        return address if address is not None and address >= 0 else None
    except ValueError:
        return None


def _withdraw_manifest_sources(artifact_roots: dict[str, Path],
                               artifact_owners: dict[str, dict[str, dict]],
                               source_paths: set[str]) -> list[str]:
    """Withdraw durable source-owned artifacts without relying on cache state."""
    withdrawn = []
    blocked = []
    for root_key, root in artifact_roots.items():
        changed = False
        owners = artifact_owners[root_key]
        for name, owner in list(owners.items()):
            if not isinstance(owner, dict) or owner.get("sourcePath") not in source_paths:
                continue
            address = owner.get("address")
            path = root / name
            if (type(address) is not int or address < 0 or name != f"{address:08x}.bin"
                    or not isinstance(owner.get("sourceSha256"), str)
                    or not isinstance(owner.get("basis"), str)
                    or not isinstance(owner.get("sha256"), str)
                    or not isinstance(owner.get("channel"), str)):
                blocked.append({"path": str(path.resolve()), "sourcePath": owner.get("sourcePath"),
                                "reason": "durable_artifact_owner_invalid"})
                continue
            try:
                if path.is_file():
                    if _digest(path.read_bytes()) != owner["sha256"]:
                        blocked.append({"path": str(path.resolve()),
                                        "sourcePath": owner["sourcePath"], "address": address,
                                        "reason": "artifact_digest_mismatch"})
                        continue
                    quarantine = root / ".withdrawn"
                    quarantine.mkdir(exist_ok=True)
                    destination = quarantine / (
                        f"{path.name}.{owner['basis'][:12]}.{owner['sha256'][:12]}.{time.time_ns()}"
                    )
                    os.replace(path, destination)
                    withdrawn.append(str(destination.resolve()))
                owners.pop(name, None)
                changed = True
            except OSError as exc:
                blocked.append({"path": str(path.resolve()), "sourcePath": owner["sourcePath"],
                                "address": address, "reason": "artifact_quarantine_failed",
                                "error": exc.__class__.__name__})
        if changed:
            _write_artifact_owners(root, owners)
    if blocked:
        raise ArtifactPublicationError(blocked)
    return withdrawn

_ADDR_RE = re.compile(r"address:\s*(0x[0-9a-fA-F]+)")
_SIZE_RE = re.compile(r"size:\s*(\d+)\s*bytes")
_FUNC_RE = re.compile(r"\b(F_[0-9a-fA-F]+)\s*\(")
# Some recovered-C pools (MizuchiRE/recovered-source, recovered_candidates)
# embed the shipped bytes and encode the address in the function name
# (e.g. `Unwind_00717140`) instead of an `address:` header + `F_<addr>` name.
_MC_RE = re.compile(r"original machine code:[ \t]*([^\s*]+)")
_NAMEADDR_RE = re.compile(r"\b[A-Za-z_]\w*_([0-9a-fA-F]{6,8})\s*\(")


def file_region_offset(raw: bytes, address: int, size: int) -> int | None:
    """Resolve a whole region inside exactly one file-backed PE section.

    Virtual-only bytes, raw padding outside the mapped virtual extent,
    cross-section regions, malformed section tables and ambiguous overlaps do
    not describe bytes observed from the requested virtual address.
    """
    try:
        if raw[:2] != b"MZ" or type(address) is not int or type(size) is not int or size <= 0:
            return None
        pe = struct.unpack_from("<I", raw, 0x3C)[0]
        if raw[pe:pe + 4] != b"PE\0\0":
            return None
        count = struct.unpack_from("<H", raw, pe + 6)[0]
        optional_size = struct.unpack_from("<H", raw, pe + 20)[0]
        optional = pe + 24
        magic = struct.unpack_from("<H", raw, optional)[0]
        if magic == 0x10B and optional_size >= 32:
            image_base = struct.unpack_from("<I", raw, optional + 28)[0]
        elif magic == 0x20B and optional_size >= 32:
            image_base = struct.unpack_from("<Q", raw, optional + 24)[0]
        else:
            return None
        sections = optional + optional_size
        if sections + count * 40 > len(raw):
            return None
        matches = []
        overlaps = 0
        request_end = address + size
        for index in range(count):
            virtual_size, rva, raw_size, raw_offset = struct.unpack_from(
                "<IIII", raw, sections + index * 40 + 8
            )
            delta = address - image_base - rva
            backed_size = min(virtual_size, raw_size)
            section_start = image_base + rva
            section_end = section_start + backed_size
            if (raw_offset + raw_size <= len(raw)
                    and max(address, section_start) < min(request_end, section_end)):
                overlaps += 1
            if (0 <= delta and delta + size <= backed_size
                    and raw_offset + raw_size <= len(raw)):
                matches.append(raw_offset + delta)
        return matches[0] if len(matches) == 1 and overlaps == 1 else None
    except (ValueError, struct.error):
        return None


def pe_mapper(blob: bytes):
    """Return a whole-region VA mapper bound to one captured PE snapshot."""
    return lambda address, size: file_region_offset(blob, address, size)


def text_bytes_and_relocs(obj: bytes) -> tuple[bytes, list[int]] | None:
    """Return (.text raw bytes, [reloc offsets within .text])."""
    if len(obj) < 20 or len(obj) > 64 * 1024 * 1024:  # guard against a pathological object
        return None
    nsec, _t, _symptr, _nsym, opt, _flags = struct.unpack("<HIIIHH", obj[2:20])
    off = 20 + opt
    for _ in range(nsec):
        sh = obj[off:off + 40]
        off += 40
        name = sh[:8].rstrip(b"\x00").decode("latin1")
        if not name.startswith(".text"):
            continue
        srawsz, srawptr, relptr = struct.unpack_from("<III", sh, 16)
        nrel = struct.unpack_from("<H", sh, 32)[0]
        text = obj[srawptr:srawptr + srawsz]
        offs = []
        for r in range(nrel):
            rv = struct.unpack_from("<I", obj, relptr + r * 10)[0]
            offs.append(rv)
        return text, offs
    return None


def masked_diff_count(cand: bytes, target: bytes, reloc_offsets: list[int]) -> int:
    """Diagnostic distance after masking operands; unequal lengths never match.

    A small nonzero count (1-5) is a near-miss the permuter can usually close in
    seconds; a large count means the recovered C is structurally different and
    belongs to the slow tier. Returning the distance (not just a bool) lets the
    finish pipeline rank the remainder and permute near-misses first.
    """
    n = min(len(cand), len(target))
    a, b = bytearray(cand[:n]), bytearray(target[:n])
    for o in reloc_offsets:
        if type(o) is not int or o < 0 or o + 4 > len(cand):
            raise ValueError("Invalid relocation operand range")
        for i in range(o, min(o + 4, n)):
            a[i] = 0
            b[i] = 0
    return abs(len(cand) - len(target)) + sum(a[i] != b[i] for i in range(n))


def masked_equal(cand: bytes, target: bytes, reloc_offsets: list[int]) -> bool:
    return masked_diff_count(cand, target, reloc_offsets) == 0


def _parse(src: str, raw: bytes, mapper, size_map: dict[int, int] | None = None) -> tuple[int, int, bytes] | None:
    """Return (addr, size, target_bytes). Handles multiple pool formats.

    ``size_map`` (addr -> size, from the func DB) supplies the size for
    candidate pools whose header carries an ``address:`` but no ``size:`` field
    (ghidra_bulk's whole-program candidates name the function e.g. ``return_void``
    and omit size). Without it those pools all fail to parse.
    """
    ma = _ADDR_RE.search(src)
    named = _NAMEADDR_RE.search(src)
    addr = int(ma.group(1), 16) if ma else (int(named.group(1), 16) if named else None)
    if addr is None:
        return None
    ms, mc = _SIZE_RE.search(src), _MC_RE.search(src)
    try:
        embedded = bytes.fromhex(mc.group(1)) if mc else None
        sizes = [int(ms.group(1))] if ms else []
        if embedded is not None:
            sizes.append(len(embedded))
        if size_map and addr in size_map:
            sizes.append(size_map[addr])
        if not sizes or any(type(size) is not int or size <= 0 or size != sizes[0] for size in sizes):
            return None
        size = sizes[0]
        offset = mapper(addr, size)
        if type(offset) is not int or offset < 0 or size > len(raw) - offset:
            return None
        target = raw[offset:offset + size]
        if embedded is not None and embedded != target:
            return None
        return addr, size, target
    except (ValueError, TypeError, OverflowError):
        return None


def verify_one(cfile: Path, raw: bytes, mapper, compiler: str, size_map: dict[int, int] | None = None,
               bin_dir: Path | None = None, maxc_dir: Path | None = None,
               source_text: str | None = None, source_bytes: bytes | None = None,
               target_snapshot: dict | None = None) -> dict:
    try:
        captured = source_bytes if source_bytes is not None else (source_text.encode("utf-8") if source_text is not None else cfile.read_bytes())
        src = captured.decode("utf-8", errors="strict")
    except (UnicodeError, OSError):
        return {"file": cfile.name, "ok": False, "rawEqual": False, "reason": "invalid-source-encoding"}
    evidence = {"sourcePath": str(cfile.resolve()), "sourceSha256": hashlib.sha256(captured).hexdigest(),
                "comparisonPolicy": "raw-region-v1", "comparisonScope": "local-function"}
    # An asm-floor stub (__declspec(naked) + the original bytes) reproduces the
    # shipped bytes by construction -- it IS the original, not recovered C.
    # Counting it as byte-exact would launder the assembly floor into the
    # "decompiled" metric, so it is excluded here (and never emits a .bin).
    if "compile-only-asm" in src[:2000]:
        return {"file": cfile.name, "ok": False, "reason": "asm-floor", "asm_floor": True}
    parsed = _parse(src, raw, mapper, size_map)
    if parsed is None:
        return {"file": cfile.name, "ok": False, "reason": "unparsed-header"}
    addr, size, target = parsed
    evidence['targetRegion'] = {'address': addr, 'offset': mapper(addr, size), 'size': size,
                                'sha256': hashlib.sha256(target).hexdigest()}
    if target_snapshot is not None:
        evidence['targetSnapshot'] = dict(target_snapshot)
    with tempfile.TemporaryDirectory(prefix="recon-", dir="/tmp") as td:
        cpath = Path(td) / "in.c"
        opath = Path(td) / "out.obj"
        cpath.write_bytes((_PREAMBLE + src).encode("utf-8"))
        fname = "recovered"  # symbol not needed; .text section is the function
        try:
            compile_result = subprocess.run(["bash", compiler, str(cpath), str(opath), fname],
                                            capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return {"file": cfile.name, "addr": hex(addr), "ok": False, "reason": "compile-timeout"}
        if compile_result.returncode != 0 or not opath.exists():
            # Keep the compiler's own bounded explanation in the receipt.  The
            # result remains a failed verification; this only makes the next
            # readable-C repair actionable without re-running the compiler.
            diagnostic = (compile_result.stderr or compile_result.stdout or "").strip()
            # Known MSVC source/type diagnostics are deterministic rejections.
            # Fatal/environment/resource errors and unknown compiler output remain
            # inconclusive, not semantic mismatches and not assumed transient.
            deterministic = re.search(r"\berror C[234]\d{3}\b", diagnostic, re.IGNORECASE) is not None
            return {"file": cfile.name, "addr": hex(addr), "ok": False,
                    "reason": "compile-rejected" if deterministic else "compile-failed",
                    "failureClass": "deterministic-source-rejection" if deterministic else "unclassified-compiler-failure",
                    "compilerReturnCode": compile_result.returncode,
                    "compilerDiagnostic": diagnostic[-2000:]}
        tr = text_bytes_and_relocs(opath.read_bytes())
    if tr is None:
        return {"file": cfile.name, "addr": hex(addr), "ok": False, "reason": "no-text-section"}
    text, reloc_offsets = tr
    try:
        diff = masked_diff_count(text, target, reloc_offsets)
    except ValueError:
        return {**evidence, "file": cfile.name, "addr": hex(addr), "ok": False,
                "rawEqual": False, "reason": "invalid-relocations"}
    byte_exact = diff == 0
    raw_equal = text == target
    # The normal substitution channel carries only the compiler's exact raw
    # region. A masked-only match remains useful in the receipt, but copying
    # target relocation operands would manufacture contribution-shaped bytes.
    if raw_equal and bin_dir is not None:
        (bin_dir / f"{addr:08x}.bin").write_bytes(text)
    # max-c substitution bytes: for the readable (not-necessarily-byte-exact)
    # build, place the recovered C's compiled bytes for ANY function whose
    # compile fits the original slot -- reloc operands taken from the shipped
    # image so calls/globals resolve. This maximizes real-C coverage; the image
    # is NOT byte-identical where the C differs from the original.
    if maxc_dir is not None and len(text) >= size:
        mc = bytearray(text[:size])
        for o in reloc_offsets:
            for i in range(o, min(o + 4, size)):
                mc[i] = target[i]
        (maxc_dir / f"{addr:08x}.bin").write_bytes(bytes(mc))
    return {**evidence, "file": cfile.name, "addr": hex(addr), "size": size, "func": fname,
            "rawEqual": raw_equal, "compiledSize": len(text), "maskedEqual": byte_exact,
            "relocs": len(reloc_offsets), "ok": byte_exact, "diff": diff,
            "reloc_linked": False,
            "reason": "byte-exact-relocation-masked" if byte_exact else "mismatch"}



CACHE_SCHEMA = "agentdecompile.byteexact-cache/v3"
_VERIFIER_REVISION = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_STABLE_REASONS = {"byte-exact-relocation-masked", "mismatch", "asm-floor", "unparsed-header", "compile-rejected"}


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _cache_basis(raw: bytes, compiler: str, size_map: dict[int, int],
                 manifest_path: str | None) -> tuple[str, bool]:
    """Hash observed inputs; caller explicitly declares transitive closure completeness.

    A wrapper's bytes cannot identify every compiler, DLL, header or environment
    value it consumes. Without a complete manifest old positive claims are never
    reusable, although fresh compilation and bounded failure retry remain possible.
    """
    wrapper = Path(compiler).resolve()
    bash = shutil.which("bash")
    manifest: dict = {}
    closure: list[tuple[str, str]] = []
    if manifest_path:
        manifest_file = Path(manifest_path).resolve()
        manifest = json.loads(manifest_file.read_text())
        if not isinstance(manifest, dict) or manifest.get("complete") is not True:
            raise ValueError("cache input manifest must declare complete=true")
        entries = manifest.get("files")
        if not isinstance(entries, list) or not entries or not all(isinstance(x, str) for x in entries):
            raise ValueError("cache input manifest requires a nonempty files list")
        for entry in entries:
            path = Path(entry)
            if not path.is_absolute():
                path = manifest_file.parent / path
            path = path.resolve()
            closure.append((str(path), _digest(path.read_bytes())))
    names = manifest.get("environment", [])
    if not isinstance(names, list) or not all(isinstance(x, str) for x in names):
        raise ValueError("cache input manifest environment must be a list of names")
    env_names = sorted(set(names) | {"PATH", "WINEPREFIX", "WINELOADER", "WINESERVER", "INCLUDE", "LIB"})
    basis = {
        "raw": _digest(raw), "compiler": str(wrapper), "wrapper": _digest(wrapper.read_bytes()),
        "bash": (bash, _digest(Path(bash).read_bytes()) if bash else None),
        "verifier": _VERIFIER_REVISION, "preamble": _digest(_PREAMBLE.encode()),
        "sizes": sorted(size_map.items()), "closure": sorted(closure),
        "environment": {name: os.environ.get(name) for name in env_names},
        "manifest": manifest,
    }
    return _digest(json.dumps(basis, sort_keys=True).encode()), bool(manifest)


def _cache_reusable(entry: dict, key: str, complete: bool, now: float) -> bool:
    if entry.get("key") != key or not isinstance(entry.get("result"), dict):
        return False
    if entry["result"].get("ok") not in (True, False):
        return False
    if entry["result"].get("reason") in _STABLE_REASONS:
        return complete and _artifacts_valid(entry)
    deadline = entry.get("retry_after")
    recorded = entry.get("observed_at")
    # A clock rollback must not turn an unknown failure into permanent cache.
    return (type(deadline) in (int, float) and type(recorded) in (int, float)
            and math.isfinite(deadline) and math.isfinite(recorded) and recorded <= now < deadline)


def _artifacts_valid(entry: dict) -> bool:
    artifacts = entry.get("artifacts", [])
    if not isinstance(artifacts, list):
        return False
    try:
        result = entry.get("result", {})
        address = _result_address(result)
        source_path = result.get("sourcePath")
        source_sha256 = result.get("sourceSha256")
        basis = entry.get("basis")
        for item in artifacts:
            if (not isinstance(item, dict) or address is None
                    or not isinstance(source_path, str) or not isinstance(source_sha256, str)
                    or not isinstance(basis, str)):
                return False
            path = Path(item["path"]).resolve()
            expected = {
                "sourcePath": source_path,
                "sourceSha256": source_sha256,
                "basis": basis,
                "address": address,
                "sha256": item["sha256"],
                "channel": item["channel"],
            }
            if (_digest(path.read_bytes()) != item["sha256"]
                    or _load_artifact_owners(path.parent).get(path.name) != expected):
                return False
        return True
    except (OSError, KeyError, TypeError):
        return False


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verified-dir", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--db", help="corpus DB for function sizes (pools whose header omits size:)")
    ap.add_argument("--binary-id", type=int, help="binary_id for the --db size lookup")
    ap.add_argument("--bin-dir", help="also emit <addr>.bin substitution inputs for "
                    "relocation-free byte-exact functions (feeds whole_image_relink)")
    ap.add_argument("--maxc-bin-dir", help="emit slot-fitting compiled bytes for ANY compiling "
                    "function (byte-exact or not) for the readable max-C image")
    ap.add_argument("--no-incremental", action="store_true",
                    help="explicit fresh recompile of every selected function, ignoring cached outcomes")
    ap.add_argument("--cache-input-manifest", help="JSON complete=true, files and optional environment names identifying full compiler dependency closure")
    ap.add_argument("--transient-retry-seconds", type=float, default=300.0,
                    help="minimum cooldown before retrying an inconclusive compiler result")
    args = ap.parse_args(argv)
    if not math.isfinite(args.transient_retry_seconds) or args.transient_retry_seconds <= 0:
        ap.error("--transient-retry-seconds must be positive")

    bin_dir = None
    if args.bin_dir:
        bin_dir = Path(args.bin_dir)
        bin_dir.mkdir(parents=True, exist_ok=True)
    maxc_dir = None
    if getattr(args, "maxc_bin_dir", None):
        maxc_dir = Path(args.maxc_bin_dir)
        maxc_dir.mkdir(parents=True, exist_ok=True)
    artifact_roots = {str(root.resolve()): root for root in (bin_dir, maxc_dir) if root is not None}
    root_locks = []
    if artifact_roots:
        import fcntl
        for root_key in sorted(artifact_roots):
            root = artifact_roots[root_key]
            lock = (root / ".agentdecompile-artifact-owners.lock").open("a")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close()
                for held in root_locks:
                    held.close()
                raise ArtifactPublicationError([{
                    "path": str(root.resolve()),
                    "reason": "artifact_output_owner_active",
                }])
            root_locks.append(lock)

    files = sorted(Path(args.verified_dir).glob("*.c"))
    if args.limit:
        files = files[:args.limit]
    artifact_owners = {key: _load_artifact_owners(root) for key, root in artifact_roots.items()}
    source_paths = {str(path.resolve()) for path in files}
    try:
        raw = Path(args.raw).read_bytes()
    except OSError:
        _withdraw_manifest_sources(artifact_roots, artifact_owners, source_paths)
        raise
    target_snapshot = {'path': str(Path(args.raw).resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
                       'size': len(raw), 'scope': 'captured-image-snapshot',
                       'observation': 'invocation-pinned', 'currentFileVerified': False}
    mapper = pe_mapper(raw)
    size_map: dict[int, int] = {}
    if args.db and args.binary_id is not None:
        try:
            con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
            size_map = {int(a): int(s or 0) for a, s in con.execute(
                "SELECT addr, size FROM func WHERE binary_id=?", (args.binary_id,))}
            con.close()
        except (OSError, sqlite3.Error):
            _withdraw_manifest_sources(artifact_roots, artifact_owners, source_paths)
            raise
        print(f"loaded {len(size_map)} function sizes from DB", flush=True)
    out_path = Path(args.out)
    state_path = out_path.with_suffix(out_path.suffix + ".state.json")
    try:
        basis, complete = _cache_basis(raw, args.compiler, size_map, args.cache_input_manifest)
    except (OSError, ValueError, TypeError) as exc:
        print(f"error: cache-basis-unavailable: {exc}", flush=True)
        withdrawn = _withdraw_manifest_sources(artifact_roots, artifact_owners, source_paths)
        _write_json_atomic(out_path, {"total": 0, "byteExact": 0, "results": [],
                                      "current": False, "reason": "cache-basis-unavailable",
                                      "withdrawnArtifacts": withdrawn})
        return 2
    now = time.time()
    cache: dict[str, dict] = {}
    if state_path.is_file():
        try:
            document = json.loads(state_path.read_text())
            if document.get("schema") == CACHE_SCHEMA:
                entries = document.get("entries", {})
                if isinstance(entries, dict):
                    cache = {k: v for k, v in entries.items() if isinstance(v, dict)}
        except (OSError, ValueError, AttributeError):
            pass  # Old receipts are not upgraded to content-verified records.
    try:
        snapshots = {f.name: f.read_bytes() for f in files}
    except OSError:
        _withdraw_manifest_sources(artifact_roots, artifact_owners, source_paths)
        raise
    output_roots = [str(p.resolve()) if p else None for p in (bin_dir, maxc_dir)]
    keys = {name: _digest(json.dumps([basis, _digest(blob), output_roots]).encode())
            for name, blob in snapshots.items()}
    new_state: dict[str, dict] = dict(cache)
    results_by_name: dict[str, dict] = {}
    fresh: list[Path] = []
    deferred_withdrawals: set[str] = set()
    for f in files:
        entry = cache.get(f.name, {})
        if not args.no_incremental and _cache_reusable(entry, keys[f.name], complete, now):
            new_state[f.name] = entry
            results_by_name[f.name] = dict(entry["result"], reused=True)
        elif (not args.no_incremental and not complete and entry.get("key") == keys[f.name]
              and entry.get("result", {}).get("reason") in _STABLE_REASONS):
            # Do not amplify an unavailable closure into a full compile every poll.
            new_state[f.name] = entry
            results_by_name[f.name] = {"file": f.name, "ok": False, "reason": "cache-basis-incomplete",
                                      "detail": "provide a complete cache input manifest or request an explicit fresh audit"}
            deferred_withdrawals.add(f.name)
        else:
            fresh.append(f)
    print(f"verifying {len(files)} recovered .c files; {len(fresh)} new/changed or retry-eligible; "
          f"{len(files)-len(fresh)} reused/deferred", flush=True)

    def checkpoint() -> None:
        _write_json_atomic(state_path, {"schema": CACHE_SCHEMA, "entries": new_state})

    # Workers use frozen source text and private emitted bytes. Publication waits
    # for the complete basis and each source to be rechecked after compilation.
    from concurrent.futures import as_completed
    with tempfile.TemporaryDirectory(prefix="verify-pass-") as workspace:
        staging = Path(workspace)
        def run(f: Path) -> tuple[dict, list[tuple[Path, Path, str]]]:
            own = staging / f.name
            own.mkdir()
            staged_bin, staged_maxc = own / "bin", own / "maxc"
            staged_bin.mkdir()
            staged_maxc.mkdir()
            distribution = None
            try:
                from . import cross_place, cross_place_admission as admission
                address = cross_place.parse_addr(snapshots[f.name].decode('utf-8'))
                with admission.read_database(args.db) as distribution_db:
                    distribution = admission.capture_source_basis(distribution_db, args.binary_id,
                        address, f, snapshots[f.name], target=args.raw)
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
                pass  # Distribution is narrower; existing local verifier is unchanged.
            result = verify_one(f, raw, mapper, args.compiler, size_map,
                                staged_bin if bin_dir else None, staged_maxc if maxc_dir else None,
                                source_bytes=snapshots[f.name], target_snapshot=target_snapshot)
            if distribution and result.get('ok'):
                try:
                    with admission.read_database(args.db) as distribution_db:
                        current = admission.capture_source_basis(distribution_db, args.binary_id,
                            address, f, snapshots[f.name], target=args.raw)
                    if current == distribution:
                        result['distribution'] = distribution
                except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
                    pass  # Never downgrade a local result for unsupported distribution.

            emitted = []
            for origin, destination, channel in (
                    (staged_bin, bin_dir, "raw-exact"),
                    (staged_maxc, maxc_dir, "max-c-diagnostic")):
                if destination:
                    emitted.extend((p, destination / p.name, channel) for p in origin.glob("*.bin"))
            return result, emitted

        def withdraw_owned(entry: dict, f: Path) -> list[str]:
            """Atomically move only artifacts whose full ownership still matches."""
            withdrawn = []
            blocked = []
            result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
            address = _result_address(result)
            owner_source = str(f.resolve())
            owner_source_sha256 = result.get("sourceSha256")
            owner_basis = entry.get("basis")
            if (address is None or not isinstance(owner_basis, str)
                    or result.get("sourcePath") != owner_source
                    or not isinstance(owner_source_sha256, str)):
                if entry.get("artifacts"):
                    raise ArtifactPublicationError([{
                        "sourcePath": owner_source,
                        "reason": "artifact_entry_ownership_incomplete",
                    }])
                return withdrawn
            for artifact in entry.get("artifacts", []):
                if not isinstance(artifact, dict):
                    blocked.append({"sourcePath": owner_source, "address": address,
                                    "reason": "invalid_artifact_record"})
                    continue
                try:
                    path = Path(artifact["path"]).resolve()
                    root = path.parent
                    root_key = str(root)
                    channel = artifact["channel"]
                    expected = {
                        "sourcePath": owner_source,
                        "sourceSha256": owner_source_sha256,
                        "basis": owner_basis,
                        "address": address,
                        "sha256": artifact["sha256"],
                        "channel": channel,
                    }
                except (KeyError, OSError, TypeError):
                    blocked.append({"sourcePath": owner_source, "reason": "invalid_artifact_record"})
                    continue
                if root_key not in artifact_roots or path.name != f"{address:08x}.bin":
                    blocked.append({"path": str(path), "sourcePath": owner_source,
                                    "address": address, "reason": "artifact_path_not_owned"})
                    continue
                recorded_owner = artifact_owners[root_key].get(path.name)
                if recorded_owner != expected:
                    # A prior fail-closed invocation may have durably withdrawn
                    # the file and owner before it could rewrite disposable
                    # cache state. That fully absent pair is already withdrawn;
                    # every present or conflicting case remains blocking.
                    if recorded_owner is None and not path.exists():
                        continue
                    blocked.append({"path": str(path), "sourcePath": owner_source,
                                    "address": address, "reason": "artifact_owner_mismatch"})
                    continue
                try:
                    if path.is_file():
                        if _digest(path.read_bytes()) != expected["sha256"]:
                            blocked.append({"path": str(path), "sourcePath": owner_source,
                                            "address": address, "reason": "artifact_digest_mismatch"})
                            continue
                        quarantine = root / ".withdrawn"
                        quarantine.mkdir(exist_ok=True)
                        destination = quarantine / (
                            f"{path.name}.{owner_basis[:12]}.{expected['sha256'][:12]}.{time.time_ns()}"
                        )
                        os.replace(path, destination)
                        withdrawn.append(str(destination.resolve()))
                    artifact_owners[root_key].pop(path.name, None)
                    _write_artifact_owners(root, artifact_owners[root_key])
                except OSError as exc:
                    blocked.append({"path": str(path), "sourcePath": owner_source,
                                    "address": address, "reason": "artifact_quarantine_failed",
                                    "error": exc.__class__.__name__})
                    continue
            if blocked:
                raise ArtifactPublicationError(blocked)
            return withdrawn

        def withdraw_current_source(entry: dict, f: Path) -> list[str]:
            withdrawn = withdraw_owned(entry, f)
            withdrawn.extend(_withdraw_manifest_sources(
                artifact_roots, artifact_owners, {str(f.resolve())}
            ))
            return withdrawn

        def guard_active_paths(f: Path, address: int | None) -> None:
            """Refuse unowned/conflicting active paths left after withdrawal."""
            if address is None:
                return
            diagnostics = []
            for root_key, root in artifact_roots.items():
                path = root / f"{address:08x}.bin"
                if not path.is_file():
                    continue
                owner = artifact_owners[root_key].get(path.name)
                reason = None
                if not isinstance(owner, dict):
                    reason = "unowned_active_artifact"
                else:
                    try:
                        owner_valid = (owner.get("address") == address
                                       and isinstance(owner.get("sourcePath"), str)
                                       and isinstance(owner.get("sourceSha256"), str)
                                       and isinstance(owner.get("basis"), str)
                                       and isinstance(owner.get("channel"), str)
                                       and _digest(path.read_bytes()) == owner.get("sha256"))
                    except OSError:
                        owner_valid = False
                    if not owner_valid:
                        reason = "active_artifact_owner_invalid"
                    elif owner["sourcePath"] == str(f.resolve()):
                        reason = "owned_artifact_without_current_state"
                if reason:
                    diagnostics.append({"path": str(path.resolve()), "sourcePath": str(f.resolve()),
                                        "address": address, "reason": reason,
                                        "existingOwner": owner})
            if diagnostics:
                raise ArtifactPublicationError(diagnostics)

        def publish(pending: dict, *, final: bool = False) -> None:
            try:
                current_raw = Path(args.raw).read_bytes()
                current_sizes = size_map
                if args.db and args.binary_id is not None:
                    with sqlite3.connect(f"file:{args.db}?mode=ro", uri=True) as con:
                        current_sizes = {int(a): int(s or 0) for a, s in con.execute(
                            "SELECT addr, size FROM func WHERE binary_id=?", (args.binary_id,))}
                current_basis, _ = _cache_basis(current_raw, args.compiler, current_sizes, args.cache_input_manifest)
            except (OSError, ValueError, TypeError, sqlite3.Error):
                current_basis = None
            for f in (files if final else [p for p in fresh if p.name in pending]):
                try:
                    source_current = f.read_bytes() == snapshots[f.name]
                except OSError:
                    source_current = False
                if current_basis != basis or not source_current:
                    previous_entry = new_state.get(f.name, {})
                    withdrawn = withdraw_current_source(previous_entry, f)
                    previous_result = (previous_entry.get("result")
                                       if isinstance(previous_entry.get("result"), dict) else {})
                    pending_result = pending.get(f.name, ({}, []))[0]
                    guard_active_paths(f, _result_address(previous_result) or _result_address(pending_result))
                    results_by_name[f.name] = {"file": f.name, "ok": False,
                                               "reason": "inputs-changed-during-verification",
                                               "withdrawnArtifacts": withdrawn}
                    new_state.pop(f.name, None)
                    continue
                if final and f.name in deferred_withdrawals:
                    previous_entry = new_state.get(f.name, {})
                    withdrawn = withdraw_current_source(previous_entry, f)
                    previous_result = (previous_entry.get("result")
                                       if isinstance(previous_entry.get("result"), dict) else {})
                    guard_active_paths(f, _result_address(previous_result))
                    if withdrawn:
                        results_by_name[f.name]["withdrawnArtifacts"] = withdrawn
                    # Preserve the bounded no-recompile decision while ensuring
                    # neither cache state nor the receipt names an active file.
                    new_state[f.name] = dict(previous_entry, artifacts=[])
                    continue
                if f.name not in pending:
                    continue
                result, emitted = pending[f.name]
                withdrawn = withdraw_current_source(new_state.get(f.name, {}), f)
                artifacts = []
                address = _result_address(result)
                guard_active_paths(f, address)
                for source, dest, channel in emitted:
                    if address is None or dest.name != f"{address:08x}.bin":
                        continue
                    if dest.exists():
                        raise ArtifactPublicationError([{
                            "path": str(dest.resolve()), "sourcePath": str(f.resolve()),
                            "address": address, "reason": "active_artifact_path_already_exists",
                            "existingOwner": artifact_owners[str(dest.parent.resolve())].get(dest.name),
                        }])
                    data = source.read_bytes()
                    descriptor, temporary_name = tempfile.mkstemp(
                        prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent
                    )
                    temporary = Path(temporary_name)
                    try:
                        with os.fdopen(descriptor, "wb") as output:
                            output.write(data)
                            output.flush()
                            os.fsync(output.fileno())
                        try:
                            os.link(temporary, dest)
                        except FileExistsError:
                            raise ArtifactPublicationError([{
                                "path": str(dest.resolve()), "sourcePath": str(f.resolve()),
                                "address": address, "reason": "active_artifact_publish_race",
                                "existingOwner": artifact_owners[str(dest.parent.resolve())].get(dest.name),
                            }])
                    finally:
                        temporary.unlink(missing_ok=True)
                    artifact = {"path": str(dest.resolve()), "sha256": _digest(data),
                                "channel": channel, "address": address,
                                "ownerSourcePath": str(f.resolve()),
                                "ownerSourceSha256": _digest(snapshots[f.name]),
                                "ownerBasis": basis}
                    artifacts.append(artifact)
                    artifact_owners[str(dest.parent.resolve())][dest.name] = {
                        "sourcePath": str(f.resolve()),
                        "sourceSha256": _digest(snapshots[f.name]),
                        "basis": basis, "address": address,
                        "sha256": artifact["sha256"], "channel": channel,
                    }
                    _write_artifact_owners(dest.parent, artifact_owners[str(dest.parent.resolve())])
                if withdrawn:
                    result = dict(result, withdrawnArtifacts=withdrawn)
                observed = time.time()
                entry = {"key": keys[f.name], "result": result, "observed_at": observed,
                         "artifacts": artifacts, "basis": basis,
                         "complete_toolchain_basis": complete}
                if result.get("reason") not in _STABLE_REASONS:
                    # Rate limit only: a total per-function/incident spending cap
                    # belongs to the admission ledger, not this cache TTL.
                    entry["retry_after"] = observed + args.transient_retry_seconds
                new_state[f.name] = entry
                results_by_name[f.name] = dict(result, reused=False)
            for root_key, root in artifact_roots.items():
                _write_artifact_owners(root, artifact_owners[root_key])
            checkpoint()
        pending: dict[str, tuple[dict, list]] = {}
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(run, f): f for f in fresh}
            for fut in as_completed(futs):
                f = futs[fut]
                try:
                    pending[f.name] = fut.result()
                except Exception as exc:  # Inconclusive execution is not a permanent negative.
                    pending[f.name] = ({"file": f.name, "ok": False, "reason": f"error:{exc.__class__.__name__}"}, [])
                if len(pending) >= 50:
                    publish(pending)
                    pending.clear()
        publish(pending, final=True)
    results = [results_by_name[f.name] for f in files]
    for result in results:
        entry = new_state.get(result["file"], {})
        result["basis"] = basis
        result["sourceDigest"] = _digest(snapshots[result["file"]])
        result["sourceSha256"] = result["sourceDigest"]
        result["sourcePath"] = str((Path(args.verified_dir) / result["file"]).resolve())
        result["targetSnapshot"] = dict(target_snapshot)
        result["artifacts"] = entry.get("artifacts", []) if result.get("reason") not in {
            "cache-basis-incomplete", "inputs-changed-during-verification"} else []
        result["artifactsCurrent"] = bool(result["artifacts"]) and result.get("reason") in _STABLE_REASONS
    ok = [r for r in results if r.get("ok")]
    _write_json_atomic(out_path, {"total": len(results), "byteExact": len(ok), "results": results,
                                  "basis": basis, "completeToolchainBasis": complete,
                                  "scope": "local-relocation-masked; not whole-image or fresh-source acceptance"})
    from collections import Counter
    print(f"\nCurrent byte-exact (relocation-masked, reused entries labeled): {len(ok)}/{len(results)} "
          f"({100*len(ok)/max(len(results),1):.1f}%)")
    print("reasons:", dict(Counter(r.get("reason", "?") for r in results)))
    print("receipts:", args.out)
    return 2 if any(r.get("reason") in {"cache-basis-incomplete", "inputs-changed-during-verification"} for r in results) else 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Serialize cache and output publication even when called outside the periodic wrapper.
    output = next((value.split("=", 1)[1] for value in arguments if value.startswith("--out=")), None)
    if "--out" in arguments:
        index = arguments.index("--out")
        if index + 1 < len(arguments):
            output = arguments[index + 1]
    if output is None:
        return _main(arguments)  # argparse supplies the normal usage error/help.
    try:
        import fcntl
    except ImportError:
        print("error: verification requires POSIX flock support on this host", flush=True)
        return 2
    try:
        with Path(str(Path(output).resolve()) + ".verify.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("error: verification-output-owner-active", flush=True)
                return 2
            try:
                return _main(arguments)
            except ArtifactPublicationError as exc:
                print("error: artifact-publication-blocked", flush=True)
                _write_json_atomic(Path(output), {
                    "total": 0,
                    "byteExact": 0,
                    "results": [],
                    "current": False,
                    "reason": "artifact-publication-blocked",
                    "unresolvedArtifacts": exc.diagnostics,
                })
                return 2
            except (OSError, sqlite3.Error) as exc:
                print(f"error: verification-input-or-output-unavailable: {exc}", flush=True)
                # Invalidate only while holding publication authority. An open or
                # acquisition failure must never overwrite another owner's receipt.
                try:
                    _write_json_atomic(Path(output), {"total": 0, "byteExact": 0, "results": [],
                                                     "current": False, "reason": "verification-input-or-output-unavailable"})
                except OSError:
                    pass
                return 2
    except OSError as exc:
        print(f"error: verification-output-lock-unavailable: {exc}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

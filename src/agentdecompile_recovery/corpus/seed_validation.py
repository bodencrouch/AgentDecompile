"""Audit copied recovery seeds without confusing byte reuse with recovered C.

Writers take explicit Path arguments. The two ledger names stay distinct so a
static audit cannot overwrite the destination compile ledger.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import pathlib
import re
import subprocess
import shutil
import inspect
import tempfile
from collections import Counter, defaultdict
from typing import Iterable

from .corpus_env import recovered_source_root
from .ingest_recovered import load_verified_coverage
from .source_claims import is_real_c

RESULTS = pathlib.Path("seed_validation.jsonl")
COMPILE_RESULTS = pathlib.Path("seed_validation_compile.jsonl")
SUMMARY = pathlib.Path("seed_validation_summary.json")
COMPILE_SUMMARY = pathlib.Path("seed_validation_compile_summary.json")

MS_PREAMBLE = """
typedef signed char int8;
typedef unsigned char uint8;
typedef signed short int16;
typedef unsigned short uint16;
typedef signed int int32;
typedef unsigned int uint32;
typedef unsigned char byte;
typedef unsigned char undefined;
typedef unsigned char undefined1;
typedef unsigned short undefined2;
typedef unsigned int undefined4;
typedef unsigned __int64 undefined8;
typedef unsigned int uint;
typedef unsigned long ulong;
"""

GNU_PREAMBLE = """
#define __cdecl
#define __stdcall
#define __fastcall
#define __thiscall
typedef signed char int8;
typedef unsigned char uint8;
typedef signed short int16;
typedef unsigned short uint16;
typedef signed int int32;
typedef unsigned int uint32;
typedef unsigned char byte;
typedef unsigned char undefined;
typedef unsigned char undefined1;
typedef unsigned short undefined2;
typedef unsigned int undefined4;
typedef unsigned long long undefined8;
typedef unsigned int uint;
typedef unsigned long ulong;
"""


@dataclasses.dataclass(frozen=True)
class Seed:
    source_path: str
    destination_repo: str
    destination_address: str
    destination_name: str
    size: int
    source_original_bytes: bytes
    defined_name: str
    payload: str
    source_evidence: str | None = None


def normalize_address(value: str | int) -> str:
    """Canonical lower-case hex without presentation zero padding."""
    if isinstance(value, int):
        return f"{value:x}"
    return f"{int(str(value), 16):x}"


def group_candidates(rows: Iterable[dict]) -> dict[tuple[str, str], list[dict]]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["dst_slug"], normalize_address(row["dst_addr"]))].append(row)
    return dict(grouped)


def reuse_key(source_path: str, destination_repo: str,
              destination_address: str | int) -> tuple[str, str, str]:
    return source_path, destination_repo, normalize_address(destination_address)


def candidate_reuse_key(
    row: dict,
    *,
    recovered_root: pathlib.Path | None = None,
) -> tuple[str, str, str]:
    root = recovered_root if recovered_root is not None else recovered_source_root()
    source = pathlib.Path(root) / row["src_program"] / f"{row['src_name']}.c"
    return reuse_key(str(source), row["dst_repo"], row["dst_addr"])


def source_has_verified_coverage(
    verified: set[tuple[str, str]], source: pathlib.Path | str
) -> bool:
    """Require the authoritative coverage verdict; source comments are metadata."""
    path = pathlib.Path(source)
    return (path.parent.name, path.stem) in verified


DEF_RE = re.compile(
    r"^[A-Za-z_][\w\s\*]*?\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{", re.M
)


def parse_seed(text: str) -> Seed:
    src = re.search(r"^ \* src=(.+)$", text, re.M)
    dst = re.search(r"^ \* dst=(\S+) @ 0x([0-9a-fA-F]+)$", text, re.M)
    meta = re.search(r"^ \* dst_name=(.+) size=(\d+)$", text, re.M)
    original = re.search(r"original machine code:\s*([0-9a-fA-F]+)", text)
    evidence = re.search(r"^ \* evidence:\s*(\S+)", text, re.M)
    first_end = text.find("*/")
    payload = text[first_end + 2:].lstrip("\r\n") if first_end >= 0 else ""
    defined = DEF_RE.search(payload)
    if not all((src, dst, meta, original, defined)):
        raise ValueError("seed is missing required provenance or function metadata")
    return Seed(
        source_path=src.group(1),
        destination_repo=dst.group(1),
        destination_address=normalize_address(dst.group(2)),
        destination_name=meta.group(1),
        size=int(meta.group(2)),
        source_original_bytes=bytes.fromhex(original.group(1)),
        defined_name=defined.group(1),
        payload=payload,
        source_evidence=evidence.group(1) if evidence else None,
    )


def _evidence_ancestors(seed: Seed, root: pathlib.Path) -> list[pathlib.Path]:
    if not seed.source_evidence:
        return []
    evidence = pathlib.Path(seed.source_evidence)
    candidate = evidence if evidence.is_absolute() else root / evidence
    try:
        candidate.relative_to(root)
    except ValueError:
        return []
    ancestors = []
    parent = candidate.parent
    while parent != root.parent:
        ancestors.append(parent)
        if parent == root:
            break
        parent = parent.parent
    return ancestors


def source_context(seed: Seed, root: pathlib.Path) -> str | None:
    """Load the exact generated context recorded by the source recovery."""
    for parent in _evidence_ancestors(seed, root):
        context = parent / "ctx.h"
        if context.is_file():
            return context.read_text(errors="replace")
    return None


def source_target_artifacts(
    seed: Seed, root: pathlib.Path
) -> tuple[pathlib.Path | None, list[dict]]:
    """Find the original relocation-aware target object and its byte spec."""
    name = pathlib.Path(seed.source_path).stem
    for parent in _evidence_ancestors(seed, root):
        target = parent / "target" / f"{name}.o"
        spec = parent / "target" / "specs" / f"{name}.json"
        if target.is_file():
            relocs = []
            if spec.is_file():
                try:
                    relocs = json.loads(spec.read_text()).get("relocations") or []
                except (OSError, ValueError, TypeError):
                    relocs = []
            return target, relocs
    return None, []


def mask_relocations(data: bytes, relocations: Iterable[dict]) -> bytes:
    """Blank only bytes owned by the linker for x86 COFF relocation fields."""
    masked = bytearray(data)
    for relocation in relocations:
        offset = int(relocation["immOffset"])
        size = int(relocation["immSize"])
        if 0 <= offset and offset + size <= len(masked):
            masked[offset:offset + size] = b"\0" * size
    return bytes(masked)


def objdiff_only_coff_symbol_decoration(output: str) -> bool:
    """Accept objdiff differences caused only by MSVC's leading global underscore."""
    pattern = re.compile(
        r"row \d+: base=(\"(?:\\.|[^\"])*\") \[[^]]+\]\s+"
        r"target=(\"(?:\\.|[^\"])*\") \[[^]]+\]"
    )
    differences = pattern.findall(output)
    if not differences:
        return False

    def normalized(value: str) -> str:
        text = json.loads(value)
        return re.sub(r"(?<![A-Za-z0-9_])_([A-Za-z][A-Za-z0-9_]*)", r"\1", text)

    return all(normalized(base) == normalized(target) for base, target in differences)


def select_object_symbol(symbols: dict[str, bytes], defined_name: str) -> tuple[str, bytes]:
    """Find a C symbol across ELF and cdecl/stdcall/fastcall COFF spellings."""
    exact = (defined_name, f"_{defined_name}")
    for name in exact:
        if name in symbols:
            return name, symbols[name]
    decorated = [
        (name, data) for name, data in symbols.items()
        if re.fullmatch(rf"(?:_|@)?{re.escape(defined_name)}(?:@\d+)?", name)
    ]
    if len(decorated) == 1:
        return decorated[0]
    raise LookupError(f"could not resolve one object symbol for {defined_name}")


def read_jsonl(path: pathlib.Path) -> list[dict]:
    with path.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_reuse_index(path: pathlib.Path) -> dict[tuple[str, str, str], list[dict]]:
    out: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    with path.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            source = row.get("recovered_from") or {}
            target = row.get("reuse_target") or {}
            if source.get("source_path") and target.get("repo_path") \
                    and target.get("address") is not None:
                out[reuse_key(source["source_path"], target["repo_path"],
                              target["address"])].append(row)
    return dict(out)


def logical_ids_for_links(links: Iterable[dict]) -> list[int]:
    """Return the distinct identities behind a source/target link."""
    return sorted({int(row["logical_id"]) for row in links if row.get("logical_id") is not None})


def target_observation(
    slug: str,
    address: str,
    size: int,
    cache: dict,
    *,
    raw_dir: pathlib.Path,
    mapper_for,
) -> tuple[bytes, dict]:
    """Read bytes and provenance from an invocation-owned, pinned image snapshot.

    Cache identity includes the resolved image and mapper provider, never just a
    product slug. Reusing this snapshot does not claim the on-disk image is still
    current; callers needing a fresh observation must use a new cache.
    """
    if type(size) is not int or size <= 0:
        raise ValueError("destination size must be a positive integer")
    try:
        address_value = int(address, 16)
    except (TypeError, ValueError) as exc:
        raise ValueError("destination address must be hexadecimal") from exc
    if address_value < 0:
        raise ValueError("destination address must be nonnegative")
    path = (pathlib.Path(raw_dir) / slug).resolve()
    key = (str(path), mapper_for)
    if key not in cache:
        raw = path.read_bytes()
        mapper, kind = mapper_for(raw)
        if mapper is None:
            raise ValueError(f"no image mapper for {slug}")
        snapshot = {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw),
                    'path': str(path), 'kind': str(kind), 'observation': 'invocation-pinned',
                    'scope': 'captured-image-snapshot', 'currentFileVerified': False}
        cache[key] = raw, mapper, snapshot
    raw, mapper, snapshot = cache[key]
    offset = mapper(address_value)
    if type(offset) is not int or offset < 0 or offset + size > len(raw):
        raise ValueError(f"destination address 0x{address} is not mapped")
    region = raw[offset:offset + size]
    return region, {'targetSnapshot': dict(snapshot),
                    'targetRegion': {'address': address_value, 'offset': offset, 'size': size,
                                     'sha256': hashlib.sha256(region).hexdigest()}}


def destination_bytes(slug: str, address: str, size: int, cache: dict, *,
                      raw_dir: pathlib.Path, mapper_for) -> bytes:
    """Compatibility byte-only view of the same pinned target observation."""
    return target_observation(slug, address, size, cache, raw_dir=raw_dir,
                              mapper_for=mapper_for)[0]


COMPILE_RESULT_FIELDS = (
    "compile_status", "compile_detail", "object_symbol", "compiled_bytes",
    "objdiff_verified", "objdiff_symbol_normalized", "relocations_masked",
    "comparisonPolicy", "relocation_normalized_match",
)


def compile_basis(seed: Seed, compiler: pathlib.Path, evidence_root: pathlib.Path,
                  manifest=None, env_overrides=None, *, objdiff_check=None,
                  coff_functions=None, elf_symbol_bytes=None) -> tuple[dict, str, dict]:
    """Fingerprint observed inputs; closure completeness is a caller declaration."""
    preamble = source_context(seed, evidence_root) or (
        MS_PREAMBLE if "msvc" in compiler.name else GNU_PREAMBLE)
    environment = {**os.environ, **(env_overrides or {})}
    complete, reason, dependencies, declared = False, 'manifest_not_supplied', [], {}
    try:
        if manifest is not None:
            manifest_path = pathlib.Path(manifest).resolve()
            declared = json.loads(manifest_path.read_text())
            files = declared.get('files') if isinstance(declared, dict) else None
            names = declared.get('environment', []) if isinstance(declared, dict) else None
            if (not isinstance(declared, dict) or declared.get('complete') is not True
                    or not isinstance(files, list) or not files
                    or not all(isinstance(item, str) and item for item in files)
                    or not isinstance(names, list) or not all(isinstance(item, str) for item in names)):
                raise ValueError('invalid closure declaration')
            for item in files:
                path = pathlib.Path(item)
                if not path.is_absolute():
                    path = manifest_path.parent / path
                path = path.resolve()
                dependencies.append((str(path), hashlib.sha256(path.read_bytes()).hexdigest()))
            complete, reason = True, 'caller_declared_complete'
    except (OSError, ValueError, TypeError):
        complete, reason = False, 'manifest_invalid_or_unreadable'
    try:
        wrapper_hash = hashlib.sha256(compiler.read_bytes()).hexdigest()
    except OSError:
        wrapper_hash = None
        complete, reason = False, 'compiler_unreadable'
    target_object, relocations = source_target_artifacts(seed, evidence_root)
    target_inputs = None
    if target_object is not None:
        spec_path = target_object.parent / 'specs' / (target_object.stem + '.json')
        try:
            target_inputs = {'path': str(target_object.resolve()),
                             'object': hashlib.sha256(target_object.read_bytes()).hexdigest(),
                             'spec': hashlib.sha256(spec_path.read_bytes()).hexdigest() if spec_path.is_file() else None,
                             'relocations': relocations}
        except OSError:
            target_inputs = {'unreadable': str(target_object)}
            complete, reason = False, 'target_artifact_unreadable'
    parser_inputs = {}
    for name, parser in (('coff', coff_functions), ('elf', elf_symbol_bytes)):
        if parser is None:
            parser_inputs[name] = None
            continue
        try:
            module_path = inspect.getsourcefile(parser)
            if not module_path:
                raise ValueError('parser source unavailable')
            parser_inputs[name] = {'module': str(pathlib.Path(module_path).resolve()),
                                  'callable': parser.__qualname__,
                                  'sha256': hashlib.sha256(pathlib.Path(module_path).read_bytes()).hexdigest()}
        except (OSError, ValueError, TypeError, AttributeError):
            parser_inputs[name] = None
            complete, reason = False, 'parser_revision_unavailable'
    if not any(parser_inputs.values()):
        complete, reason = False, 'object_parser_unavailable'
    verifier_inputs = None
    if target_object is not None:
        try:
            node = shutil.which('node', path=environment.get('PATH'))
            if objdiff_check is None or node is None:
                raise ValueError('object verifier unavailable')
            verifier_inputs = {'checker': hashlib.sha256(pathlib.Path(objdiff_check).read_bytes()).hexdigest(),
                               'checkerPath': str(pathlib.Path(objdiff_check).resolve()),
                               'node': hashlib.sha256(pathlib.Path(node).read_bytes()).hexdigest(), 'nodePath': node}
        except (OSError, ValueError):
            complete, reason = False, 'object_verifier_unavailable'
    # Hash every actually passed environment value, a conservative superset of
    # selected relevant/declared names. No raw environment values enter receipts.
    material = {'wrapper': wrapper_hash, 'compiler': str(compiler.resolve()),
                'cwd': str(pathlib.Path.cwd().resolve()), 'targetArtifacts': target_inputs,
                'objectParsers': parser_inputs, 'objectVerifier': verifier_inputs,
                'preamble': hashlib.sha256(preamble.encode('utf-8')).hexdigest(),
                'environment': hashlib.sha256(json.dumps(environment, sort_keys=True).encode()).hexdigest(),
                'dependencies': sorted(dependencies), 'declaration': declared,
                'verifier': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
                'comparisonPolicy': 'raw-region-v1'}
    return ({'key': hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest(),
             'closureComplete': complete, 'closureReason': reason,
             'closureProof': 'explicit-declaration-not-automatically-proven'}, preamble, environment)


def can_reuse_compile_result(current: dict, previous: dict | None) -> bool:
    if not previous or previous.get("compile_status") != "byte_exact" or previous.get("comparisonPolicy") != "raw-region-v1":
        return False
    basis, prior_basis = current.get('compileBasis'), previous.get('compileBasis')
    if (not isinstance(basis, dict) or not isinstance(prior_basis, dict)
            or basis.get('closureComplete') is not True or prior_basis.get('closureComplete') is not True
            or not isinstance(basis.get('key'), str) or re.fullmatch(r'[0-9a-f]{64}', basis['key']) is None
            or basis['key'] != prior_basis.get('key')):
        return False
    if not isinstance(current.get("sourceSha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", current["sourceSha256"]):
        return False
    current_snapshot = current.get('targetSnapshot')
    previous_snapshot = previous.get('targetSnapshot')
    if not isinstance(current_snapshot, dict) or not isinstance(previous_snapshot, dict):
        return False
    digest = current_snapshot.get('sha256')
    if not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None:
        return False
    if digest != previous_snapshot.get('sha256'):
        return False
    if not isinstance(current.get('targetRegion'), dict) or current['targetRegion'] != previous.get('targetRegion'):
        return False
    keys = ("seed", "source_path", "destination_bytes", "sourceSha256")
    return all(current.get(key) == previous.get(key) for key in keys)


def compile_seed(
    slug: str,
    seed: Seed,
    target: bytes,
    *,
    compiler: pathlib.Path,
    evidence_root: pathlib.Path,
    objdiff_check: pathlib.Path | None = None,
    env_overrides: dict[str, str] | None = None,
    coff_functions=None,
    elf_symbol_bytes=None,
    frozen_preamble: str | None = None,
    frozen_environment: dict | None = None,
) -> dict:
    preamble = frozen_preamble if frozen_preamble is not None else source_context(seed, evidence_root) or (
        MS_PREAMBLE if "msvc" in compiler.name else GNU_PREAMBLE
    )
    with tempfile.TemporaryDirectory(prefix="ad-seed-") as td:
        tmp = pathlib.Path(td)
        source = tmp / "seed.c"
        obj = tmp / "seed.o"
        source.write_text(preamble + "\n" + seed.payload)
        env = dict(frozen_environment) if frozen_environment is not None else os.environ.copy()
        if frozen_environment is None:
            env.update(env_overrides or {})
        try:
            run = subprocess.run(
                [str(compiler), str(source), str(obj), seed.defined_name],
                capture_output=True, text=True, env=env, timeout=120,
            )
        except subprocess.TimeoutExpired:
            return {"compile_status": "timeout"}
        if run.returncode != 0 or not obj.exists():
            detail = ((run.stdout or "") + (run.stderr or ""))[-800:]
            return {"compile_status": "failed", "compile_detail": detail}
        try:
            blob = obj.read_bytes()
            if blob[:4] == b"\x7fELF":
                if elf_symbol_bytes is None:
                    raise LookupError("elf_symbol_bytes helper is required")
                symbols = elf_symbol_bytes(blob, prefix="")
            else:
                if coff_functions is None:
                    raise LookupError("coff_functions helper is required")
                symbols = coff_functions(blob, prefix="")
            object_name, compiled = select_object_symbol(symbols, seed.defined_name)
        except Exception as exc:
            return {"compile_status": "object_unreadable", "compile_detail": str(exc)}
        target_object, relocations = source_target_artifacts(seed, evidence_root)
        objdiff_verified = False
        diff_return = 0
        if target_object is not None:
            if objdiff_check is None or not pathlib.Path(objdiff_check).is_file():
                return {
                    "compile_status": "verifier_unavailable",
                    "compile_detail": "objdiff checker path is required",
                }
            try:
                diff = subprocess.run(
                    [shutil.which("node", path=env.get("PATH")) or "node", str(objdiff_check), str(obj), str(target_object), object_name],
                    capture_output=True, text=True, timeout=60, env=env,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {"compile_status": "verifier_unavailable", "compile_detail": str(exc)}
            diff_output = (diff.stdout or "") + (diff.stderr or "")
            diff_return = diff.returncode
            if diff.returncode != 0 and not objdiff_only_coff_symbol_decoration(diff_output):
                return {
                    "compile_status": "object_mismatch",
                    "compile_detail": diff_output[-1200:],
                }
            objdiff_verified = True
        exact = bool(target) and compiled == target
        normalized_match = len(compiled) == len(target) and (
            mask_relocations(compiled, relocations) == mask_relocations(target, relocations)
        )
        return {
            "compile_status": "byte_exact" if exact else "not_byte_exact",
            "comparisonPolicy": "raw-region-v1",
            "relocation_normalized_match": normalized_match,
            "object_symbol": object_name,
            "objdiff_verified": objdiff_verified,
            "objdiff_symbol_normalized": bool(
                target_object is not None and diff_return != 0
            ),
            "relocations_masked": len(relocations),
            "compiled_bytes": compiled[:max(len(target), min(len(compiled), 64))].hex(),
        }


def audit(
    *,
    seeds_dir: pathlib.Path,
    candidates_path: pathlib.Path,
    reuse_path: pathlib.Path,
    results_path: pathlib.Path,
    summary_path: pathlib.Path,
    coverage_dir: pathlib.Path | None = None,
    compile_destinations: bool = False,
    retry_failed_only: bool = False,
    compile_results_path: pathlib.Path | None = None,
    raw_dir: pathlib.Path | None = None,
    mapper_for=None,
    compiler_for=None,
    evidence_root: pathlib.Path | None = None,
    compile_input_manifest: pathlib.Path | None = None,
    objdiff_check: pathlib.Path | None = None,
    coff_functions=None,
    elf_symbol_bytes=None,
) -> dict:
    candidate_rows = read_jsonl(pathlib.Path(candidates_path))
    groups = group_candidates(candidate_rows)
    reuse = build_reuse_index(pathlib.Path(reuse_path))
    verified_coverage = (
        load_verified_coverage(pathlib.Path(coverage_dir)) if coverage_dir else set()
    )
    raw_cache: dict = {}
    results = []
    previous_results = {}
    compile_ledger = pathlib.Path(compile_results_path or COMPILE_RESULTS)
    if retry_failed_only and compile_ledger.is_file():
        previous_results = {
            row["seed"]: row for row in read_jsonl(compile_ledger) if row.get("seed")
        }

    seeds_dir = pathlib.Path(seeds_dir)
    for path in sorted(seeds_dir.rglob("*.c")):
        slug = path.parent.name
        result = {"seed": str(path), "dst_slug": slug}
        problems = []
        try:
            source_snapshot = path.read_bytes()
            text = source_snapshot.decode("utf-8")
            seed = parse_seed(text)
            result["sourceSha256"] = hashlib.sha256(source_snapshot).hexdigest()
            result.update({
                "dst_repo": seed.destination_repo,
                "dst_addr": seed.destination_address,
                "dst_name": seed.destination_name,
                "source_path": seed.source_path,
                "source_name": pathlib.Path(seed.source_path).stem,
                "size": seed.size,
                "real_c": is_real_c(seed.payload),
            })
            source = pathlib.Path(seed.source_path)
            source_text = source.read_text(errors="replace") if source.is_file() else None
            result["source_exists"] = source_text is not None
            result["source_copy_exact"] = bool(
                source_text is not None and source_text.strip() == seed.payload.strip()
            )
            result["source_verified_byte_exact"] = source_has_verified_coverage(
                verified_coverage, source
            )
            source_program = source.parent.name
            candidate_key = (
                source_program, source.stem, slug, seed.destination_address
            )
            result["candidate_manifest_match"] = candidate_key in {
                (r["src_program"], r["src_name"], r["dst_slug"],
                 normalize_address(r["dst_addr"]))
                for r in candidate_rows
            }
            result["destination_group_candidates"] = len(
                groups.get((slug, seed.destination_address), [])
            )
            result["filename_matches_address"] = (
                normalize_address(path.stem) == seed.destination_address
            )
            if raw_dir is not None and mapper_for is not None:
                target, observation = target_observation(
                    slug, seed.destination_address, seed.size, raw_cache,
                    raw_dir=raw_dir, mapper_for=mapper_for,
                )
                result.update(observation)
                result["destination_bytes"] = target.hex()
                result["source_bytes_match_destination"] = (
                    seed.source_original_bytes == target
                )
            else:
                target = b""
                result["destination_bytes"] = seed.source_original_bytes.hex()
                result["source_bytes_match_destination"] = True
            links = reuse.get(reuse_key(
                seed.source_path, seed.destination_repo, seed.destination_address
            ), [])
            logical_ids = logical_ids_for_links(links)
            result["logical_ids"] = logical_ids
            result["logical_identity_link"] = len(logical_ids) == 1
            result["identity_confidence"] = max(
                (float(r.get("identity_confidence") or 0) for r in links), default=0.0
            )
            required = (
                "real_c", "source_exists", "source_copy_exact",
                "source_verified_byte_exact", "candidate_manifest_match",
                "filename_matches_address", "source_bytes_match_destination",
            )
            problems.extend(name for name in required if not result.get(name))
            if problems:
                result["static_status"] = "invalid"
            elif len(logical_ids) > 1:
                result["static_status"] = "ambiguous_identity"
            elif not logical_ids:
                result["static_status"] = "mechanical_only"
            else:
                result["static_status"] = "identity_linked"

            if compile_destinations and result["static_status"] == "identity_linked":
                previous = previous_results.get(result["seed"])
                if compiler_for is not None and evidence_root is not None:
                    compiler, overrides = compiler_for(slug)
                    compiler = pathlib.Path(compiler)
                    basis, preamble, environment = compile_basis(seed, compiler, evidence_root,
                                                                compile_input_manifest, overrides,
                                                                objdiff_check=objdiff_check, coff_functions=coff_functions,
                                                                elf_symbol_bytes=elf_symbol_bytes)
                    result['compileBasis'] = basis
                    if can_reuse_compile_result(result, previous):
                        result.update({key: previous[key] for key in COMPILE_RESULT_FIELDS if key in previous})
                        result['compileResultReused'] = True
                    else:
                        result.update(compile_seed(
                            slug, seed, target or seed.source_original_bytes,
                            compiler=compiler, evidence_root=evidence_root, env_overrides=overrides,
                            frozen_preamble=preamble, frozen_environment=environment,
                            objdiff_check=objdiff_check, coff_functions=coff_functions, elf_symbol_bytes=elf_symbol_bytes,
                        ))
                        after, _, _ = compile_basis(seed, compiler, evidence_root,
                                                    compile_input_manifest, overrides,
                                                    objdiff_check=objdiff_check, coff_functions=coff_functions,
                                                    elf_symbol_bytes=elf_symbol_bytes)
                        if after != basis and result.get('compile_status') == 'byte_exact':
                            result['compile_status'] = 'compile_inputs_changed'
                            result['compile_detail'] = 'Compiler/context/environment dependency basis changed during observation'
                else:
                    result["compile_status"] = "not_run"
            else:
                result["compile_status"] = "not_run"
            # The compiler consumed the frozen parsed seed, never a second file
            # read. Do not publish its verdict as current after an in-flight edit.
            if path.read_bytes() != source_snapshot:
                result.pop("sourceSha256", None)
                result["compile_status"] = "source_changed"
                result["static_status"] = "invalid"
                problems.append("source_changed_during_validation")
        except Exception as exc:
            problems.append(type(exc).__name__)
            result.update({
                "static_status": "invalid",
                "compile_status": "not_run",
                "error": str(exc),
            })
        result["problems"] = problems
        results.append(result)

    dest = pathlib.Path(results_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w") as fh:
        for result in results:
            fh.write(json.dumps(result, sort_keys=True) + "\n")

    materialized_slugs = {r["dst_slug"] for r in results}
    eligible_rows = [r for r in candidate_rows if r["dst_slug"] in materialized_slugs]
    eligible_groups = group_candidates(eligible_rows)
    linked_rows = [r for r in eligible_rows if candidate_reuse_key(r) in reuse]
    linked_groups = group_candidates(linked_rows)
    status = Counter(r["static_status"] for r in results)
    compiled = Counter(r["compile_status"] for r in results)
    summary = {
        "candidate_rows": len(candidate_rows),
        "candidate_unique_destinations": len(groups),
        "copy_eligible_candidate_rows": len(eligible_rows),
        "copy_eligible_unique_destinations": len(eligible_groups),
        "copy_attempt_overcount": len(eligible_rows) - len(eligible_groups),
        "materialized_seed_files": len(results),
        "destinations_with_multiple_candidates": sum(
            len(rows) > 1 for rows in eligible_groups.values()
        ),
        "identity_linked_candidate_rows": len(linked_rows),
        "identity_linked_unique_destinations": len(linked_groups),
        "static_status": dict(sorted(status.items())),
        "compile_status": dict(sorted(compiled.items())),
        "compile_requested": compile_destinations,
        "promotion_rule": (
            "real C + verified source + exact destination bytes + logical identity "
            "+ destination byte-exact compilation"
        ),
    }
    pathlib.Path(summary_path).write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds-dir", type=pathlib.Path, required=True)
    parser.add_argument("--candidates", type=pathlib.Path, required=True)
    parser.add_argument("--reuse", type=pathlib.Path, required=True)
    parser.add_argument("--results", type=pathlib.Path, required=True)
    parser.add_argument("--summary", type=pathlib.Path, required=True)
    parser.add_argument("--coverage-dir", type=pathlib.Path)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--compile-input-manifest", type=pathlib.Path)
    args = parser.parse_args(argv)
    audit(
        seeds_dir=args.seeds_dir,
        candidates_path=args.candidates,
        reuse_path=args.reuse,
        results_path=args.results,
        summary_path=args.summary,
        coverage_dir=args.coverage_dir,
        compile_destinations=args.compile or args.retry_failed,
        retry_failed_only=args.retry_failed,
        compile_input_manifest=args.compile_input_manifest,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

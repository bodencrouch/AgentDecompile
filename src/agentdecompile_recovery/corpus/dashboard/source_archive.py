"""Export a whole-program C generation and complete recorded source snapshot.

The manifest inventories every recorded function, including missing source.
Compilation, function coverage and byte proof are deliberately separate claims.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from agentdecompile_recovery.corpus.source_claims import is_machine_code_shim
from .analysis_view import _knowledge_sources
from .common import live_db, live_root

_SOURCE_SUFFIXES = {'.c', '.cc', '.cpp', '.cxx', '.h', '.hh', '.hpp', '.hxx', '.s', '.asm', '.inc', '.cmake', '.vcxproj', '.sln', '.def'}
_BUILD_NAMES = {'CMakeLists.txt', 'Makefile', 'makefile', 'meson.build', 'meson_options.txt'}
_MAX_FILES = 50_000
_MAX_FILE_BYTES = 16 * 1024 * 1024
_MAX_INPUT_BYTES = 512 * 1024 * 1024
_MAX_OUTPUT_BYTES = 1024 * 1024 * 1024


def _checked(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise InterruptedError('Source archive cancelled; no completed download was published.')


def _hashes(path: Path, cancel: threading.Event) -> tuple[str, str]:
    before = path.stat()
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            _checked(cancel)
            sha.update(chunk)
            md5.update(chunk)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError('The selected binary changed while its identity was being read.')
    return sha.hexdigest(), md5.hexdigest()


def _safe_file(path: Path, roots: list[Path]) -> Path | None:
    """Require a regular file whose entire path stays inside an allowed root."""
    try:
        absolute = path.absolute()
        resolved = path.resolve(strict=True)
        if absolute != resolved or not resolved.is_file():
            return None
        return resolved if any(resolved.is_relative_to(root) for root in roots) else None
    except (OSError, ValueError):
        return None


def _read_limited(path: Path, cancel: threading.Event) -> bytes:
    size = path.stat().st_size
    if size > _MAX_FILE_BYTES:
        raise ValueError(f'{path} exceeds the {_MAX_FILE_BYTES // (1024 * 1024)} MiB per-file safety limit.')
    chunks: list[bytes] = []
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            _checked(cancel)
            chunks.append(chunk)
    return b''.join(chunks)


def _body_kind(text: str, assembly: bool = False) -> str:
    if assembly:
        return 'assembly-listing'
    if is_machine_code_shim(text):
        return 'assembly-substrate'
    # A declaration, error string or comment-only skeleton is useful context,
    # but cannot count as a function source body.
    code = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S).strip()
    return 'advisory-c' if '{' in code and '}' in code else 'context-only'


def resolve_export_context(params: dict[str, Any], cancel: threading.Event) -> dict[str, Any]:
    """Resolve one exact inventory/program binding without touching Ghidra state."""
    root, db = live_root(), live_db()
    if root is None or db is None or not db.is_file():
        raise ValueError('A workspace with a recorded binary inventory is required.')
    slug = str(params.get('slug') or '').strip()
    locator = str(params.get('locator') or '').strip()
    program = str(params.get('program') or params.get('programPath') or '').strip()
    con = sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        binary = con.execute('SELECT * FROM binary WHERE slug=?', (slug,)).fetchone() if slug else None
        if binary is None and locator and program and 'program_binding' in tables:
            candidates = con.execute("SELECT b.* FROM binary b JOIN program_binding p ON p.source_path=b.repo_path WHERE p.locator=? AND ltrim(p.program,'/')=?", (locator, program.lstrip('/'))).fetchall()
            if len(candidates) == 1:
                binary = candidates[0]
        if binary is None:
            raise ValueError('Select one registered binary. A project name does not identify a source export target.')
        source = Path(binary['repo_path']).expanduser().resolve()
        sha256, fingerprint = _hashes(source, cancel)
        bindings = [] if 'program_binding' not in tables else [dict(row) for row in con.execute('SELECT locator,program FROM program_binding WHERE source_path=?', (binary['repo_path'],))]
        exact = [row for row in bindings if (not locator or row['locator'] == locator) and (not program or str(row['program']).lstrip('/') == program.lstrip('/'))]
        context = {'slug': binary['slug'], 'binaryId': binary['id'], 'repo': str(source), 'sourceSha256': sha256, 'programFingerprint': fingerprint}
        if len(exact) == 1:
            context.update(exact[0])
        return context
    finally:
        con.close()


def build_archive(params: dict[str, Any], cancel: threading.Event, on_output: Callable[[str], None] | None = None,
                  export_program: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Generate/export using the caller's shared native job path, then atomically ZIP.

    ``export_program(output_path, context)`` must return an ``ok`` boolean and
    diagnostic metadata. It receives an exact stored project/program binding.
    Existing program exports are never silently substituted for this invocation.
    """
    logs: list[str] = []

    def progress(message: str) -> None:
        logs.append(message)
        if on_output:
            on_output('\n'.join(logs[-80:]))

    _checked(cancel)
    root, db = live_root(), live_db()
    if root is None or db is None or not db.is_file():
        raise ValueError('A workspace with a recorded binary inventory is required.')
    workspace = root.resolve()
    slug = str(params.get('slug') or '').strip()
    locator = str(params.get('locator') or '').strip()
    program = str(params.get('program') or params.get('programPath') or '').strip()
    progress('Reading the complete recorded function inventory.')
    con = sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        con.execute('BEGIN')
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        binary = con.execute('SELECT * FROM binary WHERE slug=?', (slug,)).fetchone() if slug else None
        if binary is None and locator and program and 'program_binding' in tables:
            candidates = con.execute("SELECT b.* FROM binary b JOIN program_binding p ON p.source_path=b.repo_path WHERE p.locator=? AND ltrim(p.program,'/')=?", (locator, program.lstrip('/'))).fetchall()
            if len(candidates) == 1:
                binary = candidates[0]
        if binary is None:
            raise ValueError('Select one registered binary. A project name does not identify a source export target.')
        source = Path(binary['repo_path']).expanduser().resolve()
        sha256, fingerprint = _hashes(source, cancel)
        recorded_md5 = str(dict(binary).get('md5') or '').lower()
        inventory_bound = bool(re.fullmatch(r'[0-9a-f]{32}', recorded_md5))
        if inventory_bound and recorded_md5 != fingerprint:
            raise ValueError('The binary bytes no longer match the imported function inventory. Reimport the changed binary before exporting source.')
        bindings = [] if 'program_binding' not in tables else [dict(row) for row in con.execute('SELECT locator,program FROM program_binding WHERE source_path=?', (binary['repo_path'],))]
        exact = [row for row in bindings if (not locator or row['locator'] == locator) and (not program or str(row['program']).lstrip('/') == program.lstrip('/'))]
        context = {'slug': binary['slug'], 'binaryId': binary['id'], 'repo': str(source), 'sourceSha256': sha256, 'programFingerprint': fingerprint}
        if len(exact) == 1:
            context.update(exact[0])
        knowledge, _ = _knowledge_sources(con, binary, tables, locator, program)
        columns = {row[1] for row in con.execute('PRAGMA table_info(func)')}
        selected = [name for name in ('addr', 'name', 'name_origin', 'source', 'source_file', 'namespace', 'signature') if name in columns]
        inventory = [dict(row) for row in con.execute('SELECT '+','.join(selected)+' FROM func WHERE binary_id=? ORDER BY addr', (binary['id'],))]
        recovered = [dict(row) for row in con.execute('SELECT addr,path FROM recovered_function WHERE binary_id=? AND addr IS NOT NULL', (binary['id'],))] if 'recovered_function' in tables else []
        if 'logical_name' in tables and 'identity' in tables:
            for row in inventory:
                human = row.get('source') == 'USER_DEFINED' or str(row.get('name_origin') or '').lower() in {'human', 'human-authored', 'user', 'user_defined'}
                if human and row.get('name'):
                    continue
                name = con.execute('SELECT ln.name FROM identity i JOIN logical_name ln ON ln.logical_id=i.logical_id WHERE i.binary_id=? AND i.addr=? ORDER BY i.confidence DESC,i.logical_id LIMIT 1', (binary['id'], row['addr'])).fetchone()
                if name and name[0]:
                    row['name'] = name[0]
    finally:
        con.close()
    export_id = uuid.uuid4().hex
    output_root = workspace / 'exports' / 'source-archives'
    if output_root.resolve() != output_root:
        raise ValueError('The source export directory must remain inside this workspace.')
    directory = output_root / export_id
    directory.mkdir(parents=True, exist_ok=False)
    generated = directory / 'generated'
    generated.mkdir()
    generation: dict[str, Any] = dict(params.get('_prefetchedGeneration') or {'ok': False, 'requested': True, 'reason': 'No unique project/program binding is available for whole-program source generation.'})
    prefetched = Path(str(params.get('_prefetchedGenerationDir') or '')) if params.get('_prefetchedGenerationDir') else None
    if prefetched is not None:
        safe_prefetched = _safe_file(prefetched / 'program.c', [prefetched])
        if safe_prefetched is not None:
            (generated / 'program.c').write_bytes(_read_limited(safe_prefetched, cancel))
        header = _safe_file(prefetched / 'program.h', [prefetched])
        if header is not None:
            (generated / 'program.h').write_bytes(_read_limited(header, cancel))
    elif export_program and context.get('locator') and context.get('program'):
        _checked(cancel)
        progress('Exporting whole-program C and a header from the selected Ghidra program.')
        try:
            generation = dict(export_program(generated / 'program.c', context))
            generation['requested'] = True
        except InterruptedError:
            raise
        except Exception as exc:
            generation = {'ok': False, 'requested': True, 'error': str(exc)}
    elif not export_program:
        generation['reason'] = 'The native whole-program exporter is unavailable; preserving all recorded source witnesses.'
    _checked(cancel)
    progress('Packaging source witnesses, assembly evidence and the full function inventory.')
    manifest: dict[str, Any] = {'schemaVersion': 1, 'createdAt': time.time(), 'exportId': export_id,
        'binary': {**dict(binary), 'sha256': sha256, 'currentMd5': fingerprint,
                   'inventoryTargetBinding': 'Recorded import fingerprint matches current bytes' if inventory_bound else 'No recorded import fingerprint; inventory freshness is unverified'}, 'context': context,
        'generationTask': generation, 'claim': 'Source snapshot. Compilation and byte verification are not established by this archive.',
        'files': [], 'warnings': [], 'functions': []}
    observation = generation.get('observation') or {}
    native_count = observation.get('functionCount') if isinstance(observation, dict) else None
    if (isinstance(native_count, bool) or not isinstance(native_count, int) or native_count < 0
            or str(observation.get('md5') or '').lower() != fingerprint):
        native_count = None
    inventory_matches = native_count == len(inventory) if native_count is not None else None
    inventory_warning = ''
    if inventory_matches is False:
        inventory_warning = (f'The selected Ghidra program currently reports {native_count} functions, but the saved corpus inventory contains {len(inventory)}. '
                             'The per-function manifest covers the saved records only. Refresh extracted facts before treating it as the current program inventory.')
        manifest['warnings'].append({'stage': 'inventory', 'reason': inventory_warning})
    known = {int(row['addr']): row for row in inventory}
    exported: dict[int, list[dict]] = {address: [] for address in known}
    seen: dict[tuple[int, str, str], str] = {}
    temporary = directory / 'source.zip.partial'
    destination = directory / 'source.zip'
    allowed_roots = [workspace]
    configured = os.environ.get('AGENT_DECOMPILE_RECOVERED_DIR', '').strip()
    if configured:
        allowed_roots.append(Path(configured).expanduser().resolve())
    input_bytes = 0
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            def put(name: str, content: bytes, claim: str, provenance: dict) -> None:
                nonlocal input_bytes
                _checked(cancel)
                if len(manifest['files']) >= _MAX_FILES:
                    raise ValueError(f'Source archive exceeds the {_MAX_FILES:,}-file safety limit.')
                if len(content) > _MAX_FILE_BYTES:
                    raise ValueError(f'{name} exceeds the {_MAX_FILE_BYTES // (1024 * 1024)} MiB per-file safety limit.')
                input_bytes += len(content)
                if input_bytes > _MAX_INPUT_BYTES:
                    raise ValueError(f'Source archive exceeds the {_MAX_INPUT_BYTES // (1024 * 1024)} MiB input safety limit.')
                archive.writestr(name, content)
                if temporary.stat().st_size > _MAX_OUTPUT_BYTES:
                    raise ValueError(f'Source archive exceeds the {_MAX_OUTPUT_BYTES // (1024 * 1024)} MiB output safety limit.')
                manifest['files'].append({'path': name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(), 'claim': claim, 'provenance': provenance})

            def witness(address: int, text: str, provenance: dict, assembly: bool = False) -> None:
                if address not in known or not text.strip():
                    return
                kind = _body_kind(text, assembly)
                content = text.encode('utf-8')
                digest = hashlib.sha256(content).hexdigest()
                key = (address, kind, digest)
                if key in seen:
                    for item in exported[address]:
                        if item['path'] == seen[key]:
                            item['provenance'].append(provenance)
                    return
                folder = 'source/functions' if kind == 'advisory-c' else 'assembly/substrate' if kind == 'assembly-substrate' else 'assembly/listings' if assembly else 'context/functions'
                suffix = '.asm' if assembly else '.c'
                name = f'{folder}/0x{address:08x}-{digest[:16]}{suffix}'
                put(name, content, kind, provenance)
                seen[key] = name
                exported[address].append({'path': name, 'claim': kind, 'sha256': digest, 'provenance': [provenance]})

            generated_count = 0
            generated_c = False
            for path in generated.rglob('*'):
                _checked(cancel)
                safe = _safe_file(path, [generated])
                if safe is None or safe.suffix.lower() not in _SOURCE_SUFFIXES:
                    continue
                content = _read_limited(safe, cancel)
                if not content:
                    continue
                shim = is_machine_code_shim(content.decode('utf-8', errors='replace'))
                is_c = safe.suffix.lower() in {'.c', '.cc', '.cpp', '.cxx'}
                generated_c |= is_c
                prefix = 'assembly/generated' if shim else 'source/whole-program'
                put(prefix+'/'+safe.relative_to(generated).as_posix(), content, 'assembly-substrate' if shim else 'advisory-generated-source', {'tool': 'Ghidra whole-program exporter', 'currentExecution': True, 'generationSucceeded': generation.get('ok') is True})
                generated_count += 1
            generation['filesWritten'] = generated_count
            generation['wholeProgramCWritten'] = generated_c
            if generation.get('ok') and not generated_c:
                generation.update(ok=False, error='The exporter reported success but produced no C file in this execution.')
            for index, source_db in enumerate(knowledge, 1):
                _checked(cancel)
                progress(f'Reading complete source text from witness {index} of {len(knowledge)}.')
                try:
                    with sqlite3.connect(Path(source_db['path']).as_uri()+'?mode=ro', uri=True, timeout=10) as kb:
                        kb.execute('BEGIN')
                        rows_read = 0
                        for entry, code, assembly in kb.execute('SELECT entry_hex,decompiled,asm FROM func_knowledge WHERE program=?', (source_db['program'],)):
                            _checked(cancel)
                            rows_read += 1
                            try:
                                address = int(str(entry), 16)
                            except ValueError:
                                continue
                            if code:
                                witness(address, str(code), source_db)
                            if assembly:
                                witness(address, str(assembly), source_db, assembly=True)
                            if rows_read % 200 == 0:
                                progress(f'Read {rows_read} function records from witness {index}; preserved {len(seen)} source and assembly files.')
                except sqlite3.Error as exc:
                    manifest['warnings'].append({'source': source_db['path'], 'reason': str(exc)})
            for row in recovered:
                _checked(cancel)
                path = Path(str(row['path']))
                if not path.is_absolute():
                    path = workspace / path
                safe = _safe_file(path, allowed_roots)
                if safe is None:
                    manifest['warnings'].append({'source': str(path), 'reason': 'Recorded source is missing or outside its allowed source root.'})
                    continue
                content = _read_limited(safe, cancel)
                _checked(cancel)
                witness(int(row['addr']), content.decode('utf-8', errors='replace'), {'kind': 'binary-bound recovered_function row', 'path': str(safe), 'freshness': 'Not independently reverified'})
            # Include project headers/layout only from the same fingerprint-bound
            # workflow directory used to produce a selected source witness.
            for source_db in knowledge:
                if source_db.get('kind') != 'fingerprint-bound workflow knowledge':
                    continue
                work = Path(source_db['path']).parent
                candidates = iter((work / 'ghidra_types.h',))
                source_tree = work / 'source'
                if source_tree.is_dir() and source_tree.resolve() == source_tree:
                    from itertools import chain
                    candidates = chain(candidates, source_tree.rglob('*'))
                for path in candidates:
                    _checked(cancel)
                    safe = _safe_file(path, [work])
                    if safe is None or (safe.suffix.lower() not in _SOURCE_SUFFIXES and safe.name not in _BUILD_NAMES):
                        continue
                    content = _read_limited(safe, cancel)
                    kind = _body_kind(content.decode('utf-8', errors='replace'), safe.suffix.lower() in {'.s', '.asm'})
                    prefix = 'assembly/projects' if kind in {'assembly-substrate', 'assembly-listing'} else 'source/projects'
                    put(prefix+'/'+source_db['runId']+'/'+safe.relative_to(work).as_posix(), content, kind, source_db)
            # A protected file transformation or external replacement during export
            # invalidates the target identity; never publish under the old hash.
            final_sha, _ = _hashes(source, cancel)
            if final_sha != sha256:
                raise ValueError('The selected binary changed during export; the archive was not published.')
            source_count = substrate_count = assembly_count = 0
            for row in inventory:
                address = int(row['addr'])
                entries = exported[address]
                has_source = any(item['claim'] == 'advisory-c' for item in entries)
                has_substrate = any(item['claim'] == 'assembly-substrate' for item in entries)
                source_count += has_source
                substrate_count += has_substrate
                assembly_count += any(item['claim'] == 'assembly-listing' for item in entries)
                manifest['functions'].append({**row, 'addr': f'0x{address:08x}', 'sourceAvailable': has_source,
                    'files': entries, 'compiles': None, 'byteVerified': None,
                    'missingReason': None if has_source else 'No address-bound C body is available. Whole-program output, if present, has not been enumerated into individual function coverage.'})
            coverage = {'inventoryFunctions': len(inventory), 'sourceFunctions': source_count, 'missingSourceFunctions': len(inventory)-source_count,
                'currentProgramFunctions': native_count, 'inventoryMatchesCurrentProgram': inventory_matches,
                'assemblySubstrateFunctions': substrate_count, 'assemblyListingFunctions': assembly_count,
                'completeRecordedFunctionSource': bool(inventory) and source_count == len(inventory),
                'wholeProgramCWritten': generated_c, 'wholeProgramFunctionCoverage': None, 'compiles': None, 'byteVerified': None}
            manifest['coverage'] = coverage
            manifest['partial'] = not coverage['completeRecordedFunctionSource'] or generation.get('ok') is not True or not inventory_bound or inventory_matches is False
            if not inventory_bound:
                manifest['warnings'].append({'stage': 'inventory', 'reason': 'No recorded import fingerprint is available; the saved inventory has not been bound to the current target bytes.'})
            if not generation.get('ok'):
                manifest['warnings'].append({'stage': 'whole-program-source', 'reason': generation.get('error') or generation.get('reason') or 'Whole-program export did not complete.'})
            readme = f'''# {binary['slug']} source archive

This archive records source for the selected binary with SHA-256 `{sha256}`.
The manifest lists all {len(inventory)} recorded functions, including missing source.
{inventory_warning}

`source/whole-program/` contains C and headers generated during this export when the Ghidra exporter was available. Exporter success does not establish per-function coverage or compilation.
`source/functions/` contains full address-bound C witnesses. These are advisory source, not proven original source.
`assembly/` keeps machine-code substrate and assembly listings separate from C source coverage.
`source/projects/` preserves existing project layout, headers and build files from fingerprint-bound recovery workspaces when available. Existing layouts may contain unfinished stubs.
`context/` contains declarations or other text that does not establish a function body.

Address-bound C witnesses: {source_count} of {len(inventory)}. Missing C witnesses: {len(inventory)-source_count}.
Whole-program C file written in this execution: {generated_c}.
Compilation and byte verification have not been performed by this export. Read `manifest.json` for provenance and exact coverage limitations.
'''
            archive.writestr('README.md', readme)
            archive.writestr('manifest.json', json.dumps(manifest, indent=2, ensure_ascii=False))
            if temporary.stat().st_size > _MAX_OUTPUT_BYTES:
                raise ValueError(f'Source archive exceeds the {_MAX_OUTPUT_BYTES // (1024 * 1024)} MiB output safety limit.')
        _checked(cancel)
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    progress(f'Source ZIP ready: {source_count} address-bound C witnesses, {len(inventory)-source_count} without an address-bound C body. See the manifest for whole-program output.')
    return {'ok': True, 'exportId': export_id, 'path': str(destination),
        'artifactUrl': f'/dashboard/api/workbench/source-archives/{export_id}/download',
        'downloadUrl': f'/dashboard/api/workbench/source-archives/{export_id}/download', 'filename': str(binary['slug'])+'-source.zip',
        'coverage': coverage, 'partial': manifest['partial'], 'generationTask': generation,
        'warnings': manifest['warnings'][:20], 'warningCount': len(manifest['warnings']),
        'bytes': destination.stat().st_size, 'sourceSha256': sha256,
        'claim': manifest['claim']}


def build_project_archive(params: dict[str, Any], cancel: threading.Event,
                          on_output: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Package a recorded project snapshot, never acquire or regenerate analysis.

    Membership uses the same durable project resolver as the workbench. The
    inventory and names share one SQLite snapshot; recorded fingerprints allow
    recovery witnesses to survive an unavailable original executable.
    """
    from .common import corpus_file_identity, corpus_read_snapshot
    from .project_universe import canonical, project_universe, read_json

    root = live_root()
    expected = str(params.get('corpus_identity') or '')
    project_id = str(params.get('project_id') or '')
    if root is None or not expected or not project_id:
        raise ValueError('Select a persisted project and its corpus identity before downloading source.')
    workspace = root.resolve()
    sessions_path = workspace / 'workbench-sessions.json'
    sessions_digest = hashlib.sha256(_read_limited(sessions_path, cancel)).hexdigest()
    universe = project_universe(limit=1)
    if universe.get('corpusIdentity') != expected:
        raise ValueError('The selected corpus changed; refresh project facts before exporting.')
    projects = [p for p in universe.get('projects', []) if p.get('id') == project_id]
    if len(projects) != 1:
        raise ValueError('The selected project is no longer present in persisted workspace state.')
    project = {key: projects[0].get(key) for key in ('id', 'title', 'locator', 'kind')}
    if params.get('locator') and canonical(params['locator']) != canonical(project['locator']):
        raise ValueError('The requested project locator does not match its persisted identity.')
    members = [m for m in universe.get('builds', []) if project_id in m.get('projectIds', [])]
    if not members:
        raise ValueError('No recorded project members are available; no empty source download was published.')
    export_id = uuid.uuid4().hex
    title = re.sub(r'[^A-Za-z0-9._-]+', '-', str(project['title'] or 'project')).strip('-')[:160] or 'project'
    filename = title + '-source.zip'
    directory = workspace / 'exports' / 'source-archives' / export_id
    if directory.resolve() != directory:
        raise ValueError('Source archives must remain inside the selected workspace.')
    directory.mkdir(parents=True, exist_ok=False)
    temporary, destination = directory / 'source.zip.partial', directory / 'source.zip'
    allowed = [workspace]
    configured = os.environ.get('AGENT_DECOMPILE_RECOVERED_DIR', '').strip()
    if configured:
        allowed.append(Path(configured).expanduser().resolve())
    manifest: dict[str, Any] = {'schemaVersion': 2, 'scope': 'project', 'project': project,
        'exportId': export_id, 'createdAt': time.time(), 'corpusIdentity': expected,
        'claim': 'Recorded source snapshot, not a fresh build, max-C acceptance or byte-parity receipt.',
        'generationTask': {'requested': False, 'reason': 'Reuse recorded artifacts only.'},
        'members': [], 'files': [], 'warnings': list(universe.get('errors') or [])}
    totals = {'members': len(members), 'boundMembers': 0, 'inventoryFunctions': 0,
              'sourceFunctions': 0, 'assemblyListingFunctions': 0, 'assemblySubstrateFunctions': 0}
    used = 0
    try:
        with corpus_read_snapshot(expected) as (con, basis), zipfile.ZipFile(
                temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            con.row_factory = sqlite3.Row
            con.set_progress_handler(lambda: int(cancel.is_set()), 1000)
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            binaries = {r['id']: dict(r) for r in con.execute('SELECT * FROM binary')}
            errors: list[str] = []
            receipts = []
            for path in sorted((workspace / 'preparations').glob('*.json')):
                _checked(cancel)
                if re.fullmatch(r'[0-9a-f]{32}', path.stem):
                    receipt = read_json(path, errors)
                    if receipt.get('id') == path.stem:
                        receipts.append(receipt)
            manifest['warnings'].extend(errors)

            def put(name: str, content: bytes, kind: str, provenance: dict, *, metadata: bool = False) -> str:
                nonlocal used
                _checked(cancel)
                if (len(content) > (_MAX_INPUT_BYTES if metadata else _MAX_FILE_BYTES)
                        or len(manifest['files']) >= _MAX_FILES):
                    raise ValueError('Project archive exceeds its per-file or file-count safety limit.')
                used += len(content)
                if used > _MAX_INPUT_BYTES:
                    raise ValueError('Project archive exceeds its aggregate input-byte safety limit.')
                digest = hashlib.sha256(content).hexdigest()
                archive.writestr(name, content)
                manifest['files'].append({'path': name, 'sha256': digest, 'bytes': len(content),
                                          'claim': kind, 'provenance': provenance})
                if temporary.stat().st_size > _MAX_OUTPUT_BYTES:
                    raise ValueError('Project archive exceeds its output-byte safety limit.')
                return name

            for index, member in enumerate(members, 1):
                _checked(cancel)
                if on_output:
                    on_output(f'Packaging recorded source for project member {index}/{len(members)}: {member.get("name", "")}')
                item = {'membership': member, 'functions': [], 'warnings': []}
                manifest['members'].append(item)
                ids = list(dict.fromkeys(member.get('binaryIds') or []))
                if len(ids) != 1 or ids[0] not in binaries or member.get('repositoryBindingState') == 'unresolved':
                    item['missingReason'] = 'Project member has no unique recorded corpus binding.'
                    continue
                binary = binaries[ids[0]]
                fingerprint = str(binary.get('md5') or '').lower()
                bound = bool(re.fullmatch(r'[0-9a-f]{32}', fingerprint))
                item['binary'] = binary
                item['targetBinding'] = 'recorded import fingerprint' if bound else 'no recorded fingerprint'
                totals['boundMembers'] += 1
                inventory = [dict(r) for r in con.execute('SELECT addr,name FROM func WHERE binary_id=? ORDER BY addr', (binary['id'],))]
                if 'logical_name' in tables and 'identity' in tables:
                    names = {}
                    for row in con.execute('SELECT i.addr,ln.name FROM identity i JOIN logical_name ln ON ln.logical_id=i.logical_id WHERE i.binary_id=? ORDER BY i.confidence DESC,i.logical_id', (binary['id'],)):
                        names.setdefault(row[0], row[1])
                    for row in inventory:
                        row['logicalName'] = names.get(row['addr'])
                known = {int(row['addr']): [] for row in inventory}
                prefix = f'members/{index:04d}-{binary["id"]}'
                seen = set()

                def witness(address: int, text: str, provenance: dict, assembly: bool = False) -> None:
                    if address not in known or not text.strip():
                        return
                    content = text.encode('utf-8')
                    kind, digest = _body_kind(text, assembly), hashlib.sha256(content).hexdigest()
                    if (address, kind, digest) in seen:
                        return
                    seen.add((address, kind, digest))
                    folder = 'source' if kind == 'advisory-c' else 'assembly' if kind.startswith('assembly-') else 'context'
                    name = put(f'{prefix}/{folder}/0x{address:08x}-{digest[:16]}.{ "asm" if assembly else "c"}', content, kind, provenance)
                    known[address].append({'path': name, 'claim': kind, 'sha256': digest})

                stores = []
                for receipt in receipts:
                    for program, checkpoint in (receipt.get('checkpoints') or {}).items():
                        if not isinstance(checkpoint, dict) or not bound:
                            continue
                        if (checkpoint.get('binaryId') != binary['id'] or checkpoint.get('slug') != binary['slug']
                                or checkpoint.get('programFingerprint') != fingerprint
                                or checkpoint.get('knowledgeFingerprint') != fingerprint
                                or canonical(checkpoint.get('repoPath')) != canonical(binary['repo_path'])):
                            continue
                        if canonical(receipt.get('locator')) != canonical(member.get('locator')) or str(program).lstrip('/') != str(member.get('program')).lstrip('/'):
                            continue
                        path = workspace / 'recovery' / receipt['id'] / str(binary['id']) / f'knowledge-{fingerprint}.sqlite'
                        if canonical(checkpoint.get('knowledgeDb')) != str(path) or _safe_file(path, [workspace]) is None:
                            continue
                        stores.append({'path': str(path), 'program': program, 'runId': receipt['id'], 'programFingerprint': fingerprint, 'kind': 'recorded fingerprint-bound knowledge'})
                # Reuse unique-basename legacy witnesses without upgrading their provenance.
                from .actions.catalog import env_defaults
                kb = Path(str(env_defaults().get('kb') or ''))
                basename = Path(binary['repo_path']).name
                if kb.is_file() and sum(Path(b['repo_path']).name == basename for b in binaries.values()) == 1:
                    stores.append({'path': str(kb.resolve()), 'program': basename, 'kind': 'unique-basename legacy knowledge; freshness unverified'})
                for store in stores:
                    try:
                        with sqlite3.connect(Path(store['path']).as_uri() + '?mode=ro', uri=True, timeout=10) as kbcon:
                            for entry, code, asm in kbcon.execute('SELECT entry_hex,decompiled,asm FROM func_knowledge WHERE program=?', (store['program'],)):
                                _checked(cancel)
                                try:
                                    address = int(str(entry), 16)
                                except ValueError:
                                    continue
                                if code:
                                    witness(address, str(code), store)
                                if asm:
                                    witness(address, str(asm), store, True)
                    except sqlite3.Error as exc:
                        item['warnings'].append(str(exc))
                    if store.get('runId'):
                        work = Path(store['path']).parent
                        from itertools import chain
                        paths = iter((work / 'ghidra_types.h',))
                        tree = work / 'source'
                        if tree.is_dir() and tree.resolve() == tree:
                            paths = chain(paths, tree.rglob('*'))
                        for path in paths:
                            safe = _safe_file(path, [work])
                            if safe and (safe.suffix.lower() in _SOURCE_SUFFIXES or safe.name in _BUILD_NAMES):
                                content = _read_limited(safe, cancel)
                                kind = _body_kind(content.decode('utf-8', errors='replace'), safe.suffix.lower() in {'.s', '.asm'})
                                put(f'{prefix}/recorded-layout/{store["runId"]}/{safe.relative_to(work).as_posix()}', content, kind, store)
                if 'recovered_function' in tables:
                    for row in con.execute('SELECT addr,path FROM recovered_function WHERE binary_id=? AND addr IS NOT NULL', (binary['id'],)):
                        path = Path(str(row['path']))
                        safe = _safe_file(path if path.is_absolute() else workspace / path, allowed)
                        if safe:
                            witness(int(row['addr']), _read_limited(safe, cancel).decode('utf-8', errors='replace'), {'kind': 'recorded recovered_function; freshness unverified', 'path': str(safe)})
                        else:
                            item['warnings'].append(f'Recorded source missing or outside allowed roots: {path}')
                for row in inventory:
                    entries = known[int(row['addr'])]
                    kinds = {entry['claim'] for entry in entries}
                    for key, kind in [('sourceFunctions', 'advisory-c'), ('assemblyListingFunctions', 'assembly-listing'), ('assemblySubstrateFunctions', 'assembly-substrate')]:
                        totals[key] += kind in kinds
                    item['functions'].append({**row, 'addr': f'0x{int(row["addr"]):08x}', 'files': entries,
                        'byteVerified': None, 'compiles': None, 'missingReason': None if 'advisory-c' in kinds else 'No recorded address-bound C body; assembly evidence is not a C replacement.'})
                totals['inventoryFunctions'] += len(inventory)
                item['inventoryFunctions'] = len(inventory)
                if not inventory:
                    item['missingReason'] = 'No recorded function inventory for this member.'
            totals['missingSourceFunctions'] = totals['inventoryFunctions'] - totals['sourceFunctions']
            manifest['coverage'] = {**totals, 'compiles': None, 'byteVerified': None, 'wholeImageVerified': False}
            manifest['partial'] = bool(manifest['warnings']) or totals['boundMembers'] != totals['members'] or totals['missingSourceFunctions'] > 0 or any(m.get('missingReason') or m.get('warnings') or m.get('targetBinding') == 'no recorded fingerprint' for m in manifest['members'])
            if hashlib.sha256(_read_limited(sessions_path, cancel)).hexdigest() != sessions_digest:
                raise ValueError('Project membership changed while exporting; retry from the current project.')
            if corpus_file_identity(live_db()) != basis:
                raise ValueError('The corpus changed while exporting; no archive was published.')
            put('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode(), 'coverage manifest', {}, metadata=True)
            put('README.md', ('# Project source snapshot\n\n'+manifest['claim']+'\n\nEvery recorded member is inventoried in manifest.json. Missing C and missing assembly remain explicit gaps; this export does not invent executable .S fallbacks or certify existing layouts as buildable.\n').encode(), 'claim boundary', {})
        _checked(cancel)
        current = project_universe(limit=1)
        def membership_key(value: dict) -> str:
            return json.dumps([{k: m.get(k) for k in ('id', 'program', 'locator', 'binaryIds', 'repositoryBindingState')}
                for m in value.get('builds', []) if project_id in m.get('projectIds', [])], sort_keys=True)
        if current.get('corpusIdentity') != expected or membership_key(current) != membership_key(universe):
            raise ValueError('Project membership or corpus changed during export; no archive was published.')
        (directory / 'download.json').write_text(json.dumps({'filename': filename}), encoding='utf-8')
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return {'ok': True, 'scope': 'project', 'project': project, 'exportId': export_id,
            'filename': filename, 'downloadUrl': f'/dashboard/api/workbench/source-archives/{export_id}/download',
            'partial': manifest['partial'], 'coverage': manifest['coverage'], 'claim': manifest['claim'],
            'bytes': destination.stat().st_size}


def _worker_main(request_path: str) -> int:
    """Process-only entrypoint. Input is JSON/path data; no MCP or JVM state crosses."""
    cancel = threading.Event()
    try:
        params = json.loads(Path(request_path).read_text(encoding='utf-8'))
        def emit(message: str) -> None:
            print(json.dumps({'event': 'progress', 'message': message}), flush=True)
        result = (build_project_archive if params.get('_projectSourceArchive') else build_archive)(params, cancel, emit)
        result.update({'workerPid': os.getpid(), 'parentPid': os.getppid(),
                       'resolveWorkerPid': params.get('_resolveWorkerPid'),
                       'processIsolated': True, 'ownershipResolved': True})
        print(json.dumps({'event': 'result', 'result': result}, default=str), flush=True)
        return 0 if result.get('ok') else 1
    except BaseException as exc:
        print(json.dumps({'event': 'error', 'error': str(exc)}), flush=True)
        return 1


def _resolve_main(request_path: str) -> int:
    try:
        params = json.loads(Path(request_path).read_text(encoding='utf-8'))
        context = resolve_export_context(params, threading.Event())
        print(json.dumps({'event': 'context', 'context': context, 'workerPid': os.getpid()}), flush=True)
        return 0
    except BaseException as exc:
        print(json.dumps({'event': 'error', 'error': str(exc), 'workerPid': os.getpid()}), flush=True)
        return 1


def create_source_archive_router() -> APIRouter:
    router = APIRouter()

    @router.get('/dashboard/api/workbench/source-archives/{export_id}/download')
    def download(export_id: str):
        root = live_root()
        if root is None or not re.fullmatch(r'[0-9a-f]{32}', export_id):
            return JSONResponse({'error': 'Source archive not found'}, status_code=404)
        directory = root.resolve() / 'exports' / 'source-archives' / export_id
        path = _safe_file(directory / 'source.zip', [directory])
        if path is None:
            return JSONResponse({'error': 'Source archive not found'}, status_code=404)
        filename = 'source-' + export_id + '.zip'
        metadata = _safe_file(directory / 'download.json', [directory])
        if metadata is not None and metadata.stat().st_size <= 4096:
            try:
                proposed = json.loads(metadata.read_text(encoding='utf-8')).get('filename')
                if isinstance(proposed, str) and re.fullmatch(r'[A-Za-z0-9._-]{1,180}\.zip', proposed):
                    filename = proposed
            except (OSError, ValueError, AttributeError):
                pass
        return FileResponse(path, filename=filename, media_type='application/zip', headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})

    return router


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        raise SystemExit(_worker_main(sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == '--resolve':
        raise SystemExit(_resolve_main(sys.argv[2]))
    raise SystemExit(2)

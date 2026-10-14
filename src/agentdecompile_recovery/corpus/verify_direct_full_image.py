"""Fresh direct-build diagnostics and an independent whole-file comparison.

This route owns a new work directory, invokes the recovery compiler/link
frontdoor, compares local function diagnostics using that build's captured objects,
then compares the linked candidate with the shipped PE. Same-build linked
replacement contribution is unavailable, so these diagnostics cannot establish
terminal recovery, even when the complete files are byte-identical.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import struct
import time
from pathlib import Path

from .compile_link import compile_and_link_tree, _read_observation_bytes, select_compile_units
from .verify_full_image_receipt import _sha256
from .verify_recovered_byteexact import _prepare_verification, _compare_compiled_object, pe_mapper, _compiler_environment


def _placement_contract_preflight(path: Path, raw: bytes, units: list[Path]) -> dict:
    """Validate a bounded layout request before compilation; not producer proof."""
    content = _read_observation_bytes(path.resolve(), limit=2 * 1024**2)
    contract = json.loads(content)
    if not isinstance(contract, dict) or contract.get('schema') != 'agentdecompile.coff-placement-contract/v1':
        raise ValueError('unsupported-native-placement-contract')
    for key in ('sourceSha256', 'objectSha256', 'targetSha256'):
        value = contract.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('native-placement-contract-digest')
    if contract['targetSha256'] != hashlib.sha256(raw).hexdigest():
        raise ValueError('native-placement-contract-target-mismatch')
    try:
        pe = struct.unpack_from('<I', raw, 0x3c)[0]
        if raw[pe:pe + 4] != b'PE\0\0' or struct.unpack_from('<H', raw, pe + 24)[0] != 0x10b:
            raise ValueError('native-placement-contract-target-not-pe32')
        image_base = struct.unpack_from('<I', raw, pe + 52)[0]
    except struct.error as exc:
        raise ValueError('native-placement-contract-target-truncated') from exc
    if type(contract.get('imageBase')) is not int or contract['imageBase'] != image_base:
        raise ValueError('native-placement-contract-image-base')
    limits = contract.get('limitations')
    if (not isinstance(limits, list) or not 0 < len(limits) <= 64
            or any(not isinstance(item, str) or not item.strip() for item in limits)):
        raise ValueError('native-placement-contract-limitations')
    placements, externals = contract.get('placements'), contract.get('externals')
    if not isinstance(placements, list) or not 0 < len(placements) <= 4096:
        raise ValueError('native-placement-contract-placements')
    if not isinstance(externals, list) or len(externals) > 4096:
        raise ValueError('native-placement-contract-externals')
    seen = set()
    for entry in placements:
        if (not isinstance(entry, dict) or type(entry.get('section')) is not int
                or not 0 < entry['section'] <= 4096 or entry['section'] in seen
                or type(entry.get('address')) is not int or not 0 <= entry['address'] <= 0xffffffff
                or not isinstance(entry.get('provenance'), str) or not entry['provenance'].strip()
                or not isinstance(entry.get('targetSha256'), str)
                or len(entry['targetSha256']) != 64
                or any(c not in '0123456789abcdef' for c in entry['targetSha256'])
                or pe_mapper(raw)(entry['address'], 1) is None):
            raise ValueError('native-placement-contract-section-binding')
        seen.add(entry['section'])
    seen.clear()
    for entry in externals:
        if (not isinstance(entry, dict) or not isinstance(entry.get('name'), str)
                or not 0 < len(entry['name']) <= 4096 or '\0' in entry['name']
                or entry['name'] in seen or type(entry.get('address')) is not int
                or not 0 <= entry['address'] <= 0xffffffff
                or not isinstance(entry.get('provenance'), str) or not entry['provenance'].strip()):
            raise ValueError('native-placement-contract-external-binding')
        seen.add(entry['name'])
    if len(units) > 65536:
        raise ValueError('native-placement-contract-source-capacity')
    matching, total = [], 0
    for unit in units:
        source = _read_observation_bytes(unit, limit=min(64 * 1024**2, 256 * 1024**2 - total))
        total += len(source)
        if hashlib.sha256(source).hexdigest() == contract['sourceSha256']:
            matching.append(unit)
    if len(matching) != 1:
        raise ValueError('native-placement-contract-source-not-unique')
    return contract


def _captured_native_closure(contract: dict, captures: list, objects: dict, raw: bytes,
                             size_map: dict[int, int]) -> dict:
    """Bind layout to this build's capability, never a serialized observation."""
    from .coff_object import parse_object_inventory

    matches = [capability for capability, row in captures
               if row.get('sourceSha256') == contract['sourceSha256']]
    if len(matches) != 1:
        raise ValueError('native-placement-current-source-observation-not-unique')
    capability = matches[0]
    record = capability.record
    if record['objectSha256'] != contract['objectSha256']:
        raise ValueError('native-placement-current-object-digest-mismatch')
    # Inventory uses this build's callback bytes, not a retained-object path.
    # The writer independently validates the genuine producer capability.
    obj = objects.get(capability)
    if not isinstance(obj, bytes) or hashlib.sha256(obj).hexdigest() != record['objectSha256']:
        raise ValueError('native-placement-current-object-observation-invalid')
    inventory = parse_object_inventory(obj)
    primaries = []
    for entry in contract['placements']:
        number, address = entry['section'], entry['address']
        if number > len(inventory['sections']):
            raise ValueError('native-placement-current-section-missing')
        section = inventory['sections'][number - 1]
        offset = pe_mapper(raw)(address, section['size'])
        if offset is None or hashlib.sha256(raw[offset:offset + section['size']]).hexdigest() != entry['targetSha256']:
            raise ValueError('native-placement-current-region-digest-mismatch')
        functions = [symbol for symbol in inventory['symbols'].values()
                     if symbol['storageClass'] == 2 and symbol['section'] == number
                     and (symbol['type'] & 0x30) == 0x20]
        if (section['characteristics'] & 0x20 and len(functions) == 1
                and functions[0]['value'] == 0 and size_map.get(address) == section['size']):
            primaries.append({'objectSha256': record['objectSha256'], 'section': number,
                              'address': address, 'size': section['size']})
    if len(primaries) != 1:
        raise ValueError('native-placement-current-primary-not-unique')
    return {'observations': (capability,),
            'placements': [{'objectSha256': record['objectSha256'], 'section': entry['section'],
                            'address': entry['address']} for entry in contract['placements']],
            'externals': {entry['name']: entry['address'] for entry in contract['externals']},
            'image_base': contract['imageBase'], 'target_sha256': contract['targetSha256'],
            'primary_regions': primaries,
            'metadata_policy': {'defaultLibraries': 'suppress-explicit-externals',
                                'safeSEH': 'omit-table', 'debug': 'discard'}}


def _database_image_identity(connection: sqlite3.Connection, binary_id: int,
                              raw: bytes) -> dict:
    """Bind database function metadata to this image using its strongest stored hash.

    Current corpus databases carry SHA-256. Older per-binary KOTORXID databases
    carry only the original image MD5; accept that legacy basis only when the
    SHA-256 column is absent or NULL, and report the weaker basis explicitly.
    A populated but mismatching SHA-256 is never downgraded to MD5.
    """
    columns = {str(row[1]) for row in connection.execute('PRAGMA table_info(binary)')}
    if 'content_sha256' in columns:
        if 'md5' in columns:
            row = connection.execute(
                'SELECT content_sha256, md5 FROM binary WHERE id=?', (binary_id,)
            ).fetchone()
        else:
            row = connection.execute(
                'SELECT content_sha256, NULL FROM binary WHERE id=?', (binary_id,)
            ).fetchone()
        if not row:
            raise ValueError('selected database binary is missing')
        if row[0] is not None and str(row[0]).strip():
            expected = hashlib.sha256(raw).hexdigest()
            if str(row[0]).strip().lower() != expected:
                raise ValueError('selected database binary SHA-256 differs from captured target')
            return {'method': 'sha256', 'digest': expected}
        legacy_md5 = row[1]
    elif 'md5' in columns:
        row = connection.execute('SELECT md5 FROM binary WHERE id=?', (binary_id,)).fetchone()
        if not row:
            raise ValueError('selected database binary is missing')
        legacy_md5 = row[0]
    else:
        raise ValueError('selected database has no supported binary identity hash')
    if not isinstance(legacy_md5, str) or len(legacy_md5.strip()) != 32:
        raise ValueError('selected database binary has no usable SHA-256 or legacy MD5 identity')
    expected = hashlib.md5(raw).hexdigest()
    if legacy_md5.strip().lower() != expected:
        raise ValueError('selected database binary MD5 differs from captured target')
    return {'method': 'legacy-md5-fallback', 'digest': expected,
            'claim': 'Legacy metadata identity only; the captured image remains SHA-256 bound.'}


def compare_build_unit(event: dict, raw: bytes, size_map: dict[int, int], snapshot: dict) -> dict:
    """Compare an owned process-local observation; never compile or publish."""
    source = Path(event['sourcePath'])
    invocation = event.get('invocation')
    compiler_attestation = (invocation.get('compilerRunAttestation')
                            if isinstance(invocation, dict) else None)
    compiler_launch_state = (invocation.get('compilerLaunchState')
                            if isinstance(invocation, dict) else None)
    evidence = {key: event.get(key) for key in ('sourcePath', 'objectPath', 'sourceSha256',
        'normalizedInputSha256', 'objectSha256', 'sourceLanguage', 'freshCompilation',
        'reusedObject', 'compilerIdentity', 'invocation')}
    evidence['compilerRunAttestation'] = compiler_attestation or {
        'status': 'marker-not-found', 'diagnosticOnly': True, 'complete': False,
        'reason': 'no-captured-compiler-marker-for-this-unit'}
    evidence['compilerLaunchState'] = compiler_launch_state or 'unknown'
    evidence.update({'ok': False, 'diagnosticOnly': True, 'byteVerified': False,
                     'wholeImageVerified': False, 'sameBuildObjectObservation': True})
    original, obj = event.get('sourceBytes'), event.get('objectBytes')
    if (not isinstance(original, bytes) or not isinstance(obj, bytes)
            or hashlib.sha256(original).hexdigest() != event.get('sourceSha256')
            or hashlib.sha256(obj).hexdigest() != event.get('objectSha256')):
        return {**evidence, 'reason': 'invalid-build-object-observation'}
    prepared = _prepare_verification(source, raw, pe_mapper(raw), size_map,
                                     source_bytes=original, target_snapshot=snapshot)
    comparison = (prepared if isinstance(prepared, dict) else
                  _compare_compiled_object(source, prepared, obj, bin_dir=None, maxc_dir=None))
    native = event.get('nativeCompilationObservation')
    if native is not None:
        # Consume the owned same-build capability, not its serialized record or
        # a second compilation. The independent FPO extent can disagree with
        # this older whole-section comparer without granting source acceptance.
        from .source_contribution import observe_native_target_region
        if isinstance(prepared, dict):
            evidence['nativeTargetObservation'] = {
                'diagnosticOnly': True, 'accepted': False, 'byteVerified': False,
                'wholeImageVerified': False, 'rawEqual': False,
                'reason': 'native-target-source-selection-refused',
            }
        else:
            binding = snapshot.get('selectedDatabase', {})
            evidence['nativeTargetObservation'] = observe_native_target_region(
                native, target_raw=raw, address=prepared[2], size=prepared[3],
                db=binding.get('path'), binary_id=binding.get('binaryId'),
            )
    # The old comparer also reports masked scheduling distance. Preserve that
    # evidence without promoting its `ok` bit to accepted same-build recovery.
    return {**evidence, 'reason': 'same-build-object-diagnostic', 'comparison': comparison,
            'claim': 'Captured object supplied to this build; no certified linked region, toolchain closure or source acceptance.'}


def _fresh_output_capability(path):
    """Own a newly created child of one existing, physically held parent.

    Identity checks detect replacement; this does not exclude unmanaged writers
    or qualify historical ownership clearance. Refused trees are never removed.
    """
    import os
    import stat

    path = Path(os.path.abspath(path))
    if path.name in {"", ".", ".."}:
        raise ValueError("fresh-output-child-name-invalid")
    parent_fd = child_fd = None
    try:
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        parent_info = os.fstat(parent_fd)
        if not stat.S_ISDIR(parent_info.st_mode):
            raise ValueError("fresh-output-parent-not-directory")
        os.mkdir(path.name, mode=0o700, dir_fd=parent_fd)
        created = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        child_fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                           dir_fd=parent_fd)
        child_info = os.fstat(child_fd)
        if (not stat.S_ISDIR(created.st_mode) or not stat.S_ISDIR(child_info.st_mode)
                or (created.st_dev, created.st_ino) != (child_info.st_dev, child_info.st_ino)):
            raise ValueError("fresh-output-child-replaced-during-capture")
        capability = {"path": path, "parentFd": parent_fd, "childFd": child_fd,
                      "parentIdentity": (parent_info.st_dev, parent_info.st_ino),
                      "childIdentity": (child_info.st_dev, child_info.st_ino)}
        _verify_fresh_output_capability(capability)
        return capability
    except BaseException:
        try:
            if child_fd is not None:
                os.close(child_fd)
        finally:
            if parent_fd is not None:
                os.close(parent_fd)
        raise


def _verify_fresh_output_capability(capability):
    """Check both held directories and their current pathname bindings."""
    import os
    import stat

    path = capability["path"]
    parent_fd, child_fd = capability["parentFd"], capability["childFd"]
    checks = ((os.fstat(parent_fd), capability["parentIdentity"]),
              (os.stat(path.parent, follow_symlinks=False), capability["parentIdentity"]),
              (os.fstat(child_fd), capability["childIdentity"]),
              (os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False),
               capability["childIdentity"]))
    for observed, expected in checks:
        if not stat.S_ISDIR(observed.st_mode) or (observed.st_dev, observed.st_ino) != expected:
            raise ValueError("fresh-output-directory-identity-changed")


def _close_fresh_output_capability(capability):
    import os

    if capability is not None:
        try:
            os.close(capability["childFd"])
        finally:
            os.close(capability["parentFd"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="fresh direct build diagnostics and whole-file comparison; terminal contribution unsupported")
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument("--src-dir", type=Path, required=True)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--binary-id", type=int, required=True)
    ap.add_argument("--compiler", type=Path, required=True)
    ap.add_argument("--vcroot", type=Path, required=True)
    ap.add_argument("--wineprefix", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True,
                    help="new, nonexistent directory for this one receipt")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--candidate", action="append", default=[],
                    help="optional eligible source path relative to src-dir; repeat for a bounded diagnostic build")
    ap.add_argument("--compiler-options", help="Opt-in per-job owned MSVC CL_OPT override")
    ap.add_argument("--native-placement-contract", type=Path,
                    help="optional digest-bound COFF layout for captured native code/data/EH; diagnostic only")
    args = ap.parse_args(argv)

    target = args.target.resolve()
    # Keep the requested final component: resolving it would follow a
    # pre-existing symlink before exclusive child creation can refuse it.
    work = args.work_dir.absolute()
    errors: list[str] = []
    if not target.is_file():
        errors.append(f"target missing: {target}")
    if not args.src_dir.is_dir():
        errors.append(f"source directory missing: {args.src_dir}")
    if not args.raw.is_file():
        errors.append(f"raw image missing: {args.raw}")
    if not args.db.is_file():
        errors.append(f"database missing: {args.db}")
    if not args.compiler.is_file():
        errors.append(f"compiler wrapper missing: {args.compiler}")
    if not (args.vcroot / "bin" / "link.exe").is_file():
        errors.append(f"VC7 link.exe missing below: {args.vcroot}")
    if work.exists():
        errors.append(f"work directory must not already exist: {work}")
    started_ns = time.time_ns()
    candidate = work / "candidate.exe"
    same_build_diagnostics = work / "same-build-object-diagnostics.json"
    build: dict[str, object] = {"startedNs": started_ns, "workDir": str(work)}
    owns_work = False
    output_capability = None
    rows: list[dict] = []
    native_compilations = []
    native_objects = {}
    generated_units = 0
    raw = b''
    size_map: dict[int, int] = {}
    snapshot = {}
    placement_contract = None
    selected_units: list[Path] = []
    compiler_environment = None
    if not errors:
        try:
            compiler_environment = _compiler_environment(str(args.compiler), args.compiler_options)
            compiler_environment['VCROOT'] = str(args.vcroot.resolve())
            compiler_environment['WINEPREFIX'] = str(args.wineprefix.resolve())
            build['compilerConfiguration'] = {
                'compilerOptionsOverride': args.compiler_options is not None,
                'CL_OPT': compiler_environment.get('CL_OPT'),
                'vcroot': compiler_environment['VCROOT'],
                'wineprefix': compiler_environment['WINEPREFIX'],
                'scope': 'Captured compiler child inputs, not complete toolchain qualification.',
            }
            selected_units = select_compile_units(args.src_dir, args.candidate or None)
            build['sourceSelection'] = {
                'scope': 'selected-candidates' if args.candidate else 'full-tree',
                'selectedFiles': [str(unit.resolve().relative_to(args.src_dir.resolve()))
                                  if unit.resolve().is_relative_to(args.src_dir.resolve()) else str(unit)
                                  for unit in selected_units],
                'selectedCount': len(selected_units),
                'fullSourceCoverage': not bool(args.candidate),
                'claim': 'Eligible source inventory selection, not successful compilation or recovery proof.',
            }
        except (OSError, ValueError) as exc:
            errors.append(f'candidate selection preflight failed: {exc}')
    if not errors:
        try:
            raw = _read_observation_bytes(args.raw.resolve())
            target_hash = hashlib.sha256(_read_observation_bytes(target)).hexdigest()
            if hashlib.sha256(raw).hexdigest() != target_hash:
                raise ValueError('comparison image differs from selected target')
            with sqlite3.connect(args.db.resolve().as_uri() + '?mode=ro', uri=True) as connection:
                # Identity and function extents must come from one database view.
                connection.execute('BEGIN')
                database_identity = _database_image_identity(connection, args.binary_id, raw)
                size_map = {int(address): int(size or 0) for address, size in connection.execute(
                    'SELECT addr,size FROM func WHERE binary_id=?', (args.binary_id,))}
            snapshot = {'path': str(args.raw.resolve()), 'sha256': target_hash,
                        'size': len(raw), 'scope': 'same-build-captured-target',
                        'currentFileVerified': False,
                        'databaseImageIdentity': database_identity,
                        'selectedDatabase': {'path': str(args.db.resolve()),
                                             'binaryId': args.binary_id}}
            if args.native_placement_contract is not None:
                placement_contract = _placement_contract_preflight(args.native_placement_contract, raw, selected_units)
                from .source_contribution import _native_closure_target
                _native_closure_target(raw, placement_contract['imageBase'])
        except (OSError, ValueError, sqlite3.Error) as exc:
            errors.append(f'comparison preflight failed: {exc}')

    def observe_unit(event: dict) -> None:
        nonlocal generated_units
        if event.get('generatedEntrypoint'):
            generated_units += 1
            return
        row = compare_build_unit(event, raw, size_map, snapshot)
        rows.append(row)
        native = event.get('nativeCompilationObservation')
        if native is not None:
            native_compilations.append((native, row))
            native_objects[native] = event.get('objectBytes')

    def observe_link(linking):
        from .source_contribution import native_link_selection_evidence
        # Capabilities remain process-local. The receipt records the map-bound
        # PE byte comparison for qualified fresh functions, but not complete
        # linker closure, COMDAT/fixup coverage, or whole-image proof.
        for compilation, row in native_compilations:
            row['nativeLinkSelectionEvidence'] = native_link_selection_evidence(
                compilation, linking)

    try:
        if not errors:
            try:
                output_capability = _fresh_output_capability(work)
                work = output_capability["path"]
                # Every derived output must use the same captured spelling;
                # absolute() can retain '..' while the capability normalizes it.
                candidate = work / "candidate.exe"
                same_build_diagnostics = work / "same-build-object-diagnostics.json"
                build["workDir"] = str(work)
                build["outputOwnership"] = {
                    "source": "fresh-output-physical-directory-capability-v1",
                    "parentIdentity": output_capability["parentIdentity"],
                    "childIdentity": output_capability["childIdentity"],
                    "unmanagedWriterClearanceQualified": False,
                    "historicalOwnershipResolved": False,
                }
            except (OSError, ValueError) as exc:
                errors.append(f"fresh output ownership refused: {exc}")
        if not errors:
            owns_work = True
            try:
                _verify_fresh_output_capability(output_capability)
                linked = compile_and_link_tree(
                    args.src_dir, candidate, compiler=str(args.compiler), obj_dir=work / "objects",
                    workers=max(1, args.workers), entrypoint=True, vcroot=args.vcroot,
                    source_paths=args.candidate or None,
                    compiler_environment=compiler_environment,
                    wineprefix=str(args.wineprefix),
                    unit_observer=observe_unit,
                    link_observer=observe_link,
                )
                build["compileLink"] = linked
                if not linked.get("ok"):
                    errors.append("direct compiler/link did not produce a linked PE")
            except Exception as exc:  # preserve a negative receipt for operator diagnosis
                errors.append(f"direct build raised {exc.__class__.__name__}: {exc}")
            rows.sort(key=lambda row: row.get('sourcePath', ''))
            coverage = build.get('compileLink', {}).get('observationCoverage')
            coverage_state = 'unavailable'
            not_observed = None
            if isinstance(coverage, dict):
                counts = ('selectedUnits', 'attemptedUnits', 'successfulUnits', 'failedUnits',
                          'notDispatchedUnits', 'observedUnits', 'generatedEntrypointUnits')
                valid = all(type(coverage.get(key)) is int and coverage[key] >= 0 for key in counts)
                if valid:
                    valid = (coverage['attemptedUnits'] + coverage['notDispatchedUnits'] == coverage['selectedUnits']
                             and coverage['successfulUnits'] + coverage['failedUnits'] == coverage['attemptedUnits']
                             and coverage['observedUnits'] == len(rows) + generated_units
                             and coverage['observedUnits'] == coverage['successfulUnits']
                             and generated_units <= coverage['generatedEntrypointUnits'] <= coverage['selectedUnits'])
                coverage_state = 'consistent' if valid else 'inconsistent'
                if valid:
                    not_observed = coverage['selectedUnits'] - coverage['observedUnits']
            if coverage_state != 'consistent':
                errors.append(f'same-build observation coverage {coverage_state}')
            diagnostics = {'schema': 'agentdecompile.same-build-object-comparison/v1',
                'diagnosticOnly': True, 'byteVerified': False, 'wholeImageVerified': False,
                'total': len(rows), 'byteExact': 0, 'results': rows,
                'generatedEntrypointCount': generated_units,
                'observationCoverage': coverage, 'coverageState': coverage_state,
                'unobservedUnitCount': not_observed,
                'freshObjectCount': sum(row.get('freshCompilation') is True for row in rows),
                'reusedObjectCount': sum(row.get('reusedObject') is True for row in rows),
                'rawEqualDiagnosticCount': sum(row.get('comparison', {}).get('rawEqual') is True for row in rows),
                'secondCompilerPass': False,
                'claim': ('Custom captured-object/target-slice diagnostics plus any per-function linker-map '
                          'byte observations; no genuine objdiff receipt, complete linker closure, or recovery acceptance.')}
            _verify_fresh_output_capability(output_capability)
            same_build_diagnostics.write_text(json.dumps(diagnostics, indent=2) + '\n', encoding='utf-8')
            build['sameBuildDiagnostics'] = {key: value for key, value in diagnostics.items() if key != 'results'}

        target_info = None
        if target.is_file():
            try:
                current_target = _read_observation_bytes(target)
                current_hash = hashlib.sha256(current_target).hexdigest()
                target_info = {"path": str(target), "size": len(current_target), "sha256": current_hash}
                if snapshot and current_hash != snapshot['sha256']:
                    errors.append('selected target changed after comparison capture')
                build['selectedTargetCurrentFileVerified'] = bool(snapshot and current_hash == snapshot['sha256'])
                if snapshot:
                    current_raw = _read_observation_bytes(args.raw.resolve())
                    snapshot['currentFileVerified'] = hashlib.sha256(current_raw).hexdigest() == snapshot['sha256']
                    if not snapshot['currentFileVerified']:
                        errors.append('comparison image changed after comparison capture')
            except (OSError, ValueError) as exc:
                errors.append(f'selected target recapture failed: {exc}')
        if snapshot:
            build['comparisonCapture'] = dict(snapshot)
        # Publish exact-placement diagnostics separately from the stock linked PE.
        # Equality of copied floor cannot establish compiler/linker or C recovery.
        if (owns_work and native_compilations and snapshot.get('currentFileVerified')
                and build.get('selectedTargetCurrentFileVerified')):
            from .source_contribution import _native_placement_entry, publish_native_regions

            placements = []
            selection = {'nativeObservationCount': len(native_compilations),
                         'examinedCount': min(len(native_compilations), 64),
                         'notExaminedCount': max(0, len(native_compilations) - 64),
                         'eligibleCount': 0, 'refusedCount': 0,
                         'diagnosticOnly': True, 'accepted': False}
            for capability, row in native_compilations[:64]:
                evidence = row.get('nativeTargetObservation', {})
                binding = evidence.get('selectedDatabaseRow', {})
                try:
                    if evidence.get('rawEqual') is not True:
                        raise ValueError(evidence.get('reason', 'native_target_binding_unavailable'))
                    entry = (capability, binding['address'], binding['size'])
                    # Existing owner independently rechecks DB/content/extent,
                    # source eligibility, unsupported COMDAT/EH and final writer.
                    _native_placement_entry(capability, target_raw=raw, address=entry[1],
                                            size=entry[2], db=args.db, binary_id=args.binary_id)
                    placements.append(entry)
                    row['nativePlacementSelection'] = {'eligible': True, 'diagnosticOnly': True,
                                                         'accepted': False}
                except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
                    selection['refusedCount'] += 1
                    row['nativePlacementSelection'] = {'eligible': False, 'diagnosticOnly': True,
                                                         'accepted': False, 'reason': str(exc)}
            selection['eligibleCount'] = len(placements)
            build['nativePlacementSelection'] = selection
            publication = {'status': 'unavailable', 'reason': 'no_eligible_native_placement',
                           'diagnosticOnly': True, 'accepted': False,
                           'compilerProducedWholeImage': False, 'wholeImageVerified': False,
                           'sourceVerified': False, 'linkedSourceContributionVerified': False}
            if placement_contract is not None:
                try:
                    closure = _captured_native_closure(placement_contract, native_compilations, native_objects, raw, size_map)
                    ordinary = [entry for entry in placements if entry[0] not in closure['observations']]
                    selection['closureObservationCount'] = len(closure['observations'])
                    selection['ordinaryPlacementCount'] = len(ordinary)
                    selection['ordinaryEntriesReplacedByClosure'] = len(placements) - len(ordinary)
                    _verify_fresh_output_capability(output_capability)
                    publication = publish_native_regions(target_path=target,
                        output_path=work / 'native-placement.exe', target_raw=raw,
                        placements=ordinary, native_closure=closure, db=args.db, binary_id=args.binary_id)
                    build['nativePlacementContract'] = {
                        'sourceSha256': placement_contract['sourceSha256'],
                        'objectSha256': placement_contract['objectSha256'],
                        'diagnosticOnly': True, 'accepted': False,
                        'limitations': placement_contract['limitations']}
                except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
                    publication.update({'status': 'refused', 'reason': str(exc),
                        'claim': 'Requested layout did not qualify current-build native closure; no fallback publication.'})
            elif placements:
                try:
                    _verify_fresh_output_capability(output_capability)
                    publication = publish_native_regions(target_path=target,
                        output_path=work / 'native-placement.exe', target_raw=raw,
                        placements=placements, db=args.db, binary_id=args.binary_id)
                except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
                    publication.update({'status': 'refused', 'reason': str(exc),
                        'claim': 'No valid publication attested; any partial owned output remains diagnostic-only.'})
            build['nativePlacementPublication'] = publication
            # Selection annotations belong to the same owned object diagnostic file.
            diagnostics['results'] = rows
            _verify_fresh_output_capability(output_capability)
            same_build_diagnostics.write_text(json.dumps(diagnostics, indent=2) + '\n', encoding='utf-8')
        candidate_info = None
        if candidate.is_file():
            try:
                before = candidate.stat()
                candidate_bytes = _read_observation_bytes(candidate)
                after = candidate.stat()
                fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
                if any(getattr(before, field) != getattr(after, field) for field in fields):
                    raise ValueError('candidate changed during receipt capture')
                candidate_info = {"path": str(candidate), "size": len(candidate_bytes),
                                  "mtimeNs": after.st_mtime_ns,
                                  "sha256": hashlib.sha256(candidate_bytes).hexdigest()}
                if after.st_mtime_ns < started_ns:
                    errors.append("candidate was not written by this direct build")
            except (OSError, ValueError) as exc:
                errors.append(f'candidate capture failed: {exc}')
        else:
            errors.append("direct compiler/link candidate missing")
        diagnostics_info = ({'path': str(same_build_diagnostics), 'sha256': _sha256(same_build_diagnostics),
                             'resultCount': len(rows), 'acceptedCount': 0, 'diagnosticOnly': True,
                             'schema': 'agentdecompile.same-build-object-comparison/v1'}
                            if same_build_diagnostics.is_file() else None)
        if not same_build_diagnostics.is_file():
            errors.append("fresh same-build object diagnostics missing")
        elif same_build_diagnostics.stat().st_mtime_ns < started_ns:
            errors.append("same-build object diagnostics were not written by this direct build")
        elif not rows:
            errors.append('no same-build recovered-function object diagnostics')
        byte_identical = bool(candidate_info and target_info and
                              candidate_info["size"] == target_info["size"] and
                              candidate_info["sha256"] == target_info["sha256"])
        if not byte_identical:
            errors.append("direct compiler/link candidate whole file differs from shipped target")
        linked_rows = [row.get('nativeLinkSelectionEvidence', {}) for row in rows]
        mapped_linked_rows = [row for row in linked_rows if row.get('selectedObjectMapped') is True]
        byte_equal_linked_rows = [row for row in mapped_linked_rows
                                  if row.get('linkedContributionRawEqual') is True]
        linked_contribution = {
            "status": "partial-diagnostic" if mapped_linked_rows else "unavailable",
            "reason": "complete_linked_image_contribution_unavailable",
            "diagnosticOnly": True,
            "accepted": False,
            "selectedObjectMappedCount": len(mapped_linked_rows),
            "rawEqualFunctionCount": len(byte_equal_linked_rows),
            "rawDifferentFunctionCount": len(mapped_linked_rows) - len(byte_equal_linked_rows),
            "completeInventoryCovered": False,
            "linkedSourceContributionVerified": False,
            "missingBindings": [
                "source_inventory_capture",
                "effective_toolchain_identity",
                "complete_same_build_object_image_coverage",
                "linked_region_fixups",
                "final_compiled_replacement_ownership",
                "variant_binding",
            ],
        }
        errors.append(linked_contribution["reason"])
        verified = False
        receipt = {
            "schema": "agentdecompile.direct-compiler-full-image-diagnostic-receipt.v1",
            "startedNs": started_ns,
            "target": target_info,
            "candidate": candidate_info,
            "build": build,
            "sameBuildDiagnostics": diagnostics_info,
            "proofGates": {
                "functionObjdiff": {
                    "status": "not-run-by-this-route",
                    "reason": "same-build object diagnostics are custom byte comparisons, not objdiff output",
                },
                "wholeImageByteEquality": {
                    "status": "matched" if byte_identical else "mismatch",
                    "verified": byte_identical,
                },
                "completeLinkedContribution": {
                    "status": linked_contribution["status"],
                    "verified": False,
                },
            },
            "claimScope": "direct-build/local-function diagnostics and whole-file equality; not terminal recovery",
            "linkedContribution": linked_contribution,
            "compilerProducedWholeImage": False,
            "wholeFileByteIdentical": byte_identical,
            "verified": verified,
            "errors": errors,
        }
        out = work / "receipt.json"
        if owns_work:
            _verify_fresh_output_capability(output_capability)
            out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"verified": verified, "wholeFileByteIdentical": byte_identical,
                          "errors": errors, "out": str(out) if owns_work else None}, indent=2))
        return 0 if verified else 1

    except (OSError, ValueError) as exc:
        # A replaced output cannot safely receive even a negative receipt.
        # Retain the diagnostic on stdout and leave all trees untouched.
        errors.append(f"direct verification stopped: {exc.__class__.__name__}: {exc}")
        print(json.dumps({"verified": False, "wholeFileByteIdentical": False,
                          "errors": errors, "out": None}, indent=2))
        return 1
    finally:
        _close_fresh_output_capability(output_capability)


if __name__ == "__main__":
    raise SystemExit(main())

"""One admitted, bounded preserved-C experiment; never a recovery promotion.

The dashboard caller must own compiler, Wine prefix and output resources before
calling this function. Frozen proposal edges are independent of live KX writes.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import os
import pathlib
import re
import shutil
import sys
import time

from ..package_verify import prepare_msvc_invocation
from ..inventory import BinaryView, pe_file_offset, pe_inventory
from ..source_parity_probes import x86_32, pe_highlow_sites, reject_relocation_overlap
from ..targets import TargetIdentity, pe_machine
from . import mkobj, toolchain_identity
from .dashboard.kotorxid_binding import KotorXIDCandidateSource, read_frozen_candidate_bytes
from .seed_validation import CompilerBinding, DestinationArtifacts, Seed, compile_basis, compile_seed
from .source_claims import is_real_c


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _write_json(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write('\n')


def _read_identity(path):
    path = pathlib.Path(path)
    if not path.is_absolute():
        raise ValueError('consumed_path_not_absolute')
    resolved = path.resolve(strict=True)
    before = resolved.stat()
    if not resolved.is_file():
        raise ValueError('consumed_path_not_file')
    blob = resolved.read_bytes()
    after = resolved.stat()
    stamp = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if stamp(before) != stamp(after) or path.resolve(strict=True) != resolved:
        raise ValueError('consumed_file_changed_during_read')
    return blob, {'path': str(path), 'resolvedPath': str(resolved),
                  'sha256': _sha(blob), 'stat': list(stamp(after))}


def _pe_region(view, pe, relocation_sites, address, size):
    """Check the complete span and every PE loader fixup before cutting bytes."""
    if type(size) is not int or size <= 0 or type(address) is not int:
        raise ValueError('destination_span_invalid')
    rva = address - pe['imageBase']
    offset = pe_file_offset(view, pe['sections'], rva, size)
    section = next(s for s in pe['sections'] if s['virtualAddress'] <= rva
                   and rva + size <= s['virtualAddress'] + s['rawSize'])
    if not section['executable']:
        raise ValueError('destination_section_not_executable')
    reject_relocation_overlap(relocation_sites, rva, size)
    return offset, view.bytes(offset, size)


def run_candidate_wave(*, source: KotorXIDCandidateSource,
                       original_receipt_path: pathlib.Path, recipe: dict,
                       context_bytes: bytes, context_origin: str, cap: int,
                       output_directory: pathlib.Path, objdiff_check: pathlib.Path,
                       coff_functions, checker_environment: dict | None = None,
                       admission_identities: list | None = None) -> dict:
    """Run distinct candidates once, preserving failures and all proposal edges.

    Refusal before directory claim raises ValueError. Candidate exclusions and
    attempted failures are durable JSON receipts. No closure means no proof reuse.
    Context bytes (including b'') are an explicit caller-selected hypothesis.
    """
    started = time.monotonic()
    if not isinstance(source, KotorXIDCandidateSource) or type(cap) is not int or cap <= 0:
        raise ValueError('frozen_source_and_positive_cap_required')
    if not isinstance(context_bytes, bytes) or not isinstance(context_origin, str) or not context_origin.strip():
        raise ValueError('explicit_context_bytes_and_origin_required')
    context = context_bytes.decode('utf-8', errors='strict')
    context_sha256 = _sha(context_bytes)
    recipe = json.loads(_json_bytes(recipe))  # isolate the caller's mutable dictionary
    if (recipe.get('schema') != 'agentdecompile.provisional-compiler-recipe/v1'
            or recipe.get('recipeState') != 'provisional' or recipe.get('support') != 'unmeasured'
            or recipe.get('closureBound') is not False):
        raise ValueError('only_provisional_recipe_supported_measured_recipe_deferred')
    if recipe.get('programFingerprint') != source.selected_target_sha256:
        raise ValueError('recipe_target_sha256_mismatch')
    if type(recipe.get('timeout')) is not int or recipe['timeout'] <= 0:
        raise ValueError('recipe_timeout_must_be_positive_integer')
    # run_command has two five-second cleanup waits; leave five additional
    # seconds for wrapper setup/receipt persistence before the outer deadline.
    compiler_timeout = recipe['timeout'] + 10 + 5
    if not isinstance(recipe.get('architecture'), str) or not x86_32(recipe['architecture']):
        raise ValueError('recipe_architecture_not_i386')
    if not re.fullmatch('[0-9a-f]{64}', source.selected_target_sha256) or not re.fullmatch('[0-9a-f]{32}', source.selected_target_md5):
        raise ValueError('selected_target_hashes_invalid')
    consumed = list(admission_identities or [])
    checker_environment = dict(checker_environment or {})
    def consume(path):
        blob, identity = _read_identity(path)
        consumed.append(identity)
        return blob
    receipt = json.loads(consume(original_receipt_path))
    if (receipt.get('schema') != 'agentdecompile.original-target.v1'
            or receipt.get('state') != 'ready'
            or receipt.get('authority') != 'original-imported-executable'
            or receipt.get('program') != source.target_repo_path
            or receipt.get('analysisImageIsAuthority') is not False):
        raise ValueError('original_target_receipt_not_authoritative')
    for field in ('sourceSha256', 'targetSha256'):
        if receipt.get(field) != source.selected_target_sha256:
            raise ValueError('original_target_receipt_sha256_mismatch')
    if receipt.get('expectedSha256') not in (None, '', source.selected_target_sha256):
        raise ValueError('original_target_expected_sha256_mismatch')
    if receipt.get('expectedMd5') not in (None, '', source.selected_target_md5):
        raise ValueError('original_target_expected_md5_mismatch')
    raw = consume(receipt['targetPath'])
    origin = consume(receipt['sourcePath'])
    for blob in (raw, origin):
        if _sha(blob) != source.selected_target_sha256 or hashlib.md5(blob).hexdigest() != source.selected_target_md5:
            raise ValueError('original_target_current_hash_mismatch')
    analysis = receipt.get('analysisImagePath')
    if analysis and pathlib.Path(analysis).resolve() in (
            pathlib.Path(receipt['targetPath']).resolve(), pathlib.Path(receipt['sourcePath']).resolve()):
        raise ValueError('derived_analysis_image_rejected')
    # Confirm PE architecture even when every proposal is later excluded.
    if raw[:2] != b'MZ':
        raise ValueError('target_not_pe')
    if pe_machine(raw) != 'x86':
        raise ValueError('target_architecture_not_i386_pe32')
    target_path = pathlib.Path(receipt['targetPath'])
    view = BinaryView(target_path, raw)
    identity = TargetIdentity(pathlib.Path(receipt['sourcePath']), target_path,
        source.selected_target_sha256, len(raw), 'pe', 'x86', source.selected_target_sha256, raw)
    pe = pe_inventory(identity, view)
    if pe['machine'] != '0x014c' or pe['optionalHeaderMagic'] != '0x010b':
        raise ValueError('target_architecture_not_i386_pe32')
    relocation_sites = pe_highlow_sites(view, pe)
    wrapper = pathlib.Path(recipe['compilerScript'])
    consume(wrapper)
    if not os.access(wrapper, os.X_OK):
        raise ValueError('recipe_wrapper_not_executable')
    if json.loads(consume(wrapper.parent / 'provisional-compiler-recipe.json')) != recipe:
        raise ValueError('recipe_file_binding_mismatch')
    if (recipe.get('wrapperContext', {}).get('python') != str(pathlib.Path(sys.executable).resolve())
            or recipe.get('wrapperContext', {}).get('sourceRoot') != str(pathlib.Path(__file__).resolve().parents[2])):
        raise ValueError('recipe_wrapper_context_mismatch')
    consume(pathlib.Path(sys.executable).resolve())
    consume(objdiff_check)
    parser_path = inspect.getsourcefile(coff_functions) if callable(coff_functions) else None
    if not parser_path or not getattr(coff_functions, '__qualname__', None):
        raise ValueError('coff_parser_identity_unavailable')
    consume(pathlib.Path(parser_path).resolve())
    for module_path in (pathlib.Path(__file__), pathlib.Path(inspect.getsourcefile(compile_seed)),
                        pathlib.Path(inspect.getsourcefile(prepare_msvc_invocation)),
                        pathlib.Path(mkobj.__file__), pathlib.Path(toolchain_identity.__file__)):
        consume(module_path.resolve())
    for helper in (pe_inventory, x86_32, pe_machine):
        consume(pathlib.Path(inspect.getsourcefile(helper)).resolve())
    def check_binding():
        prepared = prepare_msvc_invocation(source=pathlib.Path('candidate.c'),
            args=recipe['compilerArgs'], msvc_root=pathlib.Path(recipe['compilerRoot']),
            wine=recipe['wine'], wineprefix=pathlib.Path(recipe['wineprefix']), strict_c=True)
        toolchain_identity.compare_live_binding(recipe['binding'], **{
            key: prepared[key] for key in ('command', 'env', 'requested_args', 'policy')})
        if prepared['effectiveArgs'] != recipe['effectiveArgs']:
            raise ValueError('recipe_effective_arguments_changed')
        return prepared
    check_binding()
    node = shutil.which('node', path=checker_environment.get('PATH', os.environ.get('PATH')))
    if not node:
        raise ValueError('objdiff_node_unavailable')
    consume(pathlib.Path(node).resolve())
    def recheck():
        for expected in consumed:
            _, current = _read_identity(expected['path'])
            if current != expected:
                raise ValueError('consumed_identity_changed: ' + expected['path'])
        check_binding()
    root = pathlib.Path(output_directory)
    if not root.is_absolute():
        raise ValueError('wave_output_directory_not_absolute')
    recheck()
    root.mkdir(exist_ok=False)
    evidence = {'schema': 'agentdecompile.candidate-wave/v1', 'targetRepo': source.target_repo_path,
                'targetSha256': source.selected_target_sha256, 'targetMd5': source.selected_target_md5,
                'consumedIdentities': consumed, 'recipe': recipe, 'recipeSha256': _sha(_json_bytes(recipe)),
                'context': {'origin': context_origin, 'sha256': context_sha256,
                            'hypothesis': True, 'bytes': len(context_bytes)},
                'coffParser': coff_functions.__qualname__, 'cap': cap,
                'checkerEnvironment': checker_environment,
                'resourceAdmission': 'caller-owned', 'reusableProof': False,
                'compilerTimeoutSeconds': compiler_timeout,
                'claimScope': 'fresh-per-function-experiment-only'}
    evidence['architecture'] = {'recipeHypothesis': recipe['architecture'],
                                'peMachine': pe['machine'], 'peMagic': pe['optionalHeaderMagic']}
    _write_json(root / 'wave-inputs.json', evidence)
    (root / 'context.h').write_bytes(context_bytes)
    exclusions = [dataclasses.asdict(item) for item in source.exclusions]
    groups = {}
    for proposal in source.candidates:
        edge = dataclasses.asdict(proposal)
        try:
            if not proposal.source_real_c or not proposal.reuse_real_c:
                raise ValueError('resolver_real_c_flags_required')
            payload = read_frozen_candidate_bytes(proposal, allowed_source_root=source.allowed_source_root).decode('utf-8', errors='strict')
            if not is_real_c(payload):
                raise ValueError('source_not_real_c')
            row = json.loads(proposal.preserved_row_json or 'null')
            coverage = row.get('coverage') if isinstance(row, dict) else None
            symbol = coverage.get('symbol') if isinstance(coverage, dict) else None
            match = re.fullmatch(r'(?:_([A-Za-z_][A-Za-z0-9_]*)(?:@[0-9]+)?|@([A-Za-z_][A-Za-z0-9_]*)@[0-9]+)', symbol or '')
            if not match:
                raise ValueError('preserved_coverage_symbol_missing_or_ambiguous')
            defined = match.group(1) or match.group(2)
            if proposal.target_size != proposal.reuse_size:
                raise ValueError('destination_size_proposal_mismatch')
            size = proposal.target_size
            offset, target = _pe_region(view, pe, relocation_sites, proposal.target_address, size)
            mkobj.find_call_targets(target, mkobj.MACHINE['coff-i386'], reference_free_only=True)
            key = _sha(_json_bytes([source.selected_target_sha256, proposal.target_address, size,
                                    proposal.source_file_sha256, symbol, context_sha256, evidence['recipeSha256']]))
            if key in groups:
                groups[key]['edges'].append(edge)
                groups[key]['proposals'].append(proposal)
            else:
                groups[key] = dict(proposal=proposal, payload=payload, symbol=symbol, defined=defined,
                                   size=size, offset=offset, target=target, edges=[edge], proposals=[proposal])
        except (ValueError, TypeError, OSError) as exc:
            exclusions.append({'edge': edge, 'reason': str(exc)})
    attempts = []
    fatal = None
    for key, item in groups.items():
        if len(attempts) >= cap or fatal:
            exclusions.append({'edges': item['edges'], 'reason': 'wave_stopped: ' + fatal if fatal else 'distinct_attempt_cap_reached'})
            continue
        attempt = root / ('attempt-%04d-%s' % (len(attempts) + 1, key[:12]))
        attempt.mkdir(exist_ok=False)
        result = {'key': key, 'edges': item['edges'], 'emittedSymbol': item['symbol'],
                  'destinationAddress': item['proposal'].target_address,
                  'reusableProof': False, 'state': 'attempted', 'identitiesUnchanged': False}
        attempts.append(result)
        attempt_started = time.monotonic()
        try:
            recheck()
            proposal = item['proposal']
            for bound in item['proposals']:
                read_frozen_candidate_bytes(bound, allowed_source_root=source.allowed_source_root)
            # Unchanged full donor source, separate from the actual context+source translation unit.
            (attempt / 'candidate.c').write_bytes(item['payload'].encode('utf-8'))
            reference = mkobj.build_object(item['target'], item['symbol'], mkobj.MACHINE['coff-i386'], {})
            object_path, spec_path = attempt / 'target.o', attempt / 'target.json'
            object_path.write_bytes(reference)
            spec = {'relocations': [], 'symbol': item['symbol'], 'referencePolicy': 'reference-free-only',
                    'address': proposal.target_address, 'offset': item['offset'], 'size': item['size'],
                    'regionSha256': _sha(item['target'])}
            _write_json(spec_path, spec)
            artifacts = DestinationArtifacts(source.target_repo_path, f'{proposal.target_address:x}',
                item['size'], source.selected_target_sha256, _sha(item['target']),
                object_path, _sha(reference), spec_path, _sha(spec_path.read_bytes()), 'reference-free-only')
            original_hex = (json.loads(proposal.preserved_row_json)['coverage']).get('originalBytes')
            historical = bytes.fromhex(original_hex) if isinstance(original_hex, str) and re.fullmatch(r'(?:[0-9a-fA-F]{2})*', original_hex) else b''
            seed = Seed(proposal.source_path, source.target_repo_path, f'{proposal.target_address:x}',
                        proposal.target_name or '', item['size'], historical, item['defined'], item['payload'], proposal.source_evidence)
            binding = CompilerBinding(wrapper, environment_overrides=checker_environment,
                                      argument_protocol='source-output')
            basis, frozen_preamble, environment = compile_basis(seed, binding, root,
                objdiff_check=objdiff_check, coff_functions=coff_functions,
                destination_artifacts=artifacts, frozen_preamble=context)
            result['compileBasis'] = basis
            # Parent environment is the exact environment fingerprinted above;
            # the bound wrapper independently constructs its compiler allowlist.
            recheck()
            try:
                compiled_result = compile_seed(source.target_slug, seed, item['target'], compiler=binding,
                    evidence_root=root, objdiff_check=objdiff_check, coff_functions=coff_functions,
                    frozen_preamble=frozen_preamble, frozen_environment=environment,
                    destination_artifacts=artifacts, artifact_directory=attempt / 'compile',
                    compiler_timeout=compiler_timeout)
            except Exception as exc:
                # Even a late diagnostics/execution.json failure may conceal a
                # timeout. Do not admit another compiler onto this prefix.
                fatal = 'resource_clearance_required: uncertain_compile_call_exception'
                result.update(compile_status='compile_call_exception', compile_detail=str(exc),
                              resourceClearanceRequired=True,
                              execution={'resourceClearanceRequired': True,
                                         'resourceClearanceReason': 'uncertain_compile_call_exception',
                                         'artifactDirectory': str(attempt / 'compile')})
            else:
                result.update(compiled_result)
            if result.get('execution', {}).get('resourceClearanceRequired'):
                fatal = 'resource_clearance_required: ' + result['execution']['resourceClearanceReason']
                result['resourceClearanceRequired'] = True
            recheck()
            for bound in item['proposals']:
                read_frozen_candidate_bytes(bound, allowed_source_root=source.allowed_source_root)
            result['identitiesUnchanged'] = True
            result['state'] = ('exact' if result.get('compile_status') == 'byte_exact'
                               and result.get('objdiff_verified') is True
                               and result.get('object_symbol') == item['symbol'] else 'failed')
            if result.get('object_symbol') and result['object_symbol'] != item['symbol']:
                result['reason'] = 'compiled_symbol_disagrees_with_preserved_coverage'
        except (ValueError, TypeError, OSError, LookupError) as exc:
            result.update(state='failed', reason=str(exc))
            try:
                recheck()
            except (ValueError, TypeError, OSError) as changed:
                if fatal is None:
                    fatal = str(changed)
        finally:
            result['elapsedSeconds'] = time.monotonic() - attempt_started
            _write_json(attempt / 'receipt.json', result)
    exact_addresses = sorted({a['destinationAddress'] for a in attempts if a['state'] == 'exact'})
    summary = {'schema': evidence['schema'], 'selected': len(source.candidates),
               'selectedUnit': 'proposal-edges', 'attemptedUnit': 'distinct-candidate-attempts',
               'distinctSelected': len(groups), 'attempted': len(attempts),
               'compiled': sum(a.get('execution', {}).get('compilerSucceeded') is True for a in attempts),
               'exact': len(exact_addresses), 'exactUnit': 'unique-destination-functions',
               'exactAttempts': sum(a['state'] == 'exact' for a in attempts),
               'exactFunctionAddresses': exact_addresses, 'excluded': len(exclusions),
               'excludedProposalEdges': sum(len(e.get('edges', [])) if 'edges' in e else 1 for e in exclusions),
               'exclusions': exclusions, 'attempts': attempts, 'elapsedSeconds': time.monotonic() - started,
               'reusableProof': False, 'claimScope': evidence['claimScope'], 'stopReason': fatal,
               'resourceClearanceRequired': bool(fatal and fatal.startswith('resource_clearance_required'))}
    _write_json(root / 'summary.json', summary)
    return summary


_CATALOG_PATHS = ('db', 'allowed-source-root', 'preserved-selection-manifest',
    'materialized-binaries-root', 'target-receipt', 'context-path', 'compiler-root',
    'wineprefix', 'wine', 'objdiff-check', 'objdiff-wasm-root', 'out-dir')
_CATALOG_STRINGS = ('target-repo-path', 'target-sha256', 'target-md5',
                    'context-origin', 'architecture')
_ADMISSION_SCHEMA = 'agentdecompile.candidate-wave-admission/v1'


def validate_frozen_catalog_parameters(params: dict) -> None:
    """Validate historical completeness without refreshing any file or DB."""
    if params.get('argv') not in (None, '', []):
        raise ValueError('candidate_wave_argv_override_refused')
    if params.get('_candidate-wave-contract') != _ADMISSION_SCHEMA:
        raise ValueError('candidate_wave_contract_missing')
    for key in (*_CATALOG_PATHS, '_candidate-wave-execution-root'):
        value = params.get(key)
        if (not isinstance(value, str) or not value or not pathlib.Path(value).is_absolute()
                or str(pathlib.Path(value).resolve()) != value):
            raise ValueError('candidate_wave_frozen_path_required: ' + key)
    for key in _CATALOG_STRINGS:
        if not isinstance(params.get(key), str) or not params[key].strip():
            raise ValueError('candidate_wave_explicit_input_required: ' + key)
    for key in ('cap', 'timeout'):
        if type(params.get(key)) is not int or params[key] < 1:
            raise ValueError('candidate_wave_positive_integer_required: ' + key)
    flags = params.get('compiler-arg')
    if not isinstance(flags, list) or not flags or any(not isinstance(flag, str) or not flag or '\x00' in flag for flag in flags):
        raise ValueError('candidate_wave_explicit_compiler_flags_required')
    if not re.fullmatch('[0-9a-f]{64}', params['target-sha256']) or not re.fullmatch('[0-9a-f]{32}', params['target-md5']):
        raise ValueError('candidate_wave_selected_hashes_invalid')
    if not x86_32(params['architecture']):
        raise ValueError('candidate_wave_only_i386_supported')
    envelope = json.loads(params.get('admission-json') or 'null')
    policy = {key: params[key] for key in (*_CATALOG_PATHS, *_CATALOG_STRINGS, 'compiler-arg', 'cap', 'timeout')}
    if (not isinstance(envelope, dict) or envelope.get('schema') != _ADMISSION_SCHEMA
            or envelope.get('policy') != policy
            or envelope.get('executionRoot') != params['_candidate-wave-execution-root']
            or envelope.get('prefixIdentity') != params.get('_candidate-wave-prefix-identity')
            or not isinstance(envelope.get('inputs'), list) or not envelope['inputs']
            or not isinstance(envelope.get('invocation'), dict)
            or not isinstance(envelope.get('binding'), dict)
            or not isinstance(envelope.get('checkerEnvironment'), dict)
            or not isinstance(envelope.get('databaseIdentity'), dict)
            or not isinstance(envelope.get('directoryIdentities'), list) or not envelope['directoryIdentities']
            or not isinstance(envelope.get('sourceRoot'), str) or not pathlib.Path(envelope['sourceRoot']).is_absolute()
            or not isinstance(envelope.get('python'), str) or not pathlib.Path(envelope['python']).is_absolute()
            or not isinstance(envelope.get('node'), str) or not pathlib.Path(envelope['node']).is_absolute()
            or not isinstance(envelope.get('effectiveArgs'), list)
            or not isinstance(envelope.get('targetInputs'), dict)
            or set(envelope['targetInputs']) != {'sourcePath', 'targetPath'}
            or envelope.get('recipeState') != 'provisional' or envelope.get('support') != 'unmeasured'
            or envelope.get('closureBound') is not False):
        raise ValueError('candidate_wave_frozen_envelope_incomplete_or_changed')
    for identity in [envelope['databaseIdentity'], *envelope['directoryIdentities']]:
        if (not isinstance(identity, dict) or set(identity) != {'path', 'resolvedPath', 'uid', 'dev', 'ino'}
                or any(not isinstance(identity[key], str) or not pathlib.Path(identity[key]).is_absolute()
                       for key in ('path', 'resolvedPath'))
                or any(type(identity[key]) is not int for key in ('uid', 'dev', 'ino'))):
            raise ValueError('candidate_wave_frozen_path_identity_invalid')
    if (envelope['databaseIdentity']['path'] != params['db']
            or envelope['invocation'].get('command', [])[:2] != [params['wine'], str(pathlib.Path(params['compiler-root']) / 'bin' / 'cl.exe')]
            or envelope['invocation'].get('requested_args') != params['compiler-arg']
            or envelope['binding'].get('schema') != 'agentdecompile.provisional-msvc-invocation-binding/v1'
            or envelope['binding'].get('command') != envelope['invocation'].get('command')
            or envelope['checkerEnvironment'].get('AGENT_DECOMPILE_OBJDIFF_WASM_ROOT') != params['objdiff-wasm-root']):
        raise ValueError('candidate_wave_frozen_execution_binding_invalid')
    expected_directories = {params[key] for key in
        ('allowed-source-root', 'materialized-binaries-root', 'compiler-root', 'wineprefix', 'objdiff-wasm-root')}
    expected_directories.add(str(pathlib.Path(params['out-dir']).parent))
    if {identity['path'] for identity in envelope['directoryIdentities']} != expected_directories:
        raise ValueError('candidate_wave_required_directory_identity_missing')
    checker_env = envelope['checkerEnvironment']
    if (set(checker_env) != {'AGENT_DECOMPILE_OBJDIFF_WASM_ROOT', 'MIZUCHI_ROOT', 'NODE_OPTIONS', 'NODE_PATH', 'PATH'}
            or any(not isinstance(value, str) for value in checker_env.values())
            or any(checker_env[key] != '' for key in ('MIZUCHI_ROOT', 'NODE_OPTIONS', 'NODE_PATH'))
            or checker_env['PATH'] != envelope['invocation'].get('env', {}).get('PATH')):
        raise ValueError('candidate_wave_checker_environment_changed')
    expected_paths = {params[key] for key in ('target-receipt', 'context-path', 'preserved-selection-manifest', 'objdiff-check', 'wine')}
    expected_paths.update((envelope['python'], envelope['node'],
        str(pathlib.Path(params['compiler-root']) / 'bin' / 'cl.exe'),
        str(pathlib.Path(envelope['sourceRoot']) / 'agentdecompile_recovery' / 'corpus' / 'candidate_wave.py')))
    if any(not isinstance(path, str) or not pathlib.Path(path).is_absolute() for path in envelope['targetInputs'].values()):
        raise ValueError('candidate_wave_frozen_target_paths_invalid')
    expected_paths.update(envelope['targetInputs'].values())
    expected_paths.update(str(pathlib.Path(params['objdiff-wasm-root']) / 'node_modules' / 'objdiff-wasm' / relative)
                          for relative in ('package.json', 'dist/objdiff.js', 'dist/objdiff.core.wasm'))
    actual_paths = set()
    for identity in envelope['inputs']:
        if (not isinstance(identity, dict) or set(identity) != {'path', 'resolvedPath', 'sha256', 'stat'}
                or not isinstance(identity['path'], str) or not pathlib.Path(identity['path']).is_absolute()
                or not isinstance(identity['resolvedPath'], str) or not pathlib.Path(identity['resolvedPath']).is_absolute()
                or not isinstance(identity['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', identity['sha256'])
                or not isinstance(identity['stat'], list) or len(identity['stat']) != 5
                or any(type(value) is not int for value in identity['stat'])):
            raise ValueError('candidate_wave_frozen_file_identity_invalid')
        actual_paths.add(identity['path'])
    if not expected_paths <= actual_paths:
        raise ValueError('candidate_wave_required_file_identity_missing')
    output = pathlib.Path(params['out-dir'])
    for path in [*(params[key] for key in _CATALOG_PATHS if key != 'out-dir'),
                 *(identity['path'] for identity in envelope['inputs']),
                 *(identity['resolvedPath'] for identity in envelope['inputs'])]:
        if pathlib.Path(path) == output or output in pathlib.Path(path).parents:
            raise ValueError('candidate_wave_input_inside_owned_output: ' + path)
    for key in ('compiler-root', 'wineprefix'):
        path = pathlib.Path(params[key])
        if path in output.parents:
            raise ValueError('candidate_wave_output_inside_execution_resource: ' + key)


def catalog_resource_claims(params: dict) -> tuple:
    validate_frozen_catalog_parameters(params)
    return tuple(sorted((('output', params['out-dir']), ('compiler', params['compiler-root']),
                         ('wineprefix', params['wineprefix']))))


def _proposal_database_identity(path):
    """Pin the selected DB file, never its refreshable contents or sidecars."""
    path = pathlib.Path(path)
    resolved = path.resolve(strict=True)
    info = resolved.stat()
    if not resolved.is_file():
        raise ValueError('candidate_wave_database_not_file')
    return {'path': str(path), 'resolvedPath': str(resolved),
            'uid': info.st_uid, 'dev': info.st_dev, 'ino': info.st_ino}


def _recheck_catalog_inputs(params, *, require_new_output=True):
    from .wineprefix_clearance import prefix_identity
    validate_frozen_catalog_parameters(params)
    envelope = json.loads(params['admission-json'])
    if prefix_identity(params['wineprefix']) != envelope['prefixIdentity']:
        raise ValueError('candidate_wave_prefix_identity_changed')
    if _proposal_database_identity(params['db']) != envelope['databaseIdentity']:
        raise ValueError('candidate_wave_proposal_database_replaced')
    for identity in envelope['inputs']:
        if _read_identity(identity['path'])[1] != identity:
            raise ValueError('candidate_wave_admitted_input_changed: ' + identity['path'])
    prepared = prepare_msvc_invocation(source=pathlib.Path('candidate.c'),
        args=params['compiler-arg'], msvc_root=pathlib.Path(params['compiler-root']),
        wine=params['wine'], wineprefix=pathlib.Path(params['wineprefix']), strict_c=True)
    invocation = {key: prepared[key] for key in ('command', 'env', 'requested_args', 'policy')}
    if invocation != envelope['invocation']:
        raise ValueError('candidate_wave_admitted_invocation_changed')
    toolchain_identity.compare_live_binding(envelope['binding'], **invocation)
    node = shutil.which('node', path=envelope['checkerEnvironment']['PATH'])
    if node is None or str(pathlib.Path(node).resolve()) != envelope['node']:
        raise ValueError('candidate_wave_objdiff_node_resolution_changed')
    for identity in envelope['directoryIdentities']:
        if _directory_identity(identity['path']) != identity:
            raise ValueError('candidate_wave_input_directory_replaced: ' + identity['path'])
    if require_new_output and (pathlib.Path(params['out-dir']).exists() or pathlib.Path(params['out-dir']).is_symlink()):
        raise ValueError('candidate_wave_output_must_be_new')
    return envelope


def _directory_identity(path):
    if not pathlib.Path(path).is_dir():
        raise ValueError('candidate_wave_directory_required: ' + str(path))
    info = pathlib.Path(path).stat()
    return {'path': str(path), 'resolvedPath': str(pathlib.Path(path).resolve(strict=True)),
            'uid': info.st_uid, 'dev': info.st_dev, 'ino': info.st_ino}


def catalog_child_environment(params):
    """Keep the frozen compiler environment independent of objdiff PATH isolation."""
    from .toolchain_identity import MEASURED_MSVC_ENV_KEYS
    validate_frozen_catalog_parameters(params)
    envelope = json.loads(params['admission-json'])
    environment = dict(os.environ)
    for key in MEASURED_MSVC_ENV_KEYS:
        environment.pop(key, None)
        if key in envelope['invocation']['env']:
            environment[key] = envelope['invocation']['env'][key]
    environment.update(envelope['checkerEnvironment'])
    environment['PYTHONPATH'] = envelope['sourceRoot']
    environment.pop('PYTHONHOME', None)
    return environment


def freeze_catalog_parameters(params: dict, execution_root: pathlib.Path) -> dict:
    """Read-only plan: no output, recipe, wrapper, DB write or process launch."""
    from .wineprefix_clearance import prefix_identity
    from .exact_corpus import coff_functions
    from .. import cli, inventory, package_verify, source_parity_probes, targets
    from . import seed_validation, source_claims, compiler_action_contract, wineprefix_clearance
    from .dashboard import kotorxid_binding
    root = pathlib.Path(execution_root)
    if not root.is_absolute():
        raise ValueError('candidate_wave_absolute_execution_root_required')
    root = root.resolve()
    if params.get('_candidate-wave-contract') is not None:
        if params.get('_candidate-wave-execution-root') != str(root):
            raise ValueError('candidate_wave_execution_root_changed')
        _recheck_catalog_inputs(params)
        return dict(params)
    if params.get('admission-json'):
        raise ValueError('candidate_wave_admission_is_dashboard_owned')
    frozen = dict(params)
    for key in _CATALOG_PATHS:
        value = frozen.get(key)
        if not isinstance(value, (str, pathlib.Path)) or not str(value).strip():
            raise ValueError('candidate_wave_explicit_path_required: ' + key)
        path = pathlib.Path(value).expanduser()
        path = path if path.is_absolute() else root / path
        frozen[key] = str(path.resolve(strict=key != 'out-dir'))
    flags = frozen.get('compiler-arg')
    if not isinstance(flags, list) or not flags or any(not isinstance(flag, str) or not flag or '\x00' in flag for flag in flags):
        raise ValueError('candidate_wave_explicit_compiler_flags_required')
    for key in ('cap', 'timeout'):
        value = frozen.get(key)
        if isinstance(value, bool):
            raise ValueError('candidate_wave_positive_integer_required: ' + key)
        frozen[key] = int(value)
        if str(frozen[key]) != str(value):
            raise ValueError('candidate_wave_integer_required: ' + key)
    inputs = []
    def consume(path):
        blob, identity = _read_identity(pathlib.Path(path))
        inputs.append(identity)
        return blob
    receipt = json.loads(consume(frozen['target-receipt']))
    if (receipt.get('schema') != 'agentdecompile.original-target.v1'
            or receipt.get('state') != 'ready' or receipt.get('authority') != 'original-imported-executable'
            or receipt.get('program') != frozen.get('target-repo-path')
            or receipt.get('analysisImageIsAuthority') is not False):
        raise ValueError('candidate_wave_original_target_authority_required')
    for key in ('sourceSha256', 'targetSha256'):
        if receipt.get(key) != frozen.get('target-sha256'):
            raise ValueError('candidate_wave_original_target_sha256_mismatch')
    for key in ('targetPath', 'sourcePath'):
        blob = consume(receipt[key])
        if _sha(blob) != frozen.get('target-sha256') or hashlib.md5(blob).hexdigest() != frozen.get('target-md5'):
            raise ValueError('candidate_wave_original_target_current_hash_mismatch')
    consume(frozen['context-path']).decode('utf-8', errors='strict')
    consume(frozen['preserved-selection-manifest'])
    consume(frozen['objdiff-check'])
    prepared = prepare_msvc_invocation(source=pathlib.Path('candidate.c'), args=frozen.get('compiler-arg'),
        msvc_root=pathlib.Path(frozen['compiler-root']), wine=frozen['wine'],
        wineprefix=pathlib.Path(frozen['wineprefix']), strict_c=True)
    invocation = {key: prepared[key] for key in ('command', 'env', 'requested_args', 'policy')}
    binding = toolchain_identity.bind_invocation(toolchain_identity.inspect_only(command=prepared['command']),
        allow_provisional=True, **invocation)
    for path in prepared['command'][:2]:
        consume(path)
    # Freeze the actual parser/implementation and Python and Node executables,
    # not a guessed installed checkout or historical wrapper.
    for module in (sys.modules[__name__], cli, inventory, package_verify, source_parity_probes, targets,
                   seed_validation, source_claims, mkobj, toolchain_identity, compiler_action_contract,
                   wineprefix_clearance, kotorxid_binding):
        consume(pathlib.Path(module.__file__).resolve())
    for relative in ('dashboard/actions/jobs.py', 'dashboard/actions/catalog.py', 'dashboard/actions/introspect.py',
                     'propagate_conventions.py', 'supervision.py'):
        consume(pathlib.Path(__file__).parent / relative)
    consume(pathlib.Path(inspect.getsourcefile(coff_functions)).resolve())
    consume(pathlib.Path(sys.executable).resolve())
    node = shutil.which('node', path=prepared['env']['PATH'])
    if not node:
        raise ValueError('candidate_wave_objdiff_node_unavailable')
    consume(pathlib.Path(node).resolve())
    wasm_package = pathlib.Path(frozen['objdiff-wasm-root']) / 'node_modules' / 'objdiff-wasm'
    for relative in ('package.json', 'dist/objdiff.js', 'dist/objdiff.core.wasm'):
        if not (wasm_package / relative).is_file():
            raise ValueError('candidate_wave_objdiff_asset_unavailable: ' + relative)
    for path in sorted(wasm_package.rglob('*')):
        if path.is_file():
            consume(path)
    frozen['_candidate-wave-contract'] = _ADMISSION_SCHEMA
    frozen['_candidate-wave-execution-root'] = str(root)
    frozen['_candidate-wave-prefix-identity'] = prefix_identity(frozen['wineprefix'])
    envelope = {'schema': _ADMISSION_SCHEMA, 'executionRoot': str(root),
        'policy': {key: frozen[key] for key in (*_CATALOG_PATHS, *_CATALOG_STRINGS, 'compiler-arg', 'cap', 'timeout')},
        'prefixIdentity': frozen['_candidate-wave-prefix-identity'], 'inputs': inputs,
        'databaseIdentity': _proposal_database_identity(frozen['db']),
        'directoryIdentities': [_directory_identity(frozen[key]) for key in
            ('allowed-source-root', 'materialized-binaries-root', 'compiler-root', 'wineprefix', 'objdiff-wasm-root')]
            + [_directory_identity(pathlib.Path(frozen['out-dir']).parent)],
        'sourceRoot': str(pathlib.Path(__file__).resolve().parents[2]),
        'python': str(pathlib.Path(sys.executable).resolve()), 'node': str(pathlib.Path(node).resolve()),
        'targetInputs': {key: receipt[key] for key in ('sourcePath', 'targetPath')},
        'invocation': invocation, 'binding': binding, 'effectiveArgs': prepared['effectiveArgs'],
        'checkerEnvironment': {'AGENT_DECOMPILE_OBJDIFF_WASM_ROOT': frozen['objdiff-wasm-root'],
            'MIZUCHI_ROOT': '', 'NODE_OPTIONS': '', 'NODE_PATH': '', 'PATH': prepared['env']['PATH']},
        'recipeState': 'provisional', 'support': 'unmeasured', 'closureBound': False}
    frozen['admission-json'] = _json_bytes(envelope).decode('utf-8')
    _recheck_catalog_inputs(frozen)
    return frozen


def run_catalog_candidate_wave(params: dict) -> dict:
    """Admitted child: snapshot proposals once, then create exclusive artifacts."""
    from ..package_verify import create_provisional_msvc_recipe
    from .dashboard.kotorxid_binding import resolve_kotorxid_candidates
    from .exact_corpus import coff_functions
    from .wineprefix_clearance import prefix_identity
    envelope = json.loads(params.get('admission-json') or 'null')
    if not isinstance(envelope, dict) or envelope.get('schema') != _ADMISSION_SCHEMA:
        raise ValueError('candidate_wave_requires_dashboard_admission')
    # Internal fields travel in the frozen envelope, never filled from child defaults.
    frozen = {key: str(value) if isinstance(value, pathlib.Path) else value for key, value in params.items()}
    frozen['_candidate-wave-contract'] = envelope['schema']
    frozen['_candidate-wave-execution-root'] = envelope['executionRoot']
    frozen['_candidate-wave-prefix-identity'] = envelope['prefixIdentity']
    if (envelope.get('sourceRoot') != str(pathlib.Path(__file__).resolve().parents[2])
            or envelope.get('python') != str(pathlib.Path(sys.executable).resolve())):
        raise ValueError('candidate_wave_child_source_root_changed')
    _recheck_catalog_inputs(frozen)
    source = resolve_kotorxid_candidates(frozen['db'], target_repo_path=frozen['target-repo-path'],
        selected_target_sha256=frozen['target-sha256'], selected_target_md5=frozen['target-md5'],
        allowed_source_root=frozen['allowed-source-root'],
        preserved_selection_manifest=frozen['preserved-selection-manifest'],
        materialized_binaries_root=frozen['materialized-binaries-root'])
    _recheck_catalog_inputs(frozen)
    root = pathlib.Path(frozen['out-dir'])
    root.mkdir(exist_ok=False)
    _write_json(root / 'admission.json', envelope)
    _write_json(root / 'proposal-snapshot.json', dataclasses.asdict(source))
    wave_started = False
    try:
        recipe_root = root / 'recipe'
        recipe_root.mkdir(exist_ok=False)
        # Separate exclusive recipe and wave trees keep run_candidate_wave's new
        # directory contract intact. No artifact is created before child admission.
        recipe = create_provisional_msvc_recipe(compiler_root=pathlib.Path(frozen['compiler-root']),
            wine=frozen['wine'], wineprefix=pathlib.Path(frozen['wineprefix']),
            args=frozen['compiler-arg'], timeout=frozen['timeout'],
            program_fingerprint=frozen['target-sha256'], architecture=frozen['architecture'], out_dir=recipe_root)
        expected = {'programFingerprint': frozen['target-sha256'], 'architecture': frozen['architecture'],
            'compilerRoot': frozen['compiler-root'], 'wine': frozen['wine'], 'wineprefix': frozen['wineprefix'],
            'compilerArgs': frozen['compiler-arg'], 'timeout': frozen['timeout'], 'binding': envelope['binding'],
            'effectiveArgs': envelope['effectiveArgs'], 'recipeState': 'provisional', 'support': 'unmeasured',
            'closureBound': False, 'compilerScript': str(recipe_root / 'provisional-compiler-compile.sh'),
            'wrapperContext': {'python': str(pathlib.Path(sys.executable).resolve()),
                               'sourceRoot': str(pathlib.Path(__file__).resolve().parents[2])}}
        if any(recipe.get(key) != value for key, value in expected.items()):
            raise ValueError('candidate_wave_generated_recipe_disagrees_with_admission')
        _recheck_catalog_inputs(frozen, require_new_output=False)
        if prefix_identity(frozen['wineprefix']) != envelope['prefixIdentity']:
            raise ValueError('candidate_wave_prefix_changed_before_wave')
        wave_started = True
        summary = run_candidate_wave(source=source, original_receipt_path=pathlib.Path(frozen['target-receipt']),
            recipe=recipe, context_bytes=_read_identity(frozen['context-path'])[0],
            context_origin=frozen['context-origin'], cap=frozen['cap'], output_directory=root / 'wave',
            objdiff_check=pathlib.Path(frozen['objdiff-check']), coff_functions=coff_functions,
            checker_environment=envelope['checkerEnvironment'], admission_identities=envelope['inputs'])
        summary['outputDirectory'] = str(root)
        _write_json(root / 'summary.json', summary)
        return summary
    except Exception as exc:
        failure = {'schema': _ADMISSION_SCHEMA, 'state': 'failed', 'stopReason': str(exc),
            'selected': len(source.candidates), 'attempted': None, 'compiled': None, 'exact': None,
            'outputDirectory': str(root), 'reusableProof': False,
            'claimScope': 'fresh-per-function-experiment-only',
            'resourceClearanceRequired': wave_started, 'ownershipUnresolved': wave_started,
            'reason': 'inspect retained wave receipts; outer executor must establish session and prefix clearance'}
        _write_json(root / 'failure.json', failure)
        return failure

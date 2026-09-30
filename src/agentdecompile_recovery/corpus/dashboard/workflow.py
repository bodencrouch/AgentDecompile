"""Missing-only recovery continuation for the shared preparation coordinator.

All execution uses catalog jobs. An action returning zero is not a proof gate;
receipts and target prerequisites decide the visible result of each stage.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

STAGES = [
    ('calibrate-global', 'Check compiler and layout'),
    ('materialize-target', 'Materialize original byte target'),
    ('assembly-floor', 'Create source project'),
    ('recover-source', 'Compiling C replacement'),
    ('apply-cross-build', 'Place compiling C in equivalent builds'),
    ('leftover-recover', 'Targeted recovery'),
    ('verify-byte-accuracy', 'Byte audit'),
]
DEFAULT_BUDGET_SECONDS = None
MAX_BUDGET_SECONDS = 7 * 24 * 60 * 60
VERSION = 4


def read_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def transient_failure(result: dict[str, Any]) -> bool:
    """Retry only failures with evidence that another attempt can help.

    Timeouts are deliberately excluded: an MCP request can time out while its
    native mutation continues, and repeating it could duplicate accepted work.
    """
    text = str(result.get('error') or result.get('log') or '').lower()
    deterministic = ('invalid', 'unsupported', 'permission denied', 'not found', 'unknown tool', 'syntaxerror', 'timeout', 'timed out')
    return not any(word in text for word in deterministic) and any(word in text for word in (
        'connection refused', 'temporarily unavailable', 'database is locked', 'resource busy',
        'unable to lock due to active transaction', 'http 503', 'http 429',
    ))


_EXTERNAL_DENIAL = (
    'entitlement', 'not entitled', 'billing', 'payment required', 'http 402', 'quota exceeded',
    'spending limit', 'account suspended', 'runner disabled', 'actions are disabled',
    'insufficient permissions to run', 'subscription required',
)


def external_action_required(result: dict[str, Any]) -> bool:
    """A refusal before any work started that only an outside action can clear (FP-27).

    Entitlement, billing, quota or a disabled runner is not a compile or behaviour failure,
    earns no retry of its own and must never be promoted to a local result.
    """
    text = str(result.get('error') or result.get('log') or '').lower()
    return bool(result.get('externalActionRequired')) or any(word in text for word in _EXTERNAL_DENIAL)


def _compiler(profile: dict[str, Any]) -> str | None:
    value = profile.get('compilerScript')
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    return str(path) if path.is_file() else shutil.which(value)


def _known_source_examples(work: Path, root: Path, slug: str) -> Path | None:
    """Find only a pre-existing, verified candidate/target probe corpus."""
    candidates = (
        work / 'matched-examples.jsonl',
        work / 'source-parity-index' / 'default' / 'matched-examples.jsonl',
        root / 'source-parity-index' / slug / 'matched-examples.jsonl',
        root / 'source-parity-index' / 'default' / 'matched-examples.jsonl',
        root / 'output' / 'source-parity-index' / slug / 'matched-examples.jsonl',
        root / 'output' / 'source-parity-index' / 'default' / 'matched-examples.jsonl',
    )
    return next((path for path in candidates if path.is_file()), None)


def _leftover_queue(work: Path, root: Path) -> Path | None:
    for candidate in (work / 'logical_queue.jsonl', root / 'output' / 'work_queue' / 'logical_queue.jsonl'):
        if candidate.is_file():
            return candidate
    return None


def _knowledge_has_program(path: Path, program: str) -> bool:
    if not path.is_file():
        return False
    try:
        with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as con:
            return bool(con.execute('SELECT 1 FROM func_knowledge WHERE program=? LIMIT 1', (program,)).fetchone())
    except (sqlite3.Error, ValueError):
        return False


def _extract_advisory_witnesses(
    *,
    row: dict[str, Any],
    checkpoint: dict[str, Any],
    work: Path,
    program: str,
    context: dict[str, Any],
    action: Callable[..., dict[str, Any]],
    update: Callable[..., None],
) -> tuple[Path, bool, str | None]:
    """Fill the fingerprint-bound Ghidra C cache before compiler admission.

    Ghidra output is useful evidence and must be acquired from the analyzed
    program even when no measured compiler profile exists yet.  Compilation,
    propagation, and byte proof remain downstream of profile admission.
    """
    fingerprint = str(checkpoint.get('programFingerprint') or 'unknown')
    program_kb = work / ('knowledge-' + fingerprint + '.sqlite')
    progress_path = work / 'decompilation-progress.json'
    if (checkpoint.get('knowledgeFingerprint') != fingerprint or
            checkpoint.get('knowledgeDb') != str(program_kb) or not program_kb.is_file()):
        for key in ('knowledgeCursor', 'knowledgeComplete', 'knowledgeAvailable'):
            checkpoint.pop(key, None)
    cursor = str(checkpoint.get('knowledgeCursor') or '')
    failure: str | None = None
    row['functionProgressFile'] = str(progress_path)
    try:
        while not checkpoint.get('knowledgeComplete') or checkpoint.get('knowledgeFingerprint') != fingerprint:
            config = {'kb': str(program_kb), 'program': program, 'cursor': cursor, 'progress': str(progress_path)}
            decompiled = action('recover-source', 'mcp.execute-script', {
                'programPath': str(context.get('program') or program), '_preparationProbe': True,
                'code': knowledge_script(config), 'timeout': 180,
            }, context)
            payload = decompiled.get('data') or {}
            if not decompiled['ok'] or not isinstance(payload, dict) or 'more' not in payload:
                failure = str(decompiled.get('error') or 'Ghidra source extraction retained completed functions and will continue from its cursor.')
                break
            observed_fingerprint = str(payload.get('programFingerprint') or '')
            if observed_fingerprint and observed_fingerprint != fingerprint:
                # A shared-folder name is only an inventory key.  Source
                # witnesses must be tied to the executable actually opened by
                # Ghidra, otherwise a moved/imported program could reuse a
                # cache from a different build.  Rename the just-created
                # cache when this is the first fingerprint observation; a
                # later change leaves the old receipt intact and restarts on
                # the next durable admission.
                if fingerprint == 'unknown':
                    bound_kb = work / ('knowledge-' + observed_fingerprint + '.sqlite')
                    if program_kb != bound_kb and program_kb.exists() and not bound_kb.exists():
                        program_kb.replace(bound_kb)
                    program_kb = bound_kb
                    fingerprint = observed_fingerprint
                    checkpoint['programFingerprint'] = observed_fingerprint
                else:
                    checkpoint.pop('knowledgeCursor', None)
                    checkpoint.pop('knowledgeComplete', None)
                    checkpoint.pop('knowledgeAvailable', None)
                    checkpoint['programFingerprint'] = observed_fingerprint
                    failure = 'The opened Ghidra program changed since the prior source receipt; a fresh fingerprint-bound extraction is queued.'
                    break
            cursor = str(payload['cursor'])
            checkpoint.update(
                knowledgeCursor=cursor,
                knowledgeComplete=not payload['more'],
                knowledgeFingerprint=fingerprint,
                knowledgeDb=str(program_kb),
                knowledgeAvailable=payload['available'],
            )
            update('recover-source', 'running', f'{program}: {payload["attempted"]} of {payload["total"]} functions decompiled.',
                   workProgress={'completed': payload['attempted'], 'total': payload['total'], 'unit': 'functions'})
    finally:
        row.pop('functionProgressFile', None)
    return program_kb, _knowledge_has_program(program_kb, program), failure


def continue_recovery(row: dict[str, Any], root: Path, db: Path,
                      action: Callable[..., dict[str, Any]], update: Callable[..., None],
                      execution_routes: dict[str, tuple[str, str]] | None = None,
                      recovery_family: str = '', programs: list[str] | None = None,
                      all_programs: list[str] | None = None) -> None:
    """Recover one explicit family while projecting stages across the project."""
    all_programs = list(all_programs or row.get('programs') or [])
    programs = list(programs or all_programs)
    execution_routes = execution_routes or {}
    family_key = hashlib.sha256(recovery_family.encode()).hexdigest()[:16] if recovery_family else 'legacy'
    family_receipt = row.setdefault('recoveryFamilies', {}).setdefault(recovery_family or 'legacy', {
        'family': recovery_family or 'legacy', 'programs': programs,
    })
    family_receipt.update(state='running', updatedAt=time.time())

    def aggregate(key: str) -> tuple[int, str, list[str]]:
        outcomes = [row['checkpoints'].get(item, {}).get('workflow', {}).get(key, {}) for item in all_programs]
        completed = sum(outcome.get('status') == 'completed' for outcome in outcomes)
        status = 'completed' if all_programs and completed == len(all_programs) else ('partial' if any(outcome.get('status') in {'partial', 'completed'} for outcome in outcomes) else 'blocked')
        reasons = list(dict.fromkeys(str(outcome.get('reason') or '') for outcome in outcomes if outcome.get('status') != 'completed'))
        return completed, status, reasons

    for program in programs:
        checkpoint = row['checkpoints'].setdefault(program, {})
        states = checkpoint.setdefault('workflow', {})
        work = root / 'recovery' / row['id'] / family_key / str(checkpoint.get('binaryId') or 'unresolved')
        execution_locator, execution_program = execution_routes.get(program, (row['locator'], program))
        context = {'locator': execution_locator, 'program': execution_program,
                   'slug': checkpoint.get('slug') or '', 'repo': checkpoint.get('repoPath') or ''}

        def result(key: str, status: str, reason: str, **details: Any) -> None:
            states[key] = {'status': status, 'reason': reason, 'updatedAt': time.time(), **details}
            completed, _, _ = aggregate(key)
            update(key, 'running', f'{program}: {reason}', completed=completed, total=len(all_programs),
                   currentProgram=program, recoveryFamily=recovery_family,
                   outcomes={p: row['checkpoints'].get(p, {}).get('workflow', {}).get(key, {}) for p in all_programs})

        def block_after(start: str, reason: str) -> None:
            keys = [key for key, _ in STAGES]
            for key in keys[keys.index(start):]:
                if states.get(key, {}).get('status') in {'completed', 'partial'}:
                    continue
                result(key, 'blocked', reason, dependencies=[start])

        if not checkpoint.get('analysisConfirmed') or not checkpoint.get('factsComplete'):
            block_after('calibrate-global', 'Waiting for confirmed analysis and function facts.')
            continue
        work.mkdir(parents=True, exist_ok=True)
        # Target materialization and Ghidra witnesses are independent of a
        # compiler profile.  Do them before calibration: otherwise a project
        # with no prior source probes can never produce the evidence needed to
        # make subsequent recovery work concrete.
        from .target_image import catalog_target_authority, materialize_original_target
        expected_hash = ''
        try:
            with sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True) as con:
                found = con.execute('SELECT content_sha256 FROM binary WHERE id=?', (checkpoint.get('binaryId'),)).fetchone()
                expected_hash = str(found[0] or '') if found else ''
        except (sqlite3.Error, ValueError, OSError):
            pass
        registry_path = Path(os.environ.get(
            'AGENT_DECOMPILE_TARGET_AUTHORITY_REGISTRY',
            str(root / 'original-target-authorities' / 'k1-k2-target-authorities.json'),
        ))
        authority = catalog_target_authority(registry_path, str(checkpoint.get('repoPath') or ''))
        target_source = checkpoint.get('executablePath') or ''
        target_md5 = ''
        if authority is not None:
            target_source = authority['sourcePath']
            target_md5 = str(authority['expectedMd5'])
            expected_hash = ''
        target_image = materialize_original_target(
            target_source, work,
            program=program,
            program_fingerprint=str(checkpoint.get('programFingerprint') or ''),
            expected_sha256=expected_hash,
            expected_md5=target_md5,
            protection=checkpoint.get('protection'),
            source_provenance=authority,
        )
        checkpoint['targetImage'] = target_image
        if target_image.get('ok'):
            original_target = Path(str(target_image['targetPath']))
            result('materialize-target', 'completed', 'Original executable bytes copied and hash-bound for independent comparison.',
                   receipt=target_image['receiptPath'], targetImage=target_image)
            floor_dir = work / 'assembly-floor'
            floor = action('assembly-floor', 'corpus.roundtrip', {
                'repo-path': checkpoint['repoPath'], 'db': str(db),
                'raw': str(original_target), 'out-dir': str(floor_dir),
            }, context)
            floor_data = floor.get('data') or {}
            floor_receipt = floor_dir / '_roundtrip.json'
            target_hash = str(target_image.get('targetSha256') or '')
            floor_ok = (
                floor.get('ok') and floor_data.get('identical') is True
                and floor_data.get('sha256_original') == target_hash
                and floor_data.get('sha256_rebuilt') == target_hash
                and floor_receipt.is_file()
            )
            result(
                'assembly-floor', 'completed' if floor_ok else 'partial',
                'Complete assembly substrate reproduces the original file bytes.' if floor_ok
                else floor.get('error') or 'Assembly substrate did not reproduce the original file bytes.',
                receipt=str(floor_receipt), source=floor_data.get('source'),
                targetReceipt=target_image['receiptPath'], targetSha256=target_hash,
                size=floor_data.get('size'), rebuiltSize=floor_data.get('rebuilt_size'),
                functions=floor_data.get('functions'), bytesInFunctions=floor_data.get('bytes_in_functions'),
                bytesFiller=floor_data.get('bytes_filler'), representation='byte-authoritative-assembly-substrate',
                claimBoundary='This assembly reproduces the shipped file image; it is not recovered authored C/C++.',
            )
        else:
            original_target = None
            result('materialize-target', 'blocked', str(target_image.get('reason') or 'Original byte target could not be materialized.'), targetImage=target_image)


        profile_path = work / 'compiler-profile.json'
        # A project can supply its measured configuration at workspace level.
        configured = os.environ.get('AGENT_DECOMPILE_COMPILER_PROFILE', '').strip()
        profile_admission: dict[str, Any] | None = None
        if configured:
            profile_path = Path(configured).expanduser()
        header = work / 'ghidra_types.h'
        layout_config = {'db': str(db), 'binaryId': checkpoint['binaryId'], 'program': program, 'header': str(header)}
        exported_types = action('calibrate-global', 'mcp.execute-script', {'programPath': execution_program, '_preparationProbe': True, 'code': layout_script(layout_config), 'timeout': 180}, context)
        type_data = exported_types.get('data') or {}
        fields = {'work-dir': str(work)}
        if exported_types['ok'] and isinstance(type_data, dict) and type_data.get('types', 0) > 0:
            fields['types-header'] = str(header)
        else:
            if header.exists():
                header.replace(work / 'types-unavailable.h')
            result('calibrate-global', 'blocked', exported_types.get('error') or 'Target layout evidence is unavailable. Existing metadata has been retained.', jobId=exported_types.get('jobId'))
            block_after('assembly-floor', 'Waiting for target layout evidence.')
            continue
        program_kb, has_witnesses, extraction_failure = _extract_advisory_witnesses(
            row=row, checkpoint=checkpoint, work=work, program=program,
            context=context, action=action, update=update,
        )
        if has_witnesses:
            available = int(checkpoint.get('knowledgeAvailable') or 0)
            result('recover-source', 'partial',
                   f'{available} recorded Ghidra C witnesses available; compilation waits for measured toolchain evidence.',
                   knowledgeDb=str(program_kb), advisoryFunctions=available,
                   **({'extractionNote': extraction_failure} if extraction_failure else {}))
        elif extraction_failure:
            result('recover-source', 'partial', extraction_failure, knowledgeDb=str(program_kb))

        if not configured and not profile_path.exists():
            # Bind a measured compiler profile only after Ghidra has identified
            # the executable it actually opened.  Shared-folder names and
            # stored corpus inventory keys are not target identities.
            from agentdecompile_recovery.source_parity_profile_corpus import admit_measured_profile

            profile_admission = admit_measured_profile(
                matched_examples=_known_source_examples(work, root, str(checkpoint.get('slug') or '')),
                out_dir=work,
                profile_path=profile_path,
                program_fingerprint=str(checkpoint.get('programFingerprint') or ''),
                architecture=str(checkpoint.get('architecture') or ''),
            )
        if not configured and not profile_path.exists():
            profile_path = root / 'compiler-profile.json'
        profile = read_object(profile_path)
        if profile:
            fields['compiler-profile'] = str(profile_path)
        calibration = action('calibrate-global', 'corpus.calibrate-global', fields, context)
        calibration_receipt = read_object(work / 'calibrate-global.json')
        compiler = _compiler(profile)
        target_bound = (profile.get('programFingerprint') and profile['programFingerprint'] == checkpoint.get('programFingerprint')) or (profile.get('architecture') and profile['architecture'] == checkpoint.get('architecture'))
        if not target_bound:
            compiler = None
        if not calibration['ok'] or calibration_receipt.get('state') != 'done' or not compiler:
            gaps = calibration_receipt.get('gaps') or []
            if not profile:
                compiler_gap = (str(profile_admission.get('reason') or '') if profile_admission else '') or 'Target compiler profile missing: installed compilers do not establish this binary\'s compiler, flags, or ABI.'
            elif not target_bound:
                compiler_gap = 'Compiler profile is not bound to this target fingerprint or architecture.'
            elif not compiler:
                compiler_gap = 'Configured compiler script is unavailable.'
            else:
                compiler_gap = 'Calibration evidence missing: ' + ', '.join(gaps)
            reason = calibration.get('error') or compiler_gap
            result('calibrate-global', 'blocked', reason, receipt=str(work / 'calibrate-global.json'),
                   **({'profileAdmission': profile_admission} if profile_admission else {}),
                   nextAction='Configure target compiler and layout evidence')
            block_after('assembly-floor', 'Waiting for target compiler and layout evidence.')
            continue
        checkpoint['toolchain'] = compiler
        result('calibrate-global', 'completed', 'Compiler and layout inputs available; calibration receipt retained.', receipt=str(work / 'calibrate-global.json'))
        if original_target is None:
            block_after('assembly-floor', 'Waiting for an original-byte verification target.')
            continue

        source = work / 'source'
        layout = action('recover-source', 'corpus.workspace', {'db': str(db), 'donor-slug': checkpoint['slug'], 'out': str(source)}, context)
        if not layout['ok']:
            result('recover-source', 'partial', layout.get('error') or layout.get('log') or 'Project layout could not be written.', jobId=layout.get('jobId'))
        if not _knowledge_has_program(program_kb, program):
            block_after('recover-source', 'No decompiled C is available after the recorded extraction attempts.')
            continue
        generated = action('recover-source', 'corpus.ghidra-bulk', {
            'program': program, 'repo': checkpoint['repoPath'], 'db': str(db), 'out-dir': str(source),
            'kb': str(program_kb), 'compiler': compiler, 'mode': 'compile-only', 'workers': 1,
            'extract-raw': str(original_target),
        }, context)
        result('recover-source', 'completed' if generated['ok'] else 'partial',
               'C replacement attempts finished; compilation and proof remain separate.' if generated['ok'] else generated.get('error') or generated.get('log') or 'C replacement left unresolved functions.', jobId=generated.get('jobId'))
        # Successful source from partial runs is useful and can be placed.
        placed = action('apply-cross-build', 'corpus.cross-place', {
            'from': program, 'db': str(db), 'out-dir': str(source), 'repo': checkpoint['repoPath'],
        }, context)
        result('apply-cross-build', 'completed' if placed['ok'] else 'partial',
               'Placement attempts finished; each recipient still requires compilation and proof.' if placed['ok'] else placed.get('error') or placed.get('log') or 'No source could be placed.', jobId=placed.get('jobId'))

        original = original_target
        remaining = max(1, int(row['deadline'] - time.time())) if row.get('deadline') is not None else None
        recovered = action('leftover-recover', 'reconstruct.one-shot', {
            'input': str(original), 'work-dir': str(work / 'proof'), 'project': row['locator'],
            'project-program': program, 'autonomous': True,
            **({'autonomous-max-wall-seconds': remaining} if remaining is not None else {}),
            # Recovery must enrich the current Ghidra program before emitting
            # a source candidate.  Skipping this made later compilation work
            # from weaker pseudocode even when the pipeline had already
            # collected names, types, and shared identity evidence.
            'resume': True, 'dump-source': str(work / 'readable'),
        }, context)
        fallback = None
        if not recovered['ok']:
            fallback = 'corpus.genproject'
            queue = _leftover_queue(work, root)
            repo = checkpoint.get('repoPath') or context.get('repo') or ''
            if queue is not None and repo:
                result('leftover-recover', 'partial', recovered.get('error') or 'Reconstruct left unresolved functions.',
                       jobId=recovered.get('jobId'), nextFallback=fallback)
                generated = action('leftover-recover', 'corpus.genproject', {
                    'queue': str(queue), 'out': str(work / 'leftover-project'), 'db': str(db),
                    'raw': str(original), 'repo-path': repo, 'leftover-only': True,
                }, context)
                if generated['ok']:
                    fallback = 'corpus.compile-link'
                    result('leftover-recover', 'partial', 'Wrote leftover project.',
                           jobId=generated.get('jobId'), nextFallback=fallback)
            if source.is_dir():
                fallback = 'corpus.compile-link'
                result('leftover-recover', 'partial', recovered.get('error') or 'Compile remaining leftover units.',
                       jobId=recovered.get('jobId'), nextFallback=fallback)
                linked = action('leftover-recover', 'corpus.compile-link', {
                    'src-dir': str(source), 'out': str(work / 'leftover-link'),
                    **({'compiler': compiler} if compiler else {}),
                }, context)
                if linked['ok']:
                    fallback = None
                    recovered = linked
        result('leftover-recover', 'completed' if recovered['ok'] else 'partial',
               'Bounded recovery finished; proof receipts decide accepted coverage.' if recovered['ok'] else recovered.get('error') or recovered.get('log') or 'Recovery stopped with unresolved functions.',
               jobId=recovered.get('jobId'), **({'nextFallback': fallback} if fallback else {}))
        # This gate uses the canonical independent receipt audit. It does not
        # infer byte identity from process completion, source files, or linking.
        audit = action('verify-byte-accuracy', 'recover.claim-report', {'work-dir': str(work / 'proof')}, context)
        data = audit.get('data') or {}
        verified = sum(int(claim.get('count') or 0) for claim in data.get('claims', []) if claim.get('class') == 'objdiff-verified-semantic') if isinstance(data, dict) else 0
        result('verify-byte-accuracy', 'partial' if verified else 'blocked',
               f'{verified} receipt-backed semantic functions; full binary byte identity is not established.' if verified else 'No accepted byte-verification receipts. Compilation is not a match.',
               jobId=audit.get('jobId'), verifiedFunctions=verified, byteExact=False,
               targetImageReceipt=target_image['receiptPath'], targetSha256=target_image['targetSha256'])

    family_outcomes = [
        row['checkpoints'].get(program, {}).get('workflow', {}).get('verify-byte-accuracy', {})
        for program in programs
    ]
    family_receipt.update(
        state='completed' if family_outcomes and all(item.get('status') == 'completed' for item in family_outcomes) else 'partial',
        updatedAt=time.time(),
        outcomes={program: row['checkpoints'].get(program, {}).get('workflow', {}) for program in programs},
    )
    for key, _ in STAGES:
        completed, status, reasons = aggregate(key)
        update(key, status, '; '.join(reasons[:3]) or f'{completed} programs completed this stage.', completed=completed, total=len(all_programs), currentProgram='', currentAction='', recoveryFamily='')


def merge_evidence(db: str, run: str) -> dict[str, Any]:
    """Add match-supported identities without rebuilding or renumbering them.

    An edge cannot merge two existing logical IDs or put different functions
    from the same build into one new identity. Such conflicts remain available
    in the match table. Concrete human metadata is never rewritten.
    """
    from agentdecompile_recovery.corpus.store import connect
    from agentdecompile_recovery.corpus.stabs_link import ensure_columns
    from agentdecompile_recovery.corpus.correspondence import allows_identity_binding
    from agentdecompile_recovery.corpus.match_store import quarantined_source_tokens

    con = connect(Path(db))
    try:
        ensure_columns(con)
        con.execute('BEGIN IMMEDIATE')
        existing = {(r['binary_id'], r['addr']): r['logical_id'] for r in con.execute('SELECT * FROM identity')}
        parent, anchors, binaries, witnesses = {}, {}, {}, {}
        # Same token the matcher persists in evidence.dependencies (A3).
        quarantined_sources = quarantined_source_tokens(con, run)

        def find(node):
            if node not in parent:
                parent[node] = node
                anchors[node] = {existing[node]} if node in existing else set()
                binaries[node] = {node[0]}
            root = node
            while parent[root] != root:
                root = parent[root]
            while parent[node] != node:
                old = parent[node]
                parent[node] = root
                node = old
            return root

        conflicts = 0
        for match in con.execute("SELECT * FROM match WHERE run=? AND status IN ('auto','verify') ORDER BY score DESC", (run,)):
            evidence = json.loads(match['evidence'] or '{}')
            relation = match['relation'] if 'relation' in match.keys() else 'one_to_one'
            if not allows_identity_binding(evidence, relation, quarantined_sources):
                continue
            source, target = (match['src_binary'], match['src_addr']), (match['dst_binary'], match['dst_addr'])
            left, right = find(source), find(target)
            if left != right:
                if len(anchors[left] | anchors[right]) > 1 or binaries[left] & binaries[right]:
                    conflicts += 1
                    continue
                parent[right] = left
                anchors[left] |= anchors[right]
                binaries[left] |= binaries[right]
            evidence = {'run': run, 'source': source, 'target': target, 'score': match['score'], 'status': match['status'], 'witness': match['evidence']}
            for node in (source, target):
                witnesses.setdefault(node, evidence)
        groups = {}
        for node in parent:
            groups.setdefault(find(node), []).append(node)
        created = bound = 0
        touched = set()
        for root, members in groups.items():
            if len(members) < 2:
                continue
            old_ids = anchors[find(root)]
            logical = next(iter(old_ids)) if old_ids else None
            if logical is None:
                # Prefer a human-authored name when choosing the display witness.
                facts = [con.execute('SELECT f.*,b.game FROM func f JOIN binary b ON b.id=f.binary_id WHERE f.binary_id=? AND f.addr=?', node).fetchone() for node in members]
                facts = [fact for fact in facts if fact is not None]
                if not facts:
                    continue
                facts.sort(key=lambda fact: (str(fact['name_origin']).lower() not in {'human','user_defined','user'}, str(fact['name'] or '').startswith('FUN_')))
                chosen = facts[0]
                logical = con.execute('INSERT INTO logical_function (canon_key,canon_class,canon_method,game,best_name,best_signature,source_file,object_file,n_members,notes) VALUES(?,?,?,?,?,?,?,?,0,?)',
                    tuple(chosen[key] for key in ('canon_key','canon_class','canon_method','game','name','signature','source_file','object_file')) + ('Match-supported identity; concrete metadata preserved.',)).lastrowid
                created += 1
            touched.add(logical)
            group_score = min(float(witnesses[node]['score'] or 0) for node in members if node in witnesses)
            group_status = 'verify' if any(witnesses[node]['status'] == 'verify' for node in members if node in witnesses) else 'auto'
            for node in members:
                if node in existing or node not in witnesses:
                    continue
                witness = witnesses[node]
                witness = {**witness, 'componentMinimumScore': group_score, 'componentStatus': group_status}
                confidence = round(.5 + .5 * group_score if group_status == 'auto' else .35 + .45 * group_score, 4)
                con.execute('INSERT INTO identity(logical_id,binary_id,addr,confidence,method,evidence) VALUES(?,?,?,?,?,?)',
                    (logical, *node, confidence, 'match:' + run + ':' + witness['status'], json.dumps(witness)))
                bound += 1
        for logical in touched:
            con.execute('UPDATE logical_function SET n_members=(SELECT COUNT(*) FROM identity WHERE logical_id=?) WHERE id=?', (logical, logical))
        con.commit()
        return {'createdIdentities': created, 'boundFunctions': bound, 'retainedConflicts': conflicts, 'sourceAttributions': 0,
                'sourcePropagation': 'separate_explicit_operation_required',
                'claim': 'advisory', 'metadataPolicy': 'Existing identities and concrete names, labels, comments, and structures retained.'}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def input_revision(fields: dict[str, Any]) -> list[Any]:
    """A repaired input at the same path is a new attempt, not a stale failure."""
    import hashlib
    revisions = []
    for key in ('compiler-profile', 'types-header', 'compiler', 'input', 'binary', 'source', 'kb'):
        value = fields.get(key)
        if not isinstance(value, str) or not value:
            continue
        path = Path(value).expanduser()
        try:
            stat = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and stat.st_size <= 4 * 1024 * 1024 else None
            revisions.append([key, str(path), stat.st_size, stat.st_mtime_ns, digest])
        except OSError:
            revisions.append([key, str(path), 'unavailable'])
    return revisions


def knowledge_script(config: dict[str, Any]) -> str:
    """Decompile one bounded missing-only chunk in the existing owned JVM."""
    return 'import json\nconfig = json.loads(' + repr(json.dumps(config)) + ')\n' + r'''
import time, sqlite3
from pathlib import Path
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import TimeoutTaskMonitor
from java.util.concurrent import TimeUnit
from agentdecompile_recovery.corpus.ingest_ghidra_knowledge import SCHEMA
monitor = TimeoutTaskMonitor.timeoutIn(120, TimeUnit.SECONDS)
con = sqlite3.connect(config['kb'])
con.executescript(SCHEMA)
con.execute('CREATE TABLE IF NOT EXISTS knowledge_attempt (program TEXT, entry_hex TEXT, error TEXT, PRIMARY KEY(program,entry_hex))')
decompiler = DecompInterface()
started = time.time()
count = 0
last = config['cursor']
failed = 0
try:
    if not decompiler.openProgram(currentProgram):
        raise RuntimeError('The decompiler could not open the already analyzed program.')
    manager = currentProgram.getFunctionManager()
    total = int(manager.getFunctionCount())
    iterator = manager.getFunctions(toAddr(config['cursor']), True) if config['cursor'] else manager.getFunctions(True)
    while iterator.hasNext() and count < 64 and time.time() - started < 90:
        function = iterator.next()
        entry = function.getEntryPoint()
        address = str(entry)
        last = hex(int(str(entry), 16) + 1)
        if con.execute('SELECT 1 FROM knowledge_attempt WHERE program=? AND entry_hex=?', (config['program'], address)).fetchone():
            continue
        if con.execute("SELECT 1 FROM func_knowledge WHERE program=? AND entry_hex=? AND decompiled IS NOT NULL AND decompiled<>''", (config['program'], address)).fetchone():
            continue
        outcome = decompiler.decompileFunction(function, 20, monitor)
        if outcome.decompileCompleted() and outcome.getDecompiledFunction() is not None:
            code = str(outcome.getDecompiledFunction().getC())
            offset = None
            try:
                info = currentProgram.getMemory().getAddressSourceInfo(entry)
                offset = int(info.getFileOffset()) if info is not None else None
            except Exception:
                pass
            values = (config['program'], address, str(function.getName()), int(function.getBody().getNumAddresses()), offset,
                      str(function.getCallingConventionName()), str(function.getPrototypeString(False,False)), code, None, None, None)
            # The KB is fingerprint-scoped. Existing source and authored metadata
            # are retained; this stage fills only records not already available.
            con.execute('INSERT OR IGNORE INTO func_knowledge VALUES(?,?,?,?,?,?,?,?,?,?,?)', values)
            error = ''
        else:
            error = str(outcome.getErrorMessage() or 'Decompiler produced no source')
            failed += 1
        con.execute('INSERT OR IGNORE INTO knowledge_attempt VALUES(?,?,?)', (config['program'], address, error))
        con.commit()
        count += 1
        done = int(con.execute('SELECT COUNT(*) FROM knowledge_attempt WHERE program=?', (config['program'],)).fetchone()[0])
        target = Path(config['progress'])
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps({'completed':done,'total':total,'unit':'functions','program':config['program'],'updatedAt':time.time()}))
        temporary.replace(target)
    more = bool(iterator.hasNext())
    available = int(con.execute("SELECT COUNT(*) FROM func_knowledge WHERE program=? AND decompiled IS NOT NULL AND decompiled<>''", (config['program'],)).fetchone()[0])
    done = int(con.execute('SELECT COUNT(*) FROM knowledge_attempt WHERE program=?', (config['program'],)).fetchone()[0])
    con.execute('INSERT OR REPLACE INTO ingest_status VALUES(?,?,?,?,?)', (config['program'],done,total,time.time()-started,int(not more)))
    con.commit()
    __result__ = json.dumps({'cursor':last,'more':more,'attempted':done,'total':total,'available':available,'chunkFailed':failed,'claim':'advisory','programFingerprint':str(currentProgram.getExecutableMD5())})
finally:
    decompiler.dispose()
    con.close()
'''


def layout_script(config: dict[str, Any]) -> str:
    """Export missing type evidence without replacing curated stored layouts."""
    return 'import json\nconfig = json.loads(' + repr(json.dumps(config)) + ')\n' + r'''
from agentdecompile_recovery.corpus.store import connect
from agentdecompile_recovery.corpus.export_types import SCHEMA, emit_struct, emit_enum, c_ident
from agentdecompile_recovery.corpus.build_types_header import build_header
from ghidra.program.model.data import Enum, Structure, Union
from ghidra.util.task import TimeoutTaskMonitor
from java.util.concurrent import TimeUnit
monitor = TimeoutTaskMonitor.timeoutIn(120, TimeUnit.SECONDS)
con = connect(config['db'])
try:
    con.executescript(SCHEMA)
    inserted = 0
    for data_type in currentProgram.getDataTypeManager().getAllDataTypes():
        monitor.checkCancelled()
        if isinstance(data_type, (Structure, Union)):
            rendered = emit_struct(data_type)
            kind = 'union' if isinstance(data_type, Union) else 'struct'
        elif isinstance(data_type, Enum):
            rendered = emit_enum(data_type)
            kind = 'enum'
        else:
            continue
        if rendered is None:
            continue
        definition, fields = rendered
        changed = con.execute('INSERT OR IGNORE INTO ghidra_type(binary_id,name,kind,size,definition,n_fields) VALUES(?,?,?,?,?,?)',
            (config['binaryId'],c_ident(data_type.getName()),kind,int(data_type.getLength()),definition,fields))
        inserted += changed.rowcount
    con.commit()
    result = build_header(con, config['binaryId'], config['header'], program=config['program'])
    result.update(inserted=inserted, claim='context-hint', metadataPolicy='Existing stored layouts retained')
    __result__ = json.dumps(result)
finally:
    con.close()
'''

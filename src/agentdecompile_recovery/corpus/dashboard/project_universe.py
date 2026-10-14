"""Read-only membership and bounded stored evidence for every open project.

Project ownership comes from locators, full DomainFile paths and durable
bindings. A selected binary or a coincidentally equal filename is not ownership.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .common import format_address, live_db, live_root, parse_address


def read_json(path: Path, errors: list[str]) -> dict:
    """Do not use repairing persistence loaders on this observation path."""
    try:
        if not path.is_file():
            return {}
        if path.stat().st_size > 16 * 1024 * 1024:
            errors.append(f'Recorded state exceeds observation limit: {path}')
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError) as exc:
        errors.append(f'Recorded state unavailable: {path}: {exc}')
        return {}


def canonical(value: Any) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    if '://' in text:
        parsed = urlparse(text)
        return parsed._replace(scheme=parsed.scheme.lower(), path=parsed.path.rstrip('/')).geturl()
    return str(Path(text).expanduser().resolve(strict=False))


def program_path(value: Any) -> str:
    return '/' + str(value or '').replace('\\', '/').strip().strip('/')


def recorded_runs(errors: list[str]) -> list[dict]:
    from .preparation import list_runs

    try:
        return [row for row in list_runs() if not row.get('supersededBy')]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f'Preparation evidence unavailable: {exc}')
        return []


def recorded_match_status():
    """Preparation/checkpoint providers and stored identity methods are advisory."""
    from .workbench import _bsim_datadir

    errors: list[str] = []
    providers: list[dict] = []
    stages: list[dict] = []
    for run in recorded_runs(errors):
        for stage in run.get('stages') or []:
            if stage.get('key') in {'matching', 'bsim'}:
                stages.append({'runId': run.get('id'), 'locator': run.get('locator'),
                               **{k: stage.get(k) for k in ('key', 'status', 'reason', 'completed', 'total', 'currentAction')}})
        for program, checkpoint in (run.get('checkpoints') or {}).items():
            if not isinstance(checkpoint, dict) or not checkpoint.get('bsimUrl'):
                continue
            url = str(checkpoint['bsimUrl'])
            providers.append({'provider': 'file' if url.startswith('file:') else 'recorded-bsim',
                              'url': url, 'program': program, 'locator': run.get('locator'),
                              'runId': run.get('id'), 'receipt': checkpoint.get('bsimReceipt'),
                              'fingerprint': checkpoint.get('bsimFingerprint'),
                              'state': 'recorded' if checkpoint.get('bsimComplete') else 'pending',
                              'optional': True, 'required': False,
                              'claim': 'recorded-preparation; provider availability not freshly probed'})
    methods: list[dict] = []
    db = live_db()
    if db:
        try:
            with sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True, timeout=2) as con:
                import time
                deadline = time.monotonic() + 3
                con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
                tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'identity' in tables:
                    methods = [{'method': row[0] or 'unspecified', 'bindings': row[1],
                                'source': 'recorded-identity', 'claim': 'advisory',
                                'scope': 'first-10000-recorded-bindings; not a corpus total'}
                               for row in con.execute('SELECT method,COUNT(*) FROM (SELECT method FROM identity LIMIT 10000) GROUP BY method LIMIT 100')]
        except (OSError, sqlite3.Error, ValueError) as exc:
            errors.append(f'Recorded matching methods unavailable: {exc}')
    try:
        datadir = _bsim_datadir()
    except ValueError:
        datadir = None
    if datadir is not None:
        from agentdecompile_recovery.corpus import bsim_ops as bo
        try:
            legacy = bo.report(datadir=datadir)
        except Exception as exc:
            legacy = {'state': 'database_unreachable', 'summary': str(exc)[:400]}
        providers.append({**legacy, 'provider': 'optional-postgresql', 'datadir': str(datadir),
                          'optional': True, 'required': False, 'claim': 'explicit-provider-probe'})
    recorded = any(p.get('state') == 'recorded' for p in providers)
    return {'ok': True, 'optional': True, 'required': False,
            'state': 'recorded' if recorded else 'optional_not_configured' if not providers else 'optional_pending',
            'summary': 'Recorded matching evidence is available. BSim is optional.' if methods or recorded else 'Matching uses stored function features. BSim is optional and can be configured below.',
            'providers': providers, 'methods': methods, 'preparationStages': stages,
            'datadir': str(datadir) if datadir else '', 'executables': None, 'exes': [],
            'errors': errors, 'claimBoundary': 'Recorded pair and signature receipts are advisory; missing BSim does not block other matching methods.'}


def query_project_functions(context, binary_ids, q, offset, limit):
    """Query recorded functions without project discovery or corpus aggregation.

    Membership and database identity are supplied by the already-loaded project
    snapshot. This path counts no global populations and resolves names only
    after selecting a bounded page. Missing source witnesses remain unknown.
    """
    import time
    from contextlib import closing
    from ..match_review import ReviewError, _current
    from .common import corpus_file_identity

    if (not isinstance(binary_ids, (list, tuple)) or not 1 <= len(binary_ids) <= 2000
            or any(type(value) is not int or not 0 <= value <= (1 << 63) - 1 for value in binary_ids)
            or not isinstance(q, str) or len(q) > 512
            or type(offset) is not int or not 0 <= offset <= 1_000_000
            or type(limit) is not int or not 1 <= limit <= 500):
        raise ReviewError('malformed_request')
    ids = sorted(set(binary_ids))
    needle = q.strip()
    _current(context)
    basis = corpus_file_identity(context.path)
    try:
        with closing(sqlite3.connect(context.path.as_uri() + '?mode=ro', uri=True, timeout=2)) as con:
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA query_only=ON')
            con.execute('BEGIN')
            _current(context)
            deadline = time.monotonic() + 5
            con.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
            if 'func' not in tables or 'binary' not in tables:
                raise ReviewError('unavailable')
            marks = ','.join('?' for _ in ids)
            binaries = {row['id']: dict(row) for row in con.execute(
                f'SELECT id,slug,bits FROM binary WHERE id IN ({marks})', ids)}
            identity = 'identity' in tables
            logical_names = identity and 'logical_name' in tables
            indexes = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            where, params = f'f.binary_id IN ({marks})', list(ids)
            address = parse_address(needle) if needle else None
            if address is not None and (needle.lower().startswith('0x') or needle.isdigit()
                                       or len(needle) in (8, 16)):
                if address > (1 << 63) - 1:
                    raise ReviewError('address_out_of_range')
                where += ' AND f.addr=?'
                params.append(address)
            elif needle:
                # Treat the typed name literally, not as SQL wildcard syntax.
                pattern = '%' + needle.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
                where += " AND (COALESCE(f.name,'') LIKE ? ESCAPE '\\'"
                params.append(pattern)
                if logical_names:
                    logical_index = ' INDEXED BY ix_identity_logical' if 'ix_identity_logical' in indexes else ''
                    where += f" OR (f.binary_id,f.addr) IN (SELECT i.binary_id,i.addr FROM identity i{logical_index} WHERE i.logical_id IN (SELECT logical_id FROM logical_name WHERE name LIKE ? ESCAPE '\\') AND i.binary_id IN ({marks}))"
                    params.extend((pattern, *ids))
                where += ')'
            # The covering index excludes bulky feature/listing payloads from
            # name scans. Older stores without it can use their existing index.
            index = ' INDEXED BY ix_func_priority_cover' if 'ix_func_priority_cover' in indexes else ''
            page_keys = con.execute(f'''SELECT f.binary_id,f.addr FROM func f{index}
                WHERE {where} ORDER BY f.binary_id,f.addr LIMIT ? OFFSET ?''',
                [*params, limit + 1, offset]).fetchall()
            results = []
            columns = {row[1] for row in con.execute('PRAGMA table_info(func)')}
            display_columns = ','.join(sorted({'binary_id', 'addr', 'name', 'size'} |
                                             ({'source', 'name_origin'} & columns)))
            for key in page_keys[:limit]:
                if time.monotonic() > deadline:
                    raise ReviewError('busy')
                row = con.execute(f'SELECT {display_columns} FROM func WHERE binary_id=? AND addr=?',
                                  (key['binary_id'], key['addr'])).fetchone()
                if row is None or row['binary_id'] not in binaries:
                    raise ReviewError('corrupt_basis')
                logical_id, logical_name = None, None
                if identity:
                    binding = con.execute('SELECT logical_id FROM identity WHERE binary_id=? AND addr=? LIMIT 1',
                                          (row['binary_id'], row['addr'])).fetchone()
                    if binding:
                        logical_id = binding[0]
                        if logical_names:
                            name = con.execute('SELECT name FROM logical_name WHERE logical_id=?', (logical_id,)).fetchone()
                            logical_name = name[0] if name else None
                # Preserve the same human-authored precedence as the existing
                # workbench inventory; this is display policy, not authenticity.
                human = ('source' in columns and row['source'] == 'USER_DEFINED') or (
                    'name_origin' in columns and str(row['name_origin'] or '').lower()
                    in ('human', 'human-authored', 'user', 'user_defined'))
                name = row['name'] if human and row['name'] else logical_name or row['name']
                binary = binaries[row['binary_id']]
                address_text = format_address(row['addr'], binary.get('bits') or 32)
                results.append({'binaryId': row['binary_id'], 'slug': binary['slug'],
                    'addr': address_text, 'address': row['addr'],
                    'name': name or 'FUN_' + address_text[2:], 'size': row['size'] or 0,
                    'logicalId': logical_id, 'recordedName': row['name'], 'logicalName': logical_name,
                    'nameSource': 'human' if human and row['name'] else 'logical' if logical_name else 'recorded',
                    'matchedNames': [value for value in (row['name'], logical_name)
                                     if needle and value and needle.casefold() in str(value).casefold()]})
            _current(context)
            return {'ok': True, 'binaryIds': ids, 'corpusIdentity': basis['identity'],
                'scope': {'binaryIds': ids, 'query': needle},
                'functions': {'available': True, 'results': results, 'offset': offset,
                    'limit': limit, 'hasMore': len(page_keys) > limit, 'total': None,
                    'totalKnown': False, 'query': needle,
                    'claimBoundary': 'Recorded function search; absence of a row is not proof that a function or match does not exist.'},
                'missingBinaryIds': [value for value in ids if value not in binaries]}
    except sqlite3.Error as exc:
        # Keep this classification explicit: repeated comprehension qualnames
        # can collide in the current reload admission registry. No new closure
        # is needed just to recognize a bounded/locked read.
        message = str(exc).lower()
        code = 'unavailable'
        for word in ('locked', 'busy', 'interrupted'):
            if word in message:
                code = 'busy'
                break
        raise ReviewError(code) from exc


def project_universe(*, q: str = '', offset: Any = 0, limit: Any = 100) -> dict:
    from ..ghidra_project import classify_locator
    from agentdecompile_recovery.ghidra_db.store import store_roots, list_store_programs

    def bounded(value: Any, default: int, maximum: int) -> int:
        try:
            return max(0, min(maximum, int(value)))
        except (ValueError, TypeError):
            return default

    start, cap = bounded(offset, 0, 1_000_000), max(1, bounded(limit, 100, 500))
    errors: list[str] = []
    root = live_root()
    state = read_json(root / 'workbench-sessions.json', errors) if root else {}
    projects: list[dict] = []
    members: dict[tuple[str, str], dict] = {}
    aliases: dict[str, set[str]] = {}
    sessions = [s for s in state.get('sessions', []) if isinstance(s, dict) and not s.get('hidden')]
    if len(sessions) > 100:
        errors.append('Open project observation limited to 100 sessions.')
    for session in sessions[:100]:
        locator = canonical(session.get('locator'))
        # Legacy standalone binary tabs have no project locator. Retain their
        # recorded exact source path; do not turn their focus into a new project.
        standalone = not locator
        source = canonical(session.get('program')) if standalone else locator
        pid = str(session.get('id') or hashlib.sha256(source.encode()).hexdigest()[:20])
        project = {'id': pid, 'title': str(session.get('title') or source or 'Untitled project'),
                   'locator': locator, 'kind': str(session.get('kind') or ('binary' if standalone else 'project'))}
        projects.append(project)
        imports = session.get('imports') or []
        project['recordedImports'] = [i if isinstance(i, str) else {k: i.get(k) for k in ('slug', 'path', 'locator', 'program')} for i in imports[:500] if isinstance(i, (str, dict))]

        def member(owner: str, program: str, name: str, **extra: Any) -> dict:
            key = (owner, program_path(program))
            if key not in members:
                ident = hashlib.sha256((owner + '\0' + key[1]).encode()).hexdigest()[:24]
                members[key] = {'id': 'member:' + ident, 'slug': '', 'name': name,
                                'program': key[1], 'locator': locator, 'projectIds': [],
                                'binaryIds': [], 'funcs': None, 'named': None, 'bound': None,
                                'bindingState': 'unbound', **extra}
            item = members[key]
            if pid not in item['projectIds']:
                item['projectIds'].append(pid)
            return item

        if standalone:
            if source:
                member(source, source, Path(source).name, sourcePath=source,
                       importSlugs=[i for i in imports if isinstance(i, str)])
            continue
        try:
            info = classify_locator(locator)
            if info.get('kind') != 'empty':
                project['kind'] = str(info.get('kind'))
            else:
                errors.append(f'{project["title"]}: {info.get("error") or "Project inventory unavailable"}')
            stores = store_roots(locator) if '://' not in locator else []
            owners = {canonical(p) for p in stores} or {locator}
            aliases[locator] = owners
            found = 0
            for owner in sorted(owners):
                entries = list_store_programs(owner) if '://' not in owner else []
                for entry in entries[:5000]:
                    member(owner, entry.project_path, entry.name,
                           repositoryLocator=owner, fileId=entry.file_id or '')
                    found += 1
                if len(entries) > 5000:
                    errors.append(f'{project["title"]}: repository inventory limited to 5000 members.')
            # A remote repository can still expose full paths in its durable
            # preparation receipt even when its local inventory is unavailable.
            if not found:
                for value in info.get('programs') or []:
                    path = (info.get('program_paths') or {}).get(str(value), str(value))
                    member(locator, str(path), str(value))
        except (OSError, ValueError, RuntimeError) as exc:
            aliases[locator] = {locator}
            errors.append(f'{project["title"]}: inventory unavailable: {exc}')

    runs = recorded_runs(errors)
    page = {'results': [], 'total': 0, 'offset': start, 'limit': cap, 'hasMore': False}
    result = {'ok': True, 'scope': 'projects', 'projects': projects, 'builds': [],
              'functions': page, 'errors': errors,
              'claimBoundary': 'Stored source, compilation and historical region receipts are separate; no fresh whole-image verification is performed.'}
    db = live_db()
    if db is None:
        errors.append('No stored corpus database is selected.')
        result['builds'] = list(members.values())
        return result
    from .common import corpus_file_identity
    database_basis = corpus_file_identity(db)
    result['corpusIdentity'] = database_basis['identity']
    try:
        with sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True, timeout=2) as con:
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA query_only=ON')
            # Bound wall work as well as output when a corpus is exceptionally large.
            import time
            deadline = time.monotonic() + 15
            con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            con.execute('BEGIN')
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            binaries = {r['id']: dict(r) for r in con.execute('SELECT * FROM binary ORDER BY id LIMIT 2001')}
            if len(binaries) > 2000:
                errors.append('Corpus binding observation limited to 2000 binary records.')
                binaries.pop(next(reversed(binaries)))
            sources = {canonical(b['repo_path']): b for b in binaries.values()}
            owners_cache: dict[str, set[str]] = {}

            def owners_for(value: Any) -> set[str]:
                loc = canonical(value)
                if loc not in owners_cache:
                    owners_cache[loc] = aliases.get(loc) or ({canonical(p) for p in store_roots(loc)} if loc and '://' not in loc else set()) or {loc}
                return owners_cache[loc]

            def bind(item: dict, binary: dict, reason: str) -> None:
                if binary['id'] not in item['binaryIds']:
                    item['binaryIds'].append(binary['id'])
                item['bindingState'] = 'recorded'
                item.setdefault('bindingEvidence', []).append(reason)

            if 'program_binding' in tables:
                bindings = list(con.execute('SELECT source_path,locator,program FROM program_binding ORDER BY updated DESC LIMIT 5001'))
                if len(bindings) > 5000:
                    errors.append('Durable program bindings limited to 5000 records.')
                for binding in bindings[:5000]:
                    binary = sources.get(canonical(binding['source_path']))
                    if binary is None:
                        continue
                    binding_owners = owners_for(binding['locator'])
                    observed = []
                    for candidate_owner in binding_owners:
                        if (candidate_owner, program_path(binding['program'])) in members:
                            observed.append(candidate_owner)
                    # Collection ownership does not identify each child repo.
                    # Keep unresolved recorded paths once at the collection.
                    resolved_owners = observed if len(observed) == 1 else list(binding_owners) if len(binding_owners) == 1 else [canonical(binding['locator'])]
                    for owner in resolved_owners:
                        item = members.get((owner, program_path(binding['program'])))
                        if item is None:
                            related = []
                            for project in projects:
                                if project['locator'] and (project['locator'] == canonical(binding['locator']) or owner in aliases.get(project['locator'], {project['locator']})):
                                    related.append(project)
                            if related:
                                key = (owner, program_path(binding['program']))
                                ident = hashlib.sha256((owner + '\0' + key[1]).encode()).hexdigest()[:24]
                                item = {'id': 'member:' + ident, 'slug': '', 'name': Path(binding['program']).name,
                                        'program': key[1], 'locator': related[0]['locator'], 'repositoryLocator': owner,
                                        'projectIds': [p['id'] for p in related], 'binaryIds': [], 'funcs': None,
                                        'named': None, 'bound': None, 'bindingState': 'unbound',
                                        'inventoryState': 'recorded-binding; current repository member not observed'}
                                members[key] = item
                        if item is not None:
                            bind(item, binary, 'durable exact project/program binding')
                            if len(observed) > 1:
                                item['repositoryBindingState'] = 'unresolved'
                                item['bindingReason'] = 'The collection binding does not identify a unique child repository.'
            for item in members.values():
                # Persisted synthetic corpus source keys are exact project/path
                # identities too. No basename search or suffix matching occurs.
                source = item.get('sourcePath') or (
                    canonical(str(Path(item['repositoryLocator']) / item['program'].lstrip('/')))
                    if item.get('repositoryLocator') else '')
                if source in sources:
                    bind(item, sources[source], 'exact recorded source identity')
            for run in runs:
                owner_set = owners_for(run.get('locator'))
                for path, checkpoint in (run.get('checkpoints') or {}).items():
                    if not isinstance(checkpoint, dict) or path not in (run.get('programs') or []):
                        continue
                    binary = binaries.get(checkpoint.get('binaryId'))
                    if binary is None or checkpoint.get('slug') != binary['slug'] or canonical(checkpoint.get('repoPath')) != canonical(binary['repo_path']):
                        continue
                    for project in projects:
                        if canonical(run.get('locator')) != project['locator']:
                            continue
                        observed = list(o for o in owner_set if (o, program_path(path)) in members)
                        owner = observed[0] if len(observed) == 1 else canonical(run.get('locator'))
                        key = (owner, program_path(path))
                        if key not in members:
                            ident = hashlib.sha256((owner + '\0' + key[1]).encode()).hexdigest()[:24]
                            members[key] = {'id': 'member:' + ident, 'slug': '', 'name': Path(path).name,
                                            'program': key[1], 'locator': project['locator'], 'projectIds': [project['id']],
                                            'binaryIds': [], 'funcs': None, 'named': None, 'bound': None,
                                            'bindingState': 'unbound', 'inventoryState': 'recorded-checkpoint'}
                        bind(members[key], binary, 'identity-checked preparation checkpoint')
                        if len(observed) > 1:
                            members[key]['repositoryBindingState'] = 'unresolved'
                            members[key]['bindingReason'] = 'The collection checkpoint does not identify a unique child repository.'
                        workflow = checkpoint.get('workflow') or {}
                        members[key].setdefault('recordedPreparation', []).append({
                            'runId': run.get('id'), 'program': path,
                            'factsComplete': checkpoint.get('factsComplete'),
                            'bsimUrl': checkpoint.get('bsimUrl'), 'bsimReceipt': checkpoint.get('bsimReceipt'),
                            'stages': [{k: s.get(k) for k in ('key', 'status', 'reason', 'completed', 'total', 'receipt')}
                                       for s in workflow.get('stages', []) if isinstance(s, dict)],
                            'claim': 'recorded-checkpoint; fresh compilation and whole-image verification not performed here'})

            selected = sorted({bid for item in members.values() for bid in item['binaryIds']})
            for item in members.values():
                ids = item['binaryIds']
                if len(ids) == 1:
                    b = binaries[ids[0]]
                    item.update(slug=b['slug'], binaryId=b['id'], arch=b.get('arch'), bits=b.get('bits'),
                                recoveryFamily=b.get('recovery_family'), sourcePath=b['repo_path'])
                elif len(ids) > 1:
                    item['bindingState'] = 'ambiguous'
                    item['bindingReason'] = 'Multiple stored binaries claim this full project/program identity.'
            result['builds'] = sorted(members.values(), key=lambda item: (item['locator'], item['program']))
            if not selected or 'func' not in tables:
                return result
            marks = ','.join('?' for _ in selected)
            counts = {r[0]: (r[1], r[2]) for r in con.execute(f"SELECT binary_id,COUNT(*),COALESCE(SUM(name IS NOT NULL AND name!='' AND name NOT GLOB 'FUN_*' AND name NOT GLOB 'sub_*'),0) FROM func WHERE binary_id IN ({marks}) GROUP BY binary_id", selected)}
            bound = {r[0]: r[1] for r in con.execute(f'SELECT binary_id,COUNT(*) FROM identity WHERE binary_id IN ({marks}) GROUP BY binary_id', selected)} if 'identity' in tables else {}
            for item in result['builds']:
                if item['binaryIds']:
                    item.update(funcs=sum(counts.get(b, (0, 0))[0] for b in item['binaryIds']), named=sum(counts.get(b, (0, 0))[1] for b in item['binaryIds']), bound=sum(bound.get(b, 0) for b in item['binaryIds']))
            if 'identity' in tables and 'match' in tables:
                from ..match_review import recorded_family_relationships
                result['relationships'] = recorded_family_relationships(con, selected, deadline)
            else:
                result['relationships'] = {'available': False, 'edges': [], 'sampled': True,
                    'partial': True, 'totalKnown': False,
                    'reason': 'Stored identities and their matching lineage are unavailable.'}
            name_expr = 'COALESCE(f.name,\'\')'
            logical = '(SELECT i.logical_id FROM identity i WHERE i.binary_id=f.binary_id AND i.addr=f.addr LIMIT 1)' if 'identity' in tables else 'NULL'
            if 'identity' in tables and 'logical_name' in tables:
                name_expr = "CASE WHEN f.source='USER_DEFINED' OR lower(COALESCE(f.name_origin,'')) IN ('human','human-authored','user','user_defined') THEN COALESCE(f.name,'') ELSE COALESCE((SELECT ln.name FROM identity i JOIN logical_name ln ON ln.logical_id=i.logical_id WHERE i.binary_id=f.binary_id AND i.addr=f.addr LIMIT 1),f.name,'') END"
            where, params = f'f.binary_id IN ({marks})', list(selected)
            needle = str(q or '').strip()[:512]
            if needle:
                address = parse_address(needle)
                if address is not None and (needle.lower().startswith('0x') or needle.isdigit()):
                    if not 0 <= address <= 0x7fffffffffffffff:
                        errors.append('Address query is outside the supported SQLite signed 64-bit range (0 through 0x7fffffffffffffff).')
                        page['queryError'] = 'address_out_of_range'
                        return result
                    where += ' AND f.addr=?'
                    params.append(address)
                else:
                    # Resolve display names only for the page. A correlated
                    # display-name lookup on every COUNT row is needlessly
                    # expensive when searching an absent name in a large corpus.
                    if 'identity' in tables and 'logical_name' in tables:
                        where += f" AND (COALESCE(f.name,'') LIKE ? OR (f.binary_id,f.addr) IN (SELECT i.binary_id,i.addr FROM logical_name ln JOIN identity i ON i.logical_id=ln.logical_id WHERE ln.name LIKE ? AND i.binary_id IN ({marks})))"
                        params.extend(('%' + needle + '%', '%' + needle + '%', *selected))
                    else:
                        where += " AND COALESCE(f.name,'') LIKE ?"
                        params.append('%' + needle + '%')
            page['total'] = con.execute(f'SELECT COUNT(*) FROM func f WHERE {where}', params).fetchone()[0]
            columns = {r[1] for r in con.execute('PRAGMA table_info(recovered_function)')} if 'recovered_function' in tables else set()
            rows = list(con.execute(f'SELECT f.binary_id,f.addr,{name_expr} AS name,f.size,{logical} AS logical_id FROM func f WHERE {where} ORDER BY f.binary_id,f.addr LIMIT ? OFFSET ?', (*params, cap, start)))
            recorded: dict[tuple[int, int], list[dict]] = {}
            partial_pairs: set[tuple[int, int]] = set()
            if rows and {'binary_id', 'addr', 'real_c', 'path', 'evidence'} <= columns:
                page_keys = sorted({(r['binary_id'], r['addr']) for r in rows})
                pair_marks = ','.join('(?,?)' for _ in page_keys)
                pair_params = []
                for binary_id, function_address in page_keys:
                    pair_params.extend((binary_id, function_address))
                # Exact requested pairs exclude off-page cross-products. Rank
                # witnesses separately for each pair so a prolific function
                # cannot consume another function's evidence allowance. The
                # ninth row is a per-pair truncation sentinel; expose only eight.
                witnesses = list(con.execute(
                    f'WITH page_pairs(binary_id,addr) AS (VALUES {pair_marks}), '
                    'ranked AS (SELECT binary_id,addr,real_c,path,substr(evidence,1,2048) AS evidence, '
                    'ROW_NUMBER() OVER (PARTITION BY binary_id,addr ORDER BY real_c DESC,path) AS witness_rank '
                    'FROM recovered_function WHERE (binary_id,addr) IN (SELECT binary_id,addr FROM page_pairs)) '
                    'SELECT binary_id,addr,real_c,path,evidence,witness_rank FROM ranked WHERE witness_rank<=9 '
                    'ORDER BY binary_id,addr,witness_rank', pair_params))
                for witness in witnesses:
                    key = (witness['binary_id'], witness['addr'])
                    if witness['witness_rank'] == 9:
                        partial_pairs.add(key)
                    else:
                        recorded.setdefault(key, []).append({k: witness[k] for k in ('real_c', 'path', 'evidence')})
                if partial_pairs:
                    errors.append(f'Recorded source witnesses limited to eight per function for {len(partial_pairs)} requested page pair(s); truncated evidence remains partial.')
            for row in rows:
                b = binaries[row['binary_id']]
                memberships = [item for item in result['builds'] if b['id'] in item['binaryIds']]
                chosen = memberships[0]
                recovery = {'readable': None, 'compiled': None, 'historicalExact': None, 'freshWholeImage': False}
                if {'binary_id', 'addr', 'real_c', 'path', 'evidence'} <= columns:
                    witnesses = recorded.get((b['id'], row['addr']), [])
                    partial = (b['id'], row['addr']) in partial_pairs
                    metadata = []
                    for witness in witnesses:
                        try:
                            value = json.loads(witness['evidence'] or '{}')
                        except (ValueError, TypeError):
                            value = {}
                        if isinstance(value, dict):
                            metadata.append(value)
                    recovery.update(readable=True if any(r['real_c'] == 1 for r in witnesses) else None if partial else False,
                                    records=witnesses, witnessesPartial=partial,
                                    compiled=True if any(m.get('compiled') is True for m in metadata) else None,
                                    historicalExact=True if any(m.get('byte_exact') is True or m.get('byteExact') is True for m in metadata) else None,
                                    claim='recorded-source-availability; compilation and byte comparison not revalidated')
                page['results'].append({'binaryId': b['id'], 'buildId': chosen['id'], 'slug': b['slug'],
                                        'program': chosen['program'], 'locator': chosen['locator'],
                                        'projectIds': sorted({p for m in memberships for p in m['projectIds']}),
                                        'memberships': [{'buildId': m['id'], 'locator': m['locator'], 'program': m['program']} for m in memberships],
                                        'addr': format_address(row['addr'], b.get('bits') or 32), 'address': row['addr'],
                                        'name': row['name'] or 'FUN_' + format_address(row['addr'], b.get('bits') or 32)[2:],
                                        'size': row['size'] or 0, 'logicalId': row['logical_id'], 'recordedRecovery': recovery})
            page['hasMore'] = start + len(page['results']) < page['total']
    except (sqlite3.Error, OSError, ValueError, TypeError, RuntimeError, OverflowError) as exc:
        errors.append(f'Stored project evidence unavailable: {exc}')
        result['builds'] = list(members.values())
        page['available'] = False
        page['partial'] = True
    if corpus_file_identity(db) != database_basis or corpus_file_identity(live_db()) != database_basis:
        result['ok'] = False
        result['builds'] = []
        result['functions'] = {**page, 'results': [], 'available': False, 'partial': True}
        result['relationships'] = {'available': False, 'edges': [], 'partial': True,
                                   'reason': 'The selected corpus changed while reading project facts.'}
        result['corpusIdentity'] = ''
        errors.append('The selected corpus changed while reading project facts. Refresh project facts before reviewing correspondences.')
    return result

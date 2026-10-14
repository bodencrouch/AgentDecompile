"""Coherent candidate review with exact-basis preconditions and atomic audit.

Accept means review -> verify, never source parity or semantic identity. Public
adapters must supply catalog ownership and a pinned selection guard; this core
does not provide an alternate operational mutation entry point.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys
import time

from . import match_review_schema as schema

MAX_BATCH = 100
MAX_PAGE = 100
MAX_BASIS_BYTES = 256 * 1024
MAX_SQLITE_ID = (1 << 63) - 1


class ReviewError(ValueError):
    def __init__(self, code: str, *, match_id: int | None = None):
        super().__init__(code)
        self.code = code
        self.match_id = match_id

    def result(self):
        result = {'ok': False, 'error': self.code,
                  'refreshRequired': self.code in ('stale_basis', 'context_changed')}
        if self.match_id is not None:
            result['matchId'] = self.match_id
        return result


@dataclass(frozen=True)
class Context:
    path: Path
    device: int
    inode: int
    selection: str


def pin_context(path: str | Path, selection: str) -> Context:
    if not isinstance(selection, str) or not selection or len(selection) > 256:
        raise ReviewError('malformed_context')
    target = Path(path).resolve(strict=True)
    if not target.is_file():
        raise ReviewError('unavailable')
    info = target.stat()
    return Context(target, info.st_dev, info.st_ino, selection)


def _current(context: Context) -> None:
    try:
        info = context.path.stat()
    except OSError as exc:
        raise ReviewError('context_changed') from exc
    if (info.st_dev, info.st_ino) != (context.device, context.inode):
        raise ReviewError('context_changed')


@contextmanager
def _transaction(context: Context, *, write: bool):
    _current(context)
    con = None
    try:
        # URI quoting is provided by as_uri; mode=rw cannot create a missing DB.
        con = sqlite3.connect(context.path.as_uri() + ('?mode=rw' if write else '?mode=ro'),
                              uri=True, timeout=2, isolation_level=None)
        con.row_factory = sqlite3.Row
        deadline = time.monotonic() + 5
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        if not write:
            con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        _current(context)
        try:
            schema.require(con)
        except ValueError as exc:
            raise ReviewError(str(exc)) from exc
        yield con
        _current(context)
        con.execute('COMMIT')
    except sqlite3.OperationalError as exc:
        code = 'busy' if 'locked' in str(exc).lower() or 'busy' in str(exc).lower() else 'unavailable'
        raise ReviewError(code) from exc
    except sqlite3.DatabaseError as exc:
        raise ReviewError('unavailable') from exc
    finally:
        if con is not None:
            primary = sys.exc_info()[1]
            try:
                if con.in_transaction:
                    try:
                        con.rollback()
                    except sqlite3.Error as exc:
                        if primary is None:
                            raise ReviewError('unavailable') from exc
                        primary.add_note('Explicit rollback failed; connection closure was still attempted.')
            finally:
                con.close()


def _canonical(value) -> bytes:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise ReviewError('corrupt_basis') from exc
    if len(encoded) > MAX_BASIS_BYTES:
        raise ReviewError('basis_too_large')
    return encoded


def _revision(con, kind, entity_id):
    row = con.execute('SELECT revision FROM match_review_revision WHERE kind=? AND entity_id=?',
                      (kind, entity_id)).fetchone()
    if row is None or type(row[0]) is not int or row[0] <= 0:
        raise ReviewError('review_schema_corrupt')
    return row[0]


def _binary_basis(con, binary_id):
    binary = con.execute('SELECT * FROM binary WHERE id=?', (binary_id,)).fetchone()
    if binary is None:
        raise ReviewError('corrupt_basis')
    return {'row': dict(binary), 'revision': _revision(con, 'binary', binary_id)}


def _assemble_basis(con, context, row, binaries, incarnation):
    candidate = dict(row)
    for key in ('id', 'src_binary', 'src_addr', 'dst_binary', 'dst_addr'):
        if type(candidate.get(key)) is not int or candidate[key] < 0:
            raise ReviewError('corrupt_basis')
    for key in ('score', 'margin'):
        value = candidate.get(key)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ReviewError('corrupt_basis')
    if not isinstance(candidate.get('run'), str) or not candidate['run']:
        raise ReviewError('corrupt_basis')
    basis = {'schema': 'match-review-basis/v1', 'incarnation': incarnation,
             'context': {'path': str(context.path), 'device': context.device,
                         'inode': context.inode, 'selection': context.selection},
             'revision': _revision(con, 'match', candidate['id']),
             'match': candidate, 'binaries': binaries}
    token = 'v1:' + hashlib.sha256(_canonical(basis)).hexdigest()
    return basis, token


def _basis(con, context, row):
    binaries = [_binary_basis(con, row[key]) for key in ('src_binary', 'dst_binary')]
    incarnation = con.execute('SELECT incarnation FROM match_review_control WHERE singleton=1').fetchone()[0]
    return _assemble_basis(con, context, row, binaries, incarnation)


def explain_candidate(con, candidate):
    """Explain a retained candidate without re-running or bypassing the matcher.

    The authoritative cascade already admits unique anchors and graph-derived
    matches. A row left in review is not made safe by a high similarity score.
    Competitors are read from the entire run/pair, not just the visible page.
    """
    from .matching_availability import _object, recorded_signals, project_channels

    ev = _object(candidate.get('evidence'))
    signals = recorded_signals(ev)
    alternatives = {}
    truncated = False
    for address_key in ('src_addr', 'dst_addr'):
        rows = con.execute(f'''SELECT id,src_addr,dst_addr,status,score FROM match
            WHERE run=? AND src_binary=? AND dst_binary=? AND {address_key}=?
              AND id<>? AND status IN ('auto','verify','review')
            ORDER BY id LIMIT 9''', (candidate['run'], candidate['src_binary'],
                candidate['dst_binary'], candidate[address_key], candidate['id'])).fetchall()
        truncated |= len(rows) > 8
        for row in rows[:8]:
            alternatives[row['id']] = {'matchId': row['id'], 'srcAddr': row['src_addr'],
                'dstAddr': row['dst_addr'], 'status': row['status'], 'score': row['score']}
    producer_alternatives = ev.get('alternatives') if isinstance(ev.get('alternatives'), list) else []
    source_conflict = any(row['srcAddr'] == candidate['src_addr']
                          and row['dstAddr'] != candidate['dst_addr'] for row in alternatives.values())
    destination_conflict = any(row['dstAddr'] == candidate['dst_addr']
                               and row['srcAddr'] != candidate['src_addr'] for row in alternatives.values())
    producer_conflict = any(isinstance(row, dict) and row.get('dst') is not None
                           and row['dst'] != candidate['dst_addr'] for row in producer_alternatives)
    contract = _object(ev.get('contract')) or _object(_object(ev.get('contract_shadow')).get('contract'))
    relation = ev.get('relation') or candidate.get('relation') or 'not_recorded'
    reasons = []
    def reason(code, text):
        reasons.append({'code': code, 'text': text})
    if ev.get('quarantine') or ev.get('status_band') == 'quarantined':
        reason('quarantined', 'Contradictory evidence quarantined this candidate; its descendants must not be trusted.')
    if ev.get('relation') and candidate.get('relation') and ev['relation'] != candidate['relation']:
        reason('relation_conflict', 'The recorded relation and its evidence disagree; reconcile their provenance before binding.')
    if contract.get('veto') or contract.get('verdict') == 'incompatible':
        reason('contract_conflict', 'Recorded calling-contract evidence conflicts with this correspondence.')
    if source_conflict or producer_conflict:
        reason('source_alternatives', 'This source has competing destinations; keep the alternatives until distinguishing evidence resolves them.')
    if destination_conflict:
        reason('destination_collision', 'Another source competes for the same destination; a one-to-one identity cannot be assumed.')
    if relation not in ('not_recorded', 'one_to_one'):
        reason('non_identity_relation', 'This is a ' + str(relation) + ' relation, not interchangeable whole-function identity.')
    if ev.get('_content') == 0:
        reason('no_distinguishing_content', 'No distinguishing content was recorded. Similar shape or instruction frequencies can describe different functions.')
    elif not signals and not ev.get('channels') and not ev.get('primary_channel'):
        reason('evidence_gap', 'The historical row has no inspectable matching evidence; its score alone cannot justify a choice.')
    if ev.get('target_unique') is False:
        uniqueness = 'not_unique'
        reason('shortlist_not_unique', 'The matcher recorded more than one retrieved target candidate.')
    elif ev.get('target_unique') is True:
        uniqueness = 'shortlist_unique'
        reason('shortlist_only', 'Only the retrieved shortlist was unique; that is not target-wide uniqueness proof.')
    else:
        uniqueness = 'not_recorded'
        reason('uniqueness_gap', 'Target-wide uniqueness was not recorded; absence of alternatives on this page is not proof.')
    dependencies = ev.get('dependencies') if isinstance(ev.get('dependencies'), list) else []
    if dependencies:
        reason('derived_lineage', 'This result depends on recorded anchor mappings; descendants of one anchor are not independent corroboration.')
    state = ('blocked' if any(row['code'] in ('quarantined', 'contract_conflict', 'relation_conflict') for row in reasons)
             else 'ambiguous' if source_conflict or destination_conflict or producer_conflict
             or ev.get('status_band') == 'ambiguous'
             else 'needs_evidence')
    headlines = {'blocked': 'Conflicting evidence — do not bind',
                 'ambiguous': 'Competing correspondences — no safe winner',
                 'needs_evidence': 'Candidate only — distinguishing evidence needed'}
    return {'state': state, 'headline': headlines[state],
        'recommendation': 'Reuse stored anchors and caller/callee context first; acquire missing distinguishing evidence before choosing an identity.',
        'nextStep': 'resolve_conflict' if state == 'blocked' else 'acquire_distinguishing_evidence',
        'automaticEligible': False, 'reasons': reasons, 'signals': signals,
        'methods': project_channels(ev),
        'alternatives': sorted(alternatives.values(), key=lambda row: row['matchId']),
        'producerAlternatives': producer_alternatives[:8],
        'alternativesTruncated': truncated or len(producer_alternatives) > 8,
        'relation': relation, 'uniqueness': 'collision' if destination_conflict else uniqueness,
        'contract': 'conflict' if contract.get('veto') or contract.get('verdict') == 'incompatible'
                    else 'compatible' if contract.get('verdict') == 'compatible' else 'not_recorded',
        'dependencyCount': len(dependencies), 'score': candidate['score'], 'margin': candidate['margin'],
        'claimBoundary': 'Similarity ranks candidates; it is not identity probability, matching C, or byte-parity proof.'}


def _review_page(con, context, rows, limit):
    page = []
    # These reads share one pinned SQLite snapshot. Do not reuse this cache
    # across requests or mutation transactions; revisions must remain exact.
    binaries = {}
    incarnation = con.execute('SELECT incarnation FROM match_review_control WHERE singleton=1').fetchone()[0]
    for row in rows[:limit]:
        for key in ('src_binary', 'dst_binary'):
            if row[key] not in binaries:
                binaries[row[key]] = _binary_basis(con, row[key])
        basis, token = _assemble_basis(con, context, row,
            [binaries[row[key]] for key in ('src_binary', 'dst_binary')], incarnation)
        functions = {}
        for side, binary_key, address_key in (('source', 'src_binary', 'src_addr'),
                                              ('destination', 'dst_binary', 'dst_addr')):
            function = con.execute('SELECT name FROM func WHERE binary_id=? AND addr=? LIMIT 1',
                                   (row[binary_key], row[address_key])).fetchone()
            functions[side] = {'addr': row[address_key], 'name': function[0] if function else None}
        page.append({'match': basis['match'], 'binaries': basis['binaries'], 'token': token,
                     'functions': functions, 'decision': explain_candidate(con, basis['match'])})
    return {'ok': True, 'rows': page, 'total': None, 'totalKnown': False,
            'hasMore': len(rows) > limit,
            'nextAfterId': page[-1]['match']['id'] if len(rows) > limit else None,
            'selection': context.selection}


def list_review_scoped(context, after_id, limit, binary_ids, binary_id, addr):
    """Bound review to project membership and either side of a focused function.

    Run names are obtained with indexed keyset seeks, not a DISTINCT scan over
    millions of edges. Function retrieval then uses the existing run/function
    indexes. This read path performs no extraction, matching, or migration.
    """
    if (type(after_id) is not int or not 0 <= after_id <= MAX_SQLITE_ID
            or type(limit) is not int or not 1 <= limit <= MAX_PAGE
            or not isinstance(binary_ids, (list, tuple)) or not 1 <= len(binary_ids) <= 2000
            or any(type(value) is not int or not 0 <= value <= MAX_SQLITE_ID for value in binary_ids)):
        raise ReviewError('malformed_request')
    ids = sorted(set(binary_ids))
    focused = binary_id is not None or addr is not None
    if focused and (type(binary_id) is not int or binary_id not in ids
                    or type(addr) is not int or not 0 <= addr <= MAX_SQLITE_ID):
        raise ReviewError('malformed_request')
    with _transaction(context, write=False) as con:
        placeholders = ','.join('?' for _ in ids)
        scope = f'src_binary IN ({placeholders}) AND dst_binary IN ({placeholders})'
        if focused:
            # ORDER BY run on the existing covering index seeks once per run.
            runs = []
            run_deadline = time.monotonic() + 5
            record = con.execute("SELECT run FROM match WHERE run>'' AND typeof(run)='text' ORDER BY run LIMIT 1").fetchone()
            while record:
                if len(runs) >= 256 or time.monotonic() > run_deadline:
                    # Never silently truncate run coverage or let many small
                    # index seeks evade SQLite's progress-handler deadline.
                    raise ReviewError('busy')
                runs.append(record[0])
                record = con.execute("SELECT run FROM match WHERE run>? AND typeof(run)='text' ORDER BY run LIMIT 1",
                                     (record[0],)).fetchone()
            hits = {}
            if runs:
                run_slots = ','.join('?' for _ in runs)
                for side in ('src', 'dst'):
                    query = f'''SELECT * FROM match INDEXED BY ix_match_{side}
                        WHERE run IN ({run_slots}) AND {scope}
                        AND status='review' AND {side}_binary=? AND {side}_addr=? AND id>?
                        ORDER BY id LIMIT ?'''
                    params = [*runs, *ids, *ids, binary_id, addr, after_id, limit + 1]
                    for row in con.execute(query, params):
                        hits[row['id']] = row
            rows = sorted(hits.values(), key=lambda row: row['id'])[:limit + 1]
        else:
            rows = con.execute(f'''SELECT * FROM match NOT INDEXED WHERE {scope}
                AND status='review' AND id>? ORDER BY id LIMIT ?''',
                [*ids, *ids, after_id, limit + 1]).fetchall()
        result = _review_page(con, context, rows, limit)
        result['scope'] = {'binaryIds': ids, 'binaryId': binary_id, 'addr': addr,
                           'kind': 'function' if focused else 'project'}
        return result


def _correspondence_runs(con):
    runs = []
    deadline = time.monotonic() + 5
    row = con.execute("SELECT run FROM match WHERE run>'' AND typeof(run)='text' ORDER BY run LIMIT 1").fetchone()
    while row:
        if len(runs) >= 256 or time.monotonic() > deadline:
            raise ReviewError('busy')
        runs.append(row[0])
        row = con.execute("SELECT run FROM match WHERE run>? AND typeof(run)='text' ORDER BY run LIMIT 1", (row[0],)).fetchone()
    return runs


def _recorded_identity_gate(con, evidence, relation, runs):
    """Reuse the identity gate with bounded indexed checks of stored parents."""
    from .matching_availability import _object
    from .correspondence import allows_identity_binding

    embedded = _object(evidence.get('witness'))
    if embedded:
        evidence = {**embedded, **evidence}
    dependencies = set()
    for key in ('dependencies', 'dependency_ancestry'):
        values = evidence.get(key) or ()
        if not isinstance(values, (list, tuple)) or len(values) > 32:
            return False
        for token in values:
            if not isinstance(token, str):
                return False
            dependencies.add(token)
    if len(dependencies) > 32:
        return False  # Bounded inspection cannot validate a larger lineage.
    if not allows_identity_binding(evidence, relation, set()):
        return False
    if dependencies and not runs:
        return False
    run_slots = ','.join('?' for _ in runs)
    quarantined = set()
    for token in dependencies:
        if not isinstance(token, str):
            return False
        parts = token.split(':', 1)
        if (len(parts) != 2 or len(parts[0]) != 16 or not parts[1].isdigit()
                or len(parts[1]) > 19 or int(parts[1]) > MAX_SQLITE_ID):
            return False
        binaries = con.execute('''SELECT id FROM binary
            WHERE substr(content_sha256,1,16)=? LIMIT 17''', (parts[0],)).fetchall()
        if not binaries or len(binaries) > 16:
            return False
        found = False
        for binary in binaries:
            parents = con.execute(f'''SELECT evidence FROM match INDEXED BY ix_match_src
                WHERE run IN ({run_slots}) AND src_binary=? AND src_addr=? LIMIT 65''',
                [*runs, binary[0], int(parts[1])]).fetchall()
            if len(parents) > 64:
                return False
            for parent in parents:
                found = True
                prior = _object(parent[0])
                if prior.get('quarantine') or prior.get('status_band') == 'quarantined':
                    quarantined.add(token)
        if not found:
            return False
    return allows_identity_binding(evidence, relation, quarantined)


def recorded_family_relationships(con, binary_ids, outer_deadline):
    """Bounded, lineage-gated witnesses from the caller's pinned snapshot.

    Sampling is deliberately not a total correspondence count. No compilation,
    new acceptance, or matching job is performed by this observation.
    """
    from .matching_availability import _object

    ids = sorted(set(binary_ids))
    result = {'available': True, 'edges': [], 'sampled': True, 'partial': False,
              'totalKnown': False, 'sourceIdentityLimit': 256,
              'witnessLimitPerPair': 2, 'evidenceCharacterLimit': 8192, 'visitedBinaries': 0,
              'binaryIds': ids,
              'claimBoundary': 'Observed recorded identity witnesses; not matching C, byte equality, or ABI compatibility.'}
    stop = min(outer_deadline, time.monotonic() + 5)
    slots = ','.join('?' for _ in ids)
    pairs = {}
    gates = {}
    inspected = set()
    con.set_progress_handler(lambda: int(time.monotonic() > stop), 1000)
    try:
        runs = _correspondence_runs(con)
        for source in ids:
            if time.monotonic() >= stop:
                result['partial'] = True
                break
            # Materialize only the bounded donor sample, never the whole
            # identity self-join. ix_identity_logical probes each selected peer.
            rows = con.execute(f'''WITH donor AS MATERIALIZED (
                SELECT logical_id,addr,substr(evidence,1,8193) AS evidence,method FROM identity
                WHERE binary_id=? ORDER BY addr,logical_id LIMIT 256)
                SELECT donor.logical_id,donor.addr AS source_addr,
                       donor.evidence AS source_evidence,donor.method AS source_method,
                       peer.binary_id AS target_binary,peer.addr AS target_addr,
                       substr(peer.evidence,1,8193) AS target_evidence,peer.method AS target_method
                FROM donor JOIN identity peer INDEXED BY ix_identity_logical
                  ON peer.logical_id=donor.logical_id
                WHERE peer.binary_id>? AND peer.binary_id IN ({slots})
                LIMIT 4097''', [source, source, *ids]).fetchall()
            result['visitedBinaries'] += 1
            if len(rows) > 4096:
                result['partial'] = True
            for row in rows[:4096]:
                if time.monotonic() >= stop:
                    result['partial'] = True
                    break
                target = row['target_binary']
                key = (source, target)
                edge = pairs.get(key)
                if edge and len(edge['witnesses']) >= 2:
                    continue
                logical = row['logical_id']
                witness_key = (source, target, logical)
                if witness_key in inspected:
                    continue
                inspected.add(witness_key)
                valid = True
                for bid, address, evidence in (
                        (source, row['source_addr'], row['source_evidence']),
                        (target, row['target_addr'], row['target_evidence'])):
                    if evidence is not None and len(evidence) > 8192:
                        result['partial'] = True
                        valid = False
                        break  # Never validate a truncated dependency record.
                    try:
                        parsed = json.loads(evidence or '{}')
                    except (ValueError, TypeError):
                        parsed = None
                    if not isinstance(parsed, dict):
                        result['partial'] = True
                        valid = False
                        break  # Malformed evidence is not an empty legacy record.
                    binding_key = (bid, address, logical)
                    if binding_key not in gates:
                        # Both function->identity and identity->function must
                        # be unique; split/alias memberships cannot become a
                        # one-to-one family relationship by accident.
                        members = con.execute('''SELECT addr FROM identity INDEXED BY ix_identity_logical
                            WHERE binary_id=? AND logical_id=? LIMIT 2''', (bid, logical)).fetchall()
                        bindings = con.execute('''SELECT logical_id FROM identity
                            WHERE binary_id=? AND addr=? LIMIT 2''', (bid, address)).fetchall()
                        ev = parsed
                        relation = ev.get('relation') or _object(ev.get('witness')).get('relation') or 'one_to_one'
                        gates[binding_key] = (len(members) == 1 and len(bindings) == 1
                            and _recorded_identity_gate(con, ev, relation, runs))
                    if not gates[binding_key]:
                        valid = False
                        break
                if not valid:
                    continue
                if edge is None:
                    edge = {'sourceBinaryId': source, 'targetBinaryId': target,
                            'kind': 'recorded_identity', 'observedCorrespondences': 0,
                            'totalKnown': False, 'witnesses': []}
                    pairs[key] = edge
                edge['witnesses'].append({'logicalId': logical,
                    'sourceAddr': row['source_addr'], 'targetAddr': row['target_addr'],
                    'sourceMethod': row['source_method'], 'targetMethod': row['target_method']})
                edge['observedCorrespondences'] = len(edge['witnesses'])
    except (sqlite3.Error, ReviewError) as exc:
        result['partial'] = True
        result['reason'] = 'Relationship observation reached its read budget or stored lineage is unavailable.'
        result['available'] = bool(pairs)
    finally:
        con.set_progress_handler(lambda: int(time.monotonic() > outer_deadline), 10000)
    result['edges'] = list(pairs.values())
    result['validatedBindings'] = sum(gates.values())
    return result


def list_correspondence_scoped(context, after_id, limit, binary_ids, binary_id, addr):
    """Display installed correspondence separately from unresolved review.

    Preference is inspection of existing selections, not a new acceptance.
    Per-peer uniqueness reads all runs, never just the current result page.
    """
    from .matching_availability import _object
    from .correspondence import allows_identity_binding

    if (type(after_id) is not int or not 0 <= after_id <= MAX_SQLITE_ID
            or type(limit) is not int or not 1 <= limit <= MAX_PAGE
            or not isinstance(binary_ids, (list, tuple)) or not 1 <= len(binary_ids) <= 2000
            or any(type(value) is not int or not 0 <= value <= MAX_SQLITE_ID for value in binary_ids)):
        raise ReviewError('malformed_request')
    ids = sorted(set(binary_ids))
    focused = binary_id is not None or addr is not None
    if focused and (type(binary_id) is not int or binary_id not in ids
                    or type(addr) is not int or not 0 <= addr <= MAX_SQLITE_ID):
        raise ReviewError('malformed_request')
    with _transaction(context, write=False) as con:
        if not focused:
            scope_slots = ','.join('?' for _ in ids)
            records = con.execute(f'''SELECT * FROM match NOT INDEXED
                WHERE src_binary IN ({scope_slots}) AND dst_binary IN ({scope_slots})
                  AND status IN ('auto','verify','review') AND id>? ORDER BY id LIMIT ?''',
                [*ids, *ids, after_id, limit + 1]).fetchall()
            result = _review_page(con, context, records, limit)
            for row in result['rows']:
                row['existingStatus'] = row['match']['status']
                row['storedSelection'] = False
                row['correspondenceKey'] = 'match:' + str(row['match']['id'])
                if row['existingStatus'] != 'review':
                    row.pop('token', None)
            result.update(preferredByBinary=[], preferredMatchId=None, identityCorrespondences=[],
                acceptedTruncated=False, identityTruncated=False,
                scope={'binaryIds': ids, 'binaryId': None, 'addr': None, 'kind': 'project'})
            return result
        runs = _correspondence_runs(con)
        slots = ','.join('?' for _ in ids)
        run_slots = ','.join('?' for _ in runs)
        accepted = {}
        pending = {}
        if runs:
            for side in ('src', 'dst'):
                common = f'''FROM match INDEXED BY ix_match_{side}
                    WHERE run IN ({run_slots}) AND src_binary IN ({slots}) AND dst_binary IN ({slots})
                    AND {side}_binary=? AND {side}_addr=?'''
                parameters = [*runs, *ids, *ids, binary_id, addr]
                for row in con.execute('SELECT * ' + common + " AND status IN ('auto','verify') ORDER BY id LIMIT ?", [*parameters, limit + 1]):
                    accepted[row['id']] = row
                for row in con.execute('SELECT * ' + common + " AND status='review' AND id>? ORDER BY id LIMIT ?", [*parameters, after_id, limit + 1]):
                    pending[row['id']] = row
        accepted_rows = sorted(accepted.values(), key=lambda row: row['id'])[:limit]
        review_rows = sorted(pending.values(), key=lambda row: row['id'])[:limit + 1]
        result = _review_page(con, context, accepted_rows + review_rows[:limit], len(accepted_rows) + limit)
        result.update(hasMore=len(pending) > limit,
            nextAfterId=review_rows[limit - 1]['id'] if len(pending) > limit else None,
            acceptedTruncated=len(accepted) > limit,
            scope={'binaryIds': ids, 'binaryId': binary_id, 'addr': addr, 'kind': 'function'})
        preferred = {}
        collision_peers = set()
        for row in result['rows']:
            match = row['match']
            row['existingStatus'] = match['status']
            row['storedSelection'] = False
            row['correspondenceKey'] = 'match:' + str(match['id'])
            if match['status'] == 'review':
                continue
            row.pop('token', None)
            evidence = _object(match['evidence'])
            relation = evidence.get('relation') or match.get('relation') or 'one_to_one'
            decision = row['decision']
            if (not _recorded_identity_gate(con, evidence, relation, runs)
                    or decision['state'] == 'blocked'):
                decision.update(state='blocked', headline='Stored correspondence cannot be safely preferred',
                    recommendation='Inspect conflicting or unavailable dependency evidence; the existing record is retained.')
                continue
            side = 'src' if match['src_binary'] == binary_id and match['src_addr'] == addr else 'dst'
            other = 'dst' if side == 'src' else 'src'
            peer = match[other + '_binary']
            endpoints = con.execute(f'''SELECT DISTINCT {other}_addr FROM match INDEXED BY ix_match_{side}
                WHERE run IN ({run_slots}) AND {side}_binary=? AND {side}_addr=?
                  AND {other}_binary=? AND status IN ('auto','verify') LIMIT 2''',
                [*runs, binary_id, addr, peer]).fetchall()
            if len(endpoints) != 1:
                collision_peers.add(peer)
                decision.update(state='ambiguous', headline='Stored selections disagree — keep both counterparts')
                continue
            decision.update(state='stored', headline='Matcher-selected correspondence',
                recommendation='Inspect the existing selected counterpart; override only when new evidence warrants it.',
                nextStep='inspect_stored_correspondence', automaticEligible=False)
            row['storedSelection'] = True
            preferred.setdefault(peer, {'binaryId': peer, 'matchId': match['id'],
                'sourceAddr': addr, 'targetAddr': match[other + '_addr'],
                'kind': 'stored_match', 'correspondenceKey': row['correspondenceKey']})
        identities = []
        result['identityTruncated'] = False
        focal_binary = con.execute('SELECT id,slug FROM binary WHERE id=? LIMIT 1', (binary_id,)).fetchone()
        if focal_binary is None:
            raise ReviewError('context_changed')
        focal = _graph_function(con, binary_id, addr, focal_binary)
        if focal['logicalId'] is not None and _recorded_identity_gate(con, _object(focal['identities'][0]['evidence']), 'one_to_one', runs):
            peers = con.execute(f'''SELECT binary_id,addr FROM identity
                WHERE logical_id=? AND binary_id IN ({slots}) AND binary_id<>?
                ORDER BY binary_id,addr LIMIT 2001''', [focal['logicalId'], *ids, binary_id]).fetchall()
            result['identityTruncated'] = len(peers) > 2000
            for peer in peers[:2000]:
                peer_id = peer['binary_id']
                binary = con.execute('SELECT id,slug FROM binary WHERE id=? LIMIT 1', (peer_id,)).fetchone()
                if binary is None:
                    continue
                target = _graph_function(con, peer_id, peer['addr'], binary)
                if (target['logicalId'] != focal['logicalId']
                        or not _recorded_identity_gate(con, _object(target['identities'][0]['evidence']), 'one_to_one', runs)):
                    collision_peers.add(peer_id)
                    continue
                if peer_id in preferred:
                    if preferred[peer_id]['targetAddr'] != peer['addr']:
                        collision_peers.add(peer_id)
                    continue
                key = ':'.join(str(value) for value in ('identity', focal['logicalId'], binary_id, addr, peer_id, peer['addr']))
                entry = {'correspondenceKey': key,
                    'match': {'id': None, 'run': None, 'src_binary': binary_id, 'src_addr': addr,
                        'dst_binary': peer_id, 'dst_addr': peer['addr'], 'status': 'identity',
                        'relation': 'one_to_one', 'score': None, 'margin': None},
                    'existingStatus': 'identity', 'storedSelection': True,
                    'functions': {'source': {'addr': addr, 'name': focal['name']},
                                  'destination': {'addr': peer['addr'], 'name': target['name']}},
                    'binaries': [{'row': dict(focal_binary)}, {'row': dict(binary)}],
                    'identityBinding': {'logicalId': focal['logicalId'], 'source': focal['identities'], 'target': target['identities']},
                    'decision': {'state': 'stored', 'headline': 'Recorded identity binding',
                        'automaticEligible': False, 'reasons': [], 'signals': [], 'methods': [], 'alternatives': [],
                        'recommendation': 'Inspect the installed identity; its lineage is recorded, not revalidated by this display.',
                        'claimBoundary': 'Recorded identity; not source or byte-parity proof.'}}
                identities.append(entry)
                preferred[peer_id] = {'binaryId': peer_id, 'matchId': None, 'logicalId': focal['logicalId'],
                    'sourceAddr': addr, 'targetAddr': peer['addr'], 'kind': 'recorded_identity', 'correspondenceKey': key}
        for peer_id in collision_peers:
            preferred.pop(peer_id, None)
        for row in result['rows'] + identities:
            if row['match']['src_binary'] == binary_id and row['match']['src_addr'] == addr:
                peer_id = row['match']['dst_binary']
            else:
                peer_id = row['match']['src_binary']
            if peer_id in collision_peers:
                row['storedSelection'] = False
                row['decision'].update(state='ambiguous', headline='Existing bindings disagree — no safe preferred counterpart')
        result['identityCorrespondences'] = identities
        result['preferredByBinary'] = [preferred[peer_id] for peer_id in sorted(preferred)]
        result['preferredMatchId'] = next(iter(preferred.values()))['matchId'] if len(preferred) == 1 and not result['acceptedTruncated'] else None
        result['claimBoundary'] = 'Existing selections are shown automatically for inspection. Displaying them creates no new identity, approval, or parity claim.'
        return result


def _graph_function(con, binary_id, addr, binary):
    """A recorded node and its provenance, never an inferred identity by name."""
    from .matching_availability import _object

    function = con.execute('SELECT name,size FROM func WHERE binary_id=? AND addr=? LIMIT 1',
                           (binary_id, addr)).fetchone()
    bindings = con.execute('''SELECT logical_id,confidence,method,evidence FROM identity
        WHERE binary_id=? AND addr=? ORDER BY logical_id LIMIT 9''', (binary_id, addr)).fetchall()
    identities = []
    for binding in bindings[:8]:
        evidence = _object(binding['evidence'])
        embedded = _object(evidence.get('witness'))
        if embedded:
            evidence = {**embedded, **evidence}
        contract = _object(evidence.get('contract'))
        blocked = bool(evidence.get('quarantine') or evidence.get('status_band') == 'quarantined'
                       or evidence.get('identity_claim') is False
                       or contract.get('veto') or contract.get('verdict') == 'incompatible')
        dependencies = evidence.get('dependencies')
        policy_evidence = {}
        for key in ('dependencies', 'dependency_ancestry', 'quarantine', 'status_band',
                    'identity_claim', 'relation', 'contract', 'contract_shadow'):
            if key in evidence:
                policy_evidence[key] = evidence[key]
        memberships = con.execute('''SELECT addr FROM identity WHERE logical_id=? AND binary_id=?
            ORDER BY addr LIMIT 2''', (binding['logical_id'], binary_id)).fetchall()
        identities.append({'logicalId': binding['logical_id'], 'method': binding['method'],
            'confidence': binding['confidence'], 'blocked': blocked,
            'evidence': policy_evidence,
            'binaryMembershipUnique': len(memberships) == 1,
            'lineageState': 'recorded_not_revalidated',
            'dependencies': dependencies[:8] if isinstance(dependencies, list) else [],
            'dependenciesTruncated': isinstance(dependencies, list) and len(dependencies) > 8,
            'claimBoundary': 'Recorded cross-build identity; not source or byte-parity proof.'})
    unambiguous = (len(bindings) == 1 and not identities[0]['blocked']
                   and identities[0]['binaryMembershipUnique'])
    return {'binaryId': binary_id, 'addr': addr, 'slug': binary['slug'],
        'name': function['name'] if function else None, 'size': function['size'] if function else None,
        'recorded': function is not None,
        'logicalId': identities[0]['logicalId'] if unambiguous else None,
        'identities': identities, 'identitiesTruncated': len(bindings) > 8,
        'identityState': 'recorded' if unambiguous else 'contested' if bindings else 'not_recorded'}


def paired_callgraph(context, binary_ids, source_binary_id, source_addr, target_binary_id, target_addr):
    """Bounded recorded call neighborhoods for an already chosen correspondence.

    Calls and cross-build identity links are distinct. This read cannot create
    anchors, promote review candidates, or run analysis/matching preparation.
    """
    if (not isinstance(binary_ids, (list, tuple)) or not 1 <= len(binary_ids) <= 2000
            or any(type(value) is not int or not 0 <= value <= MAX_SQLITE_ID for value in binary_ids)
            or any(type(value) is not int or not 0 <= value <= MAX_SQLITE_ID
                   for value in (source_binary_id, source_addr, target_binary_id, target_addr))
            or source_binary_id not in binary_ids or target_binary_id not in binary_ids):
        raise ReviewError('malformed_request')
    ids = sorted(set(binary_ids))
    with _transaction(context, write=False) as con:
        runs = _correspondence_runs(con)
        binaries = {}
        for binary_id in (source_binary_id, target_binary_id):
            binary = con.execute('SELECT id,slug FROM binary WHERE id=? LIMIT 1', (binary_id,)).fetchone()
            if binary is None:
                raise ReviewError('context_changed')
            binaries[binary_id] = binary
        tables = set()
        for row in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')"):
            tables.add(row[0])
        available = 'calledge' in tables
        nodes = {}
        source = _graph_function(con, source_binary_id, source_addr, binaries[source_binary_id])
        target = _graph_function(con, target_binary_id, target_addr, binaries[target_binary_id])
        for center in (source, target):
            if (center['logicalId'] is not None and not _recorded_identity_gate(con,
                    center['identities'][0]['evidence'], center['identities'][0]['evidence'].get('relation') or 'one_to_one', runs)):
                center['logicalId'] = None
                center['identityState'] = 'dependency_unresolved'
            center['truncated'] = {}
            center['totalKnown'] = {}
            for direction, fixed, neighbor in (('callers', 'callee_addr', 'caller_addr'),
                                                ('callees', 'caller_addr', 'callee_addr')):
                rows = con.execute(f'''SELECT DISTINCT {neighbor} FROM calledge
                    WHERE binary_id=? AND {fixed}=? ORDER BY {neighbor} LIMIT 65''',
                    (center['binaryId'], center['addr'])).fetchall() if available else []
                center[direction] = []
                center['truncated'][direction] = len(rows) > 64
                center['totalKnown'][direction] = available and len(rows) <= 64
                for row in rows[:64]:
                    key = (center['binaryId'], row[0])
                    if key not in nodes:
                        nodes[key] = _graph_function(con, key[0], key[1], binaries[key[0]])
                        node = nodes[key]
                        if (node['logicalId'] is not None and not _recorded_identity_gate(con,
                                node['identities'][0]['evidence'], node['identities'][0]['evidence'].get('relation') or 'one_to_one', runs)):
                            node['logicalId'] = None
                            node['identityState'] = 'dependency_unresolved'
                    center[direction].append(nodes[key])
        alignments = []
        ambiguous_ids = set()
        for direction in ('callers', 'callees'):
            left = {}
            right = {}
            for center, grouped in ((source, left), (target, right)):
                for node in center[direction]:
                    if node['logicalId'] is not None:
                        grouped.setdefault(node['logicalId'], []).append(node)
            for logical_id, peers in left.items():
                others = right.get(logical_id, [])
                if len(peers) == len(others) == 1:
                    alignments.append({'direction': direction, 'sourceAddr': peers[0]['addr'],
                        'targetAddr': others[0]['addr'], 'logicalId': logical_id,
                        'kind': 'recorded-identity', 'provenance': [peers[0]['identities'][0], others[0]['identities'][0]]})
                elif others:
                    ambiguous_ids.add(logical_id)
        center_relation = ('recorded-identity' if source['logicalId'] is not None
                           and source['logicalId'] == target['logicalId'] else 'unresolved')
        return {'ok': True, 'binaryIds': ids, 'source': source, 'target': target,
            'alignments': alignments, 'ambiguousLogicalIds': sorted(ambiguous_ids),
            'centerRelation': center_relation,
            'evidenceState': 'recorded_snapshot' if available else 'not_recorded',
            'neighborLimit': 64, 'scope': {'binaryIds': ids},
            'claimBoundary': 'Directed lines are recorded calls. Cross-build links are recorded identity bindings, not byte equivalence. Missing recorded calls do not prove absence.'}


def list_review(context: Context, *, after_id: int = 0, limit: int = 50):
    if (type(after_id) is not int or not 0 <= after_id <= MAX_SQLITE_ID
            or type(limit) is not int or not 1 <= limit <= MAX_PAGE):
        raise ReviewError('malformed_request')
    with _transaction(context, write=False) as con:
        # Counting every candidate and sorting the status/score index made a
        # bounded review page time out before it could return a single row.
        # Page by the primary-key cursor; exact corpus totals are not needed.
        rows = con.execute("SELECT * FROM match NOT INDEXED WHERE status='review' AND id>? ORDER BY id LIMIT ?",
                           (after_id, limit + 1)).fetchall()
        return _review_page(con, context, rows, limit)


def validate_entries(entries):
    """Validate and copy a bounded request before catalog admission or mutation."""
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_BATCH:
        raise ReviewError('malformed_request')
    seen = set()
    result = []
    for item in entries:
        if not isinstance(item, dict) or set(item) != {'matchId', 'token', 'decision'}:
            raise ReviewError('malformed_request')
        match_id = item['matchId']
        if type(match_id) is not int or not 1 <= match_id <= MAX_SQLITE_ID:
            raise ReviewError('malformed_request')
        if match_id in seen:
            raise ReviewError('duplicate_match', match_id=match_id)
        seen.add(match_id)
        token = item['token']
        if (not isinstance(token, str) or len(token) != 67 or not token.startswith('v1:')
                or any(char not in '0123456789abcdef' for char in token[3:])
                or item['decision'] not in ('accept', 'reject')):
            raise ReviewError('malformed_request')
        result.append(dict(item))
    return result


def decide_review(context: Context, entries, *, trusted_actor: str | None = None):
    """Commit all exact observed decisions, or none, including their audits.

    The caller owns admission and a selection lock for this context throughout
    the call. Only a server-authenticated identity belongs in trusted_actor.
    """
    selected = validate_entries(entries)
    if trusted_actor is not None and (not isinstance(trusted_actor, str) or len(trusted_actor) > 256):
        raise ReviewError('malformed_actor')
    with _transaction(context, write=True) as con:
        checked = []
        for item in selected:
            row = con.execute('SELECT * FROM match WHERE id=?', (item['matchId'],)).fetchone()
            if row is None:
                raise ReviewError('stale_basis', match_id=item['matchId'])
            basis, token = _basis(con, context, row)
            if row['status'] != 'review' or token != item['token']:
                raise ReviewError('stale_basis', match_id=item['matchId'])
            checked.append((item, basis, token))
        result = []
        for item, basis, token in checked:
            status = 'verify' if item['decision'] == 'accept' else 'rejected'
            con.execute('UPDATE match SET status=? WHERE id=?', (status, item['matchId']))
            revision = _revision(con, 'match', item['matchId'])
            con.execute('''INSERT INTO match_review_audit
                (match_id,incarnation,selection,decision,old_status,new_status,
                 old_revision,new_revision,observed_token,basis_json,trusted_actor,decided_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (item['matchId'], basis['incarnation'], context.selection, item['decision'],
                 basis['match']['status'], status, basis['revision'], revision, token,
                 _canonical(basis).decode('utf-8'), trusted_actor,
                 datetime.now(timezone.utc).isoformat()))
            result.append({'matchId': item['matchId'], 'status': status, 'revision': revision})
        return {'ok': True, 'decisions': result, 'acceptance': 'review-decision-only'}

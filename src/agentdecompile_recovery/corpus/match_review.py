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


def _basis(con, context, row):
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
    binaries = []
    for binary_id in (candidate['src_binary'], candidate['dst_binary']):
        binary = con.execute('SELECT * FROM binary WHERE id=?', (binary_id,)).fetchone()
        if binary is None:
            raise ReviewError('corrupt_basis')
        binaries.append({'row': dict(binary), 'revision': _revision(con, 'binary', binary_id)})
    incarnation = con.execute('SELECT incarnation FROM match_review_control WHERE singleton=1').fetchone()[0]
    basis = {'schema': 'match-review-basis/v1', 'incarnation': incarnation,
             'context': {'path': str(context.path), 'device': context.device,
                         'inode': context.inode, 'selection': context.selection},
             'revision': _revision(con, 'match', candidate['id']),
             'match': candidate, 'binaries': binaries}
    token = 'v1:' + hashlib.sha256(_canonical(basis)).hexdigest()
    return basis, token


def list_review(context: Context, *, after_id: int = 0, limit: int = 50):
    if (type(after_id) is not int or not 0 <= after_id <= MAX_SQLITE_ID
            or type(limit) is not int or not 1 <= limit <= MAX_PAGE):
        raise ReviewError('malformed_request')
    with _transaction(context, write=False) as con:
        total = con.execute("SELECT count(*) FROM match WHERE status='review'").fetchone()[0]
        rows = con.execute("SELECT * FROM match WHERE status='review' AND id>? ORDER BY id LIMIT ?",
                           (after_id, limit + 1)).fetchall()
        page = []
        for row in rows[:limit]:
            basis, token = _basis(con, context, row)
            page.append({'match': basis['match'], 'binaries': basis['binaries'], 'token': token})
        return {'ok': True, 'rows': page, 'total': total,
                'nextAfterId': page[-1]['match']['id'] if len(rows) > limit else None,
                'selection': context.selection}


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

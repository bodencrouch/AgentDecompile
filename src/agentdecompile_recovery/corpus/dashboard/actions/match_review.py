"""Catalog-owned review adapter. No caller-provided actor attribution is trusted."""
from __future__ import annotations

import json
from pathlib import Path

from ...match_review import ReviewError, validate_entries, list_review, decide_review
from ..common import match_review_context, review_error_status

MAX_REQUEST_BYTES = 128 * 1024


def resource_paths(database):
    try:
        path = Path(database).resolve(strict=True)
        paths = [path, *(Path(str(path) + suffix) for suffix in ('-wal', '-shm', '-journal'))]
        for item in paths:
            if item.is_symlink() or (item.exists() and (not item.is_file() or item.stat().st_nlink != 1)):
                raise ReviewError('unsafe_database_alias')
        return paths
    except (OSError, RuntimeError) as exc:
        raise ReviewError('unavailable') from exc


def freeze(params, *, decide):
    """Validate and pin at submission, never choose a different database at dispatch."""
    if not isinstance(params, dict):
        raise ReviewError('malformed_request')
    try:
        size = len(json.dumps(params, allow_nan=False).encode())
    except (TypeError, ValueError) as exc:
        raise ReviewError('malformed_request') from exc
    if size > MAX_REQUEST_BYTES:
        raise ReviewError('request_too_large')
    selection = params.get('selection', '')
    if not isinstance(selection, str) or (decide and not selection):
        raise ReviewError('malformed_context')
    entries = validate_entries(params.get('entries')) if decide else None
    if not decide:
        from ...match_review import MAX_SQLITE_ID
        if (type(params.get('after_id', 0)) is not int or not 0 <= params.get('after_id', 0) <= MAX_SQLITE_ID
                or type(params.get('limit', 50)) is not int or not 1 <= params.get('limit', 50) <= 100):
            raise ReviewError('malformed_request')
    if not isinstance(params.get('db'), str) or not params['db']:
        raise ReviewError('malformed_context')
    with match_review_context(selection, params['db']) as context:
        if decide:
            resource_paths(context.path)
        result = {'db': str(context.path), 'selection': context.selection,
                  'device': context.device, 'inode': context.inode}
        if decide:
            result['entries'] = entries
        else:
            result.update(after_id=params.get('after_id', 0), limit=params.get('limit', 50))
        return result


def execute(params, cancel, *, decide):
    try:
        with match_review_context(params['selection'], params['db']) as context:
            if (context.device, context.inode) != (params['device'], params['inode']):
                raise ReviewError('context_changed')
            if cancel.is_set():
                raise ReviewError('cancelled')
            if decide:
                resource_paths(context.path)
                result = decide_review(context, params['entries'], trusted_actor=None)
            else:
                result = list_review(context, after_id=params['after_id'], limit=params['limit'])
        return 0, json.dumps(result)
    except ReviewError as exc:
        return 1, json.dumps(exc.result())


def submit_http(body, *, batch):
    from .jobs import start_job
    try:
        expected = {'entries', 'selection'} if batch else {'match_id', 'token', 'decision', 'selection'}
        if not isinstance(body, dict) or set(body) != expected:
            raise ReviewError('malformed_request')
        if not isinstance(body['selection'], str) or not 1 <= len(body['selection']) <= 256:
            raise ReviewError('malformed_context')
        entries = body['entries'] if batch else [
            {'matchId': body['match_id'], 'token': body['token'], 'decision': body['decision']}]
        entries = validate_entries(entries)
        # Holding the same guard through start_job also pins admission defaults.
        with match_review_context(body['selection']) as context:
            result, status = start_job('review.decide', {
                'db': str(context.path), 'selection': body['selection'], 'entries': entries})
        if status == 202:
            result.update(pending=True, job_id=result['job']['id'])
        return result, status
    except ReviewError as exc:
        return exc.result(), review_error_status(exc)

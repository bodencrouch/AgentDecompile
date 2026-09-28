"""Read-only per-build progress projections for both dashboard surfaces."""
from __future__ import annotations

import time

from .common import corpus_read_snapshot, CorpusReadError
from ..objdiff_report import build_report


def progress_report(*, slug: str, version: str = '', corpus_identity: str = '') -> dict:
    if not slug:
        return {'ok': True, 'status': 'unselected', 'reason': 'Select a recorded binary to read its progress report'}
    try:
        with corpus_read_snapshot(corpus_identity) as (con, corpus):
            deadline = time.monotonic() + 5
            con.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            row = con.execute('SELECT id,content_sha256 FROM binary WHERE slug=?', (slug,)).fetchone()
            if not row:
                return {'ok': False, 'error': 'Selected binary is not present in this corpus'}
            report = build_report(con, row[0], version=version or row[1])
            return {'ok': True, 'status': 'available', 'corpus': corpus,
                    'report': {key:value for key,value in report.items() if key not in ('units','assignments')},
                    'acceptance_provider': {'status':'unavailable','reason':'No independent byte-acceptance provider is connected to this projection; source classifications remain advisory'}}
    except (CorpusReadError, ValueError) as exc:
        return {'ok': False, 'status': 'unavailable', 'error': str(exc)}

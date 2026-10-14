"""Bounded migration of the retired startup compiler watchdog.

This does not recover a quarantined module, rerun module code, or interrupt
arbitrary threads. Admission must stay paused until the old thread exits.
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import marshal
import os
from pathlib import Path
import sys
import threading
import types


def retire_legacy_watchdog() -> dict:
    from .actions import jobs
    import inplace_hotreload
    from codefind import conform

    if 'lane:undeclared' not in jobs.admission_status().get('paused', {}):
        raise ValueError('Pause lane:undeclared before retiring its legacy watchdog')
    owner = inplace_hotreload._active
    if owner is None or not owner.running:
        raise ValueError('No active in-process reloader owns this runtime')
    module_name = 'agentdecompile_recovery.unified_pages'
    module = sys.modules.get(module_name)
    if module is None or not getattr(module, '__file__', None):
        raise ValueError('The legacy startup module is not loaded')
    path = Path(module.__file__).resolve(strict=True)
    if not any(path.is_relative_to(root) for root in owner.roots):
        raise ValueError('The loaded module is outside the reloader source roots')
    with owner.lock:
        matches = []
        for thread in threading.enumerate():
            if thread.name == 'text-permuter-autostart' and thread.is_alive():
                matches.append(thread)
        if not matches:
            return {'ok': True, 'pid': os.getpid(), 'state': 'absent',
                    'threadRetired': True, 'moduleRecovered': False}
        if len(matches) != 1:
            raise ValueError('Legacy watchdog ownership is ambiguous')
        thread = matches[0]
        watchdog = getattr(thread, '_target', None)
        prefix = 'mount_unified_pages.<locals>.autostart_text_permuter.<locals>.'
        if (not isinstance(watchdog, types.FunctionType)
                or watchdog.__module__ != module_name
                or watchdog.__qualname__ != prefix + 'watchdog'
                or Path(watchdog.__code__.co_filename).resolve() != path):
            raise ValueError('The named thread is not the captured legacy watchdog')
        cells = dict(zip(watchdog.__code__.co_freevars, watchdog.__closure__ or ()))
        launch = cells['try_launch_once'].cell_contents
        if (not isinstance(launch, types.FunctionType)
                or launch.__module__ != module_name
                or launch.__qualname__ != prefix + 'try_launch_once'
                or Path(launch.__code__.co_filename).resolve() != path):
            raise ValueError('Legacy admission callable identity does not match')
        if launch.__globals__.get('SystemExit', builtins.SystemExit) is not builtins.SystemExit:
            raise ValueError('Retirement exception identity was replaced')
        with path.open('rb') as stream:
            source = stream.read(2 * 1024**2 + 1)
        if len(source) > 2 * 1024**2:
            raise ValueError('Retirement source exceeds the bounded source limit')
        tree = ast.parse(source, filename=str(path))
        nodes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'try_launch_once':
                nodes.append(node)
        if (len(nodes) != 1 or not isinstance(nodes[0].body[0], ast.Raise)
                or not isinstance(nodes[0].body[0].exc, ast.Name)
                or nodes[0].body[0].exc.id != 'SystemExit'
                or nodes[0].body[0].cause is not None):
            raise ValueError('Source does not contain the explicit retirement guard')
        pending = [compile(tree, str(path), 'exec')]
        replacements = []
        while pending:
            code = pending.pop()
            if code.co_qualname == launch.__qualname__:
                replacements.append(code)
            for constant in code.co_consts:
                if isinstance(constant, types.CodeType):
                    pending.append(constant)
        if len(replacements) != 1:
            raise ValueError('Retirement code was not uniquely preserved by compilation')
        replacement = replacements[0]
        before = launch.__code__
        if (replacement.co_freevars != before.co_freevars
                or replacement.co_cellvars != before.co_cellvars
                or replacement.co_argcount != before.co_argcount
                or replacement.co_kwonlyargcount != before.co_kwonlyargcount
                or replacement.co_posonlyargcount != before.co_posonlyargcount
                or replacement.co_flags != before.co_flags):
            raise ValueError('Retirement callable layout is incompatible')
        # Conform this captured callable only, never the damaged CodeFile tree.
        conform(launch, replacement)
        return {'ok': True, 'pid': os.getpid(), 'state': 'retirement-requested',
                'threadId': thread.ident, 'threadRetired': False,
                'moduleRecovered': False, 'sourceSha256': hashlib.sha256(source).hexdigest(),
                'previousCodeSha256': hashlib.sha256(marshal.dumps(before)).hexdigest(),
                'nextAction': 'Observe thread exit before resuming admission'}

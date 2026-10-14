"""Execute a file script on a program whose lifecycle is owned by the provider."""
from pathlib import Path
import threading

_BUNDLE_LOCK = threading.RLock()


def run_ghidra_script_on_program(program, monitor, script_path, script_args=()):
    from generic.jar import ResourceFile
    from ghidra.app.script import GhidraScriptUtil, GhidraState, ScriptControls
    from java.io import PrintWriter, StringWriter

    if program is None or monitor is None:
        raise RuntimeError('Script execution requires an owned program and cancellable monitor.')
    path = Path(script_path).resolve(strict=True)
    output, errors = StringWriter(), StringWriter()
    writer, error_writer = PrintWriter(output, True), PrintWriter(errors, True)
    # Registration and cleanup must not race another invocation of this adapter.
    with _BUNDLE_LOCK:
        host = GhidraScriptUtil.acquireBundleHostReference()
        added = None
        try:
            directory = ResourceFile(str(path.parent))
            if host.getExistingGhidraBundle(directory) is None:
                added = host.add(directory, True, False)
            monitor.checkCancelled()
            source = ResourceFile(str(path))
            provider = GhidraScriptUtil.getProvider(source)
            if provider is None:
                raise RuntimeError('No Ghidra script provider for ' + str(path))
            script = provider.getScriptInstance(source, writer)
            script.setScriptArgs([str(arg) for arg in script_args])
            script.execute(GhidraState(None, None, program, None, None, None),
                           ScriptControls(writer, error_writer, monitor))
            monitor.checkCancelled()
            return {'stdout': str(output), 'stderr': str(errors)}
        except Exception as exc:
            if monitor.isCancelled():
                raise
            raise RuntimeError(f'Ghidra script failed: {exc}\n{output}\n{errors}') from exc
        finally:
            try:
                if added is not None:
                    host.remove(added)
            finally:
                GhidraScriptUtil.releaseBundleHostReference()

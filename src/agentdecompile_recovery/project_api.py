"""Small, versioned, loopback-only project-source resolution API.

Lifecycle mutations are deliberately not advertised here until they are bound
to the durable job and native project ownership coordinators.
"""

from __future__ import annotations

import ipaddress
import json
from urllib.parse import parse_qs
from typing import Any

_PREFIX = "/api/v1/projects"
_MAX_BODY = 1024 * 1024


def _response(payload: dict[str, Any], status: int = 200) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return status, [(b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(data)).encode("ascii")),
                    (b"cache-control", b"no-store")], data


def _resolve(locator: str) -> dict[str, Any]:
    if not locator.strip():
        return {"ok": False, "error": "A project locator is required."}
    from agentdecompile_recovery.corpus.ghidra_project import inspect_locator

    result = inspect_locator(locator)
    if not result.get("ok"):
        return result
    return {"ok": True, "apiVersion": 1, "project": result,
            "readOnly": True, "next": "native lifecycle operations are not yet registered"}


def _binary_scope(query):
    from agentdecompile_recovery.corpus.match_review import ReviewError
    raw = (query.get("binary_ids") or [""])[0].split(",")
    if not raw or len(raw) > 2000 or any(not v.isascii() or not v.isdecimal() or len(v) > 19 or not 0 < int(v) <= (1 << 63) - 1 for v in raw):
        raise ReviewError("malformed_request")
    return sorted(set(map(int, raw)))


async def dispatch(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """Handle only the versioned source resolver; do not mutate project state."""
    client = (scope.get("client") or ("", 0))[0]
    try:
        local = ipaddress.ip_address(client).is_loopback
    except ValueError:
        local = False
    if not local:
        status, headers, body = _response({"ok": False, "error": "Project API is loopback-only."}, 403)
    else:
        method = str(scope.get("method") or "GET").upper()
        path = str(scope.get("path") or "").rstrip("/") or "/"
        query = parse_qs((scope.get("query_string") or b"").decode("latin1"))
        if method == "GET" and path == _PREFIX:
            status, headers, body = _response({"ok": True, "apiVersion": 1,
                "capabilities": {"resolve": "read-only"},
                "sources": [".gpr + .rep", ".rep", "shared repository folder",
                            "ghidra://", "http://", "https://", ".gar", ".gzf"]})
        elif method == "GET" and path == _PREFIX + "/resolve":
            result = _resolve((query.get("locator") or [""])[0])
            status, headers, body = _response(result, 200 if result.get("ok") else 400)
        elif method == "GET" and path in {_PREFIX + "/match-review", _PREFIX + "/correspondence"}:
            query["_correspondence"] = [path == _PREFIX + "/correspondence"]
            import asyncio
            from agentdecompile_recovery.corpus.dashboard.common import match_review_context, review_error_status
            from agentdecompile_recovery.corpus.match_review import ReviewError, list_review_scoped

            def read_matches():
                from agentdecompile_recovery.corpus.dashboard.common import corpus_file_identity
                def integer(name, default, maximum):
                    value = (query.get(name) or [default])[0]
                    if not value.isascii() or not value.isdecimal() or len(value) > 19 or int(value) > maximum:
                        raise ReviewError("malformed_request")
                    return int(value)
                binary_ids = _binary_scope(query)
                if ("binary_id" in query) != ("addr" in query):
                    raise ReviewError("malformed_request")
                binary_id = integer("binary_id", "0", (1 << 63) - 1) if "binary_id" in query else None
                addr = integer("addr", "0", (1 << 63) - 1) if "addr" in query else None
                if binary_id and binary_id not in binary_ids:
                    raise ReviewError("malformed_request")
                with match_review_context((query.get("selection") or [""])[0]) as context:
                    expected = (query.get("corpus_identity") or [""])[0]
                    if not expected or corpus_file_identity(context.path)['identity'] != expected:
                        raise ReviewError("context_changed")
                    if query["_correspondence"][0]:
                        from agentdecompile_recovery.corpus.match_review import list_correspondence_scoped
                        result = list_correspondence_scoped(context, integer("after_id", "0", (1 << 63) - 1),
                            integer("limit", "50", 100), binary_ids, binary_id, addr)
                    else:
                        result = list_review_scoped(context, integer("after_id", "0", (1 << 63) - 1),
                            integer("limit", "50", 100), binary_ids, binary_id, addr)
                    result['corpusIdentity'] = expected
                    return result
            try:
                result = await asyncio.to_thread(read_matches)
                status, headers, body = _response(result)
            except ReviewError as exc:
                status, headers, body = _response(exc.result(), review_error_status(exc))
        elif method == "GET" and path == _PREFIX + "/functions":
            import asyncio
            from agentdecompile_recovery.corpus.dashboard.common import match_review_context, review_error_status
            from agentdecompile_recovery.corpus.match_review import ReviewError

            def read_functions():
                from agentdecompile_recovery.corpus.dashboard.common import corpus_file_identity
                from agentdecompile_recovery.corpus.dashboard.project_universe import query_project_functions
                binary_ids = _binary_scope(query)
                raw_offset, raw_limit = (query.get("offset") or ["0"])[0], (query.get("limit") or ["100"])[0]
                if any(not v.isascii() or not v.isdecimal() or len(v) > 7 for v in (raw_offset, raw_limit)):
                    raise ReviewError("malformed_request")
                with match_review_context() as context:
                    expected = (query.get("corpus_identity") or [""])[0]
                    if not expected or corpus_file_identity(context.path)['identity'] != expected:
                        raise ReviewError("context_changed")
                    result = query_project_functions(context, binary_ids, (query.get("q") or [""])[0], int(raw_offset), int(raw_limit))
                    result['corpusIdentity'] = expected
                    return result
            try:
                result = await asyncio.to_thread(read_functions)
                status, headers, body = _response(result)
            except ReviewError as exc:
                status, headers, body = _response(exc.result(), review_error_status(exc))
        elif method == "GET" and path == _PREFIX + "/call-comparison":
            import asyncio
            from agentdecompile_recovery.corpus.dashboard.common import match_review_context, review_error_status
            from agentdecompile_recovery.corpus.match_review import ReviewError

            def read_calls():
                from agentdecompile_recovery.corpus.dashboard.common import corpus_file_identity
                from agentdecompile_recovery.corpus.match_review import paired_callgraph
                binary_ids = _binary_scope(query)
                values = []
                for name in ("source_binary_id", "source_addr", "target_binary_id", "target_addr"):
                    raw_value = (query.get(name) or [""])[0]
                    if not raw_value.isascii() or not raw_value.isdecimal() or len(raw_value) > 19 or int(raw_value) > (1 << 63) - 1:
                        raise ReviewError("malformed_request")
                    values.append(int(raw_value))
                if values[0] not in binary_ids or values[2] not in binary_ids:
                    raise ReviewError("malformed_request")
                with match_review_context() as context:
                    expected = (query.get("corpus_identity") or [""])[0]
                    if not expected or corpus_file_identity(context.path)['identity'] != expected:
                        raise ReviewError("context_changed")
                    result = paired_callgraph(context, binary_ids, *values)
                    result['corpusIdentity'] = expected
                    return result
            try:
                result = await asyncio.to_thread(read_calls)
                status, headers, body = _response(result)
            except ReviewError as exc:
                status, headers, body = _response(exc.result(), review_error_status(exc))
        elif method == "POST" and path == _PREFIX + "/resolve":
            chunks: list[bytes] = []
            size = 0
            while True:
                event = await receive()
                if event.get("type") != "http.request":
                    continue
                chunk = event.get("body", b"")
                size += len(chunk)
                if size > _MAX_BODY:
                    status, headers, body = _response({"ok": False, "error": "Request body exceeds 1 MiB."}, 413)
                    break
                chunks.append(chunk)
                if not event.get("more_body", False):
                    try:
                        request = json.loads(b"".join(chunks) or b"{}")
                        if not isinstance(request, dict):
                            raise ValueError("request must be a JSON object")
                        result = _resolve(str(request.get("locator") or ""))
                        status, headers, body = _response(result, 200 if result.get("ok") else 400)
                    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                        status, headers, body = _response({"ok": False, "error": str(exc)}, 400)
                    break
        elif path in {_PREFIX, _PREFIX + "/resolve"}:
            status, headers, body = _response({"ok": False, "error": "Method not allowed."}, 405)
            headers.append((b"allow", b"GET, POST" if path.endswith("/resolve") else b"GET"))
        else:
            status, headers, body = _response({"ok": False, "error": "Project API route not found."}, 404)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})

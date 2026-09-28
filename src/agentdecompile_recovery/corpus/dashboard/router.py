"""FastAPI router for the corpus dashboard. Does not bind a port."""

from __future__ import annotations

import asyncio
import mimetypes
import os
from urllib.parse import quote, urlencode
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response

MAX_UPLOAD_BYTES = 512 * 1024 * 1024


async def _read_upload_bytes(upload: object) -> tuple[bytes | None, str | None]:
    if not hasattr(upload, "read"):
        return None, "file is required"
    data = await upload.read()  # type: ignore[union-attr]
    if len(data) > MAX_UPLOAD_BYTES:
        return None, f"upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB limit"
    return data, None


from agentdecompile_recovery.corpus.dashboard.pages import (
    CLAIM,
    PAGE_INDEX,
    STATIC_ROOT,
    WORKSPACE_NAME,
    graph_to_function_target,
    query_from_mapping,
    render_page,
)

_ide_url = (
    os.environ.get("AGENTDECOMPILE_WEB_IDE_URL")
    or os.environ.get("VITE_AGENTDECOMPILE_WEB_IDE_URL")
    or ""
).strip()
try:
    _ide_parts = urlsplit(_ide_url)
except ValueError:
    # A malformed optional editor URL must not prevent the dashboard from
    # importing.  The runtime-config endpoint applies the same safe fallback.
    _ide_parts = None
_ide_origin = (
    f"{_ide_parts.scheme}://{_ide_parts.netloc}"
    if _ide_parts and _ide_parts.scheme in {"http", "https"} and _ide_parts.netloc
    else ""
)
_frame_src = f"; frame-src 'self' {_ide_origin}" if _ide_origin else ""

SECURITY_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self' https://api.openai.com https://api.anthropic.com; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        + _frame_src
    ),
}


def _html(body: str, status: int = 200, title: str | None = None) -> HTMLResponse:
    page = body if "<!doctype html>" in body[:80].lower() else render_page(body, title or WORKSPACE_NAME)
    response = HTMLResponse(page, status_code=status)
    for key, value in SECURITY_HEADERS.items():
        response.headers[key] = value
    return response


def _static(name: str) -> Response:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return PlainTextResponse("not found", status_code=404)
    target = STATIC_ROOT / name
    try:
        payload = target.read_bytes()
    except OSError:
        return PlainTextResponse("not found", status_code=404)
    ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if ctype.startswith("text/"):
        ctype = f"{ctype}; charset=utf-8"
    response = Response(content=payload, media_type=ctype)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def create_dashboard_router() -> APIRouter:
    """Routes under /dashboard. Compatibility aliases stay in unified_pages."""
    router = APIRouter(tags=["dashboard"])
    from agentdecompile_recovery.corpus.dashboard.actions.openapi import create_actions_api_router

    router.include_router(create_actions_api_router())
    from agentdecompile_recovery.corpus.dashboard.react_api import create_react_router
    router.include_router(create_react_router())

    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_home(request: Request) -> Response:
        from agentdecompile_recovery.corpus.dashboard.workbench import render_workbench

        from agentdecompile_recovery.corpus.dashboard.react_api import react_entry_redirect

        # The MCP dashboard is the static delivery surface. Keep React opt-in
        # so opening /dashboard never unexpectedly switches workbenches.
        if request.query_params.get("mode", "static") == "static":
            response = HTMLResponse(render_workbench(static_mode=True))
            for key, value in SECURITY_HEADERS.items():
                response.headers[key] = value
            return response

        return react_entry_redirect(request)

    @router.get("/dashboard/explorer")
    async def dashboard_explorer() -> HTMLResponse:
        from agentdecompile_recovery.corpus.dashboard.explorer import render_explorer

        response = HTMLResponse(render_explorer())
        for key, value in SECURITY_HEADERS.items():
            response.headers[key] = value
        return response

    @router.get("/dashboard/settings/notifications", response_class=HTMLResponse)
    async def dashboard_settings_notifications() -> HTMLResponse:
        from agentdecompile_recovery.corpus.dashboard.settings_page import render_notifications_page
        response = HTMLResponse(render_notifications_page())
        for key, value in SECURITY_HEADERS.items():
            response.headers[key] = value
        return response

    @router.get("/dashboard/api/settings/notifications")
    async def get_notification_settings() -> JSONResponse:
        from agentdecompile_recovery.corpus import discord_notify
        s = discord_notify.load_settings()
        hook = s.get("discord_webhook") or ""
        # never return the full secret; show only whether one is set + a mask
        masked = (hook[:36] + "…" + hook[-6:]) if len(hook) > 46 else ("set" if hook else "")
        return JSONResponse({"configured": bool(hook), "masked": masked,
                             "lastAnnouncedByteExact": s.get("last_announced_byte_exact")})

    @router.post("/dashboard/api/settings/notifications")
    async def set_notification_settings(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus import discord_notify
        try:
            body = await request.json()
        except Exception:
            body = {}
        hook = str((body or {}).get("discord_webhook") or "").strip()
        action = str((body or {}).get("action") or "save")
        if action == "test":
            res = discord_notify.post("✅ AgentDecompile webhook connected — "
                                      "you'll get plain-language progress + ETAs here.")
            return JSONResponse({"ok": bool(res.get("ok")), "detail": res})
        if hook and not hook.startswith("https://"):
            return JSONResponse({"ok": False, "error": "webhook must be an https URL"}, status_code=400)
        discord_notify.save_settings({"discord_webhook": hook})
        return JSONResponse({"ok": True, "configured": bool(hook)})

    @router.get("/dashboard/overview")
    async def dashboard_overview(request: Request) -> RedirectResponse:
        """Keep session tabs on the static workbench; overview is a window there."""
        qs = str(request.query_params)
        target = "/dashboard?window=wb-overview"
        if qs:
            target = f"{target}&{qs}"
        return RedirectResponse(target, status_code=302)

    @router.get("/dashboard/overview-fragment")
    async def dashboard_overview_fragment(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.pages import session_overview_json

        slugs = list(request.query_params.getlist("slug")) + list(
            request.query_params.getlist("binary")
        )
        programs = list(request.query_params.getlist("program"))
        return JSONResponse(session_overview_json(slugs, programs=programs))

    @router.get("/dashboard/overview-corpus")
    async def dashboard_overview_corpus() -> RedirectResponse:
        return RedirectResponse("/dashboard?window=wb-overview", status_code=302)

    @router.get("/dashboard/healthz")
    async def dashboard_healthz() -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.pages import render_status_probes

        return JSONResponse(
            {
                "ok": True,
                "service": "dashboard",
                "pages": PAGE_INDEX,
                "claimBoundary": CLAIM,
                "probes": render_status_probes(),
            }
        )

    # Browse used to be a second page. It is a set of workbench windows now, so
    # every old browse link lands on the workbench with that window selected.
    BROWSE_WINDOW = {
        "functions": "wb-fnbrowse",
        "logical": "wb-logical",
        "review": "wb-review",
        "graph": "wb-graph",
        "builds": "wb-corpus",
    }

    def _workbench_redirect(request: Request, block: str) -> RedirectResponse:
        window = BROWSE_WINDOW.get(block, "wb-fnbrowse")
        parts = [f"window={window}"]
        for key, value in request.query_params.multi_items():
            if key in {"window", "partial"}:
                continue
            parts.append(f"{quote(str(key))}={quote(str(value))}")
        return RedirectResponse("/dashboard?" + "&".join(parts), status_code=302)

    def _browse_redirect(request: Request, fragment: str) -> RedirectResponse:
        return _workbench_redirect(request, fragment)

    @router.get("/dashboard/functions")
    async def dashboard_functions(request: Request) -> RedirectResponse:
        return _workbench_redirect(request, "functions")

    @router.get("/dashboard/browse-block")
    async def dashboard_browse_block(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.pages import browse_block_json

        payload, status = browse_block_json(
            request.query_params.get("block") or "functions",
            query_from_mapping(request.query_params),
        )
        return JSONResponse(payload, status_code=status)

    @router.get("/dashboard/function/{slug}/{addr}")
    async def dashboard_function(slug: str, addr: str, request: Request) -> RedirectResponse:
        parts = ["window=wb-fnbrowse", f"binary={quote(slug, safe='')}", f"addr={quote(addr, safe='')}"]
        for key, value in request.query_params.multi_items():
            if key in {"window", "partial", "binary", "addr"}:
                continue
            parts.append(f"{quote(str(key))}={quote(str(value))}")
        return RedirectResponse("/dashboard?" + "&".join(parts), status_code=302)

    @router.get("/dashboard/function-open")
    async def dashboard_function_open(request: Request) -> RedirectResponse:
        return RedirectResponse(graph_to_function_target(query_from_mapping(request.query_params)), status_code=302)

    @router.get("/dashboard/api/workbench/browse")
    async def workbench_browse(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import browse_sources

        payload = await asyncio.to_thread(browse_sources, str(request.query_params.get("path") or ""))
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.get("/dashboard/api/workbench/classify")
    async def workbench_classify(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import classify_source

        payload = await asyncio.to_thread(
            classify_source,
            str(request.query_params.get("locator") or request.query_params.get("path") or ""),
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.get("/dashboard/api/workbench/ghidra-defaults")
    async def workbench_ghidra_defaults() -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import ghidra_shared_defaults

        return JSONResponse(ghidra_shared_defaults())

    @router.get("/dashboard/api/workbench/context")
    async def workbench_context_api(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import workbench_context_payload

        qp = request.query_params
        payload = await asyncio.to_thread(workbench_context_payload,
            program=str(qp.get("program") or ""),
            slug=str(qp.get("slug") or qp.get("binary") or ""),
            locator=str(qp.get("locator") or ""),
        )
        return JSONResponse(payload)

    @router.get("/dashboard/api/workbench/inspect")
    async def workbench_inspect(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import inspect_source

        payload = await asyncio.to_thread(inspect_source, str(request.query_params.get("locator") or ""))
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.post("/dashboard/api/workbench/stage-drop")
    async def workbench_stage_drop(request: Request) -> JSONResponse:
        import json

        from agentdecompile_recovery.corpus.dashboard.workbench import stage_dropped_files

        form = await request.form()
        uploads = form.getlist("file")
        paths_raw = form.get("paths") or "[]"
        try:
            paths = json.loads(str(paths_raw)) if paths_raw else []
        except (TypeError, json.JSONDecodeError):
            paths = []
        if not isinstance(paths, list):
            paths = []
        items: list[tuple[str, bytes]] = []
        for index, upload in enumerate(uploads):
            data, err = await _read_upload_bytes(upload)
            if err:
                return JSONResponse({"ok": False, "error": err}, status_code=400)
            if data is None:
                continue
            if index < len(paths) and paths[index]:
                rel = str(paths[index])
            else:
                rel = getattr(upload, "filename", None) or f"file-{index}"
            items.append((rel, data))
        if not items:
            return JSONResponse({"ok": False, "error": "file is required"}, status_code=400)
        payload = await asyncio.to_thread(stage_dropped_files, items)
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.post("/dashboard/api/workbench/resolve-drop")
    async def workbench_resolve_drop(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import resolve_dropped_source

        body = await request.json()
        payload = await asyncio.to_thread(
            resolve_dropped_source,
            str(body.get("name") or ""),
            list(body.get("relativePaths") or body.get("relative_paths") or []),
            staging_id=str(body.get("staging_id") or body.get("stagingId") or ""),
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.post("/dashboard/api/workbench/projects")
    async def workbench_create_project(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import create_ghidra_project

        body = await request.json()
        payload = await asyncio.to_thread(
            create_ghidra_project,
            str(body.get("name") or "Project"),
            str(body.get("destination") or ""),
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.post("/dashboard/api/workbench/save")
    async def workbench_save_project(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import save_current_project

        body = await request.json()
        payload = await asyncio.to_thread(save_current_project, str(body.get("locator") or ""))
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.post("/dashboard/api/workbench/save-as")
    async def workbench_save_project_as(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import save_project_as_kind

        body = await request.json()
        payload = await asyncio.to_thread(
            save_project_as_kind,
            str(body.get("locator") or ""),
            target=str(body.get("target") or ""),
            name=str(body.get("name") or ""),
            dest=str(body.get("dest") or body.get("path") or ""),
            url=str(body.get("url") or ""),
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.get("/dashboard/api/workbench/sessions")
    async def workbench_sessions() -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import list_sessions

        payload = await asyncio.to_thread(list_sessions)
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.put("/dashboard/api/workbench/sessions")
    async def workbench_save_sessions(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import write_sessions

        payload = await asyncio.to_thread(write_sessions, await request.json())
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.get("/dashboard/api/workbench/workspace-state")
    async def workbench_workspace_state() -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workspace_state import load_state

        return JSONResponse({"ok": True, **await asyncio.to_thread(load_state)})

    @router.patch("/dashboard/api/workbench/workspace-state")
    async def workbench_patch_workspace_state(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workspace_state import patch_state

        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "error": "JSON object required"}, status_code=400)
        payload = await asyncio.to_thread(patch_state, body)
        if payload.get("ok"):
            return JSONResponse(payload, status_code=200)
        error = str(payload.get("error") or "workspace state update failed")
        status = 413 if "exceeds" in error.lower() or "miB" in error else 400
        return JSONResponse(payload, status_code=status)

    @router.post("/dashboard/api/workbench/programs")
    async def workbench_import_program(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import import_program_into_project

        body = await request.json()
        payload = await asyncio.to_thread(
            import_program_into_project,
            str(body.get("locator") or ""),
            path=str(body.get("path") or body.get("file") or body.get("binary") or body.get("source") or ""),
            program=str(body.get("program") or body.get("source_program") or ""),
            name=str(body.get("name") or body.get("program_name") or ""),
            analyze=bool(body.get("analyze")),
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.delete("/dashboard/api/workbench/programs")
    async def workbench_remove_program(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import remove_program_from_project

        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            body = {}
        payload = await asyncio.to_thread(
            remove_program_from_project,
            str(body.get("locator") or ""),
            str(body.get("program") or body.get("name") or ""),
            confirm=bool(body.get("confirm")),
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.get("/dashboard/api/workbench/corpus-status")
    async def workbench_corpus_status(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.recovery_status import corpus_status

        payload = await asyncio.to_thread(
            corpus_status,
            locator=request.query_params.get("locator") or "",
            program=request.query_params.get("program") or "",
            slug=request.query_params.get("slug") or request.query_params.get("binary") or "",
            scope=request.query_params.get("scope") or "",
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.get("/dashboard/api/workbench/corpus-db")
    async def workbench_corpus_db() -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.common import find_candidate_dbs, live_db, corpus_file_identity

        def _collect() -> dict:
            current = live_db()
            return {
                "ok": True,
                "current": str(current) if current is not None else None,
                "exists": bool(current is not None and current.exists()),
                "corpus": corpus_file_identity(current),
                "candidates": [str(p) for p in find_candidate_dbs()],
            }

        payload = await asyncio.to_thread(_collect)
        return JSONResponse(payload)

    @router.post("/dashboard/api/workbench/corpus-db")
    async def workbench_select_corpus_db(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.common import find_candidate_dbs, live_db, set_runtime_db_path, corpus_file_identity

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "JSON object required"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "error": "JSON object required"}, status_code=400)
        raw_path = str(body.get("path") or "").strip()
        if not raw_path:
            return JSONResponse({"ok": False, "error": "path is required"}, status_code=400)

        def _select() -> dict:
            import sqlite3
            from pathlib import Path

            candidate = Path(raw_path).expanduser()
            if not candidate.is_file():
                return {"ok": False, "error": f"not a file: {candidate}"}
            try:
                con = sqlite3.connect(f"file:{candidate}?mode=ro", uri=True, timeout=5)
                con.execute("PRAGMA schema_version")
                con.close()
            except sqlite3.Error as exc:
                return {"ok": False, "error": f"not a readable sqlite db: {exc}"}
            set_runtime_db_path(candidate)
            current = live_db()
            return {
                "ok": True,
                "current": str(current) if current is not None else None,
                "exists": True,
                "corpus": corpus_file_identity(current),
                "candidates": [str(p) for p in find_candidate_dbs()],
            }

        payload = await asyncio.to_thread(_select)
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.get("/dashboard/api/workbench/binaries")
    async def workbench_binaries(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import list_binaries

        payload = await asyncio.to_thread(list_binaries, str(request.query_params.get("locator") or ""))
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.post("/dashboard/api/workbench/binaries")
    async def workbench_add_binary(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import (
            register_path_binary,
            save_upload_binary,
        )

        content_type = request.headers.get("content-type") or ""
        if "multipart/form-data" in content_type:
            form = await request.form()
            upload = form.get("file")
            data, err = await _read_upload_bytes(upload)
            if err:
                return JSONResponse({"ok": False, "error": err}, status_code=400)
            payload = await asyncio.to_thread(save_upload_binary,
                getattr(upload, "filename", None) or "",
                data,
                slug=str(form.get("slug") or ""),
                role=str(form.get("role") or "member"),
                label=str(form.get("label") or ""),
            )
        else:
            body = await request.json()
            payload = await asyncio.to_thread(register_path_binary,
                str(body.get("path") or ""),
                slug=str(body.get("slug") or ""),
                role=str(body.get("role") or "member"),
                label=str(body.get("label") or ""),
                url=str(body.get("url") or ""),
            )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.delete("/dashboard/api/workbench/binaries/{slug}")
    async def workbench_remove_binary(slug: str, request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import remove_registered_binary

        body: dict = {}
        try:
            body = await request.json()
        except Exception:
            body = {}
        payload = remove_registered_binary(slug, confirm=bool(body.get("confirm")))
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.patch("/dashboard/api/workbench/binaries/{slug}")
    async def workbench_edit_binary(slug: str, request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import update_registered_binary

        body = await request.json()
        payload = update_registered_binary(
            slug,
            role=body.get("role"),
            label=body.get("label"),
            game=body.get("game"),
            platform=body.get("platform"),
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.get("/dashboard/api/workbench/explorer")
    async def workbench_explorer(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.explorer import explorer_snapshot

        payload = await asyncio.to_thread(
            explorer_snapshot,
            request.query_params.get("locator") or request.query_params.get("path") or "",
            request.query_params.get("slug") or request.query_params.get("binary") or "",
            request.query_params.get("program") or "",
        )
        return JSONResponse(payload)

    @router.get("/dashboard/api/workbench/functions")
    async def workbench_functions(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import list_functions

        payload = await asyncio.to_thread(
            list_functions,
            request.query_params.get("slug") or request.query_params.get("binary") or "",
            q=request.query_params.get("q") or "",
            record_filter=request.query_params.get("filter") or "all",
            offset=int(request.query_params.get("offset") or 0),
            limit=request.query_params.get("limit") or "all",
            program=request.query_params.get("program") or "",
            bsim_url=request.query_params.get("bsim_url") or request.query_params.get("bsimUrl") or "",
            locator=request.query_params.get("locator") or request.query_params.get("path") or "",
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.post("/dashboard/api/workbench/ensure-program")
    async def workbench_ensure_program(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import ensure_ghidra_program

        body = await request.json()
        payload = await asyncio.to_thread(
            ensure_ghidra_program,
            str(body.get("locator") or ""),
            str(body.get("program") or body.get("program_path") or ""),
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.get("/dashboard/api/workbench/function")
    async def workbench_function(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import function_detail

        payload = await asyncio.to_thread(
            function_detail,
            request.query_params.get("slug") or request.query_params.get("binary") or "",
            request.query_params.get("addr") or "",
            locator=request.query_params.get("locator") or request.query_params.get("path") or "",
            program=request.query_params.get("program") or "",
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.get("/dashboard/api/workbench/workspace")
    async def workbench_workspace(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import program_workspace

        payload = await asyncio.to_thread(
            program_workspace,
            request.query_params.get("locator") or request.query_params.get("path") or "",
            request.query_params.get("program") or "",
            addr=request.query_params.get("addr") or "",
            slug=request.query_params.get("slug") or request.query_params.get("binary") or "",
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.get("/dashboard/api/workbench/match-status")
    async def workbench_match_status() -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.workbench import match_status

        payload = await asyncio.to_thread(match_status)
        return JSONResponse(payload, status_code=200)

    @router.get("/dashboard/api/workbench/match-review")
    async def workbench_match_review(request: Request) -> JSONResponse:
        from .common import list_match_review, review_error_status
        from ..match_review import ReviewError
        try:
            after = request.query_params.get("after_id", "0")
            limit = request.query_params.get("limit", "50")
            if len(after) > 19 or len(limit) > 3 or not after.isascii() or not after.isdecimal() or not limit.isascii() or not limit.isdecimal():
                raise ReviewError('malformed_request')
            payload = await asyncio.to_thread(list_match_review, after_id=int(after), limit=int(limit))
            return JSONResponse(payload)
        except ReviewError as exc:
            return JSONResponse(exc.result(), status_code=review_error_status(exc))

    async def _review_submit(request: Request, *, batch: bool) -> JSONResponse:
        from .actions.match_review import MAX_REQUEST_BYTES, submit_http
        size = 0
        chunks = []
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_REQUEST_BYTES:
                return JSONResponse({"ok": False, "error": "request_too_large", "refreshRequired": False}, status_code=413)
            chunks.append(chunk)
        try:
            import json
            body = json.loads(b''.join(chunks))
        except (ValueError, UnicodeError):
            return JSONResponse({"ok": False, "error": "malformed_request", "refreshRequired": False}, status_code=400)
        payload, status = await asyncio.to_thread(submit_http, body, batch=batch)
        return JSONResponse(payload, status_code=status)

    @router.post("/dashboard/api/workbench/match-decide")
    async def workbench_match_decide(request: Request) -> JSONResponse:
        return await _review_submit(request, batch=False)

    @router.post("/dashboard/api/workbench/match-decide-batch")
    async def workbench_match_decide_batch(request: Request) -> JSONResponse:
        return await _review_submit(request, batch=True)

    @router.get("/dashboard/api/workbench/recover-status")
    async def workbench_recover_status(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.recovery_status import recover_status

        payload = await asyncio.to_thread(
            recover_status,
            locator=request.query_params.get("locator") or "",
            program=request.query_params.get("program") or "",
            slug=request.query_params.get("slug") or request.query_params.get("binary") or "",
            scope=request.query_params.get("scope") or "",
        )
        return JSONResponse(payload, status_code=200)

    @router.get("/dashboard/api/function-choices")
    async def dashboard_function_choices(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.function_choices import list_function_choices

        payload = list_function_choices(
            request.query_params.get("binary") or request.query_params.get("slug") or "",
            q=request.query_params.get("q") or "",
            around=request.query_params.get("around") or request.query_params.get("addr"),
            limit=request.query_params.get("limit") or 80,
        )
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 400)

    @router.get("/dashboard/logical/{logical_id}")
    async def dashboard_logical_one(logical_id: str) -> RedirectResponse:
        return RedirectResponse(
            "/dashboard?" + urlencode({"window": "wb-logical", "logical_id": logical_id}),
            status_code=302,
        )

    @router.get("/dashboard/binary/{slug}")
    async def dashboard_binary(slug: str) -> RedirectResponse:
        return RedirectResponse(
            "/dashboard?" + urlencode({"window": "wb-corpus", "binary": slug}),
            status_code=302,
        )

    @router.get("/dashboard/graph")
    async def dashboard_graph(request: Request) -> RedirectResponse:
        return RedirectResponse(graph_to_function_target(query_from_mapping(request.query_params)), status_code=302)

    @router.get("/dashboard/artifact")
    async def dashboard_artifact(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.pages import artifact_json

        payload, status = artifact_json(request.query_params.get("p") or "")
        return JSONResponse(payload, status_code=status)

    @router.get("/dashboard/builds")
    async def dashboard_builds(request: Request) -> RedirectResponse:
        return _workbench_redirect(request, "builds")

    @router.get("/dashboard/operations")
    async def dashboard_operations() -> RedirectResponse:
        return RedirectResponse("/dashboard?window=wb-processes", status_code=302)

    @router.get("/dashboard/review")
    async def dashboard_review_redirect(request: Request) -> RedirectResponse:
        return _browse_redirect(request, "review")

    @router.get("/dashboard/actions")
    async def dashboard_actions_redirect() -> RedirectResponse:
        return RedirectResponse("/dashboard#run", status_code=302)

    @router.get("/dashboard/report")
    async def dashboard_report_redirect() -> RedirectResponse:
        return RedirectResponse("/dashboard?window=wb-report", status_code=302)

    @router.get("/dashboard/logical")
    async def dashboard_logical_redirect(request: Request) -> RedirectResponse:
        return _workbench_redirect(request, "logical")

    @router.get("/dashboard/api/actions")
    async def dashboard_api_actions(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.actions.catalog import list_actions
        from agentdecompile_recovery.corpus.dashboard.actions.context import workbench_context

        page = (request.query_params.get("page") or "").strip()
        actions, context = await asyncio.gather(
            asyncio.to_thread(list_actions), asyncio.to_thread(workbench_context),
        )
        if page and page not in {"home", "work"}:
            actions = [item for item in actions if page in item.pages]
        return JSONResponse(
            {
                "ok": True,
                "actions": [item.to_dict() for item in actions],
                "context": context,
            }
        )

    @router.get("/dashboard/api/actions/{action_id}")
    async def dashboard_api_action(action_id: str) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.actions.catalog import action_by_id

        action = await asyncio.to_thread(action_by_id, action_id)
        if action is None:
            return JSONResponse({"ok": False, "error": f"unknown action {action_id}"}, status_code=404)
        return JSONResponse({"ok": True, "action": action.to_dict()})

    @router.get("/dashboard/api/jobs")
    async def dashboard_api_jobs() -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.actions.jobs import list_jobs

        rows = await asyncio.to_thread(list_jobs, compact=True)
        return JSONResponse({"ok": True, "jobs": [job.to_dict(include_log=False, include_details=False) for job in rows], "total": len(rows)})

    @router.get("/dashboard/api/jobs/{job_id}")
    async def dashboard_api_job(job_id: str) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.actions.jobs import get_job

        job = await asyncio.to_thread(get_job, job_id)
        if job is None:
            return JSONResponse({"ok": False, "error": f"unknown job {job_id}"}, status_code=404)
        return JSONResponse({"ok": True, "job": job.to_dict()})

    @router.post("/dashboard/api/jobs")
    async def dashboard_api_start_job(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.actions.jobs import start_job

        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "error": "JSON object required"}, status_code=400)
        payload, status = await asyncio.to_thread(
            start_job,
            str(body.get("action") or body.get("actionId") or ""),
            body.get("params") if isinstance(body.get("params"), dict) else {},
            context=body.get("context") if isinstance(body.get("context"), dict) else {},
            confirm=bool(body.get("confirm")),
            dry_run=bool(body.get("dryRun") or body.get("dry_run")),
        )
        return JSONResponse(payload, status_code=status)

    @router.post("/dashboard/api/jobs/{job_id}/cancel")
    async def dashboard_api_cancel_job(job_id: str) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.actions.jobs import cancel_job

        job = await asyncio.to_thread(cancel_job, job_id)
        if job is None:
            return JSONResponse({"ok": False, "error": f"unknown job {job_id}"}, status_code=404)
        return JSONResponse({"ok": True, "job": job.to_dict()})

    @router.post("/dashboard/api/server/shutdown")
    async def dashboard_server_shutdown(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.server_control import (
            local_control_allowed,
            request_shutdown,
        )

        if not local_control_allowed(request):
            return JSONResponse({"ok": False, "error": "server control is localhost-only"}, status_code=403)
        return JSONResponse(request_shutdown())

    @router.post("/dashboard/api/server/restart")
    async def dashboard_server_restart(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.server_control import (
            local_control_allowed,
            request_restart,
        )

        if not local_control_allowed(request):
            return JSONResponse({"ok": False, "error": "server control is localhost-only"}, status_code=403)
        return JSONResponse(request_restart())

    @router.get("/dashboard/evidence/database")
    async def dashboard_database_evidence() -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.pages import database_evidence_json

        payload, status = database_evidence_json()
        return JSONResponse(payload, status_code=status)

    @router.get("/dashboard/fragment")
    async def dashboard_fragment() -> RedirectResponse:
        return RedirectResponse("/dashboard?window=wb-overview", status_code=302)

    @router.get("/dashboard/panel")
    async def dashboard_panel(request: Request) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.pages import panel_payload_json

        sid = request.query_params.get("id") or ""
        payload, status = panel_payload_json(sid)
        return JSONResponse(payload, status_code=status)

    @router.get("/dashboard/static/{name}")
    async def dashboard_static(name: str) -> Response:
        return _static(name)

    return router

"""First-class FastAPI / Swagger operations for every cataloged action."""

from __future__ import annotations

import asyncio

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, create_model

from agentdecompile_recovery.corpus.dashboard.actions.catalog import ActionSpec, list_actions
from agentdecompile_recovery.corpus.dashboard.actions.jobs import cancel_job, get_job, list_jobs, start_job

_KIND = {"str": str, "path": str, "int": int, "float": float, "bool": bool, "array": list[Any], "object": dict[str, Any]}
_META_KEYS = frozenset({"confirm", "dryRun", "dry_run", "context", "params", "approvalId", "operationKey"})


def _safe_ident(value: str) -> str:
    out = ["A"]
    for char in value:
        out.append(char if char.isalnum() else "_")
    return "".join(out)


def model_for(action: ActionSpec) -> type[BaseModel]:
    fields: dict[str, Any] = {}
    used: set[str] = {"confirm", "dry_run", "dryRun", "context"}
    for spec in action.fields:
        py = _KIND.get(spec.kind, str)
        alias = spec.name
        safe = alias.replace("-", "_").replace(".", "_")
        if safe in {"json", "schema", "model_config", "model_fields"}:
            safe = f"field_{safe}"
        if not safe or safe[0].isdigit():
            safe = f"f_{safe}"
        while safe in used:
            safe += "_"
        used.add(safe)
        default: Any
        if spec.required and not spec.from_context:
            default = ...
        elif spec.default not in (None, [], ()):
            default = spec.default
        else:
            default = None
        fields[safe] = (
            py | None,
            Field(default=default, alias=alias, description=spec.help or spec.name, json_schema_extra=spec.schema or {}),
        )
    fields["confirm"] = (bool, Field(default=False, description="Required for mutating or dangerous actions"))
    fields["dry_run"] = (bool, Field(default=False, alias="dryRun"))
    fields["context"] = (dict[str, Any] | None, Field(default=None))
    fields["approval_id"] = (str | None, Field(default=None, alias="approvalId", description="Durable approval record for byte verification"))
    fields["operation_key"] = (str | None, Field(default=None, alias="operationKey", description="Stable idempotency key for the approved operation"))
    return create_model(
        _safe_ident(action.id),
        __config__=ConfigDict(populate_by_name=True, extra="forbid"),
        **fields,
    )


def _retained_admission_summary(admission):
    """Expose unresolved ownership without copying the complete receipt census."""
    assessments = admission.get('retainedOwnershipAssessments') or {}
    by_domain = {}
    for domain, owners in (assessments.get('byDomain') or {}).items():
        by_domain[domain] = len(owners)
    return {
        'retainedOwnershipAssessmentCount': assessments.get('count', 0),
        'retainedOwnershipByDomain': by_domain,
        'retainedPolicyMismatchCount': len(admission.get('retainedPolicyMismatches') or {}),
        'retainedOwnershipResolved': assessments.get('ownershipResolved', False),
    }


def _job_snapshot(scope):
    from agentdecompile_recovery.corpus.dashboard.actions.jobs import STORE, _copy_job, list_jobs

    if scope == "current-process":
        with STORE._lock:
            rows = [_copy_job(job) for job in STORE._jobs.values()]
        rows.sort(key=lambda job: job.created_at, reverse=True)
    else:
        rows = list_jobs(compact=True)

    admission = STORE.admission_status()
    with STORE._lock:
        holders = []
        for resource, mapping in (
            ("identity", STORE._identity_held),
            ("pair", STORE._pair_held),
            ("ghidra", STORE._ghidra_held),
            ("output-tree", STORE._external_held),
        ):
            for _key, owner_id in mapping.items():
                job = STORE._jobs.get(owner_id)
                holders.append({
                    "resource": resource,
                    "jobId": owner_id,
                    "actionId": job.action_id if job else "unknown",
                    "status": job.status if job else "missing-owner",
                    "historyOnly": job.history_only if job else None,
                    "resourceDisposition": job.resource_disposition if job else "unknown",
                    "liveRecordPresent": job is not None,
                })
    # Retained reservations can outlive the in-memory job index. Explain their
    # exact durable owner without scanning all history or doing I/O under the
    # scheduler lock. A receipt is evidence, not permission to release a lock.
    from . import job_history

    receipt_root = job_history.directory()
    owner_receipts = {}
    for holder in holders:
        owner_id = holder["jobId"]
        if holder["liveRecordPresent"] or receipt_root is None or not job_history._ID.fullmatch(owner_id):
            continue
        if owner_id not in owner_receipts:
            owner_receipts[owner_id] = job_history._job_receipt(receipt_root / (owner_id + ".json"))
        receipt = owner_receipts[owner_id]
        if receipt is None or receipt.get("id") != owner_id:
            continue
        holder["actionId"] = receipt.get("actionId") or "unknown"
        holder["retainedReceipt"] = {
            "status": receipt.get("status", "unknown"),
            "resourceDisposition": receipt.get("resourceDisposition", "unknown"),
            "executionOwnerRecorded": bool(receipt.get("executionOwner")),
            "clearanceRecorded": bool(receipt.get("clearanceObservation")),
        }
    summary = {
        "policy": admission["policy"],
        "maxConcurrent": admission["maxConcurrent"],
        "running": admission["running"],
        "lanes": admission["lanes"],
        "pausedScopeCount": len(admission["paused"]),
        "pausedScopes": dict(admission["paused"]),
        "identityLocksHeld": admission["identityHeld"],
        "pairLocksHeld": admission["pairHeld"],
        "ghidraLocksHeld": admission["ghidraHeld"],
        "outputTreesHeld": admission["outputTreesHeld"],
        "holders": holders,
    }
    summary.update(_retained_admission_summary(admission))
    return {
        "ok": True,
        "scope": scope,
        "historyIncluded": scope == "retained-history",
        "jobs": [job.to_dict(include_log=False, include_details=False) for job in rows],
        "total": len(rows),
        "admission": summary,
    }


def _reload_binding_snapshot():
    """Observe quarantined code registrations without creating or merging them."""
    import os
    import sys

    module = sys.modules.get("inplace_hotreload")
    owner = vars(module).get("_active") if module is not None else None
    codefind = sys.modules.get("codefind")
    registry = vars(codefind).get("code_registry") if codefind is not None else None
    if owner is None or registry is None:
        return {"ok": False, "error": "The active reloader or code registry is unavailable."}
    guard = owner.guard()
    if not guard.acquire(blocking=False):
        return {"ok": False, "error": "The reloader is busy; no state was changed."}
    try:
        files = []
        paths = sorted(owner._quarantined)
        for path in paths[:16]:
            codefile = owner.registry.cache.get(path)
            missing = []
            visited = 0
            truncated = False
            if codefile is not None:
                for definition in codefile.root.walk():
                    if visited >= 2000:
                        truncated = True
                        break
                    visited += 1
                    if (type(definition).__module__ != "jurigged.codetools"
                            or type(definition).__name__ != "FunctionDefinition"):
                        continue
                    codepath = tuple(definition.codepath())
                    cached = vars(definition).get("_codeobj")
                    registered = registry.codes.get((*codepath, definition.groundline))
                    if cached is None and registered is None:
                        missing.append({"callable": ".".join(str(part) for part in codepath[1:]),
                                        "originalLine": definition.groundline})
            observation = owner.files.get(path, {})
            files.append({"path": path, "state": observation.get("state"),
                          "sourceSha256": observation.get("sourceSha256"),
                          "appliedSha256": observation.get("appliedSha256"),
                          "codefileCached": codefile is not None, "visited": visited,
                          "truncated": truncated, "unregisteredCallables": missing})
        return {"ok": True, "pid": os.getpid(), "scope": "current-code-registry",
                "claim": "Current unresolved bindings are candidates, not proof of the original merge failure.",
                "quarantinedCount": len(paths), "truncated": len(paths) > 16, "files": files}
    except (AttributeError, TypeError, ValueError) as error:
        return {"ok": False, "error": "Could not inspect reloader registrations: " + type(error).__name__}
    finally:
        guard.release()


def create_actions_api_router() -> APIRouter:
    """Typed /api/v1/actions/* routes plus job aliases. Same runner as the dock."""
    router = APIRouter(tags=["actions"])

    @router.get("/api/v1/actions", summary="List every public CLI and MCP action")
    async def api_list_actions() -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.actions.context import workbench_context

        actions, context = await asyncio.gather(
            asyncio.to_thread(list_actions),
            asyncio.to_thread(workbench_context),
        )
        return JSONResponse({"ok": True, "actions": [item.to_dict() for item in actions], "context": context})

    @router.get("/api/v1/actions/{action_id}", summary="Describe one action")
    async def api_one_action(action_id: str) -> JSONResponse:
        from agentdecompile_recovery.corpus.dashboard.actions.catalog import action_by_id

        action = await asyncio.to_thread(action_by_id, action_id)
        if action is None:
            return JSONResponse({"ok": False, "error": f"unknown action {action_id}"}, status_code=404)
        return JSONResponse({"ok": True, "action": action.to_dict()})

    @router.get("/api/v1/jobs", summary="List running and recent jobs")
    async def api_list_jobs() -> JSONResponse:
        return JSONResponse(await asyncio.to_thread(_job_snapshot, "retained-history"))

    @router.get("/api/v1/jobs/{job_id}", summary="Job status and log")
    async def api_one_job(job_id: str) -> JSONResponse:
        if job_id == "reload-diagnostics":
            return JSONResponse(await asyncio.to_thread(_reload_binding_snapshot))
        if job_id == "current":
            return JSONResponse(await asyncio.to_thread(_job_snapshot, "current-process"))
        if job_id == "history":
            return JSONResponse(await asyncio.to_thread(_job_snapshot, "retained-history"))
        job = await asyncio.to_thread(get_job, job_id)
        if job is None:
            return JSONResponse({"ok": False, "error": f"unknown job {job_id}"}, status_code=404)
        return JSONResponse({"ok": True, "job": job.to_dict()})

    @router.post("/api/v1/jobs/{job_id}/cancel", summary="Cancel a queued or running job")
    async def api_cancel_job(job_id: str) -> JSONResponse:
        job = await asyncio.to_thread(cancel_job, job_id)
        if job is None:
            return JSONResponse({"ok": False, "error": f"unknown job {job_id}"}, status_code=404)
        return JSONResponse({"ok": True, "job": job.to_dict()})

    for action in list_actions():
        _mount_action(router, action)
    return router


def _mount_action(router: APIRouter, action: ActionSpec) -> None:
    model_cls = model_for(action)
    group = action.group
    command = action.command or "one-shot"
    path = f"/api/v1/actions/{group}/{command}"

    async def handler(request: Request) -> JSONResponse:
        from . import approval

        try:
            raw = await request.json()
        except Exception:
            raw = {}
        if raw in (None, ""):
            raw = {}
        if not isinstance(raw, dict):
            return JSONResponse({"error": "JSON object required"}, status_code=400)
        context = raw.get("context")
        if not isinstance(context, dict):
            context = {}
        params_only = {key: value for key, value in raw.items() if key not in _META_KEYS}
        nested = raw.get("params")
        if isinstance(nested, dict):
            params_only.update(nested)
        confirm = bool(raw.get("confirm"))
        dry = bool(raw.get("dryRun") or raw.get("dry_run"))
        if action.id == approval.ACTION_ID and not dry:
            try:
                actor = approval.local_actor(
                    request.client.host if request.client else None,
                    request.headers.get("origin"),
                    str(request.base_url).rstrip("/"),
                )
                payload, status = await asyncio.to_thread(
                    approval.submit,
                    action.id,
                    params_only,
                    context=context,
                    confirm=confirm,
                    dry_run=False,
                    approval_id=str(raw.get("approvalId") or "") or None,
                    operation_key=str(raw.get("operationKey") or "") or None,
                    actor=actor,
                )
            except approval.ApprovalError as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=exc.status)
            return JSONResponse(payload, status_code=status)
        payload, status = await asyncio.to_thread(
            start_job,
            action.id,
            params_only,
            context=context,
            confirm=confirm,
            dry_run=dry,
        )
        return JSONResponse(payload, status_code=status)

    handler.__name__ = f"run_{_safe_ident(action.id)}"
    handler.__doc__ = action.summary or action.title
    router.add_api_route(
        path,
        handler,
        methods=["POST"],
        tags=[group],
        summary=action.title,
        description=action.summary or action.title,
        response_class=JSONResponse,
        openapi_extra={
            "operationId": action.id,
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": model_cls.model_json_schema(by_alias=True)},
                },
            },
        },
    )

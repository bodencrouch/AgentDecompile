"""Page defaults for dashboard actions: store binaries and corpus env."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentdecompile_recovery.corpus.contract import pipeline_stage_presentation
from agentdecompile_recovery.corpus.dashboard.actions.catalog import env_defaults
from agentdecompile_recovery.corpus.dashboard.common import (
    CorpusBindingError,
    query_db,
    resolve_corpus_binding,
    runtime_project_root,
)


def workbench_context() -> dict[str, Any]:
    defaults = env_defaults()
    binding: dict[str, Any] | None = None
    binding_error = ""
    try:
        binding = resolve_corpus_binding()
    except CorpusBindingError as exc:
        binding_error = str(exc)
    if binding is not None:
        selected_db = Path(binding["path"])
        project_root = runtime_project_root(selected_db)
        defaults["db"] = binding["path"]
        defaults["work_dir"] = binding["output_root"] or ""
        defaults["report_file"] = str(project_root / "recovery-report.json") if project_root else ""
    else:
        # Do not advertise a default placeholder as the selected recovery corpus.
        defaults.update({"db": "", "work_dir": "", "report_file": ""})
    rows, err = ([], binding_error or "No validated corpus is selected")
    if binding is not None:
        rows, err = query_db(
            "SELECT slug, repo_path, role, func_count, named_count FROM binary ORDER BY slug",
            db=Path(binding["path"]),
        )
    binaries: list[dict[str, Any]] = []
    if not err:
        for slug, repo_path, role, funcs, named in rows:
            binaries.append(
                {
                    "slug": slug,
                    "repo": repo_path,
                    "program": repo_path or slug,
                    "role": role or "",
                    "funcs": int(funcs or 0),
                    "named": int(named or 0),
                }
            )
    return {
        "defaults": defaults,
        "binaries": binaries,
        "storeError": err,
        "corpusBinding": binding,
        "corpusIdentity": binding["identity"] if binding else "",
        "corpusBindingError": binding_error,
        "pipelineStages": pipeline_stage_presentation(),
    }

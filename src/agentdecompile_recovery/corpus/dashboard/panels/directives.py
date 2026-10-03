"""Render the engagement as one actionable, evidence-backed mission contract."""
from __future__ import annotations
import sys
import time
from pathlib import Path
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agentdecompile_recovery.corpus.dashboard.panels.common import ROOT, ago, esc, load_json, missing, rel  # noqa: E402

TITLE = "Mission contract"
from agentdecompile_recovery.corpus.dashboard.common import as_root
CONTRACT = as_root() / ".mission" / "directives.json"


def _contract_path() -> Path:
    """Directives file under the live project root (re-read each call)."""
    return as_root() / ".mission" / "directives.json"

def _resolve(path_text: str):
    text = (path_text or "").strip()
    if not text:
        return None, False, "empty path"
    root = ROOT.resolve()
    candidate = (as_root() / text).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return candidate, candidate.exists(), "outside the repo root"
    return candidate, candidate.exists(), "" if candidate.exists() else "not on disk"

def _evidence(path_text: str) -> str:
    path, exists, note = _resolve(path_text)
    if not exists:
        return f'<li class="ev broken"><code>{esc(path_text)}</code><span class="tag warn">{esc(note)}</span></li>'
    if note:
        return f'<li class="ev"><code>{esc(path_text)}</code><span class="tag">{esc(note)}</span></li>'
    return (f'<li class="ev"><a href="/artifact?p={esc(rel(path))}"><code>{esc(rel(path))}</code></a>'
            f'<span class="age">{esc(ago(path.stat().st_mtime))}</span></li>')

def _load_goal():
    data, err = load_json(_contract_path())
    if err or not isinstance(data, dict):
        return None, err or "mission contract is not an object"
    goal = data.get("master_goal")
    return (goal, None) if isinstance(goal, dict) else (None, "master_goal is missing")

def summary() -> str:
    goal, err = _load_goal()
    if err:
        return '<span class="miss">mission contract unreadable</span>'
    criteria = [x for x in goal.get("acceptance_criteria", []) if isinstance(x, str)]
    evidence = [x for x in goal.get("evidence", []) if isinstance(x, str)]
    broken = sum(not _resolve(item)[1] for item in evidence)
    state = str(goal.get("status") or "in_progress").replace("_", " ")
    audit = (f'<span class="st-failed">{broken} broken evidence links</span>' if broken
             else '<span class="st-done">all evidence paths exist</span>')
    return (f'<span class="dcount">1 goal</span><span class="dstats">'
            f'<span class="st-running">{esc(state)}</span><span>{len(criteria)} acceptance criteria</span></span>'
            f'<span class="dbroken">{audit}</span>')

def _evidence_entry(path_text: str, now: float) -> dict:
    path, exists, note = _resolve(path_text)
    entry = {"path": (path_text or "").strip(), "exists": bool(exists), "mtime": None,
             "age_seconds": None, "age": "", "note": note, "state": "missing"}
    if not path_text or not path_text.strip():
        entry["state"] = "empty"
    elif exists and note:
        entry["state"] = "outside_root"
    elif exists:
        entry["state"] = "ok"
    if exists and path is not None:
        try:
            entry["path"] = rel(path)
            mtime = path.stat().st_mtime
            entry["mtime"] = mtime
            entry["age_seconds"] = max(0, int(now - mtime))
            entry["age"] = ago(mtime)
        except OSError as exc:
            entry["note"] = f"could not stat: {exc}"
    return entry


def collect() -> dict:
    """Single data gatherer shared by render() and as_payload()."""
    now = time.time()
    contract = _contract_path()
    errors: list[str] = []
    source = {"path": rel(contract), "exists": contract.exists(), "mtime": None,
              "age_seconds": None, "age": ""}
    if source["exists"]:
        try:
            mtime = contract.stat().st_mtime
            source.update(mtime=mtime, age_seconds=max(0, int(now - mtime)), age=ago(mtime))
        except OSError as exc:
            errors.append(f"could not stat {source['path']}: {exc}")
    goal, err = _load_goal()
    if err:
        errors.append(err)
        return {"ok": False, "source": source, "goal": None, "criteria": [],
                "evidence": [], "counts": {"evidence": 0, "ok": 0, "missing": 0, "criteria": 0},
                "errors": errors}
    criteria = [{"index": i + 1, "text": x}
                for i, x in enumerate(goal.get("acceptance_criteria", [])) if isinstance(x, str)]
    evidence = [_evidence_entry(x, now) for x in goal.get("evidence", []) if isinstance(x, str)]
    n_ok = sum(1 for e in evidence if e["state"] == "ok")
    return {
        "ok": True, "source": source,
        "goal": {"id": goal.get("id") or "MASTER", "title": goal.get("title") or "",
                 "objective": goal.get("objective") or "",
                 "status": goal.get("status") or "in_progress"},
        "criteria": criteria, "evidence": evidence,
        "counts": {"criteria": len(criteria), "evidence": len(evidence), "ok": n_ok,
                   "missing": len(evidence) - n_ok},
        "errors": errors,
    }


def as_payload() -> dict:
    """Structured facts for the workbench; no markup."""
    return collect()


def render() -> str:
    d = collect()
    if not d["ok"]:
        return missing(d["errors"][0])
    goal = d["goal"]
    criteria_html = "".join(f'<li>{esc(c["text"])}</li>' for c in d["criteria"])
    evidence_html = "".join(_evidence(e["path"]) for e in d["evidence"])
    src = d["source"]
    return (f'<div class="dsummary">{summary()}</div><article class="drow st-running">'
            f'<header><span class="did">{esc(goal["id"])}</span>'
            f'<span class="pill st-running">{esc(goal["status"])}</span>'
            '<span class="dcat">authoritative engagement goal</span></header>'
            f'<h3 class="headline">{esc(goal["title"] or "Complete the mission")}</h3>'
            f'<p>{esc(goal["objective"])}</p><h4>Acceptance criteria</h4>'
            f'<ol class="contract-list">{criteria_html}</ol><h4>Live evidence</h4>'
            f'<ul class="paths">{evidence_html}</ul></article>'
            f'<div class="srcs"><a class="src" href="/artifact?p={esc(src["path"])}">{esc(src["path"])}</a>'
            f'<span class="age">{esc(src["age"])}</span></div>')


if __name__ == "__main__":
    print(render())

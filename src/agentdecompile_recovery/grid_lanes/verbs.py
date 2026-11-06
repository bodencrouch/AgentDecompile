"""Task kinds that wrap the corpus CLI's keyed verbs as grid tasks.

Each kind is one verb of ``agentdecompile_recovery.corpus.cli`` run against a **store snapshot
object** (a ``VACUUM INTO`` copy of the store, ``restricted``-tagged: rows carry slugs and repo
paths, so only fleet and operator keys are offered these tasks) in a scratch directory, under a
kill deadline, with the verb's own refusals (basis, content hash, lock) surfacing as named grid
refusals.  Parameters are rendered in the ``SubprocessVerb`` shape
(``subprocess_verb_params``) so the grid's builtin runner can execute the same argv.

Kinds:

* ``corpus-export-hookpack`` -- ``export-hookpack --db store.sqlite --out out/pack.json``;
  outputs ``pack`` + ``receipt``; MEDIUM (MEASURED 122-200 s).  The sharded form
  (``export-slice`` / ``export-site-shard`` / ``export-merge``, U148) is what makes it SMALL.
* ``corpus-backfill-pass`` -- ``backfill --db store.sqlite --pass <name> --receipts out/receipts``;
  one task per pass; outputs ``receipts`` + ``binary_rows`` + ``receipt``; SMALL.  A pass that
  reads raw images fails on a node without them (U150 turns it into records).
* ``corpus-verify-determinism`` -- ``verify-determinism --db store.sqlite``; exit 0/1 are both
  values (``identical`` true/false); MEDIUM (MEASURED 248-261 s).
* ``corpus-logical-build`` -- ``logical-build --db store.sqlite``; outputs ``logical_rows``
  (the rebuilt ``logical_function`` + ``identity`` rows, sorted, no product column) + ``receipt``;
  SMALL (MEASURED 20-22 s).
* ``corpus-attest`` -- declared only: the ``corpus attest`` verb (U28x) is not in this checkout;
  ``run`` raises ``NotConfigured``.  Its grid shape is one task per (verb, snapshot) whose kill
  deadline is the per-verb deadline, output one sorted receipt with hashed slugs; "changed since
  the previous attestation" is a view comparison, never a task.

The verbs' outputs are values: the receipt never carries an absolute path (checked with the
exchange's ``assert_portable_payload``) and never a plaintext slug.  Elapsed time and stderr
digests go to ``metrics``, so two runs of one task produce byte-identical outputs and
``verify`` is a recompute-and-compare of content addresses (1:1 -- the asymmetry rule makes
these fleet/operator lanes).

Acceptance tests (named, landed in the verification phase):

* ``test_verb_kind_task_id_stable`` -- same snapshot + params on two nodes give one task id;
* ``test_verb_refusal_is_named`` -- a store with mixed basis yields ``BasisRefused`` before any
  verb output; a NULL content hash yields ``ContentHashRefused`` with hashed names only;
* ``test_verb_receipt_portable`` -- no absolute path and no registered slug in any output;
* ``test_verb_timeout_is_infra`` -- a verb past its deadline raises ``Infra`` and writes nothing;
* ``test_logical_rows_deterministic`` -- two runs give one ``logical_rows`` ref;
* ``test_attest_declared`` -- ``corpus-attest`` describes itself and refuses by name.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping

from agentdecompile_grid.core import (
    BudgetClass,
    NotConfigured,
    ObjectRef,
    ObjectStore,
    Refused,
    TaskResult,
    TaskSpec,
    Verification,
    task_kind,
)
from agentdecompile_grid.view.applier import ensure_tables, view_hook

from ._common import (
    PlannableKind,
    Infra,
    assert_portable,
    check_kind,
    corpus_cli_argv,
    deadline_for,
    hashed_slug,
    make_result,
    materialize_object,
    put_json,
    require_input,
    run_argv,
    scrub_paths,
    subprocess_verb_params,
    verify_by_recompute,
)

RECEIPT_SCHEMA = "agentdecompile.grid.corpus-verb.v1"
STORE_FILENAME = "store.sqlite"
OUT_DIRNAME = "out"


def _subprocess_env() -> dict[str, str]:
    """The child's environment: the running interpreter's package path made explicit."""
    import agentdecompile_recovery

    src_dir = str(Path(agentdecompile_recovery.__file__).resolve().parents[1])
    env = dict(os.environ)
    env["PYTHONPATH"] = src_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def classify_refusal_line(stderr: str) -> str:
    """The named reason behind a corpus verb's exit 2 (``corpus.cli._refusal_line`` output)."""
    for line in reversed(stderr.splitlines()):
        line = line.strip()
        if not line.startswith("error:"):
            continue
        text = line[len("error:"):].strip()
        if text.startswith("ContentHashError"):
            return "content-hash:" + scrub_paths(text.split(":", 1)[1].strip())[:200]
        if text.startswith("basis"):
            return "basis:" + scrub_paths(text.split(":", 1)[1].strip())[:200]
        if text.startswith("locked"):
            return "locked"
        return "verb-refused:" + scrub_paths(text)[:120]
    return "verb-refused:exit-2"


class CorpusVerbKind(PlannableKind):
    """Base for one corpus verb as a grid task.  Subclasses set ``name``, ``verb``, ``budget``."""

    name = ""
    verb = ""
    version = 1
    budget = BudgetClass.SMALL
    capabilities = ("python",)
    ok_exit_codes = (0,)
    PARAMS_SCHEMA: Mapping[str, str] = {"timeout_s": "optional kill deadline; capped at the budget class"}
    INPUTS: Mapping[str, str] = {"store": "store snapshot object (VACUUM INTO copy; restricted)"}
    OUTPUTS: Mapping[str, str] = {"receipt": "sorted JSON receipt: verb, argv, exit code, stdout digest, summary"}
    INPUT_ROLE = "restricted"
    #: output name -> object role tag (§6.3); anything not listed is ``public`` (scrubbed values only)
    OUTPUT_ROLES: Mapping[str, str] = {}

    # ----------------------------------------------------------------- per-verb hooks
    def argv(self, spec: TaskSpec) -> list[str]:
        """Argv relative to the scratch dir (``store.sqlite`` and ``out/`` live there)."""
        return corpus_cli_argv(self.verb, "--db", STORE_FILENAME)

    def collect(self, spec: TaskSpec, objects: ObjectStore, scratch: Path, stdout: str) -> tuple[dict[str, ObjectRef], Any]:
        """``(extra outputs, summary)`` after a successful run; default parses stdout as JSON."""
        return {}, _parse_summary(stdout)

    # ----------------------------------------------------------------- SubprocessVerb shape
    def subprocess_verb_params(self, spec: TaskSpec) -> dict[str, Any]:
        argv = [a for a in self.argv(spec)]
        return subprocess_verb_params(
            argv=argv, outputs={k: v for k, v in self.OUTPUTS.items() if k != "receipt"},
            timeout_s=deadline_for(self.budget, spec.params.get("timeout_s")),
        )

    # ----------------------------------------------------------------- TaskKind
    def run(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> TaskResult:
        check_kind(spec, self.name, self.version)
        store_ref = require_input(spec, "store", kind=self.name)
        deadline = deadline_for(self.budget, spec.params.get("timeout_s"))
        scratch_dir = Path(scratch)
        out_dir = scratch_dir / OUT_DIRNAME
        out_dir.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        materialize_object(objects, store_ref, scratch_dir / STORE_FILENAME)
        argv = self.argv(spec)
        outcome = run_argv(argv, cwd=scratch_dir, timeout_s=deadline, env=_subprocess_env())
        if outcome.timed_out:
            raise Infra(f"timeout:{self.verb}:{int(deadline)}s")
        if outcome.returncode == 2:
            raise Refused(classify_refusal_line(outcome.stderr))
        if outcome.returncode not in self.ok_exit_codes:
            raise Infra(f"verb-failed:{self.verb}:exit-{outcome.returncode}:stderr-{outcome.stderr_sha256[:12]}")
        extra, summary = self.collect(spec, objects, scratch_dir, outcome.stdout)
        receipt = {
            "schema": RECEIPT_SCHEMA, "kind": self.name, "kind_version": self.version, "verb": self.verb,
            "argv": list(argv[3:]),  # verb + flags; the interpreter path is host layout, not a value
            "exit_code": outcome.returncode, "stdout_sha256": outcome.stdout_sha256,
            "store": str(store_ref), "params": dict(spec.params), "basis_hash": spec.basis_hash,
            "summary": summary,
        }
        assert_portable(receipt)
        outputs = {**extra, "receipt": put_json(objects, receipt)}
        return make_result(
            spec, outputs, elapsed_s=time.monotonic() - started,
            metrics={
                "verb_elapsed_s": round(outcome.elapsed_s, 3), "stderr_sha256": outcome.stderr_sha256,
                "stdout_bytes": len(outcome.stdout), "deadline_s": deadline,
            },
        )

    def verify(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str) -> Verification:
        return verify_by_recompute(self, spec, result, objects, scratch)

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "kind": cls.name, "version": cls.version, "verb": cls.verb, "budget": cls.budget.value,
            "capabilities": list(cls.capabilities), "roles": ["fleet", "operator"],
            "inputs": dict(cls.INPUTS), "input_role": cls.INPUT_ROLE, "params": dict(cls.PARAMS_SCHEMA),
            "outputs": dict(cls.OUTPUTS), "output_roles": {k: cls.OUTPUT_ROLES.get(k, "public") for k in cls.OUTPUTS},
            "verify": "recompute (1:1; fleet/operator lane)",
            "status": "working" if cls.verb else "declared",
        }


def _parse_summary(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return {}
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"stdout_lines": len(text.splitlines())}


def _is_sha256(text: str) -> bool:
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def _sorted_rows(con: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    cur = con.execute(sql, params)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _binary_names(con: sqlite3.Connection) -> dict[int, str]:
    """``binary.id -> content_sha256`` (or the hashed slug when no hash is recorded)."""
    out: dict[int, str] = {}
    for row in con.execute("SELECT id, slug, content_sha256 FROM binary"):
        digest_ = str(row[2] or "").strip()
        out[int(row[0])] = digest_ if digest_ else "slug:" + hashed_slug(row[1])
    return out


# --------------------------------------------------------------------------- the kinds
@task_kind
class CorpusExportHookpack(CorpusVerbKind):
    name = "corpus-export-hookpack"
    verb = "export-hookpack"
    budget = BudgetClass.MEDIUM
    OUTPUTS = {**CorpusVerbKind.OUTPUTS, "pack": "the hook pack bytes (restricted until U151's scrub receipt)"}
    OUTPUT_ROLES = {"pack": "restricted"}   # the pack names builds by slug today (U151 scrubs it)

    def argv(self, spec: TaskSpec) -> list[str]:
        return corpus_cli_argv(self.verb, "--db", STORE_FILENAME, "--out", f"{OUT_DIRNAME}/pack.json")

    def collect(self, spec, objects, scratch, stdout):
        pack = scratch / OUT_DIRNAME / "pack.json"
        if not pack.is_file():
            raise Infra("verb-failed:export-hookpack:no-pack")
        return {"pack": objects.put(pack.read_bytes())}, _parse_summary(stdout)


@task_kind
class CorpusBackfillPass(CorpusVerbKind):
    name = "corpus-backfill-pass"
    verb = "backfill"
    budget = BudgetClass.SMALL
    PARAMS_SCHEMA = {
        **CorpusVerbKind.PARAMS_SCHEMA,
        "pass": "one backfill pass name (``backfill.PASSES``); one task per pass",
        "resume": "bool (default true): honour existing receipts",
    }
    OUTPUTS = {
        **CorpusVerbKind.OUTPUTS,
        "receipts": "sorted list of the per-(pass, binary) receipts, keyed by image hash",
        "binary_rows": "derived binary columns after the pass, keyed by content hash (slugs hashed)",
    }

    def argv(self, spec: TaskSpec) -> list[str]:
        name = str(spec.params.get("pass", ""))
        if not name:
            raise Refused("missing-param:corpus-backfill-pass:pass")
        argv = corpus_cli_argv(self.verb, "--db", STORE_FILENAME, "--pass", name, "--receipts", f"{OUT_DIRNAME}/receipts")
        if not bool(spec.params.get("resume", True)):
            argv.append("--no-resume")
        return argv

    @staticmethod
    def _scrub_receipt(body: Any) -> Any:
        """A backfill receipt as a value: slug hashed, repo path and raw image path dropped."""
        if not isinstance(body, dict):
            return body
        out = dict(body)
        binary = out.get("binary")
        if isinstance(binary, dict):
            out["binary"] = {"slug": hashed_slug(binary.get("slug"))}
        out["raw_image_present"] = out.pop("raw_image", None) is not None
        key = out.get("key")
        if isinstance(key, dict) and not _is_sha256(str(key.get("identity", ""))):
            out["key"] = {**key, "identity": "slug:" + hashed_slug(key.get("identity"))}
        return out

    @staticmethod
    def _scrub_summary(summary: Any) -> Any:
        if not isinstance(summary, dict):
            return summary
        summary = dict(summary)
        summary.pop("receipts_dir", None)  # a scratch path, not a value
        passes = summary.get("passes")
        if isinstance(passes, dict):
            for name, entry in passes.items():
                if isinstance(entry, dict) and isinstance(entry.get("binaries"), list):
                    entry = dict(entry)
                    entry["binaries"] = sorted(
                        ({**{k: v for k, v in b.items() if k not in ("id", "slug")}, "slug": hashed_slug(b.get("slug"))}
                         for b in entry["binaries"] if isinstance(b, dict)),
                        key=lambda b: b["slug"],
                    )
                    passes[name] = entry
        return summary

    def collect(self, spec, objects, scratch, stdout):
        receipts_dir = scratch / OUT_DIRNAME / "receipts"
        receipts: list[Any] = []
        if receipts_dir.is_dir():
            for path in sorted(receipts_dir.rglob("*.json")):
                rel = path.relative_to(receipts_dir)
                stem = rel.stem
                if stem.startswith("slug-"):
                    stem = "slug-" + hashed_slug(stem[len("slug-"):])
                name = (rel.parent / f"{stem}{rel.suffix}").as_posix()
                try:
                    receipts.append({"name": name, "body": self._scrub_receipt(json.loads(path.read_text("utf-8")))})
                except (OSError, json.JSONDecodeError):
                    receipts.append({"name": name, "body": None})
        con = sqlite3.connect(str(scratch / STORE_FILENAME))
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info(binary)")}
            wanted = [c for c in ("content_sha256", "md5", "analyzer_version", "processor_spec_hash", "basis_hash",
                                  "language_id", "arch", "bits", "format", "image_base", "func_count") if c in cols]
            rows = _sorted_rows(con, f"SELECT id, slug, {', '.join(wanted)} FROM binary")
        finally:
            con.close()
        for row in rows:
            row["slug"] = hashed_slug(row.pop("slug"))
            row.pop("id", None)
        rows.sort(key=lambda r: (str(r.get("content_sha256") or ""), r["slug"]))
        summary = self._scrub_summary(_parse_summary(stdout))
        return {"receipts": put_json(objects, receipts), "binary_rows": put_json(objects, rows)}, summary


@task_kind
class CorpusVerifyDeterminism(CorpusVerbKind):
    name = "corpus-verify-determinism"
    verb = "verify-determinism"
    budget = BudgetClass.MEDIUM
    ok_exit_codes = (0, 1)  # 1 = not identical: a value, not a failure


@task_kind
class CorpusLogicalBuild(CorpusVerbKind):
    name = "corpus-logical-build"
    verb = "logical-build"
    budget = BudgetClass.SMALL
    OUTPUTS = {
        **CorpusVerbKind.OUTPUTS,
        "logical_rows": "rebuilt logical_function (no product column) + identity rows keyed by content hash, sorted",
    }

    def collect(self, spec, objects, scratch, stdout):
        con = sqlite3.connect(str(scratch / STORE_FILENAME))
        try:
            names = _binary_names(con)
            logical = _sorted_rows(
                con,
                "SELECT id, canon_key, canon_class, canon_method, best_name, best_signature, source_file, "
                "object_file, n_members, notes FROM logical_function ORDER BY canon_key, id",
            )
            identity = _sorted_rows(
                con, "SELECT logical_id, binary_id, addr, confidence, method, evidence FROM identity ORDER BY binary_id, addr",
            )
        finally:
            con.close()
        for row in identity:
            row["binary"] = names.get(int(row.pop("binary_id")), "unknown")
        identity.sort(key=lambda r: (r["binary"], int(r["addr"])))
        return {"logical_rows": put_json(objects, {"logical_function": logical, "identity": identity})}, _parse_summary(stdout)


@task_kind
class CorpusAttest(CorpusVerbKind):
    """Declared: ``corpus attest`` (U28x) is not in this checkout."""

    name = "corpus-attest"
    verb = ""  # no verb to build argv for
    budget = BudgetClass.SMALL
    PARAMS_SCHEMA = {
        "verb": "one of export-hookpack | backfill | verify-determinism | logical-build",
        "verb_params": "that verb's params (see its kind)",
        "deadline_s": "per-verb deadline; the worker's kill deadline for this task",
        "previous_receipt": "optional ref of the last verified attest receipt for (verb, basis) -- diffed in the view",
    }
    OUTPUTS = {"receipt": "sorted JSON receipt with hashed slugs and the output hashes (never the pack)"}

    def argv(self, spec: TaskSpec) -> list[str]:
        raise NotConfigured("corpus attest verb (U28x) not present in this checkout yet")

    def run(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> TaskResult:
        check_kind(spec, self.name, self.version)
        raise NotConfigured(
            "corpus attest verb (U28x) not present in this checkout yet; its grid shape is one "
            "corpus-attest task per (verb, snapshot) with deadline_s as the kill deadline"
        )

    def verify(self, spec, result, objects, scratch) -> Verification:
        raise NotConfigured("corpus attest verb (U28x) not present in this checkout yet")


VERB_KINDS = (CorpusExportHookpack, CorpusBackfillPass, CorpusVerifyDeterminism, CorpusLogicalBuild, CorpusAttest)


# --------------------------------------------------------------------------- view hooks
VERB_RECEIPT_SQL = """
CREATE TABLE IF NOT EXISTS grid_verb_receipt (
    task_id      TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    verb         TEXT NOT NULL,
    basis_hash   TEXT NOT NULL,
    store_ref    TEXT NOT NULL,
    exit_code    INTEGER NOT NULL,
    summary_json TEXT NOT NULL,
    outputs_json TEXT NOT NULL
);
"""


def _apply_verb_receipt(kind: str, result: TaskResult, objects: ObjectStore, con: sqlite3.Connection) -> int:
    """Record the verified verb receipt.  Binds nothing: the delta binders are U143/U150's.

    The view keeps the receipt and the output refs (pack, logical_rows, binary_rows) so the
    pipeline's own binders can consume them; identity tables are never written here.
    """
    ref = result.outputs.get("receipt")
    if ref is None or not objects.exists(ref):
        return 0
    receipt = json.loads(objects.get(ref).decode("utf-8"))
    ensure_tables(con, VERB_RECEIPT_SQL)
    con.execute(
        "INSERT OR REPLACE INTO grid_verb_receipt(task_id, kind, verb, basis_hash, store_ref, exit_code, "
        "summary_json, outputs_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            result.task_id, kind, str(receipt.get("verb", "")), str(receipt.get("basis_hash", result.basis_hash)),
            str(receipt.get("store", "")), int(receipt.get("exit_code", -1)),
            json.dumps(receipt.get("summary"), sort_keys=True, separators=(",", ":")),
            json.dumps({k: str(v) for k, v in sorted(result.outputs.items())}, sort_keys=True, separators=(",", ":")),
        ),
    )
    return 1


for _cls in VERB_KINDS:
    view_hook(_cls.name)(_apply_verb_receipt)


__all__ = [
    "CorpusAttest", "CorpusBackfillPass", "CorpusExportHookpack", "CorpusLogicalBuild",
    "CorpusVerbKind", "CorpusVerifyDeterminism", "RECEIPT_SCHEMA", "VERB_KINDS", "classify_refusal_line",
]

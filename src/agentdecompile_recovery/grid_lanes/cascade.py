"""``match-score-shard``: score one shard of candidate pairs from stored features (design §3.5).

The body of the cascade's scoring loop (match_store.py:716-768) lifted to a pure function of two
objects: a **shard** (the source functions' feature records, the destination candidates' feature
records and the candidate lists computed at plan time with ``candidate_pairs``) and the frozen
**mapping** of round *k* (``taken`` and the string-keyed ``int_map`` derive from it).  Output:
the ``scored`` tuples ``[best, margin, src_addr, dst_addr, evidence, second, second_dst]`` in the
cascade's own order ``(-best, -margin, src, dst)``.  The greedy accept and the callgraph
fixpoint (``match-assign``, U142) consume every shard of a round; nothing here writes a
``match`` row.

Budget MICRO for shards of at most ``MICRO_MAX_SOURCES`` sources, SMALL above (ESTIMATE ~9 ms
per source address: 988 s / 4 rounds / ~27k addresses).  Capability ``python``; advisory from
any key, load-bearing after an independent-key recompute (``verify``).

Feature records are exactly ``match_store.Binary.funcs[addr]`` (plus ``decomp`` when present),
so a shard scores byte-identically to the monolithic ``match_binaries`` (U142 acceptance P2).
Slugs, ``binary.id`` and ``repo_path`` never enter the shard: builds are named by content hash.

Acceptance tests (named, landed with U142):

* ``test_match_shard_equals_monolithic_scores`` -- shard sizes 1/64/1024, shuffled, across two
  nodes give the same scored tuples as the loop in ``match_binaries``;
* ``test_match_shard_task_id_changes_with_mapping``;
* ``test_match_shard_recompute_verifies`` and ``test_match_shard_two_outputs_refute_never_merge``;
* ``test_match_shard_no_slug_no_binary_id_in_object``.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from agentdecompile_grid.core import (
    BudgetClass,
    ObjectStore,
    Refused,
    ResultStatus,
    TaskResult,
    TaskSpec,
    Verification,
    task_kind,
)
from agentdecompile_grid.view.applier import ensure_tables, view_hook

from ._common import (
    PlannableKind,
    check_kind,
    get_json,
    hashed_slug,
    make_result,
    put_json,
    require_input,
    verify_by_recompute,
)

SHARD_SCHEMA = "agentdecompile.grid.match-shard.v1"
MAPPING_SCHEMA = "agentdecompile.grid.match-mapping.v1"
SCORED_SCHEMA = "agentdecompile.grid.match-scored.v1"
MICRO_MAX_SOURCES = 256


# --------------------------------------------------------------------------- pure scoring
def score_shard(shard: Mapping[str, Any], mapping_obj: Mapping[str, Any]) -> list[list[Any]]:
    """Score every ``(src, candidate)`` of *shard* against the frozen *mapping*; cascade order."""
    from ..corpus.fuzzy_fingerprint import fuzzy_bits
    from ..corpus.match_engine import candidate_margin, score_features

    mapping = {int(k): int(v) for k, v in (mapping_obj.get("mapping") or {}).items()}
    taken = set(mapping.values())
    int_map = {str(k): str(v) for k, v in mapping.items()} if mapping else None
    src = shard["src"]
    dst = shard["dst"]
    same_arch = bool(shard.get("same_arch", True))
    use_name_features = shard.get("use_name_features", True)
    fuzzy_cache: dict[tuple[str, str], int] = {}

    def bits(side: str, key: str, record: Mapping[str, Any]) -> int:
        k = (side, key)
        if k not in fuzzy_cache:
            fuzzy_cache[k] = fuzzy_bits(record)
        return fuzzy_cache[k]

    scored: list[tuple[float, float, int, int, dict, float, int | None]] = []
    for a_key, cand_list in sorted(shard["pairs"].items(), key=lambda kv: int(kv[0])):
        a = int(a_key)
        if a in mapping:
            continue
        cands = {int(c) for c in cand_list} - taken
        if not cands:
            continue
        fa = src[a_key]
        best = second = 0.0
        best_b = None
        second_b = None
        best_ev: dict = {}
        fa_score = {**fa, "canon_arity": None} if use_name_features is False else fa
        for b in sorted(cands):
            b_key = str(b)
            raw_fb = dst[b_key]
            fb = dict(raw_fb) if use_name_features is False else raw_fb
            if use_name_features is False:
                fb["canon_arity"] = None
            s, ev = score_features(
                fa_score, fb, same_arch=same_arch, mapping=int_map,
                fuzzy_left_bits=bits("src", a_key, fa), fuzzy_right_bits=bits("dst", b_key, raw_fb),
            )
            ev = dict(ev)
            src_pcode = (fa.get("decomp") or {}).get("pcode_fingerprint")
            dst_pcode = (raw_fb.get("decomp") or {}).get("pcode_fingerprint")
            if src_pcode and dst_pcode:
                ev["pcode_fingerprint"] = 1.0 if src_pcode == dst_pcode else 0.0
                if src_pcode == dst_pcode:
                    ev["channels"] = sorted(set(ev.get("channels") or ()) | {"M"})
            ev["target_candidate_count"] = len(cands)
            ev["target_unique"] = len(cands) == 1
            if s > best:
                second, second_b, best, best_b, best_ev = best, best_b, s, b, ev
            elif s > second:
                second, second_b = s, b
        if best_b is not None:
            margin = candidate_margin(best, second, len(cands))
            scored.append((best, margin, a, best_b, best_ev, second, second_b))
    scored.sort(key=lambda t: (-t[0], -t[1], t[2], t[3]))
    return [list(t) for t in scored]


# --------------------------------------------------------------------------- the kind
@task_kind
class MatchScoreShard(PlannableKind):
    name = "match-score-shard"
    version = 1
    budget = BudgetClass.MICRO
    capabilities = ("python",)
    INPUTS: Mapping[str, str] = {
        "shard": "match-shard.v1: src/dst feature records + candidate lists (plan-time candidate_pairs)",
        "mapping": "match-mapping.v1: the frozen mapping of round k ({src: dst})",
    }
    PARAMS_SCHEMA: Mapping[str, str] = {
        "round": "cascade round k", "index": "shard index within the round",
        "src": "source build content hash", "dst": "destination build content hash",
    }
    OUTPUTS: Mapping[str, str] = {"scored": "match-scored.v1: cascade-ordered scored tuples"}
    OUTPUT_ROLES: Mapping[str, str] = {"scored": "public"}   # §6.3 object role tags

    def run(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> TaskResult:
        check_kind(spec, self.name, self.version)
        shard_ref = require_input(spec, "shard", kind=self.name)
        mapping_ref = require_input(spec, "mapping", kind=self.name)
        started = time.monotonic()
        shard = get_json(objects, shard_ref)
        mapping_obj = get_json(objects, mapping_ref)
        if shard.get("schema") != SHARD_SCHEMA:
            raise Refused(f"shard-schema:{str(shard.get('schema'))[:40]}")
        if mapping_obj.get("schema") != MAPPING_SCHEMA:
            raise Refused(f"mapping-schema:{str(mapping_obj.get('schema'))[:40]}")
        scored = score_shard(shard, mapping_obj)
        out = {
            "schema": SCORED_SCHEMA, "round": int(spec.params.get("round", 0)), "index": int(spec.params.get("index", 0)),
            "src": str(spec.params.get("src", "")), "dst": str(spec.params.get("dst", "")),
            "shard": str(shard_ref), "mapping": str(mapping_ref), "scored": scored,
        }
        return make_result(
            spec, {"scored": put_json(objects, out)}, elapsed_s=time.monotonic() - started,
            metrics={"sources": len(shard.get("pairs", {})), "scored": len(scored)},
        )

    def verify(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str) -> Verification:
        return verify_by_recompute(self, spec, result, objects, scratch, compare=("scored",))

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "kind": cls.name, "version": cls.version, "budget": f"{cls.budget.value} (<= {MICRO_MAX_SOURCES} sources) | small",
            "capabilities": list(cls.capabilities), "inputs": dict(cls.INPUTS), "params": dict(cls.PARAMS_SCHEMA),
            "outputs": dict(cls.OUTPUTS), "output_roles": dict(cls.OUTPUT_ROLES), "verify": "recompute; equal scored ref", "status": "working",
            "consumer": "match-assign (U142) -- the greedy accept needs every shard of the round",
        }


# --------------------------------------------------------------------------- planning helpers
def _open_ro(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000")
    return con


def binary_id_for(con: sqlite3.Connection, name: str) -> tuple[int, str]:
    """``(binary.id, content_sha256)`` for a content hash (or unique prefix); slugs refused by name.

    A build is named by content hash on the grid; a name that matches no hash is refused with the
    hashed spelling only, so no plaintext slug reaches a message.
    """
    text = str(name or "").strip().lower()
    if not text:
        raise Refused("build-name-required")
    rows = con.execute(
        "SELECT id, content_sha256 FROM binary WHERE content_sha256 IS NOT NULL AND content_sha256 LIKE ? ORDER BY id",
        (text + "%",),
    ).fetchall()
    if len(rows) == 1:
        return int(rows[0]["id"]), str(rows[0]["content_sha256"])
    if len(rows) > 1:
        raise Refused(f"build-name-ambiguous:{text[:12]}")
    raise Refused(f"build-not-found:{hashed_slug(text)}")


def _with_decomp(side: Any, addr: int) -> dict[str, Any]:
    record = dict(side.funcs[addr])
    decomp = side.decomp.get(addr)
    if decomp:
        record["decomp"] = decomp
    return record


def plan_match_shards(
    objects: ObjectStore,
    snapshot: str | Path,
    basis_hash: str,
    shard_size: int,
    *,
    src: str,
    dst: str,
    mapping: Mapping[int, int] | None = None,
    round_index: int = 0,
    use_name_features: bool = True,
    restrict_src: Iterable[int] | None = None,
) -> list[TaskSpec]:
    """Slice one directed pair of the snapshot into ``match-score-shard`` tasks.

    Loads both sides with ``match_store.Binary`` (read-only), computes ``candidate_pairs`` per
    eligible source address against *mapping*, and puts one shard object per ``shard_size``
    sources plus one mapping object shared by every shard of the round.
    """
    from ..corpus.match_store import Binary, candidate_pairs

    shard_size = max(1, int(shard_size))
    mapping = {int(k): int(v) for k, v in (mapping or {}).items()}
    restrict = {int(a) for a in restrict_src} if restrict_src is not None else None
    con = _open_ro(snapshot)
    try:
        src_id, src_hash = binary_id_for(con, src)
        dst_id, dst_hash = binary_id_for(con, dst)
        try:
            sa, sb = Binary(con, src_id), Binary(con, dst_id)
        except sqlite3.OperationalError as exc:
            # ``Binary`` adds missing feature columns; a snapshot is read-only by contract, so a
            # legacy store must be opened once by the corpus CLI *before* it is snapshotted.
            if "readonly" in str(exc).lower() or "read-only" in str(exc).lower():
                raise Refused("snapshot-needs-migration:open-once-with-corpus-cli-before-snapshot") from exc
            raise
    finally:
        con.close()
    same_arch = (sa.meta.get("arch"), sa.meta.get("bits")) == (sb.meta.get("arch"), sb.meta.get("bits"))
    src_addrs = [
        a for a, f in sa.funcs.items()
        if not f["is_thunk"] and (f["n_instr"] or 0) >= 4 and (restrict is None or a in restrict)
    ]
    taken = set(mapping.values())
    mapping_ref = put_json(objects, {
        "schema": MAPPING_SCHEMA, "round": int(round_index), "src": src_hash, "dst": dst_hash,
        "mapping": {str(k): v for k, v in sorted(mapping.items())},
    })
    specs: list[TaskSpec] = []
    index = 0
    for start in range(0, len(src_addrs), shard_size):
        chunk = src_addrs[start:start + shard_size]
        pairs: dict[str, list[int]] = {}
        needed: set[int] = set()
        for a in chunk:
            if a in mapping:
                continue
            cands = candidate_pairs(sa, sb, a, mapping) - taken
            if not cands:
                continue
            pairs[str(a)] = sorted(cands)
            needed |= cands
        if not pairs:
            continue
        shard = {
            "schema": SHARD_SCHEMA, "index": index, "round": int(round_index), "src_binary": src_hash, "dst_binary": dst_hash,
            "same_arch": same_arch, "use_name_features": use_name_features,
            "src": {k: _with_decomp(sa, int(k)) for k in pairs},
            "dst": {str(b): _with_decomp(sb, b) for b in sorted(needed)},
            "pairs": pairs,
        }
        shard_ref = put_json(objects, shard)
        specs.append(TaskSpec(
            kind=MatchScoreShard.name, kind_version=MatchScoreShard.version,
            inputs={"shard": shard_ref, "mapping": mapping_ref},
            params={"round": int(round_index), "index": index, "src": src_hash, "dst": dst_hash},
            basis_hash=basis_hash, capabilities=tuple(MatchScoreShard.capabilities),
            budget=BudgetClass.MICRO if len(pairs) <= MICRO_MAX_SOURCES else BudgetClass.SMALL,
        ))
        index += 1
    return specs


# --------------------------------------------------------------------------- view hook
MATCH_SCORE_SQL = """
CREATE TABLE IF NOT EXISTS grid_match_score (
    task_id    TEXT PRIMARY KEY,
    src_binary TEXT NOT NULL,
    dst_binary TEXT NOT NULL,
    round      INTEGER NOT NULL,
    shard      INTEGER NOT NULL,
    scored_ref TEXT NOT NULL,
    n_scored   INTEGER NOT NULL,
    basis_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_grid_match_score_pair ON grid_match_score(src_binary, dst_binary, round);
"""


@view_hook(MatchScoreShard.name)
def apply_match_score(kind: str, result: TaskResult, objects: ObjectStore, con) -> int:
    """Record the verified shard; ``match`` rows are the assign step's (U142), never written here."""
    ref = result.outputs.get("scored")
    if ref is None or not objects.exists(ref) or result.status != ResultStatus.OK:
        return 0
    out = get_json(objects, ref)
    ensure_tables(con, MATCH_SCORE_SQL)
    con.execute(
        "INSERT OR REPLACE INTO grid_match_score VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            result.task_id, str(out.get("src", "")), str(out.get("dst", "")), int(out.get("round", 0)),
            int(out.get("index", 0)), str(ref), len(out.get("scored") or []), result.basis_hash,
        ),
    )
    return 1


__all__ = [
    "MAPPING_SCHEMA", "MICRO_MAX_SOURCES", "MatchScoreShard", "SCORED_SCHEMA", "SHARD_SCHEMA",
    "binary_id_for", "plan_match_shards", "score_shard",
]

"""Cockpit live API: every corpus program drawn as a map of its functions.

Read model only. Every value comes from the corpus identity database at request
time (opened read-only); nothing is simulated and no product, program or binary
name is hardcoded: programs are groups of binaries by ``binary.game`` (a binary
without a game value is its own program). Heavy sqlite work runs in worker
threads and is cached by (db path, file/WAL identity, ``PRAGMA data_version``).
One shared poller per database feeds every SSE observer. Contract:
``docs/cockpit/API.md``.
"""
from __future__ import annotations

import asyncio
import bisect
import json
import logging
import os
import re
import sqlite3
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse

log = logging.getLogger(__name__)

COCKPIT_STATIC = Path(__file__).parent / "static" / "cockpit"
DB_SUFFIXES = (".sqlite", ".db")
POLL_S = 2.0
PING_S = 15.0
MAX_EDGES = 30000
MAX_NEIGHBOURS = 64
ACTIVITY_LIMIT = 50
QUEUE_MAX = 512
LANES = ("decompile", "pointers", "match", "name", "compile", "signature", "import", "other")
# Job actions whose id/title keywords would pick the wrong lane, by what the action actually does.
_LANE_BY_ACTION = {
    "workbench.match-candidate": "compile",  # "Compile and verify candidate": builds C and checks bytes
    "recover.verify-package": "compile",     # byte verification of a recovered package
    "corpus.cross-place": "match",           # carries identities across builds
}
# Ordered: the first lane whose keyword occurs in the job's action id/title wins.
_LANE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("decompile", ("decomp",)),
    ("pointers", ("pointer", "xref", "vtable", "dataref", "data-ref")),
    ("match", ("match", "bsim", "identity", "logical", "compare", "variant", "review")),
    ("name", ("rename", "name", "label", "symbol")),
    ("signature", ("signature", "prototype", "convention", "type")),
    ("compile", ("compile", "build", "objdiff", "parity", "byte", "link")),
    ("import", ("import", "ingest", "prepare", "acquire", "upload", "load")),
)
_BINARY_KEYS = ("slug", "binary", "binarySlug", "binary_slug", "target_slug", "program")
_BINARY_ID_KEYS = ("binary_id", "binaryId")
_ADDR_KEYS = ("addr", "address", "functionAddress", "function_address", "entry", "function")


class CockpitError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- db resolution

def _connect(path: Path | str) -> sqlite3.Connection:
    uri = f"file:{quote(str(path), safe='/')}?mode=ro"
    con = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=5)
    try:
        con.execute("PRAGMA query_only=1")
    except sqlite3.Error:
        pass
    return con


def resolve_db(explicit: str | None = None) -> Path:
    """Resolve the one selected corpus database through the shared validator."""
    if explicit:
        path = Path(explicit).expanduser()
        if path.suffix.lower() not in DB_SUFFIXES:
            raise CockpitError(f"db must be a {'/'.join(DB_SUFFIXES)} file: {explicit}", 400)
    try:
        from .common import CorpusBindingError, resolve_corpus_binding
        binding = resolve_corpus_binding(explicit)
    except CorpusBindingError as exc:
        raise CockpitError(str(exc), 503 if not explicit else 400) from exc
    return Path(binding["path"])


# --------------------------------------------------------------------------- helpers


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "program"


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {"", "0", "false", "no", "none"}


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        text = str(value).strip()
        return int(text, 16) if text.lower().startswith("0x") or re.search(r"[a-fA-F]", text) else int(text)
    except (TypeError, ValueError):
        return None


def _iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time(), tz=timezone.utc).isoformat(timespec="seconds")


class _Schema:
    def __init__(self, con: sqlite3.Connection) -> None:
        self.cols: dict[str, set[str]] = {}
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            self.cols[name] = {row[1] for row in con.execute(f'PRAGMA table_info("{name}")')}

    def has(self, table: str, *columns: str) -> bool:
        cols = self.cols.get(table)
        return cols is not None and all(c in cols for c in columns)

    def col(self, table: str, column: str, fallback: str = "NULL") -> str:
        return column if self.has(table, column) else fallback

    def unique_on(self, con: sqlite3.Connection, table: str, *columns: str) -> bool:
        """True when a unique index (or key) of ``table`` covers exactly ``columns``."""
        if table not in self.cols:
            return False
        want = list(columns)
        for row in con.execute(f'PRAGMA index_list("{table}")'):
            if not row[2]:
                continue
            if [r[2] for r in con.execute(f'PRAGMA index_info("{row[1]}")')] == want:
                return True
        return False


# --------------------------------------------------------------------------- snapshot


class Snapshot:
    """Everything derived from one database state. Immutable once built (caches grow lazily)."""

    def __init__(self, path: Path, key: tuple) -> None:
        self.path = path
        self.key = key
        self.built_at = time.time()
        self._lock = threading.RLock()
        self._cells: dict[str, dict] = {}
        self._cells_json: dict[str, bytes] = {}
        self._bin_index: dict[int, dict] = {}
        self._warming = False
        self._load_lock = threading.Lock()  # lazy name map / build counts; never held with _lock
        self._cell_locks: dict[str, threading.Lock] = {}
        con = _connect(path)
        try:
            self._build(con)
        finally:
            con.close()

    # ---- build -----------------------------------------------------------
    def _build(self, con: sqlite3.Connection) -> None:
        s = self.schema = _Schema(con)
        funcs: dict[int, int] = {}
        if s.has("func", "binary_id"):
            funcs = {int(b): int(n) for b, n in con.execute(
                "SELECT binary_id, COUNT(*) FROM func GROUP BY binary_id") if b is not None}
        bound: dict[int, int] = {}
        if s.has("identity", "binary_id", "addr"):
            count = "COUNT(addr)" if s.unique_on(con, "identity", "binary_id", "addr") else "COUNT(DISTINCT addr)"
            bound = {int(b): int(n) for b, n in con.execute(
                f"SELECT binary_id, {count} FROM identity GROUP BY binary_id") if b is not None}
        self.binaries: dict[int, dict] = {}
        if s.has("binary", "id"):
            sql = (f"SELECT id, {s.col('binary', 'slug', 'CAST(id AS TEXT)')}, {s.col('binary', 'game')}, "
                   f"{s.col('binary', 'platform')}, {s.col('binary', 'format')} FROM binary ORDER BY id")
            for bid, slug, game, platform, fmt in con.execute(sql):
                if bid is None or funcs.get(int(bid), 0) <= 0:
                    continue  # binaries with no functions are not drawn
                self.binaries[int(bid)] = {"id": int(bid), "slug": str(slug or bid), "game": game,
                                           "platform": platform or "unknown", "format": fmt or "",
                                           "functions": funcs.get(int(bid), 0), "bound": bound.get(int(bid), 0),
                                           "real_c": 0}
        # tiers (the per-logical name map is loaded lazily, only cells/function need it)
        self._lname: dict[int, tuple] | None = None
        tiers: Counter = Counter()
        tier_names: dict[int, str] = {}
        if s.has("logical_name", "logical_id", "name", "tier"):
            sql = (f"SELECT tier, MAX({s.col('logical_name', 'tier_name')}), COUNT(*) FROM logical_name "
                   "WHERE logical_id IS NOT NULL GROUP BY tier")
            for tier, tier_name, n in con.execute(sql):
                tier_i = _int(tier) or 0
                tiers[tier_i] += int(n)
                if tier_name:
                    tier_names.setdefault(tier_i, str(tier_name))
        self.tiers = [[tier_names.get(t, str(t)), n] for t, n in sorted(tiers.items())]
        # Per-logical build counts (nb) are loaded lazily with the name map; only cells need them.
        self._nb: dict[int, int] | None = None
        methods: list[list] = []
        identity_total = 0
        if s.has("identity", "logical_id", "binary_id"):
            identity_total = sum(bound.values())
            if s.has("identity", "method"):
                methods = [[m, n] for m, n in con.execute(
                    "SELECT method, COUNT(*) FROM identity GROUP BY method ORDER BY COUNT(*) DESC")]
        self.match_methods = methods
        logical_total = 0
        if s.has("logical_function"):
            logical_total = int(con.execute("SELECT COUNT(*) FROM logical_function").fetchone()[0])
        # recovered functions: resolve NULL addresses by a name unique in the same binary
        self.recovered: list[dict] = []
        self.realc_logical: set[int] = set()
        self.realc_addrs: dict[int, set[int]] = {}
        if s.has("recovered_function", "binary_id", "name"):
            rf = "recovered_function"
            sql = (f"SELECT {s.col(rf, 'program')}, binary_id, {s.col(rf, 'addr')}, name, {s.col(rf, 'size')}, "
                   f"{s.col(rf, 'convention')}, {s.col(rf, 'real_c', '0')}, {s.col(rf, 'logical_id')} FROM {rf}")
            rows = con.execute(sql).fetchall()
            unique_names: dict[int, dict[str, int]] = {}
            wanted: dict[int, set[str]] = {}
            for r in rows:
                if r[2] is None and r[1] is not None and r[3]:
                    wanted.setdefault(int(r[1]), set()).add(str(r[3]))
            if s.has("func", "binary_id", "addr", "name"):
                for bid, names in wanted.items():
                    found: dict[str, int] = {}
                    ordered = sorted(names)
                    for start in range(0, len(ordered), 500):
                        chunk = ordered[start:start + 500]
                        marks = ",".join("?" * len(chunk))
                        for name, addr, count in con.execute(
                                f"SELECT name, MIN(addr), COUNT(*) FROM func WHERE binary_id=? AND name IN ({marks}) "
                                "GROUP BY name", (bid, *chunk)):
                            if count == 1:
                                found[name] = addr
                    unique_names[bid] = found
            lookup = s.has("identity", "logical_id", "binary_id", "addr")
            for program, bid, addr, name, size, conv, real_c, lid in rows:
                bid_i = _int(bid)
                addr_i = _int(addr)
                if addr_i is None and bid_i is not None:
                    addr_i = unique_names.get(bid_i, {}).get(name)
                logicals = {int(lid)} if _int(lid) else set()
                if addr_i is not None and bid_i is not None and lookup:
                    logicals |= {int(r[0]) for r in con.execute(
                        "SELECT logical_id FROM identity WHERE binary_id=? AND addr=?", (bid_i, addr_i)) if r[0]}
                rc = _truthy(real_c)
                self.recovered.append({"program": program, "binary_id": bid_i, "addr": addr_i, "name": name,
                                       "size": size, "convention": conv, "real_c": int(rc),
                                       "logicals": logicals})
                if rc:
                    self.realc_logical |= logicals
                    if bid_i is not None and addr_i is not None:
                        self.realc_addrs.setdefault(bid_i, set()).add(addr_i)
                    if bid_i in self.binaries:
                        self.binaries[bid_i]["real_c"] += 1
        # programs
        groups: dict[tuple, list[int]] = {}
        for bid, b in self.binaries.items():
            game = b["game"]
            key = ("game", str(game)) if game not in (None, "") else ("binary", bid)
            groups.setdefault(key, []).append(bid)
        self.programs: list[dict] = []
        self.program_by_id: dict[str, dict] = {}
        self.program_of_binary: dict[int, str] = {}
        used: set[str] = set()
        for key, members in sorted(groups.items(), key=lambda kv: (kv[0][0] != "game", str(kv[0][1]))):
            ref = max(members, key=lambda m: (self.binaries[m]["functions"], -m))
            label = key[1] if key[0] == "game" else self.binaries[ref]["slug"]
            pid = base = _slugify(str(label))
            n = 2
            while pid in used:
                pid, n = f"{base}-{n}", n + 1
            used.add(pid)
            order = [ref] + sorted(m for m in members if m != ref)
            builds = [{k: self.binaries[m][k] for k in ("id", "slug", "platform", "format", "functions", "bound", "real_c")}
                      for m in order]
            program = {"id": pid, "label": str(label), "ref": self.binaries[ref]["slug"], "ref_id": ref,
                       "n": self.binaries[ref]["functions"], "builds": builds}
            self.programs.append(program)
            self.program_by_id[pid] = program
            for m in members:
                self.program_of_binary[m] = pid
        self.programs.sort(key=lambda p: -p["n"])
        self.slug_to_binary = {b["slug"]: bid for bid, b in self.binaries.items()}
        self.totals = {
            "binaries": len(self.binaries),
            "functions": sum(b["functions"] for b in self.binaries.values()),
            "logical": logical_total,
            "bound": identity_total,
            "recovered_logical": len(self.realc_logical),
            "named_above_placeholder": sum(n for t, n in tiers.items() if 1 <= t <= 4),
            "named_of": logical_total,
        }

    @property
    def lname(self) -> dict[int, tuple]:
        """logical_id -> (name, tier, tier_name, signature, source_file); loaded on first use."""
        names = self._lname
        if names is not None:
            return names
        with self._load_lock:
            if self._lname is not None:
                return self._lname
            names = {}
            s = self.schema
            if s.has("logical_name", "logical_id", "name", "tier"):
                sql = (f"SELECT logical_id, name, tier, {s.col('logical_name', 'tier_name')}, "
                       f"{s.col('logical_name', 'signature')}, {s.col('logical_name', 'source_file')} FROM logical_name")
                con = _connect(self.path)
                try:
                    for lid, name, tier, tier_name, sig, src in con.execute(sql):
                        if lid is not None:
                            names[int(lid)] = (name, _int(tier) or 0, tier_name or "", sig, src)
                finally:
                    con.close()
            self._lname = names
            return names

    @property
    def nb(self) -> dict[int, int]:
        """logical_id -> number of distinct builds bound to it; loaded on first use."""
        counts = self._nb
        if counts is not None:
            return counts
        with self._load_lock:
            if self._nb is not None:
                return self._nb
            counts = {}
            if self.schema.has("identity", "logical_id", "binary_id"):
                con = _connect(self.path)
                try:
                    counts = {int(l): int(n) for l, n in con.execute(
                        "SELECT logical_id, COUNT(DISTINCT binary_id) FROM identity "
                        "WHERE logical_id IS NOT NULL GROUP BY logical_id")}
                finally:
                    con.close()
            self._nb = counts
            return counts

    def warm_in_background(self) -> None:
        """Start (once) loading what a first ``cells`` request needs, so it is served from cache.

        The summary is almost always followed by a cells request for the largest program; loading
        the name map, build counts and that program's cells in a worker thread overlaps them with
        the client's round trip instead of paying for them on the request.
        """
        with self._lock:
            if self._warming:
                return
            self._warming = True

        def run() -> None:
            try:
                self.lname
                self.nb
                if self.programs:
                    self.cells_json(self.programs[0]["id"])
            except Exception:
                log.debug("cockpit warm-up failed", exc_info=True)

        threading.Thread(target=run, name="cockpit-warm", daemon=True).start()

    # ---- summary ---------------------------------------------------------
    def summary(self) -> dict:
        try:
            st = self.path.stat()
            db = {"path": str(self.path), "bytes": st.st_size, "mtime": _iso(st.st_mtime)}
        except OSError:
            db = {"path": str(self.path), "bytes": None, "mtime": None}
        programs = [{k: v for k, v in p.items() if k != "ref_id"} for p in self.programs]
        return {"ok": True, "generated": _iso(), "db": db, "totals": dict(self.totals), "programs": programs,
                "tiers": self.tiers, "match_methods": self.match_methods}

    # ---- per-binary index ------------------------------------------------
    def binary_index(self, bid: int) -> dict:
        with self._lock:
            cached = self._bin_index.get(bid)
            if cached is not None:
                return cached
        s = self.schema
        con = _connect(self.path)
        try:
            addrs: list[int] = []
            sizes: list[int] = []
            fnames: list[str] = []
            if s.has("func", "binary_id", "addr"):
                sql = (f"SELECT addr, {s.col('func', 'size', '0')}, {s.col('func', 'name')} FROM func "
                       "WHERE binary_id=? ORDER BY addr")
                for addr, size, name in con.execute(sql, (bid,)):
                    addrs.append(int(addr))
                    sizes.append(int(size or 0))
                    fnames.append(name or "")
            ident: dict[int, int] = {}
            if s.has("identity", "binary_id", "addr", "logical_id"):
                ident = {int(a): int(l) for a, l in con.execute(
                    "SELECT addr, logical_id FROM identity WHERE binary_id=?", (bid,)) if a is not None and l}
        finally:
            con.close()
        index = {"addrs": addrs, "sizes": sizes, "names": fnames, "ident": ident,
                 "pos": {a: i for i, a in enumerate(addrs)}}
        with self._lock:
            self._bin_index[bid] = index
        return index

    def display_name(self, bid: int, i: int) -> str:
        index = self.binary_index(bid)
        lid = index["ident"].get(index["addrs"][i])
        entry = self.lname.get(lid) if lid else None
        if entry and entry[0]:
            return str(entry[0])
        return index["names"][i]

    # ---- cells -----------------------------------------------------------
    def _cell_key(self, program_id: str, ref: str | None) -> tuple[str, dict, int]:
        program = self.program_by_id.get(program_id)
        if program is None:
            raise CockpitError(f"unknown program: {program_id}", 404)
        bid = program["ref_id"]
        if ref and ref != program["ref"]:
            candidate = self.slug_to_binary.get(ref)
            if candidate is None or self.program_of_binary.get(candidate) != program_id:
                raise CockpitError(f"build {ref} is not part of program {program_id}", 404)
            return f"{program_id}@{candidate}", program, candidate
        return program_id, program, bid

    def cells(self, program_id: str, ref: str | None = None) -> dict:
        key, program, bid = self._cell_key(program_id, ref)
        with self._lock:
            cached = self._cells.get(key)
            build_lock = self._cell_locks.setdefault(key, threading.Lock())
        if cached is not None:
            return cached
        with build_lock:  # one build per cell set; concurrent callers (warm-up, requests) wait for it
            with self._lock:
                cached = self._cells.get(key)
            if cached is not None:
                return cached
            return self._build_cells(key, program_id, bid)

    def _build_cells(self, key: str, program_id: str, bid: int) -> dict:
        index = self.binary_index(bid)
        addrs, ident = index["addrs"], index["ident"]
        realc = self.realc_addrs.get(bid, set())
        lname, nb_of = self.lname, self.nb
        state = []
        tier = []
        nb: list[int] = []
        logical: list[int] = []
        names: dict[str, str] = {}
        for i, addr in enumerate(addrs):
            lid = ident.get(addr, 0)
            if addr in realc or (lid and lid in self.realc_logical):
                state.append("2")
            else:
                state.append("1" if lid else "0")
            entry = lname.get(lid) if lid else None
            t = entry[1] if entry else 0
            tier.append(str(t) if 0 <= t <= 9 else "0")
            nb.append(nb_of.get(lid, 0) if lid else 0)
            logical.append(lid)
            if entry and 1 <= t <= 3 and entry[0]:
                names[str(i)] = str(entry[0])
        edges = self._edges(bid, index["pos"], names)
        cells = {"ok": True, "program_id": program_id, "ref": self.binaries[bid]["slug"], "n": len(addrs),
                 "addr": addrs, "size": index["sizes"], "state": "".join(state), "nb": nb,
                 "tier": "".join(tier), "logical": logical, "names": names, "edges": edges}
        with self._lock:
            self._cells.setdefault(key, cells)
            return self._cells[key]

    def cells_json(self, program_id: str, ref: str | None = None) -> bytes:
        key, _, _ = self._cell_key(program_id, ref)
        with self._lock:
            cached = self._cells_json.get(key)
        if cached is not None:
            return cached
        payload = json.dumps(self.cells(program_id, ref), separators=(",", ":")).encode()
        with self._lock:
            self._cells_json[key] = payload
        return payload

    def cached_cells(self) -> list[tuple[str, str | None]]:
        """(program_id, ref slug or None) for every materialized cell set."""
        with self._lock:
            keys = list(self._cells)
        out = []
        for key in keys:
            pid, _, bid = key.partition("@")
            out.append((pid, self.binaries[int(bid)]["slug"] if bid else None))
        return out

    def _edges(self, bid: int, pos: dict[int, int], names: dict[str, str]) -> list[list[int]]:
        if not self.schema.has("calledge", "binary_id", "caller_addr", "callee_addr"):
            return []
        con = _connect(self.path)
        try:
            seen: set[tuple[int, int]] = set()
            for caller, callee in con.execute(
                    "SELECT caller_addr, callee_addr FROM calledge WHERE binary_id=?", (bid,)):
                i, j = pos.get(caller), pos.get(callee)
                if i is None or j is None or i == j:
                    continue
                seen.add((i, j))
        finally:
            con.close()
        named = {int(k) for k in names}
        # Named-first: both ends named, then one, then none; (i, j) order inside each bucket.
        buckets: tuple[list, list, list] = ([], [], [])
        for edge in seen:
            buckets[2 - (edge[0] in named) - (edge[1] in named)].append(edge)
        out: list[list[int]] = []
        for bucket in buckets:
            if len(out) >= MAX_EDGES:
                break
            bucket.sort()
            out.extend([i, j] for i, j in bucket[:MAX_EDGES - len(out)])
        return out

    # ---- function detail -------------------------------------------------
    def function(self, *, program_id: str | None = None, index: int | None = None,
                 binary_id: int | None = None, addr: int | None = None, ref: str | None = None) -> dict:
        if program_id is not None:
            _, program, bid = self._cell_key(program_id, ref)
            bindex = self.binary_index(bid)
            if index is None or not 0 <= index < len(bindex["addrs"]):
                raise CockpitError("index out of range", 404)
            i = index
        elif binary_id is not None and addr is not None:
            bid = binary_id
            if bid not in self.binaries:
                raise CockpitError(f"unknown binary: {binary_id}", 404)
            program = self.program_by_id[self.program_of_binary[bid]]
            bindex = self.binary_index(bid)
            i = bindex["pos"].get(addr)
            if i is None:
                raise CockpitError(f"no function at {addr:#x} in binary {binary_id}", 404)
        else:
            raise CockpitError("pass program_id and index, or binary_id and addr", 400)
        a = bindex["addrs"][i]
        lid = bindex["ident"].get(a, 0)
        s = self.schema
        con = _connect(self.path)
        try:
            frow = None
            if s.has("func", "binary_id", "addr"):
                frow = con.execute(
                    f"SELECT {s.col('func', 'name')}, {s.col('func', 'signature')}, {s.col('func', 'source_file')} "
                    "FROM func WHERE binary_id=? AND addr=?", (bid, a)).fetchone()
            lf = None
            if lid and s.has("logical_function", "id"):
                lf = con.execute(
                    f"SELECT {s.col('logical_function', 'best_name')}, {s.col('logical_function', 'best_signature')}, "
                    f"{s.col('logical_function', 'source_file')} FROM logical_function WHERE id=?", (lid,)).fetchone()
            instances: list[dict] = []
            if lid and s.has("identity", "logical_id", "binary_id", "addr"):
                sql = (f"SELECT i.binary_id, i.addr, {('i.confidence' if s.has('identity', 'confidence') else 'NULL')}, "
                       f"{('i.method' if s.has('identity', 'method') else 'NULL')}, "
                       f"{('f.size' if s.has('func', 'size') else 'NULL')} FROM identity i "
                       "LEFT JOIN func f ON f.binary_id=i.binary_id AND f.addr=i.addr WHERE i.logical_id=? "
                       "ORDER BY i.binary_id, i.addr")
                for ib, ia, conf, method, size in con.execute(sql, (lid,)):
                    b = self.binaries.get(int(ib))
                    instances.append({"binary_id": int(ib), "slug": b["slug"] if b else str(ib),
                                      "platform": b["platform"] if b else "unknown", "addr": int(ia),
                                      "size": size, "confidence": conf, "method": method})
            callers = self._neighbours(con, bid, a, "callee_addr", "caller_addr")
            callees = self._neighbours(con, bid, a, "caller_addr", "callee_addr")
            decomp = None
            if s.has("decomp", "binary_id", "addr"):
                row = con.execute(
                    f"SELECT {s.col('decomp', 'ok')}, {s.col('decomp', 'n_lines')}, {s.col('decomp', 'n_calls')}, "
                    f"{s.col('decomp', 'max_nest')} FROM decomp WHERE binary_id=? AND addr=?", (bid, a)).fetchone()
                if row:
                    decomp = {"ok": _truthy(row[0]), "n_lines": row[1], "n_calls": row[2], "max_nest": row[3]}
        finally:
            con.close()
        entry = self.lname.get(lid) if lid else None
        name = (entry[0] if entry and entry[0] else None) or (lf[0] if lf and lf[0] else None) or (frow[0] if frow else None)
        signature = (entry[3] if entry and entry[3] else None) or (lf[1] if lf and lf[1] else None) or (frow[1] if frow else None)
        source = (entry[4] if entry and entry[4] else None) or (lf[2] if lf and lf[2] else None) or (frow[2] if frow else None)
        present = {inst["binary_id"] for inst in instances}
        absent = [b["slug"] for b in program["builds"] if b["id"] not in present and not (not lid and b["id"] == bid)]
        keys = {(inst["binary_id"], inst["addr"]) for inst in instances} | {(bid, a)}
        recovered = [
            {"binary_slug": self.binaries[r["binary_id"]]["slug"] if r["binary_id"] in self.binaries else str(r["binary_id"]),
             "addr": r["addr"], "real_c": r["real_c"], "convention": r["convention"], "size": r["size"],
             "name": r["name"]}
            for r in self.recovered
            if (lid and lid in r["logicals"]) or (r["binary_id"], r["addr"]) in keys
        ]
        return {"ok": True, "program_id": program["id"], "binary_id": bid, "index": i, "addr": a,
                "size": bindex["sizes"][i], "name": name, "tier": entry[1] if entry else 0,
                "tier_name": entry[2] if entry else "", "logical_id": lid or None, "signature": signature,
                "source_file": source, "instances": instances, "absent": absent,
                "callers": callers, "callees": callees, "recovered": recovered, "decomp": decomp}

    def _neighbours(self, con: sqlite3.Connection, bid: int, addr: int, match: str, other: str) -> list[dict]:
        if not self.schema.has("calledge", "binary_id", "caller_addr", "callee_addr"):
            return []
        bindex = self.binary_index(bid)
        out: list[dict] = []
        seen: set[int] = set()
        for (value,) in con.execute(
                f"SELECT DISTINCT {other} FROM calledge WHERE binary_id=? AND {match}=? ORDER BY {other}", (bid, addr)):
            j = bindex["pos"].get(value)
            if j is None or j in seen:
                continue
            seen.add(j)
            out.append({"index": j, "name": self.display_name(bid, j), "addr": value})
            if len(out) >= MAX_NEIGHBOURS:
                break
        return out


def diff_cells(old: dict, new: dict) -> tuple[list[list], bool]:
    """Return ([[index, state, nb, tier]], reload) — reload when the cell layout changed."""
    if old["addr"] != new["addr"]:
        return [], True
    changes = []
    os_, ns = old["state"], new["state"]
    ot, nt = old["tier"], new["tier"]
    onb, nnb = old["nb"], new["nb"]
    for i in range(len(ns)):
        if os_[i] != ns[i] or onb[i] != nnb[i] or ot[i] != nt[i]:
            changes.append([i, int(ns[i]), nnb[i], int(nt[i])])
    return changes, False


# --------------------------------------------------------------------------- store (per db path)


class _Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._key_lock = threading.Lock()
        self._build_lock = threading.Lock()
        self._con: sqlite3.Connection | None = None
        self.snapshot_obj: Snapshot | None = None

    def state_key(self) -> tuple:
        st = self.path.stat()
        wal = Path(str(self.path) + "-wal")
        try:
            ws = wal.stat()
            wal_id = (ws.st_mtime_ns, ws.st_size) if ws.st_size else None
        except OSError:
            wal_id = None
        with self._key_lock:
            try:
                if self._con is None:
                    self._con = _connect(self.path)
                version = self._con.execute("PRAGMA data_version").fetchone()[0]
            except sqlite3.Error:
                if self._con is not None:
                    self._con.close()
                self._con = None
                version = None
        return (str(self.path), st.st_mtime_ns, st.st_size, wal_id, version)

    def snapshot(self) -> Snapshot:
        key = self.state_key()
        current = self.snapshot_obj
        if current is not None and current.key == key:
            return current
        with self._build_lock:
            current = self.snapshot_obj
            if current is not None and current.key == key:
                return current
            fresh = Snapshot(self.path, key)
            self.snapshot_obj = fresh
            return fresh


_STORES: dict[str, _Store] = {}
_STORES_LOCK = threading.Lock()


def store_for(path: Path) -> _Store:
    with _STORES_LOCK:
        store = _STORES.get(str(path))
        if store is None:
            store = _STORES[str(path)] = _Store(path)
        return store


# --------------------------------------------------------------------------- activity (existing job feed)


def _job_rows() -> list[dict]:
    """Rows from the dashboard's existing job store (``GET /api/v1/jobs``)."""
    try:
        from .actions.jobs import list_jobs
    except Exception:  # pragma: no cover - job store unavailable in this process
        return []
    try:
        return [job.to_dict(include_log=False, include_details=False) for job in list_jobs(compact=True)]
    except Exception:
        log.debug("cockpit: job feed unavailable", exc_info=True)
        return []


def lane_for(action_id: str, title: str = "") -> str:
    exact = _LANE_BY_ACTION.get(action_id.strip().lower())
    if exact:
        return exact
    text = f"{action_id} {title}".lower()
    for lane, words in _LANE_KEYWORDS:
        if any(word in text for word in words):
            return lane
    return "other"


def activity_event(job: dict, snap: Snapshot | None) -> dict:
    params = job.get("params") or {}
    ts = job.get("finishedAt") or job.get("startedAt") or job.get("createdAt") or 0
    event: dict[str, Any] = {"ts": ts, "lane": lane_for(str(job.get("actionId") or ""), str(job.get("title") or "")),
                             "kind": job.get("actionId") or "", "label": job.get("title") or job.get("actionId") or "",
                             "status": job.get("status") or "", "job_id": job.get("id")}
    binary_id = None
    for key in _BINARY_ID_KEYS:
        binary_id = _int(params.get(key))
        if binary_id is not None:
            break
    slug = next((str(params[k]) for k in _BINARY_KEYS if isinstance(params.get(k), str) and params.get(k)), None)
    if snap is not None:
        if binary_id is None and slug is not None:
            binary_id = snap.slug_to_binary.get(slug)
        if binary_id is not None and binary_id in snap.binaries:
            event["binary"] = snap.binaries[binary_id]["slug"]
            event["program_id"] = snap.program_of_binary.get(binary_id)
    if "binary" not in event and slug:
        event["binary"] = slug
    for key in _ADDR_KEYS:
        value = params.get(key)
        if value is None:
            continue
        addr = _int(value) if not isinstance(value, str) or re.fullmatch(r"(0x)?[0-9a-fA-F]+", value.strip()) else None
        if addr is not None:
            event["addr"] = addr
            break
    return event


def activity(snap: Snapshot | None, limit: int = ACTIVITY_LIMIT) -> list[dict]:
    events = [activity_event(job, snap) for job in _job_rows()]
    events.sort(key=lambda e: e["ts"] or 0, reverse=True)
    return events[:limit]


# --------------------------------------------------------------------------- SSE hub


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


class _Hub:
    """One poller per database; every client gets its own bounded queue."""

    def __init__(self, store: _Store, loop: asyncio.AbstractEventLoop) -> None:
        self.store = store
        self.loop = loop
        self.clients: set[asyncio.Queue] = set()
        self.task: asyncio.Task | None = None
        self._jobs: dict[str, tuple] | None = None

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
        self.clients.add(queue)
        if self.task is None or self.task.done():
            self.task = self.loop.create_task(self._run())
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.clients.discard(queue)
        if not self.clients:
            if self.task is not None and not self.task.done():
                self.task.cancel()
            self.task = None
            if _HUBS.get(str(self.store.path)) is self:
                del _HUBS[str(self.store.path)]

    def publish(self, message: str) -> None:
        for queue in list(self.clients):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # A stalled client loses intermediate diffs; it gets a fresh summary to resync.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(_sse("resync", {"reason": "client queue overflow"}))

    def _jobs_changed(self, snap: Snapshot | None) -> list[dict]:
        rows = _job_rows()
        current = {str(r.get("id")): (r.get("status"), r.get("finishedAt")) for r in rows}
        previous, self._jobs = self._jobs, current
        if previous is None:
            return []
        changed = [r for r in rows if previous.get(str(r.get("id"))) != current[str(r.get("id"))]]
        return sorted((activity_event(r, snap) for r in changed), key=lambda e: e["ts"] or 0)

    def _tick(self) -> list[str]:
        old = self.store.snapshot_obj
        new = self.store.snapshot()
        out: list[str] = []
        if old is not None and new is not old:
            summary = new.summary()
            summary["activity"] = activity(new)
            out.append(_sse("summary", summary))
            for pid, ref in old.cached_cells():
                try:
                    before, after = old.cells(pid, ref), new.cells(pid, ref)
                except CockpitError:
                    continue  # program or build vanished; the summary above carries that
                changes, reload = diff_cells(before, after)
                event: dict[str, Any] = {"program_id": pid, "changes": changes}
                if ref:
                    event["ref"] = ref
                if reload:
                    event["reload"] = True
                if changes or reload:
                    out.append(_sse("cells", event))
        for event in self._jobs_changed(new):
            out.append(_sse("activity", event))
        return out

    async def _run(self) -> None:
        try:
            while self.clients:
                try:
                    messages = await asyncio.to_thread(self._tick)
                    for message in messages:
                        self.publish(message)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.warning("cockpit poller tick failed", exc_info=True)
                await asyncio.sleep(POLL_S)
        except asyncio.CancelledError:
            pass


_HUBS: dict[str, _Hub] = {}


def _hub_for(store: _Store) -> _Hub:
    loop = asyncio.get_running_loop()
    hub = _HUBS.get(str(store.path))
    if hub is None or hub.loop is not loop:
        hub = _HUBS[str(store.path)] = _Hub(store, loop)
    return hub


# --------------------------------------------------------------------------- router


def _error(exc: Exception) -> JSONResponse:
    if isinstance(exc, CockpitError):
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=exc.status)
    log.warning("cockpit request failed", exc_info=exc)
    return JSONResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status_code=500)


async def _snapshot(db: str | None) -> Snapshot:
    path = await asyncio.to_thread(resolve_db, db)
    return await asyncio.to_thread(store_for(path).snapshot)


def _placeholder() -> str:
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Cockpit</title></head>"
            "<body><main><h1>Cockpit</h1><p>The cockpit page is not installed yet. The live API is available at "
            "<a href=\"/dashboard/api/cockpit/summary\">/dashboard/api/cockpit/summary</a>.</p></main></body></html>")


def create_cockpit_router() -> APIRouter:
    router = APIRouter(tags=["cockpit"])

    @router.get("/dashboard/api/cockpit/summary")
    async def cockpit_summary(db: str | None = None) -> Response:
        try:
            snap = await _snapshot(db)
            snap.warm_in_background()
            payload = snap.summary()
            payload["activity"] = await asyncio.to_thread(activity, snap)
            return JSONResponse(payload, headers={"Cache-Control": "no-store"})
        except Exception as exc:
            return _error(exc)

    @router.get("/dashboard/api/cockpit/program/{program_id}/cells")
    async def cockpit_cells(program_id: str, db: str | None = None, ref: str | None = None) -> Response:
        try:
            snap = await _snapshot(db)
            body = await asyncio.to_thread(snap.cells_json, program_id, ref)
            return Response(body, media_type="application/json", headers={"Cache-Control": "no-store"})
        except Exception as exc:
            return _error(exc)

    @router.get("/dashboard/api/cockpit/function")
    async def cockpit_function(program_id: str | None = None, index: int | None = None,
                               binary_id: int | None = None, addr: str | None = None,
                               db: str | None = None, ref: str | None = None) -> Response:
        try:
            address = _int(addr) if addr is not None else None
            if addr is not None and address is None:
                raise CockpitError(f"bad addr: {addr}", 400)
            snap = await _snapshot(db)
            payload = await asyncio.to_thread(snap.function, program_id=program_id, index=index,
                                              binary_id=binary_id, addr=address, ref=ref)
            return JSONResponse(payload, headers={"Cache-Control": "no-store"})
        except Exception as exc:
            return _error(exc)

    @router.get("/dashboard/api/cockpit/stream")
    async def cockpit_stream(request: Request, db: str | None = None) -> Response:
        try:
            path = await asyncio.to_thread(resolve_db, db)
            store = store_for(path)
            snap = await asyncio.to_thread(store.snapshot)
        except Exception as exc:
            return _error(exc)
        hub = _hub_for(store)
        queue = hub.subscribe()

        async def events():
            try:
                yield "retry: 3000\n\n"
                yield _sse("hello", {"db": str(path), "programs": [p["id"] for p in snap.programs]})
                while True:
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=PING_S)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield message
            finally:
                hub.unsubscribe(queue)

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    def _page_headers() -> dict[str, str]:
        from .router import SECURITY_HEADERS
        return dict(SECURITY_HEADERS)

    @router.get("/dashboard/cockpit")
    @router.get("/dashboard/cockpit/")
    async def cockpit_page() -> Response:
        entry = COCKPIT_STATIC / "index.html"
        if entry.is_file():
            return FileResponse(entry, media_type="text/html", headers=_page_headers())
        return HTMLResponse(_placeholder(), headers=_page_headers())

    @router.get("/dashboard/cockpit/{asset:path}")
    async def cockpit_asset(asset: str) -> Response:
        root = COCKPIT_STATIC.resolve()
        target = (COCKPIT_STATIC / asset).resolve()
        if not asset or not target.is_relative_to(root) or not target.is_file():
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(target, headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})

    return router

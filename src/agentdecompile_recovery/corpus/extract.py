"""Write feature-rich function snapshots for the corpus pipeline.

Ghidra-backed extract needs a live program. JSON snapshots do not: they accept
already-extracted rows (strings, consts, mnem, edges) and write ``{id}.functions.json``.

Single-writer rule for ``binary.content_sha256``: only a caller that hashed
the raw image (the ``content_sha256`` backfill pass, or an extractor handing
``meta["content_sha256"]`` in) supplies the digest. ``upsert_binary`` never
derives one from ``repo_path`` and never replaces a stored digest with NULL.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canon import canonicalize
from .corpus_config import load_maps
from .determinism_basis import BasisError, basis_hash_for, install_analyzer_version, processor_spec_hash_for
from .features import merge_tiers, tier1, tier2
from .io import write_json
from .fingerprint_hashes import attach_hashes
from .store import ensure_binary_columns, ensure_func_columns, j


def slugify(repo_path: str) -> str:
    return repo_path.strip("/").replace("/", "__").replace(" ", "_")


def resolve_source(repo_path: str, *, workspace: Path | str | None = None) -> str:
    """Map a canonical repo path to a local analysed copy when maps.json says so.

    ``maps.json`` may contain ``local_sources``: {repo_path: template}.
    Templates may include ``{w}`` for the workspace path. There is no built-in
    product map.
    """
    sources = dict(load_maps().get("local_sources") or {})
    tpl = sources.get(repo_path)
    if not tpl:
        return repo_path
    work = workspace or ""
    return str(tpl).format(w=work)


def snapshot_path(out_dir: Path, binary_id: str) -> Path:
    return Path(out_dir) / f"{binary_id}.functions.json"


def write_snapshot(out_dir: Path, binary_id: str, functions: list[dict[str, Any]]) -> Path:
    dest = snapshot_path(out_dir, binary_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(functions, indent=2) + "\n", encoding="utf-8")
    return dest


def enrich_canon(row: dict[str, Any]) -> dict[str, Any]:
    canon = canonicalize(
        row.get("name") or "",
        namespace=row.get("namespace") or "",
        plate=row.get("plate"),
        dm_name=row.get("dm_name"),
        dm_namespace=row.get("dm_namespace"),
        dm_params=row.get("dm_params"),
    )
    merged = dict(row)
    merged.update(canon)
    return merged


def functions_from_program(program, monitor=None) -> list[dict[str, Any]]:
    t1 = tier1(program)
    t2 = tier2(program, monitor)
    return [enrich_canon(row) for row in merge_tiers(t1, t2)]


def recovery_family(repo_path: str, slug: str, meta: dict[str, Any]) -> str | None:
    """Use only an explicit catalog or operator assignment.

    Returns ``None`` when nothing classifies the build. The store derives the
    isolating placeholder (``'unclassified:' || substr(content_sha256, 1, 16)``,
    ``store.backfill_recovery_family``) once the digest exists; an
    ``unclassified:*`` value handed back in *meta* is that placeholder or an
    older one, never a classification, so it is not returned either.
    """
    maps = load_maps()
    families = maps.get("recovery_families") or maps.get("recoveryFamilies") or {}
    if isinstance(families, dict):
        configured = str(families.get(repo_path) or families.get(slug) or "").strip()
        if configured:
            return configured
    for entry in maps.get("recovery_family_catalog") or []:
        if isinstance(entry, dict) and str(entry.get("repo_path") or entry.get("repoPath") or "") == repo_path:
            configured = str(entry.get("recovery_family") or entry.get("recoveryFamily") or "").strip()
            if configured:
                return configured
    configured = str(meta.get("recovery_family") or meta.get("recoveryFamily") or "").strip()
    if configured and not configured.startswith("unclassified:"):
        return configured
    return None


def live_analyzer_version() -> str | None:
    """Version of the analyzer this process runs inside, or None outside one."""
    try:
        from ghidra.framework import Application  # type: ignore[import-not-found]

        value = str(Application.getApplicationVersion() or "").strip()
        return value or None
    except Exception:  # noqa: BLE001 -- not running inside the analyzer
        return None


def stamp_analyzer_identity(
    con,
    *,
    analyzer_version: str | None,
    binary_ids: list[int] | None = None,
    source: str = "ingest",
    overwrite: bool = False,
) -> dict[str, list[int]]:
    """Write ``analyzer_version``, ``processor_spec_hash``, ``basis_hash`` and
    ``basis_source`` for *binary_ids* (default: every row).

    The one primitive both ingest and the ``analyzer_identity`` backfill pass
    use, so the two paths cannot drift. With ``overwrite=False`` a value
    already present is kept and only NULL columns are filled; a row whose
    three identity columns are all present is reported under ``unchanged``.
    Returns ``{"stamped": [...ids], "unchanged": [...ids], "skipped": [...ids]}``;
    ``skipped`` holds rows that could not be completed (no analyzer version
    or no language id). Nothing is committed here.
    """
    version = str(analyzer_version or "").strip() or None
    if version == "unknown":
        version = None
    where, params = "", ()
    if binary_ids is not None:
        marks = ",".join("?" for _ in binary_ids)
        where, params = f" WHERE id IN ({marks})", tuple(int(b) for b in binary_ids)
    rows = con.execute(
        "SELECT id, language_id, analyzer_version, processor_spec_hash, basis_hash FROM binary" + where + " ORDER BY id",
        params,
    ).fetchall()
    out: dict[str, list[int]] = {"stamped": [], "unchanged": [], "skipped": []}
    for row in rows:
        bid = int(row[0])
        have_version = row[2] if not overwrite else None
        have_spec = row[3] if not overwrite else None
        have_hash = row[4] if not overwrite else None
        if have_version and have_spec and have_hash:
            out["unchanged"].append(bid)
            continue
        new_version = have_version or version
        new_spec = have_spec or processor_spec_hash_for(row[1])
        if not new_version or not new_spec:
            out["skipped"].append(bid)
            continue
        try:
            new_hash = have_hash or basis_hash_for(new_version)
        except BasisError:
            out["skipped"].append(bid)
            continue
        con.execute(
            "UPDATE binary SET analyzer_version=?, processor_spec_hash=?, basis_hash=?, basis_source=? WHERE id=?",
            (new_version, new_spec, new_hash, source, bid),
        )
        out["stamped"].append(bid)
    return out


def _text_or_none(value: Any) -> str | None:
    """Stripped text, or ``None`` when blank, so an empty string cannot clear a stored value."""
    text = str(value or "").strip()
    return text or None


def _digest_or_none(value: Any) -> str | None:
    """``content_sha256`` is a key: stripped and lower-case, ``None`` when blank."""
    text = _text_or_none(value)
    return text.lower() if text else None


def upsert_binary(
    con,
    *,
    repo_path: str,
    slug: str,
    program=None,
    meta: dict[str, Any] | None = None,
    allow_reidentify: bool = False,
) -> int:
    """Insert or update a binary row. *meta* supplies game/platform/arch when known.

    Facts already stored are never erased by a caller that knows fewer of
    them: ``content_sha256``, ``md5``, ``language_id``, ``arch``, ``bits``,
    ``format``, ``image_base`` and ``recovery_family`` keep their stored value
    when the incoming one is NULL. ``content_sha256`` is only ever the digest a
    caller hands in (see the module docstring); this function derives none.
    A non-NULL incoming digest that differs from a stored non-NULL digest is a
    different image, hence a different build identity (D8): the call refuses
    with ``ValueError`` before writing anything to the row unless
    ``allow_reidentify=True`` (the store's own per-connect family backfill in
    ``ensure_binary_columns`` may already have run; it touches no identity column).
    A stored digest that is wrong for the raw image is repaired by the
    ``content_sha256`` backfill pass, not through here.

    New builds insert ``recovery_family`` NULL unless a catalog or operator
    value exists; ``store.backfill_recovery_family`` (every ``connect()``)
    derives the hash form once a digest is present.

    Also captures the analyzer identity: the version of the analyzer this
    process runs inside (or ``meta["analyzer_version"]``, or the configured
    install's version as a last resort), the processor-spec hash of the
    program's language, and the package ``basis_hash`` under that analyzer.
    When no analyzer version can be read the identity columns stay NULL and
    the basis refuses at export, naming the row. The stamp is written only
    after the upsert succeeded, so a refusal leaves the stamp untouched.
    """
    ensure_binary_columns(con)
    info = dict(meta or {})
    if program is not None:
        ld = program.getLanguage().getLanguageDescription()
        info.setdefault("language_id", str(ld.getLanguageID()))
        info.setdefault("arch", str(ld.getProcessor()))
        info.setdefault("bits", int(ld.getSize()))
        info.setdefault("format", str(program.getExecutableFormat()))
        info.setdefault("md5", str(program.getExecutableMD5()))
        info.setdefault("image_base", int(program.getImageBase().getOffset()))
        info.setdefault("analyzer_version", live_analyzer_version())
    analyzer_version = info.get("analyzer_version") or install_analyzer_version()
    digest = _digest_or_none(info.get("content_sha256"))
    md5 = _text_or_none(info.get("md5"))
    family = recovery_family(repo_path, slug, info)

    # Validate before any write of our own: a refusal must not leave a
    # half-updated or half-stamped row behind.
    stored = con.execute("SELECT content_sha256 FROM binary WHERE repo_path=?", (repo_path,)).fetchone()
    stored_digest = _digest_or_none(stored[0]) if stored is not None else None
    if digest and stored_digest and digest != stored_digest and not allow_reidentify:
        raise ValueError(
            f"binary {slug!r} already has content_sha256 {stored_digest[:12]}..., "
            f"incoming {digest[:12]}... is a different image and so a different build; "
            "register it separately or pass allow_reidentify=True to re-identify this row"
        )

    con.execute(
        """INSERT INTO binary(repo_path, slug, game, platform, variant, language_id,
                              arch, bits, format, md5, content_sha256, recovery_family, image_base, role)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(repo_path) DO UPDATE SET
             slug=excluded.slug, game=excluded.game, platform=excluded.platform,
             language_id=COALESCE(excluded.language_id, binary.language_id),
             arch=COALESCE(excluded.arch, binary.arch),
             bits=COALESCE(excluded.bits, binary.bits),
             format=COALESCE(excluded.format, binary.format),
             md5=COALESCE(excluded.md5, binary.md5),
             content_sha256=COALESCE(excluded.content_sha256, binary.content_sha256),
             recovery_family=COALESCE(excluded.recovery_family, binary.recovery_family),
             image_base=COALESCE(excluded.image_base, binary.image_base),
             role=excluded.role""",
        (
            repo_path,
            slug,
            info.get("game"),
            info.get("platform"),
            info.get("variant"),
            info.get("language_id"),
            info.get("arch"),
            info.get("bits"),
            info.get("format"),
            md5,
            digest,
            family,
            info.get("image_base"),
            info.get("role"),
        ),
    )
    row = con.execute("SELECT id FROM binary WHERE repo_path=?", (repo_path,)).fetchone()
    binary_id = int(row[0])
    # A re-ingest is a fresh capture: overwrite whatever an earlier ingest or
    # backfill recorded for this row.
    stamp_analyzer_identity(con, analyzer_version=analyzer_version, binary_ids=[binary_id], overwrite=True)
    con.commit()
    return binary_id


def persist_functions(con, binary_id: int, functions: list[dict[str, Any]]) -> int:
    ensure_func_columns(con)
    columns = {r[1] for r in con.execute("PRAGMA table_info(func)")}
    if not {"return_storage", "function_properties"} <= columns or not con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='func_param'"
    ).fetchone():
        raise ValueError("Function storage schema is unavailable; complete the owned store migration before extraction")
    payload = []
    edges = []
    parameters = []
    storage_rows = []
    for row in functions:
        addr = int(row.get("addr") or 0)
        row = attach_hashes(row)
        provenance = row.get("symbol_provenance") or row.get("name_origin")
        # Validate and serialize before replacing any persisted function rows.
        # None means uncollected; [] means observed empty storage (e.g. void).
        props = row.get("function_properties")
        return_storage = row.get("return_storage")
        if return_storage is not None and not isinstance(return_storage, list):
            raise ValueError("return_storage must be a list or null")
        if props is not None and not isinstance(props, dict):
            raise ValueError("function_properties must be an object or null")
        storage_rows.append((j(return_storage), j(props), binary_id, addr))
        seen_ordinals = set()
        for param in row.get("parameters") or []:
            ordinal = param.get("ordinal")
            if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0 or ordinal in seen_ordinals:
                raise ValueError(f"invalid or duplicate parameter ordinal at {addr}: {ordinal}")
            seen_ordinals.add(ordinal)
            pieces = param.get("storage")
            if pieces is not None and not isinstance(pieces, list):
                raise ValueError("parameter storage must be a list or null")
            parameters.append((binary_id, addr, ordinal, param.get("name"), param.get("dataType"), j(pieces)))
        payload.append(
            (
                binary_id,
                addr,
                row.get("name"),
                row.get("namespace"),
                row.get("source"),
                row.get("size"),
                row.get("ranges"),
                int(bool(row.get("is_thunk"))),
                row.get("thunked_to"),
                row.get("calling_convention"),
                row.get("return_type"),
                row.get("param_count"),
                j(row.get("param_types")),
                row.get("stack_frame_size"),
                row.get("stack_param_size"),
                row.get("stack_local_size"),
                row.get("plate"),
                row.get("signature"),
                row.get("n_instr"),
                row.get("n_blocks"),
                row.get("n_edges"),
                row.get("back_edges"),
                row.get("cyclomatic"),
                row.get("n_callees"),
                row.get("indirect_calls"),
                row.get("data_refs"),
                j(row.get("mnem") or row.get("mnemonic_counts")),
                j(row.get("strings")),
                j(row.get("consts")),
                j(row.get("ext_calls")),
                j(row.get("block_hashes")),
                j(row.get("cfg_nodes")),
                j(row.get("cfg_edges")),
                row.get("hash_reloc") or None,
                row.get("hash_instr") or None,
                row.get("hash_mnemonic") or None,
                row.get("hash_raw") or None,
                row.get("canon_class"),
                row.get("canon_method"),
                row.get("canon_key"),
                row.get("canon_arity"),
                row.get("name_origin"),
                provenance,
            )
        )
        for callee in row.get("callees") or row.get("callee_addrs") or []:
            edges.append((binary_id, addr, int(callee)))
    con.execute("DELETE FROM calledge WHERE binary_id=?", (binary_id,))
    con.execute("DELETE FROM func_param WHERE binary_id=?", (binary_id,))
    con.execute("DELETE FROM func WHERE binary_id=?", (binary_id,))
    con.executemany(
        """INSERT INTO func(
               binary_id, addr, name, namespace, source, size, ranges, is_thunk, thunked_to,
               calling_convention, return_type, param_count, param_types,
               stack_frame_size, stack_param_size, stack_local_size, plate, signature,
               n_instr, n_blocks, n_edges, back_edges, cyclomatic, n_callees,
               indirect_calls, data_refs, mnem, strings, consts, ext_calls, block_hashes,
               cfg_nodes, cfg_edges, hash_reloc, hash_instr, hash_mnemonic, hash_raw,
               canon_class, canon_method, canon_key, canon_arity, name_origin, symbol_provenance
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        payload,
    )
    con.executemany("UPDATE func SET return_storage=?, function_properties=? WHERE binary_id=? AND addr=?", storage_rows)
    con.executemany("INSERT INTO func_param(binary_id, addr, ordinal, name, type, pieces_json) VALUES (?,?,?,?,?,?)", parameters)
    if edges:
        con.executemany(
            "INSERT INTO calledge(binary_id, caller_addr, callee_addr) VALUES (?,?,?)",
            edges,
        )
    con.execute("UPDATE binary SET func_count=? WHERE id=?", (len(payload), binary_id))
    con.commit()
    return len(payload)


def write_extract_receipt(work_dir: Path, counts: dict[str, int]) -> Path:
    dest = Path(work_dir) / "extract.json"
    write_json(dest, {"functions": counts, "total": sum(counts.values())})
    return dest

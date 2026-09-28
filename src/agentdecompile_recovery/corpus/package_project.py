"""Copy a generated workspace into an operator-supplied output directory.

Also emits a byte-exact reconstructed tree (assembler TUs + headers) when
given an identity store and function-byte dumps.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path

from . import canon

TARGET_FLAGS = {
    ("x86", 32): "i386-linux-gnu",
    ("x86", 64): "x86_64-linux-gnu",
    ("ARM", 32): "arm-linux-gnueabi",
    ("AARCH64", 64): "aarch64-linux-gnu",
}
_SAFE = re.compile(r"[^A-Za-z0-9_./-]")


def safe_path(p: str) -> str:
    """Turn an original source path into a relative, filesystem-safe one."""
    p = p.replace("\\", "/").lstrip("/")
    for marker in ("depot/", "Dev/", "PC Source/", "Mac Source/"):
        i = p.find(marker)
        if i >= 0:
            p = p[i + len(marker):]
    return _SAFE.sub("_", p)


def load_bytes(funcbytes_path: Path) -> dict[int, bytes]:
    out: dict[int, bytes] = {}
    path = Path(funcbytes_path)
    if path.exists():
        for line in path.open():
            d = json.loads(line)
            out[d["a"]] = bytes.fromhex(d["b"])
    return out


def emit_tu(funcs: list[dict], title: str) -> str:
    lines = [
        f"/* {title}",
        " *",
        " * Byte-exact reconstruction: each function is its original machine code.",
        " */",
        "\t.section .text",
    ]
    for f in funcs:
        sym = f"F_{f['addr']:08x}"
        if f.get("canon_key"):
            lines.append(f"/* {f['canon_key']}"
                         + (f"  {f['signature']}" if f.get("signature") else "")
                         + " */")
        lines.append(f"\t.globl {sym}")
        lines.append(f"{sym}:")
        data = f["bytes"]
        for i in range(0, len(data), 16):
            lines.append("\t.byte " + ",".join(f"0x{b:02x}" for b in data[i:i + 16]))
        lines.append(f"\t.size {sym}, . - {sym}")
    return "\n".join(lines) + "\n"


def emit_header(slug: str, funcs: list[dict]) -> str:
    guard = "AD_" + _SAFE.sub("_", slug).upper() + "_H"
    lines = [
        f"/* {slug} — recovered symbol declarations. */",
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        "#ifdef __cplusplus",
        'extern "C" {',
        "#endif",
        "",
    ]
    for f in funcs:
        sym = f"F_{f['addr']:08x}"
        if f.get("canon_key"):
            lines.append(f"/* {f['canon_key']} */")
        lines.append(f"extern void {sym}(void);")
    lines += ["", "#ifdef __cplusplus", "}", "#endif", "", f"#endif /* {guard} */", ""]
    return "\n".join(lines)


def build_reconstructed(
    con,
    out_dir: Path,
    *,
    funcbytes_dir: Path,
    limit_per_tu: int = 300,
    images: dict[str, tuple[bytes, int]] | None = None,
) -> dict:
    """Emit assembler TUs for every non-excluded binary under *out_dir*.

    *images* is opt-in. It maps a slug to ``(image_bytes, size_of_image)``.
    When it is given, each summary entry gains ``recoveredProjectManifest``
    and a slug with an image gets ``manifests/<image sha256[:16]>.json``
    (``agentdecompile.recovered-project/v1``) plus its validation receipt.
    Manifest paths are relative to ``src/<slug>``, the entry's
    ``sourceRoot``, so the manifest itself names no slug or host path.
    Without *images* the output is unchanged.
    """
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    (out / "include" / "corpus").mkdir(parents=True, exist_ok=True)
    bins = [dict(r) for r in con.execute(
        "SELECT id, repo_path, slug, game, platform, arch, bits, format FROM binary "
        "ORDER BY repo_path")]
    summary = []
    targets = []
    emitted_manifests: set[str] = set()
    for b in bins:
        if b["repo_path"] in canon.DRM_EXCLUDED:
            continue
        triple = TARGET_FLAGS.get((b["arch"], b["bits"]))
        if triple is None:
            continue
        slug = b["slug"]
        akey = b["repo_path"].strip("/").replace("/", "__")
        raw_map = load_bytes(Path(funcbytes_dir) / f"{akey}.jsonl")
        if not raw_map:
            raw_map = load_bytes(Path(funcbytes_dir) / f"{slug}.jsonl")
        rows = con.execute(
            """SELECT f.addr, f.size, f.canon_key, f.signature, f.source_file,
                      i.logical_id
                 FROM func f
                 LEFT JOIN identity i ON i.binary_id=f.binary_id AND i.addr=f.addr
                WHERE f.binary_id=? AND f.n_instr>0 AND f.size>0
                ORDER BY f.addr""", (b["id"],)).fetchall()
        funcs = []
        seen: set[int] = set()
        for r in rows:
            data = raw_map.get(r["addr"])
            if data is None or r["addr"] in seen:
                continue
            seen.add(r["addr"])
            d = dict(r)
            d["bytes"] = data
            funcs.append(d)
        if not funcs:
            continue
        groups: dict[str, list[dict]] = defaultdict(list)
        for f in funcs:
            if f.get("source_file"):
                groups[safe_path(f["source_file"])].append(f)
            else:
                groups["_unattributed"].append(f)
        srcroot = out / "src" / slug
        sources = []
        tus: list[tuple[Path, list[dict]]] = []
        for gname, gfuncs in sorted(groups.items()):
            if gname == "_unattributed":
                for i in range(0, len(gfuncs), limit_per_tu):
                    chunk = gfuncs[i:i + limit_per_tu]
                    p = srcroot / "_unattributed" / f"part{i//limit_per_tu:04d}.S"
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(emit_tu(chunk, f"{slug} — unattributed functions"))
                    sources.append(p.relative_to(out).as_posix())
                    tus.append((p, chunk))
            else:
                p = srcroot / (gname + ".S")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(emit_tu(gfuncs, f"{slug} — original source: {gname}"))
                sources.append(p.relative_to(out).as_posix())
                tus.append((p, gfuncs))
        (out / "include" / "corpus" / f"{slug}.h").write_text(emit_header(slug, funcs))
        targets.append({"name": _SAFE.sub("_", slug), "triple": triple,
                        "sources": sources, "slug": slug})
        entry = {
            "binary": b["repo_path"], "target": _SAFE.sub("_", slug),
            "arch": b["arch"], "bits": b["bits"], "triple": triple,
            "functions": len(funcs), "translation_units": len(sources),
        }
        if images is not None:
            entry["recoveredProjectManifest"] = _write_project_manifest(
                con, out, b["id"], srcroot, tus, images.get(slug), emitted_manifests)
        summary.append(entry)
    (out / "build_manifest.json").write_text(json.dumps(summary, indent=1))
    return {"targets": len(targets), "functions": sum(s["functions"] for s in summary)}


def address_basis(funcs: list[dict], image_base: int, size_of_image: int) -> tuple[str | None, str | None]:
    """Decide whether every ``func.addr`` is a VA or an RVA for this image.

    Returns ``("va", None)`` or ``("rva", None)``, else ``(None, reason)``.
    The whole binary gets one basis. It is ambiguous when every function
    fits both ``[image_base, image_base + size_of_image)`` and
    ``[0, size_of_image)``, and unresolved when it fits neither as a whole.
    """
    def inside(low: int) -> bool:
        return all(low <= f["addr"] and f["addr"] + len(f["bytes"]) <= low + size_of_image for f in funcs)

    as_va, as_rva = inside(image_base), inside(0)
    if as_va and as_rva:
        return None, "address_basis_ambiguous"
    if as_va:
        return "va", None
    if as_rva:
        return "rva", None
    return None, "address_basis_unresolved"


def _write_project_manifest(con, out: Path, binary_id: int, srcroot: Path,
                            tus: list[tuple[Path, list[dict]]], image, emitted: set[str]) -> dict:
    """Per-image recovered-project manifest for the byte-exact floor tree.

    Every TU here is original machine code, so provenance is ``placeholder``,
    the toolchain is explicitly unpinned and the project is not claimed
    rebuildable. A refusal writes nothing and names its reason.
    """
    if image is None:
        return {"state": "not_emitted", "reason": "no_image_supplied"}
    from . import recovered_project_manifest as rpm

    def refused(reason: str) -> dict:
        return {"state": "refused", "reason": reason}

    try:
        row = con.execute("SELECT image_base, md5 FROM binary WHERE id=?", (binary_id,)).fetchone()
    except sqlite3.OperationalError:
        return refused("store_lacks_image_columns")
    image_base, md5 = row[0], row[1]
    image_bytes, size_of_image = image
    if image_base is None:
        return refused("image_base_unrecorded")
    if md5:
        if hashlib.md5(image_bytes).hexdigest() != str(md5).lower():
            return refused("stale_image_digest")
        digest_check = "md5_matched"
    else:
        digest_check = "md5_unrecorded"
    basis, why = address_basis([f for _, chunk in tus for f in chunk], image_base, size_of_image)
    if basis is None:
        return refused(why)

    image_id = rpm.image_identity(image_bytes, image_base=image_base, size_of_image=size_of_image)
    name = image_id["sha256"][:16]
    if name in emitted:
        return refused("manifest_name_collision")
    rebase = image_base if basis == "rva" else 0
    toolchain = rpm.unpinned_toolchain("byte-exact assembler floor; no per-build toolchain record (U54)")
    units = []
    for path, chunk in tus:
        rel = path.relative_to(srcroot).as_posix()
        units.append(rpm.unit(
            rel, source_path=rel, source_sha256=rpm.sha256_hex(path.read_bytes()),
            image_sha256=image_id["sha256"], provenance="placeholder", toolchain=toolchain,
            placements=[rpm.placement(f"F_{f['addr']:08x}", f["addr"] + rebase, len(f["bytes"]))
                        for f in chunk]))
    manifest = rpm.build_manifest(project="image-" + name, image=image_id, units=units,
                                  rebuildable=False, basis_hash=None)
    receipt = rpm.validate(manifest, srcroot, image_bytes)
    mdir = out / "manifests"
    mdir.mkdir(exist_ok=True)
    (mdir / f"{name}.json").write_bytes(rpm.dumps(manifest))
    (mdir / f"{name}.receipt.json").write_bytes(rpm.receipt_bytes(receipt))
    emitted.add(name)
    return {"state": "emitted", "path": f"manifests/{name}.json",
            "receipt": f"manifests/{name}.receipt.json",
            "sourceRoot": srcroot.relative_to(out).as_posix(),
            "addressBasis": basis, "imageDigestCheck": digest_check,
            "verdict": receipt["verdict"]}


def package_project(workspace: Path, out_dir: Path) -> dict:
    workspace = Path(workspace)
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    if workspace.is_dir():
        shutil.copytree(workspace, out_dir)
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "workspace": str(workspace),
        "files": sorted(str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file()),
        "claimBoundary": "A packaged tree is readable layout, not byte-accuracy.",
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest

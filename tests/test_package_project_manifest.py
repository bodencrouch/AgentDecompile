"""package_project.build_reconstructed emits a recovered-project manifest (P2-f).

Every store, function-byte dump and image is synthetic and built in-test
under pytest's tmp_path. No product binary, compiler, linker or server runs.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3

import pytest

from agentdecompile_recovery.corpus import package_project as pp
from agentdecompile_recovery.corpus import recovered_project_manifest as rpm

pytestmark = pytest.mark.unit

SLUG = "zz-synthslug-q7"
REPO_PATH = "synthrepo/zz-synthslug-q7/game.exe"
IMAGE_BASE = 0x00400000
SIZE_OF_IMAGE = 0x3000
IMAGE = bytes((i * 7 + 3) & 0xFF for i in range(SIZE_OF_IMAGE))

# Offsets inside the synthetic image, with a source file (None = unattributed).
FUNCS = (
    (0x1000, 0x10, "C:\\depot\\game\\a.cpp"),
    (0x1010, 0x08, None),
    (0x1020, 0x0C, "C:\\depot\\game\\b.cpp"),
)

# Tree digest of the synthetic build below as produced by package_project.py
# sha256 27b0c94bf60ebcfb151a7435601cbf0f544c60d8bfe17fadddc79488b31cdd71
# (before the manifest wiring). Without images= the output must not move.
GOLDEN_TREE_SHA256 = "b52a98540385d7e979323ff10509bbaaa141a270e64410047fed0e408fb5a6d5"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _func_bytes(addr: int, size: int) -> bytes:
    return bytes((addr + i) & 0xFF for i in range(size))


def make_store(binaries):
    """binaries: iterable of dicts with slug, repo_path, image_base, md5, funcs=[(addr,size,src)]."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE binary (id INTEGER PRIMARY KEY, repo_path TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL, game TEXT, platform TEXT, arch TEXT, bits INTEGER,
            format TEXT, md5 TEXT, image_base INTEGER);
        CREATE TABLE func (id INTEGER PRIMARY KEY, binary_id INTEGER NOT NULL, addr INTEGER NOT NULL,
            size INTEGER, canon_key TEXT, signature TEXT, source_file TEXT, n_instr INTEGER);
        CREATE TABLE identity (logical_id INTEGER, binary_id INTEGER NOT NULL, addr INTEGER NOT NULL,
            PRIMARY KEY (binary_id, addr));
    """)
    for bid, b in enumerate(binaries, start=1):
        con.execute("INSERT INTO binary VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (bid, b["repo_path"], b["slug"], "synth", "win", "x86", 32, "pe",
                     b.get("md5"), b.get("image_base")))
        for addr, size, src in b["funcs"]:
            con.execute("INSERT INTO func (binary_id, addr, size, canon_key, signature, source_file, n_instr)"
                        " VALUES (?,?,?,?,?,?,?)",
                        (bid, addr, size, f"Synth::f{addr:x}", None, src, 3))
    return con


def write_funcbytes(dirpath, binaries):
    dirpath.mkdir(parents=True, exist_ok=True)
    for b in binaries:
        lines = [json.dumps({"a": a, "b": _func_bytes(a, s).hex()}) for a, s, _ in b["funcs"]]
        (dirpath / f"{b['slug']}.jsonl").write_text("\n".join(lines) + "\n")


def binary(*, slug=SLUG, repo_path=REPO_PATH, basis="va", image_base=IMAGE_BASE, md5="match", funcs=FUNCS):
    shift = image_base if basis == "va" else 0
    return {"slug": slug, "repo_path": repo_path, "image_base": image_base,
            "md5": hashlib.md5(IMAGE).hexdigest() if md5 == "match" else md5,
            "funcs": [(off + shift, size, src) for off, size, src in funcs]}


def build(tmp_path, binaries, *, name="out", **kwargs):
    fb = tmp_path / "funcbytes"
    if not fb.exists():
        write_funcbytes(fb, binaries)
    out = tmp_path / name
    pp.build_reconstructed(make_store(binaries), out, funcbytes_dir=fb, limit_per_tu=2, **kwargs)
    return out


def tree(root) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def tree_sha(root) -> str:
    h = hashlib.sha256()
    for rel, data in tree(root).items():
        h.update(rel.encode() + b"\0" + _sha(data).encode() + b"\n")
    return h.hexdigest()


def entry(out, slug=SLUG) -> dict:
    return next(e for e in json.loads((out / "build_manifest.json").read_text()) if e["target"] == slug)


def manifest_name(image: bytes = IMAGE) -> str:
    return f"manifests/{_sha(image)[:16]}.json"


# ------------------------------------------------------------ unchanged path


def test_without_images_output_is_byte_identical_to_prechange(tmp_path):
    out = build(tmp_path, [binary()])
    assert not (out / "manifests").exists()
    assert "recoveredProjectManifest" not in entry(out)
    assert tree_sha(out) == GOLDEN_TREE_SHA256


def test_images_changes_only_manifests_and_summary(tmp_path):
    plain = build(tmp_path, [binary()], name="plain")
    wired = build(tmp_path, [binary()], name="wired", images={SLUG: (IMAGE, SIZE_OF_IMAGE)})
    a, b = tree(plain), tree(wired)
    extra = sorted(set(b) - set(a))
    assert extra == [manifest_name(), manifest_name().replace(".json", ".receipt.json")]
    assert {k for k in a if a[k] != b[k]} == {"build_manifest.json"}
    plain_entry, wired_entry = entry(plain), entry(wired)
    wired_entry.pop("recoveredProjectManifest")
    assert wired_entry == plain_entry


# ------------------------------------------------------------ emission


def test_manifest_is_emitted_and_validates(tmp_path):
    out = build(tmp_path, [binary()], images={SLUG: (IMAGE, SIZE_OF_IMAGE)})
    state = entry(out)["recoveredProjectManifest"]
    assert state["state"] == "emitted"
    assert state["verdict"] == "accepted"
    assert state["addressBasis"] == "va"
    assert state["imageDigestCheck"] == "md5_matched"
    assert state["path"] == manifest_name()
    assert state["sourceRoot"] == f"src/{SLUG}"
    manifest = json.loads((out / state["path"]).read_bytes())
    assert manifest["schema"] == rpm.SCHEMA
    assert manifest["claims"] == {"rebuildable": False}
    assert {u["provenance"] for u in manifest["units"]} == {"placeholder"}
    assert {u["toolchain"]["state"] for u in manifest["units"]} == {"unpinned"}
    placements = sorted((p["symbol"], p["va"], p["size"]) for u in manifest["units"] for p in u["placements"])
    assert placements == [(f"F_{IMAGE_BASE + o:08x}", IMAGE_BASE + o, s) for o, s, _ in FUNCS]
    receipt = rpm.validate(manifest, out / state["sourceRoot"], IMAGE)
    assert receipt["verdict"] == "accepted", receipt["refusals"]
    stored = json.loads((out / state["receipt"]).read_bytes())
    assert stored == receipt


def test_rva_addresses_are_rebased_and_symbols_match_the_tu(tmp_path):
    out = build(tmp_path, [binary(basis="rva")], images={SLUG: (IMAGE, SIZE_OF_IMAGE)})
    state = entry(out)["recoveredProjectManifest"]
    assert (state["state"], state["verdict"], state["addressBasis"]) == ("emitted", "accepted", "rva")
    manifest = json.loads((out / state["path"]).read_bytes())
    tus = "".join((out / state["sourceRoot"] / u["source"]["path"]).read_text() for u in manifest["units"])
    for u in manifest["units"]:
        for p in u["placements"]:
            rva = p["va"] - IMAGE_BASE
            assert p["symbol"] == f"F_{rva:08x}"
            assert f"{p['symbol']}:" in tus


def test_emitted_tree_is_relocatable(tmp_path):
    out = build(tmp_path, [binary()], images={SLUG: (IMAGE, SIZE_OF_IMAGE)})
    state = entry(out)["recoveredProjectManifest"]
    moved = tmp_path / "elsewhere" / "deeper"
    shutil.copytree(out / state["sourceRoot"], moved)
    manifest = json.loads((out / state["path"]).read_bytes())
    receipt = rpm.validate(manifest, moved, IMAGE)
    assert receipt["verdict"] == "accepted", receipt["refusals"]
    assert rpm.receipt_bytes(receipt) == (out / state["receipt"]).read_bytes()


# ------------------------------------------------------------ refusals


def assert_refused(out, reason):
    state = entry(out)["recoveredProjectManifest"]
    assert state["state"] == "refused"
    assert state["reason"] == reason
    assert "path" not in state
    assert not (out / "manifests").exists() or not any((out / "manifests").iterdir())


def test_stale_image_digest_is_refused_at_build(tmp_path):
    stale = hashlib.md5(IMAGE + b"stale").hexdigest()
    out = build(tmp_path, [binary(md5=stale)], images={SLUG: (IMAGE, SIZE_OF_IMAGE)})
    assert_refused(out, "stale_image_digest")


def test_stale_image_digest_is_refused_by_the_validator(tmp_path):
    out = build(tmp_path, [binary()], images={SLUG: (IMAGE, SIZE_OF_IMAGE)})
    state = entry(out)["recoveredProjectManifest"]
    manifest = json.loads((out / state["path"]).read_bytes())
    changed = bytearray(IMAGE)
    changed[0x1004] ^= 0xFF
    receipt = rpm.validate(manifest, out / state["sourceRoot"], bytes(changed))
    assert receipt["verdict"] == "refused"
    assert [r["reason"] for r in receipt["refusals"]] == ["stale_image_digest"]


def test_unrecorded_md5_is_reported_not_invented(tmp_path):
    out = build(tmp_path, [binary(md5=None)], images={SLUG: (IMAGE, SIZE_OF_IMAGE)})
    state = entry(out)["recoveredProjectManifest"]
    assert (state["state"], state["imageDigestCheck"]) == ("emitted", "md5_unrecorded")


def test_ambiguous_address_basis_is_refused(tmp_path):
    # Base 0x1000 and SizeOfImage 0x3000: every address fits both as VA and as RVA.
    out = build(tmp_path, [binary(basis="rva", image_base=0x1000)], images={SLUG: (IMAGE, SIZE_OF_IMAGE)})
    assert_refused(out, "address_basis_ambiguous")


def test_mixed_address_basis_is_refused(tmp_path):
    mixed = binary(basis="rva", funcs=((0x1000, 0x10, None),))
    mixed["funcs"].append((IMAGE_BASE + 0x1020, 0x0C, None))
    out = build(tmp_path, [mixed], images={SLUG: (IMAGE, SIZE_OF_IMAGE)})
    assert_refused(out, "address_basis_unresolved")


def test_missing_image_base_is_refused(tmp_path):
    out = build(tmp_path, [binary(basis="rva", image_base=None)], images={SLUG: (IMAGE, SIZE_OF_IMAGE)})
    assert_refused(out, "image_base_unrecorded")


def test_slug_without_image_is_not_emitted(tmp_path):
    out = build(tmp_path, [binary()], images={})
    state = entry(out)["recoveredProjectManifest"]
    assert state == {"state": "not_emitted", "reason": "no_image_supplied"}
    assert not (out / "manifests").exists()


def test_identical_images_do_not_overwrite_each_other(tmp_path):
    first = binary()
    second = binary(slug="zz-second-q7", repo_path="synthrepo/zz-second-q7/game.exe")
    images = {first["slug"]: (IMAGE, SIZE_OF_IMAGE), second["slug"]: (IMAGE, SIZE_OF_IMAGE)}
    out = build(tmp_path, [first, second], images=images)
    states = [entry(out, s)["recoveredProjectManifest"] for s in (SLUG, "zz-second-q7")]
    assert sorted(s["state"] for s in states) == ["emitted", "refused"]
    assert [s["reason"] for s in states if s["state"] == "refused"] == ["manifest_name_collision"]
    assert sorted(p.name for p in (out / "manifests").iterdir()) == sorted(
        [manifest_name().split("/")[1], manifest_name().split("/")[1].replace(".json", ".receipt.json")])


# ------------------------------------------------------------ leaks and helper


def test_no_slug_or_absolute_path_leaks(tmp_path):
    out = build(tmp_path, [binary()], images={SLUG: (IMAGE, SIZE_OF_IMAGE)})
    state = entry(out)["recoveredProjectManifest"]
    for rel in (state["path"], state["receipt"]):
        assert SLUG not in rel
        data = (out / rel).read_bytes()
        for needle in (SLUG, "synthslug", REPO_PATH, str(tmp_path), str(out), "depot", "C:"):
            assert needle.encode() not in data, (rel, needle)
    manifest = json.loads((out / state["path"]).read_bytes())
    assert manifest["project"] == "image-" + _sha(IMAGE)[:16]
    receipt = rpm.validate(manifest, out / state["sourceRoot"], IMAGE)
    assert not [r for r in receipt["refusals"] if r["reason"] in ("absolute_path_leak", "non_relocatable_path")]


def test_public_sha_helper_replaces_private_use():
    assert rpm.sha256_hex(b"abc") == _sha(b"abc")
    assert "rpm._sha256" not in pp.__loader__.get_source(pp.__name__)
    assert "address_basis" in dir(pp)

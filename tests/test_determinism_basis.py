"""The determinism basis: store-derived, pinned, refused when incomplete.

Fixture rows carry the analyzer identity ``extract.stamp_analyzer_identity``
writes at ingest; tests that need a refusal remove one column value.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agentdecompile_recovery.corpus import determinism_basis as db_mod
from agentdecompile_recovery.corpus import policy_tables
from agentdecompile_recovery.corpus.cli import build_parser, main as corpus_main
from agentdecompile_recovery.corpus.export_hookpack import export_hookpack
from agentdecompile_recovery.corpus.extract import stamp_analyzer_identity, upsert_binary
from agentdecompile_recovery.corpus.store import connect

pytestmark = pytest.mark.unit

ANALYZER = "11.4.1"

ROWS = [
    (1, "/a", "alpha", "ff" * 32, "aa" * 16, "x86:LE:32:default"),
    (2, "/b", "beta", None, "bb" * 16, "x86:LE:32:default"),
    (3, "/c", "gamma", "", "", "ppc:BE:32:default"),
]

TOP_KEYS = {
    "algorithm_version",
    "analyzer",
    "basis_version",
    "corpus_manifest_hash",
    "masking_rule_version",
    "pending",
    "seeds",
    "threshold_params",
    "toolchain_identity_hash",
}
ANALYZER_KEYS = {"loader_revision", "options_hash", "processor_spec_hash", "timeout_policy", "version"}
THRESHOLD_KEYS = {
    "bsim",
    "cfg_slack",
    "channel_confidence",
    "content_floors",
    "df_caps",
    "pair_policy",
    "weights",
    "window",
}
PENDING = [
    "analyzer.compiler_spec_ids",
    "data_packs",
    "decoder",
    "external_channels.bsim_generator_revision",
    "filler_set",
    "threshold_params.divergence",
]


def _store(path: Path, rows, *, stamp: bool = True):
    con = connect(path)
    con.executemany(
        "INSERT INTO binary(id, repo_path, slug, content_sha256, md5, language_id) VALUES (?,?,?,?,?,?)", rows
    )
    if stamp:
        stamp_analyzer_identity(con, analyzer_version=ANALYZER)
    con.commit()
    return con


def _with_site(db: Path):
    con = _store(db, ROWS)
    con.execute("INSERT INTO logical_function(id, best_name, best_signature, n_members) VALUES (1, 'Run', 'void Run()', 1)")
    con.execute("INSERT INTO identity(logical_id, binary_id, addr, confidence, method) VALUES (1, 1, 16, 1.0, 'a')")
    con.commit()
    return con


# --- shape -----------------------------------------------------------------


def test_full_key_set_is_pinned(tmp_path: Path) -> None:
    b = db_mod.basis(_store(tmp_path / "c.sqlite", ROWS))
    assert set(b) == TOP_KEYS
    assert set(b["analyzer"]) == ANALYZER_KEYS
    assert set(b["threshold_params"]) == THRESHOLD_KEYS
    assert b["pending"] == PENDING
    assert b["basis_version"] == 2
    assert b["algorithm_version"] == "phase0.2+key:content_sha256"
    assert b["masking_rule_version"] == "none"
    assert b["analyzer"]["version"] == ANALYZER
    assert b["threshold_params"] == policy_tables.threshold_params()
    assert list(b) == sorted(b)


def test_pending_fields_are_sorted_and_absent_from_the_object(tmp_path: Path) -> None:
    assert list(db_mod.PENDING_FIELDS) == sorted(db_mod.PENDING_FIELDS)
    b = db_mod.basis(_store(tmp_path / "c.sqlite", ROWS))
    for name in db_mod.PENDING_FIELDS:
        node = b
        for part in name.split("."):
            if not isinstance(node, dict) or part not in node:
                break
            node = node[part]
        else:
            pytest.fail(f"pending field {name} is present in the object")


def test_manifest_hash_sorted_with_fallbacks(tmp_path: Path) -> None:
    con = _store(tmp_path / "c.sqlite", ROWS)
    expected = hashlib.sha256("\n".join(sorted(["ff" * 32, "bb" * 16, "gamma"])).encode()).hexdigest()
    assert db_mod.corpus_manifest_hash(con) == expected
    reverse = _store(tmp_path / "r.sqlite", list(reversed(ROWS)))
    assert db_mod.basis(con) == db_mod.basis(reverse)


def test_processor_spec_hash_is_the_set_of_per_row_hashes(tmp_path: Path) -> None:
    con = _store(tmp_path / "c.sqlite", ROWS)
    per_row = sorted(
        {db_mod.processor_spec_hash_for(lang) for lang in ("x86:LE:32:default", "ppc:BE:32:default")}
    )
    stored = sorted({r[0] for r in con.execute("SELECT processor_spec_hash FROM binary")})
    assert stored == per_row
    expected = hashlib.sha256("\n".join(per_row).encode()).hexdigest()[:16]
    assert db_mod.basis(con)["analyzer"]["processor_spec_hash"] == expected
    assert db_mod.processor_spec_hash_for(None) is None
    assert db_mod.processor_spec_hash_for("  ") is None


# --- hash ------------------------------------------------------------------


def test_basis_hash_excludes_membership_and_matches_the_rows(tmp_path: Path) -> None:
    con = _store(tmp_path / "c.sqlite", ROWS)
    stored = {r[0] for r in con.execute("SELECT basis_hash FROM binary")}
    assert stored == {db_mod.basis_hash(con)} == {db_mod.basis_hash_for(ANALYZER)}
    # A different membership under the same install: same hash.
    other = _store(tmp_path / "o.sqlite", ROWS[:1])
    assert db_mod.basis_hash(other) == db_mod.basis_hash(con)
    assert db_mod.basis(other)["corpus_manifest_hash"] != db_mod.basis(con)["corpus_manifest_hash"]
    assert db_mod.basis(other)["analyzer"]["processor_spec_hash"] != db_mod.basis(con)["analyzer"]["processor_spec_hash"]
    # The hash covers exactly the object minus the excluded names.
    hashable = db_mod._without(db_mod.basis(con), db_mod.BASIS_HASH_EXCLUDED)
    assert "corpus_manifest_hash" not in hashable
    assert "processor_spec_hash" not in hashable["analyzer"]
    assert "pending" in hashable
    payload = json.dumps(hashable, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(payload).hexdigest() == db_mod.basis_hash(con)
    # A different analyzer version: a different hash.
    assert db_mod.basis_hash_for("11.4.2") != db_mod.basis_hash_for(ANALYZER)


def test_basis_hash_tracks_the_package_constants(monkeypatch) -> None:
    before = db_mod.basis_hash_for(ANALYZER)
    monkeypatch.setattr(db_mod, "ALGORITHM_VERSION", "phase0.3+key:content_sha256")
    assert db_mod.basis_hash_for(ANALYZER) != before


# --- no environment reads --------------------------------------------------


def test_basis_ignores_the_install_environment(tmp_path: Path, monkeypatch) -> None:
    con = _store(tmp_path / "c.sqlite", ROWS)
    monkeypatch.setenv("GHIDRA_INSTALL_DIR", str(tmp_path / "nowhere"))
    with_env = db_mod.basis(con)
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    without_env = db_mod.basis(con)
    assert with_env == without_env
    assert with_env["analyzer"]["version"] == ANALYZER


def test_export_bytes_are_identical_across_install_environments(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "c.sqlite"
    _with_site(db).close()
    outs = []
    for env in (os.environ.get("GHIDRA_INSTALL_DIR") or str(tmp_path / "install"), None):
        if env is None:
            monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
        else:
            monkeypatch.setenv("GHIDRA_INSTALL_DIR", env)
        out = tmp_path / f"pack-{len(outs)}.json"
        export_hookpack(connect(db), out)
        outs.append(out.read_bytes())
    assert outs[0] == outs[1]
    assert json.loads(outs[0])["basis"]["analyzer"]["version"] == ANALYZER


def test_install_helper_reads_application_properties(tmp_path: Path, monkeypatch) -> None:
    install = tmp_path / "install"
    (install / "Ghidra").mkdir(parents=True)
    (install / "Ghidra" / "application.properties").write_text(
        "application.name=Analyzer\napplication.version=99.1\n", encoding="utf-8"
    )
    assert db_mod.install_analyzer_version(install) == "99.1"
    monkeypatch.setenv("GHIDRA_INSTALL_DIR", str(install))
    assert db_mod.install_analyzer_version() == "99.1"
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    assert db_mod.install_analyzer_version() is None
    assert db_mod.install_analyzer_version(tmp_path / "missing") is None


# --- ingest ----------------------------------------------------------------


def _identity_row(con, slug: str) -> tuple:
    return tuple(
        con.execute(
            "SELECT analyzer_version, processor_spec_hash, basis_hash, basis_source FROM binary WHERE slug=?", (slug,)
        ).fetchone()
    )


def test_upsert_binary_stamps_the_analyzer_identity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    con = connect(tmp_path / "c.sqlite")
    meta = {"content_sha256": "aa" * 32, "language_id": "x86:LE:32:default", "analyzer_version": ANALYZER}
    bid = upsert_binary(con, repo_path="/x", slug="x", meta=meta)
    assert _identity_row(con, "x") == (
        ANALYZER,
        db_mod.processor_spec_hash_for("x86:LE:32:default"),
        db_mod.basis_hash_for(ANALYZER),
        "ingest",
    )
    assert db_mod.basis(con)["analyzer"]["version"] == ANALYZER
    # The same row is stamped again on a second ingest, not duplicated.
    assert upsert_binary(con, repo_path="/x", slug="x", meta=meta) == bid
    assert con.execute("SELECT count(*) FROM binary").fetchone()[0] == 1


def test_upsert_binary_falls_back_to_the_configured_install(tmp_path: Path, monkeypatch) -> None:
    install = tmp_path / "install"
    (install / "Ghidra").mkdir(parents=True)
    (install / "Ghidra" / "application.properties").write_text("application.version=88.2\n", encoding="utf-8")
    monkeypatch.setenv("GHIDRA_INSTALL_DIR", str(install))
    con = connect(tmp_path / "c.sqlite")
    upsert_binary(con, repo_path="/x", slug="x", meta={"content_sha256": "aa" * 32, "language_id": "x86:LE:32:default"})
    assert _identity_row(con, "x") == (
        "88.2",
        db_mod.processor_spec_hash_for("x86:LE:32:default"),
        db_mod.basis_hash_for("88.2"),
        "ingest",
    )


def test_upsert_binary_without_an_analyzer_version_leaves_the_row_unstamped(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    con = connect(tmp_path / "c.sqlite")
    upsert_binary(con, repo_path="/x", slug="x", meta={"content_sha256": "aa" * 32, "language_id": "x86:LE:32:default"})
    assert _identity_row(con, "x") == (None, None, None, None)
    with pytest.raises(db_mod.BasisError, match=r"analyzer\.version is absent for \[x\]"):
        db_mod.basis(con)


def test_reingest_under_a_new_analyzer_overwrites_and_refuses_as_mixed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    con = connect(tmp_path / "c.sqlite")
    for slug in ("x", "y"):
        upsert_binary(
            con,
            repo_path=f"/{slug}",
            slug=slug,
            meta={"content_sha256": slug[0].encode().hex() * 32, "language_id": "x86:LE:32:default", "analyzer_version": ANALYZER},
        )
    upsert_binary(
        con,
        repo_path="/y",
        slug="y",
        meta={"content_sha256": "79" * 32, "language_id": "x86:LE:32:default", "analyzer_version": "11.4.2"},
    )
    assert _identity_row(con, "y")[0] == "11.4.2"
    assert _identity_row(con, "x")[0] == ANALYZER
    with pytest.raises(db_mod.BasisError, match="mixed analyzer.version across binary rows"):
        db_mod.basis(con)


def test_reingest_with_no_readable_version_keeps_the_earlier_stamp(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    con = connect(tmp_path / "c.sqlite")
    meta = {"content_sha256": "aa" * 32, "language_id": "x86:LE:32:default", "analyzer_version": ANALYZER}
    upsert_binary(con, repo_path="/x", slug="x", meta=meta)
    before = _identity_row(con, "x")
    # A re-ingest that cannot say which analyzer ran keeps what ingest recorded
    # rather than blanking it: overwrite needs a value to overwrite with.
    upsert_binary(con, repo_path="/x", slug="x", meta={"content_sha256": "aa" * 32, "language_id": "x86:LE:32:default"})
    assert _identity_row(con, "x") == before
    assert db_mod.basis(con)["analyzer"]["version"] == ANALYZER


# --- refusal ---------------------------------------------------------------


def test_refuses_an_empty_store(tmp_path: Path) -> None:
    with pytest.raises(db_mod.BasisError, match="analyzer.version has no producer row"):
        db_mod.basis(connect(tmp_path / "e.sqlite"))
    assert issubclass(db_mod.BasisError, ValueError)


def test_refuses_unstamped_rows(tmp_path: Path) -> None:
    con = _store(tmp_path / "c.sqlite", ROWS, stamp=False)
    with pytest.raises(db_mod.BasisError, match=r"analyzer\.version is absent for \[alpha, beta, gamma\]"):
        db_mod.basis(con)


@pytest.mark.parametrize(
    ("column", "value", "field"),
    [
        ("analyzer_version", None, "analyzer.version"),
        ("analyzer_version", "unknown", "analyzer.version"),
        ("analyzer_version", "", "analyzer.version"),
        ("processor_spec_hash", None, "analyzer.processor_spec_hash"),
        ("basis_hash", None, "binary.basis_hash"),
    ],
)
def test_refuses_one_absent_column_value(tmp_path: Path, column, value, field) -> None:
    con = _store(tmp_path / "c.sqlite", ROWS)
    con.execute(f"UPDATE binary SET {column}=? WHERE slug='beta'", (value,))
    with pytest.raises(db_mod.BasisError) as info:
        db_mod.basis(con)
    assert str(info.value) == f"basis: {field} is absent for [beta]"


def test_refuses_mixed_basis_hash_naming_both_bases(tmp_path: Path) -> None:
    con = _store(tmp_path / "c.sqlite", ROWS)
    other = db_mod.basis_hash_for("11.4.2")
    con.execute("UPDATE binary SET basis_hash=? WHERE slug IN ('alpha', 'gamma')", (other,))
    current = db_mod.basis_hash_for(ANALYZER)
    groups = sorted([(other, "[alpha, gamma]"), (current, "[beta]")])
    expected = "basis: mixed basis_hash across binary rows: " + "; ".join(f"{h} {s}" for h, s in groups)
    with pytest.raises(db_mod.BasisError) as info:
        db_mod.basis(con)
    assert str(info.value) == expected


def test_refuses_mixed_analyzer_version(tmp_path: Path) -> None:
    con = _store(tmp_path / "c.sqlite", ROWS)
    con.execute("UPDATE binary SET analyzer_version='11.4.2' WHERE slug='gamma'")
    with pytest.raises(db_mod.BasisError, match=r"mixed analyzer\.version across binary rows: 11\.4\.1 \[alpha, beta\]; 11\.4\.2 \[gamma\]"):
        db_mod.basis(con)


def test_refuses_basis_hash_drift_after_a_package_change(tmp_path: Path, monkeypatch) -> None:
    con = _store(tmp_path / "c.sqlite", ROWS)
    monkeypatch.setattr(db_mod, "MASKING_RULE_VERSION", "u4.1")
    with pytest.raises(db_mod.BasisError, match="basis_hash drift for \\[alpha, beta, gamma\\].*re-baseline"):
        db_mod.basis(con)


def test_refuses_empty_threshold_table(tmp_path: Path, monkeypatch) -> None:
    con = _store(tmp_path / "c.sqlite", ROWS)
    monkeypatch.setattr(policy_tables, "threshold_params", lambda: {})
    with pytest.raises(db_mod.BasisError, match=r"\$\.threshold_params is empty"):
        db_mod.basis(con)
    monkeypatch.setattr(policy_tables, "threshold_params", lambda: {"pair_policy": {}, "x": 1})
    with pytest.raises(db_mod.BasisError, match=r"\$\.threshold_params\.pair_policy is empty"):
        db_mod.basis(con)


def test_refuses_an_unknown_pinned_constant(monkeypatch) -> None:
    monkeypatch.setattr(db_mod, "TOOLCHAIN_IDENTITY_HASH", "unknown")
    with pytest.raises(db_mod.BasisError, match=r"\$\.toolchain_identity_hash is absent"):
        db_mod.package_basis(ANALYZER)
    monkeypatch.setattr(db_mod, "TOOLCHAIN_IDENTITY_HASH", "")
    with pytest.raises(db_mod.BasisError, match=r"\$\.toolchain_identity_hash is absent"):
        db_mod.package_basis(ANALYZER)


# --- verification ----------------------------------------------------------


def test_first_diff_path() -> None:
    assert db_mod.first_diff_path({"a": 1}, {"a": 1}) == ""
    assert db_mod.first_diff_path({"a": {"b": [1, 2]}}, {"a": {"b": [1, 3]}}) == "$.a.b[1]"
    assert db_mod.first_diff_path({"a": 1}, {"a": 1, "z": 2}) == "$.z"


def test_verify_determinism_verb(tmp_path: Path, capsys) -> None:
    subs = build_parser()._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
    assert "verify-determinism" in subs
    db = tmp_path / "c.sqlite"
    _with_site(db).close()  # the verb runs in a fresh process with nothing else attached
    assert corpus_main(["verify-determinism", "--db", str(db)]) == 0
    assert '"identical": true' in capsys.readouterr().out

    calls = []

    def flaky(con, out):
        calls.append(out)
        export_hookpack(con, out)
        if len(calls) == 2:
            text = out.read_text(encoding="utf-8").replace('"logical_id": 1', '"logical_id": 2')
            out.write_text(text, encoding="utf-8")

    result = db_mod.verify_export(db, flaky)
    assert result == {"identical": False, "diff": "$.sites.Run.logical_id"}


def test_cli_verbs_exit_2_with_the_refusal_message(tmp_path: Path, capsys) -> None:
    db = tmp_path / "c.sqlite"
    con = _with_site(db)
    con.execute("UPDATE binary SET analyzer_version=NULL WHERE slug='alpha'")
    con.commit()
    con.close()
    out = tmp_path / "pack.json"
    assert corpus_main(["export-hookpack", "--db", str(db), "--out", str(out)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "error: basis: analyzer.version is absent for [alpha]"
    assert not out.exists()
    assert corpus_main(["verify-determinism", "--db", str(db)]) == 2
    assert capsys.readouterr().err.strip() == "error: basis: analyzer.version is absent for [alpha]"


@pytest.mark.parametrize("hashseed", ["0", "1"])
def test_export_bytes_do_not_depend_on_pythonhashseed(tmp_path: Path, hashseed: str) -> None:
    db = tmp_path / "c.sqlite"
    _with_site(db).close()
    out = tmp_path / f"pack-{hashseed}.json"
    env = dict(os.environ, PYTHONHASHSEED=hashseed)
    env["PYTHONPATH"] = os.pathsep.join(p for p in [str(Path(__file__).resolve().parents[1] / "src"), env.get("PYTHONPATH", "")] if p)
    code = (
        "import sys; from pathlib import Path\n"
        "from agentdecompile_recovery.corpus.store import connect\n"
        "from agentdecompile_recovery.corpus.export_hookpack import export_hookpack\n"
        "export_hookpack(connect(sys.argv[1]), Path(sys.argv[2]))\n"
    )
    subprocess.run([sys.executable, "-c", code, str(db), str(out)], check=True, env=env)
    reference = tmp_path / "reference.json"
    export_hookpack(connect(db), reference)
    assert out.read_bytes() == reference.read_bytes()

"""Run: PYTHONPATH=src python3 tests/test_matching_preset_metadata.py."""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agentdecompile_recovery.corpus.dashboard.binary_coverage import _matching_presets, annotate_binary_coverage


def test_matching_preset_metadata():
    matching_preloaded = "agentdecompile_recovery.corpus.dashboard.actions.matching" in sys.modules
    digest, revision = "a" * 64, "b" * 64
    with TemporaryDirectory() as directory:
        base = Path(directory)
        root = base / "presets"
        project = base / "project"
        root.mkdir()
        project.mkdir()
        (project / "target.o").write_bytes(b"target bytes are not read by discovery")
        (project / "context.h").write_text("private context")
        with (project / "oversized.h").open("wb") as stream:
            stream.truncate(2 * 1024 * 1024 + 1)
        (base / "outside.o").write_bytes(b"outside")
        (project / "escape.o").symlink_to(base / "outside.o")
        (project / "inside.o").symlink_to(project / "target.o")
        payload = {"id": "gcc", "label": "GNU C", "platform": "linux-x86",
                   "artifactHash": " " + digest.upper() + " ", "projectRoot": str(project),
                   "compilerScript": "DO NOT EXECUTE", "contextPath": "../project/context.h",
                   "targets": {"candidate_fn": {"path": "inside.o", "sha256": " " + revision.upper() + " ", "symbol": "_candidate_fn"}}}
        path = root / "gcc.json"
        path.write_text(json.dumps(payload))
        (root / "broken.json").write_text("{")
        (root / "array.json").write_text("[]")
        (root / "invalid id.json").write_text(json.dumps({**payload, "id": "invalid id"}))
        (root / "mismatch.json").write_text(json.dumps(payload))
        (root / "wrong-hash.json").write_text(json.dumps({**payload, "id": "wrong-hash", "artifactHash": "c" * 64}))
        (base / "outside.json").write_text(json.dumps({**payload, "id": "escape"}))
        (root / "escape.json").symlink_to(base / "outside.json")
        (root / "alias.json").symlink_to(path)
        (root / "loop.json").symlink_to(root / "loop.json")
        expected = [{"id": "gcc", "label": "GNU C", "platform": "linux-x86",
                     "targets": [{"function": "candidate_fn", "symbol": "_candidate_fn", "targetRevision": revision}]}]
        with patch.dict(os.environ, {"AGENT_DECOMPILE_MATCHING_PRESET_ROOT": str(root)}):
            # Reading only preset JSON is permitted; target/context contents stay private.
            read_text = Path.read_text
            def only_presets(path, *args, **kwargs):
                assert path.suffix == ".json" and path.is_relative_to(root)
                return read_text(path, *args, **kwargs)
            with patch.object(Path, "read_bytes", side_effect=AssertionError("No target/context reads")), patch.object(Path, "read_text", only_presets):
                assert _matching_presets(digest) == expected
                row = {"kind": "record", "format": "pe", "sha256": digest}
                annotate_binary_coverage([row], {})
                assert row["coverage"]["matchingPreset"] == {"status": "available", "ids": ["gcc"], "presets": expected}
                assert row["coverage"]["proof"]["phase"] == "comparison-pending"
            for change in ({"compilerScript": " "}, {"projectRoot": str(base / "absent")},
                           {"timeoutSeconds": "bad"}, {"contextPath": str(base / "outside.o")},
                           {"contextPath": str(project / "escape.o")}, {"contextPath": str(project / "oversized.h")}, {"targets": []},
                           {"targets": {"../bad": payload["targets"]["candidate_fn"]}},
                           {"targets": {"candidate_fn": None}}):
                path.write_text(json.dumps({**payload, **change}))
                assert _matching_presets(digest) == [], change
            for change in ({"path": "../outside.o"}, {"path": "escape.o"}, {"path": "missing.o"},
                           {"path": str(base / "outside.o")}, {"sha256": "bad"}, {"symbol": " "}):
                target = {**payload["targets"]["candidate_fn"], **change}
                path.write_text(json.dumps({**payload, "targets": {"candidate_fn": target}}))
                assert _matching_presets(digest) == [], change
            # Absolute paths beneath the declared project root are legal, but never public.
            target = {"path": str(project / "target.o"), "sha256": revision}
            clean = {**payload, "label": str(project), "platform": "private\\path", "targets": {"candidate_fn": target, "bad": {"sha256": "bad"}}}
            clean.pop("id")
            path.write_text(json.dumps(clean))
            metadata = _matching_presets(digest)
            assert metadata == [{"id": "gcc", "label": "gcc", "platform": "unknown", "targets": [{"function": "candidate_fn", "symbol": "candidate_fn", "targetRevision": revision}]}]
            text = json.dumps(metadata)
            assert all(secret not in text for secret in (str(base), "compilerScript", "projectRoot", "contextPath", "target.o", "private context", "DO NOT EXECUTE"))
            assert _matching_presets("not-sha256") == []
        (base / "root-link").symlink_to(root, target_is_directory=True)
        with patch.dict(os.environ, {"AGENT_DECOMPILE_MATCHING_PRESET_ROOT": str(base / "root-link")}):
            assert _matching_presets(digest) == metadata
        for configured in ("", str(base / "missing"), str(path)):
            with patch.dict(os.environ, {"AGENT_DECOMPILE_MATCHING_PRESET_ROOT": configured}):
                assert _matching_presets(digest) == []
        # Reading public metadata must not pull in the matching executor. Other
        # test modules may already have imported it, so only a fresh import fails.
        assert matching_preloaded or "agentdecompile_recovery.corpus.dashboard.actions.matching" not in sys.modules


if __name__ == "__main__":
    test_matching_preset_metadata()
    print("Matching preset public metadata: PASS")

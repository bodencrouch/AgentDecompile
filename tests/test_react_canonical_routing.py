"""Run directly: PYTHONPATH=src .venv/bin/python tests/test_react_canonical_routing.py."""
from html import unescape
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdecompile_recovery.corpus.dashboard import react_api
from agentdecompile_recovery.corpus.dashboard.router import SECURITY_HEADERS
from agentdecompile_recovery.unified_pages import mount_unified_pages


def test_canonical_react_delivery():
    # Both full and proxy servers use this mount; no lifespan/native jobs run here.
    app = FastAPI()
    with patch("agentdecompile_recovery.corpus.dashboard.actions.openapi.list_actions", return_value=[]):
        mount_unified_pages(app)
    client = TestClient(app)
    query = "binary=a%2Fb&program=one&program=two&addr=0x123&mode=atlas"
    with TemporaryDirectory() as directory:
        root = Path(directory)
        assets = root / "react"
        (assets / "assets").mkdir(parents=True)
        (root / "secret.js").write_text("secret")
        (assets / "assets" / "escape.js").symlink_to(root / "secret.js")
        for name in ("entry.js", "entry.css", "editor.worker.js", "module.wasm"):
            (assets / "assets" / name).write_text("fixture asset")
        entry = assets / "index.html"
        entry.write_text('<!doctype html><div id="root"></div><script src="/react/assets/entry.js"></script><link href="/react/assets/entry.css" rel="stylesheet">')
        with patch.object(react_api, "ASSETS", assets):
            for path in ("/react", "/react/", "/react/foo", "/react/foo/bar", "/react/index.html"):
                response = client.get(path + "?" + query)
                assert response.status_code == 200, (path, response.text)
                assert 'id="root"' in response.text
                for key, value in SECURITY_HEADERS.items():
                    assert response.headers[key] == value
            for path in ("/dashboard", "/dashboard/static/react", "/dashboard/static/react/", "/dashboard/static/react/index.html"):
                response = client.get(path + "?" + query + "#source", follow_redirects=False)
                assert response.status_code == 302
                assert response.headers["location"] == "/react/?" + query
                # A Location without a fragment preserves the browser's original fragment.
                assert "#" not in response.headers["location"]
            for base in ("/react/", "/dashboard/static/react/"):
                for name in ("entry.js", "entry.css", "editor.worker.js", "module.wasm"):
                    response = client.get(base + "assets/" + name)
                    assert response.status_code == 200
                    assert response.text == "fixture asset"
                    assert response.headers["x-content-type-options"] == "nosniff"
                    assert "text/html" not in response.headers["content-type"]
                for name in ("missing.js", "missing.css", "missing.wasm", "missing.worker.js", "assets/absent", "assets/escape.js", "%2e%2e/secret.js", "assets/%2e%2e/%2e%2e/secret.js", "assets%5cescape.js"):
                    response = client.get(base + name)
                    assert response.status_code == 404, (base, name, response.status_code)
                    assert 'id="root"' not in response.text
            assert client.get("/dashboard/api/runtime-config").json()["ok"] is True
            for incomplete in (True, False):
                if incomplete:
                    (assets / "assets" / "entry.js").unlink()
                else:
                    entry.unlink()
                response = client.get("/react/foo?" + query)
                assert response.status_code == 503
                assert "React workstation delivery unavailable" in response.text
                assert "window.location.hash" in response.text
                fallback = unescape(re.search(r'id="static-workbench-fallback" href="([^"]+)"', response.text)[1])
                parts = urlsplit(fallback)
                assert parts.path == "/dashboard"
                assert parse_qs(parts.query) == {"mode": ["static"], "binary": ["a/b"], "program": ["one", "two"], "addr": ["0x123"]}
                with patch("agentdecompile_recovery.corpus.dashboard.workbench.render_workbench", return_value="legacy workbench"):
                    static = client.get(fallback, follow_redirects=False)
                assert static.status_code == 200 and static.text == "legacy workbench"
                assert "location" not in static.headers


if __name__ == "__main__":
    test_canonical_react_delivery()
    print("canonical React routing: PASS")

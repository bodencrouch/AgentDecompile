"""Cockpit live API against a tiny synthetic corpus database."""
from __future__ import annotations

import json
import socket
import sqlite3
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdecompile_recovery.corpus.dashboard import cockpit

SCHEMA = """
CREATE TABLE binary(id INTEGER PRIMARY KEY, slug TEXT UNIQUE, game TEXT, platform TEXT, format TEXT);
CREATE TABLE func(binary_id INTEGER, addr INTEGER, name TEXT, size INTEGER, signature TEXT, source_file TEXT,
                  PRIMARY KEY(binary_id, addr));
CREATE TABLE identity(logical_id INTEGER, binary_id INTEGER, addr INTEGER, confidence REAL, method TEXT, evidence TEXT);
CREATE UNIQUE INDEX ux_identity_bin_addr ON identity(binary_id, addr);
CREATE TABLE logical_function(id INTEGER PRIMARY KEY, canon_key TEXT, best_name TEXT, best_signature TEXT, source_file TEXT);
CREATE TABLE logical_name(logical_id INTEGER, name TEXT, tier INTEGER, tier_name TEXT, signature TEXT, source_file TEXT);
CREATE TABLE recovered_function(program TEXT, binary_id INTEGER, addr INTEGER, name TEXT, size INTEGER,
                                convention TEXT, real_c INTEGER, logical_id INTEGER);
CREATE TABLE calledge(binary_id INTEGER, caller_addr INTEGER, callee_addr INTEGER);
CREATE TABLE decomp(binary_id INTEGER, addr INTEGER, ok INTEGER, n_lines INTEGER, n_calls INTEGER, max_nest INTEGER);
"""


def build_db(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO binary VALUES(?,?,?,?,?)", [
        (1, "a-win", "G", "win", "PE"), (2, "a-mac", "G", "mac", "Mach-O"),
        (3, "solo", None, "linux", "ELF"), (4, "empty", "H", "win", "PE")])
    con.executemany("INSERT INTO func VALUES(?,?,?,?,?,?)", [
        (1, 0x1000, "FUN_1000", 16, "void f(void)", None), (1, 0x1010, "FUN_1010", 8, None, None),
        (1, 0x1020, "FUN_1020", 4, None, None), (1, 0x1030, "uniq_fn", 12, None, None),
        (1, 0x1040, "FUN_1040", 2, None, None),
        (2, 0x2000, "alpha", 16, None, None), (2, 0x2010, "beta", 8, None, None), (2, 0x2020, "x", 4, None, None),
        (3, 0x3000, "s0", 4, None, None), (3, 0x3010, "s1", 4, None, None)])
    con.executemany("INSERT INTO identity VALUES(?,?,?,?,?,NULL)", [
        (1, 1, 0x1000, 0.9, "name-unique"), (1, 2, 0x2000, 0.8, "match:auto"),
        (2, 1, 0x1010, 0.9, "name-unique"), (2, 2, 0x2010, 0.7, "match:auto"),
        (3, 1, 0x1020, 0.5, "name-weak")])
    con.executemany("INSERT INTO logical_function VALUES(?,?,?,?,?)", [
        (1, "k1", "Alpha", "int Alpha(void)", "alpha.c"), (2, "k2", "Beta", None, None), (3, "k3", "Gamma", None, None)])
    con.executemany("INSERT INTO logical_name VALUES(?,?,?,?,?,?)", [
        (1, "Alpha", 1, "human", "int Alpha(void)", "alpha.c"), (2, "Beta", 4, "derived", None, None),
        (3, "Gamma", 3, "symbol", None, None)])
    con.executemany("INSERT INTO recovered_function VALUES(?,?,?,?,?,?,?,?)", [
        # real C for logical 2 lives only in the *other* build (a-mac)
        ("a-mac", 2, 0x2010, "beta", 8, "__cdecl", 1, None),
        # NULL addr resolved by a name unique within a-win
        ("a-win", 1, None, "uniq_fn", 12, "__stdcall", 1, None),
        # machine-code only: does not make logical 1 real-C
        ("a-win", 1, 0x1000, "FUN_1000", 16, "__cdecl", 0, 1)])
    con.executemany("INSERT INTO calledge VALUES(?,?,?)", [
        (1, 0x1000, 0x1010), (1, 0x1000, 0x1020), (1, 0x1010, 0x1020), (1, 0x1000, 0x9999), (1, 0x1000, 0x1010)])
    con.execute("INSERT INTO decomp VALUES(1, 4096, 1, 20, 2, 1)")
    con.commit()
    con.close()
    return path


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.delenv(cockpit.ENV_DB, raising=False)
    monkeypatch.setattr(cockpit, "_job_rows", lambda: [])
    cockpit._STORES.clear()
    cockpit._HUBS.clear()
    return build_db(tmp_path / "corpus.sqlite")


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(cockpit.create_cockpit_router())
    return TestClient(app)


def test_summary_shape_and_grouping(db, client, monkeypatch):
    monkeypatch.setattr(cockpit, "_job_rows", lambda: [
        {"id": "j1", "actionId": "mcp.decompile-function", "title": "Decompile", "status": "running",
         "createdAt": 10.0, "startedAt": 11.0, "finishedAt": None, "params": {"slug": "a-win", "address": "0x1000"}},
        {"id": "j2", "actionId": "corpus.match", "title": "Match builds", "status": "ok",
         "createdAt": 1.0, "startedAt": 2.0, "finishedAt": 5.0, "params": {"binaryId": 3}},
    ])
    body = client.get("/dashboard/api/cockpit/summary", params={"db": str(db)}).json()
    assert body["ok"] is True
    assert set(body) >= {"generated", "db", "totals", "programs", "tiers", "match_methods", "activity"}
    assert body["db"]["path"] == str(db.resolve()) and body["db"]["bytes"] > 0
    assert body["totals"] == {"binaries": 3, "functions": 10, "logical": 3, "bound": 5, "recovered_logical": 1,
                              "named_above_placeholder": 3, "named_of": 3}
    programs = {p["id"]: p for p in body["programs"]}
    assert set(programs) == {"g", "solo"}  # the binary without functions is not drawn
    g = programs["g"]
    assert (g["label"], g["ref"], g["n"]) == ("G", "a-win", 5)
    assert [b["slug"] for b in g["builds"]] == ["a-win", "a-mac"]
    assert g["builds"][0] == {"id": 1, "slug": "a-win", "platform": "win", "format": "PE", "functions": 5,
                              "bound": 3, "real_c": 1}
    assert g["builds"][1]["real_c"] == 1 and g["builds"][1]["bound"] == 2
    assert programs["solo"]["label"] == "solo"
    assert body["tiers"] == [["human", 1], ["symbol", 1], ["derived", 1]]
    assert dict(map(tuple, body["match_methods"])) == {"name-unique": 2, "match:auto": 2, "name-weak": 1}
    first, second = body["activity"]
    assert first == {"ts": 11.0, "lane": "decompile", "kind": "mcp.decompile-function", "label": "Decompile",
                     "status": "running", "job_id": "j1", "binary": "a-win", "program_id": "g", "addr": 0x1000}
    assert second["lane"] == "match" and second["program_id"] == "solo" and second["ts"] == 5.0


def test_cells_state_rules(db, client):
    body = client.get("/dashboard/api/cockpit/program/g/cells", params={"db": str(db)}).json()
    assert body["ok"] is True and body["ref"] == "a-win" and body["n"] == 5
    assert body["addr"] == [0x1000, 0x1010, 0x1020, 0x1030, 0x1040]
    assert body["size"] == [16, 8, 4, 12, 2]
    # 0x1000 bound; 0x1010 real C via its logical fn in the other build; 0x1020 bound;
    # 0x1030 real-C row matched by unique name; 0x1040 unbound.
    assert body["state"] == "12120"
    assert body["nb"] == [2, 2, 1, 0, 0]
    assert body["tier"] == "14300"
    assert body["logical"] == [1, 2, 3, 0, 0]
    assert body["names"] == {"0": "Alpha", "2": "Gamma"}  # tiers 1-3 only
    assert body["edges"] == [[0, 2], [0, 1], [1, 2]]  # deduped, in-build only, named-first
    other = client.get("/dashboard/api/cockpit/program/g/cells", params={"db": str(db), "ref": "a-mac"}).json()
    assert other["ref"] == "a-mac" and other["state"] == "120"
    missing = client.get("/dashboard/api/cockpit/program/nope/cells", params={"db": str(db)})
    assert missing.status_code == 404 and missing.json()["ok"] is False


def test_function_detail(db, client):
    body = client.get("/dashboard/api/cockpit/function", params={"db": str(db), "program_id": "g", "index": 0}).json()
    assert body["ok"] is True
    assert (body["name"], body["tier"], body["tier_name"], body["logical_id"]) == ("Alpha", 1, "human", 1)
    assert body["signature"] == "int Alpha(void)" and body["source_file"] == "alpha.c"
    assert [(i["slug"], i["platform"], i["addr"], i["size"], i["method"]) for i in body["instances"]] == [
        ("a-win", "win", 0x1000, 16, "name-unique"), ("a-mac", "mac", 0x2000, 16, "match:auto")]
    assert body["absent"] == []
    assert body["callers"] == []
    assert body["callees"] == [{"index": 1, "name": "Beta", "addr": 0x1010}, {"index": 2, "name": "Gamma", "addr": 0x1020}]
    assert [(r["binary_slug"], r["real_c"]) for r in body["recovered"]] == [("a-win", 0)]
    assert body["decomp"] == {"ok": True, "n_lines": 20, "n_calls": 2, "max_nest": 1}

    gamma = client.get("/dashboard/api/cockpit/function", params={"db": str(db), "binary_id": 1, "addr": "0x1020"}).json()
    assert gamma["name"] == "Gamma" and gamma["absent"] == ["a-mac"] and gamma["decomp"] is None
    assert [c["index"] for c in gamma["callers"]] == [0, 1]

    beta = client.get("/dashboard/api/cockpit/function", params={"db": str(db), "program_id": "g", "index": 1}).json()
    assert [(r["binary_slug"], r["addr"], r["real_c"]) for r in beta["recovered"]] == [("a-mac", 0x2010, 1)]

    unbound = client.get("/dashboard/api/cockpit/function", params={"db": str(db), "binary_id": 1, "addr": 4160}).json()
    assert unbound["logical_id"] is None and unbound["instances"] == [] and unbound["absent"] == ["a-mac"]
    assert unbound["name"] == "FUN_1040"

    bad = client.get("/dashboard/api/cockpit/function", params={"db": str(db), "program_id": "g", "index": 99})
    assert bad.status_code == 404 and bad.json()["ok"] is False
    assert client.get("/dashboard/api/cockpit/function", params={"db": str(db)}).status_code == 400


def test_db_resolution(db, client, monkeypatch, tmp_path):
    missing = client.get("/dashboard/api/cockpit/summary", params={"db": str(tmp_path / "missing.sqlite")})
    assert missing.status_code == 400 and missing.json()["ok"] is False
    monkeypatch.setenv(cockpit.ENV_DB, str(db))
    body = client.get("/dashboard/api/cockpit/summary").json()
    assert body["ok"] is True and body["db"]["path"] == str(db.resolve())
    # ?db= wins over the environment
    other = build_db(tmp_path / "other.sqlite")
    assert client.get("/dashboard/api/cockpit/summary", params={"db": str(other)}).json()["db"]["path"] == str(other.resolve())
    # ?db= only names existing .sqlite/.db files
    wrong = tmp_path / "notes.txt"
    wrong.write_text("x")
    rejected = client.get("/dashboard/api/cockpit/summary", params={"db": str(wrong)})
    assert rejected.status_code == 400 and rejected.json()["ok"] is False
    dotdb = build_db(tmp_path / "corpus.db")
    assert client.get("/dashboard/api/cockpit/summary", params={"db": str(dotdb)}).json()["ok"] is True


def test_bound_counts_distinct_addresses_without_unique_index(tmp_path, client, monkeypatch):
    monkeypatch.setattr(cockpit, "_job_rows", lambda: [])
    path = tmp_path / "loose.sqlite"
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE binary(id INTEGER PRIMARY KEY, slug TEXT, game TEXT);"
        "CREATE TABLE func(binary_id INTEGER, addr INTEGER, name TEXT);"
        "CREATE TABLE identity(logical_id INTEGER, binary_id INTEGER, addr INTEGER, method TEXT);"
        "INSERT INTO binary VALUES(1,'b1','P'),(2,'b2','P');"
        "INSERT INTO func VALUES(1,16,'f'),(1,32,'g'),(2,16,'f');"
        # two logical candidates for the same address: one bound address, not two
        "INSERT INTO identity VALUES(7,1,16,'m'),(8,1,16,'m'),(7,2,16,'m');")
    con.commit()
    con.close()
    body = client.get("/dashboard/api/cockpit/summary", params={"db": str(path)}).json()
    assert [(b["slug"], b["bound"]) for b in body["programs"][0]["builds"]] == [("b1", 1), ("b2", 1)]
    assert dict(map(tuple, body["match_methods"])) == {"m": 3}
    cells = client.get("/dashboard/api/cockpit/program/p/cells", params={"db": str(path)}).json()
    assert cells["state"][1] == "0" and cells["nb"][1] == 0


def test_missing_tables_degrade(tmp_path, client, monkeypatch):
    monkeypatch.setattr(cockpit, "_job_rows", lambda: [])
    path = tmp_path / "bare.sqlite"
    con = sqlite3.connect(path)
    con.executescript("CREATE TABLE binary(id INTEGER PRIMARY KEY, slug TEXT);"
                      "CREATE TABLE func(binary_id INTEGER, addr INTEGER);"
                      "INSERT INTO binary VALUES(1,'only'); INSERT INTO func VALUES(1, 16);")
    con.commit()
    con.close()
    body = client.get("/dashboard/api/cockpit/summary", params={"db": str(path)}).json()
    assert body["ok"] is True and [p["id"] for p in body["programs"]] == ["only"]
    cells = client.get("/dashboard/api/cockpit/program/only/cells", params={"db": str(path)}).json()
    assert cells["state"] == "0" and cells["edges"] == [] and cells["tier"] == "0"


def test_static_page(client):
    page = client.get("/dashboard/cockpit")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert client.get("/dashboard/cockpit/..%2F..%2Frouter.py").status_code == 404
    for asset, kind in (("cockpit.js", "javascript"), ("cockpit.css", "css")):
        response = client.get(f"/dashboard/cockpit/{asset}")
        assert response.status_code == 200 and kind in response.headers["content-type"]
    assert client.get("/dashboard/cockpit/missing.js").status_code == 404


def test_lane_mapping():
    assert cockpit.lane_for("mcp.decompile-function") == "decompile"
    assert cockpit.lane_for("mcp.rename-function") == "name"
    assert cockpit.lane_for("workbench.commit-signatures") == "signature"
    assert cockpit.lane_for("workbench.prepare") == "import"
    assert cockpit.lane_for("corpus.logical-build") == "match"
    assert cockpit.lane_for("workbench.export-source-zip") == "other"
    assert cockpit.lane_for("workbench.match-candidate", "Compile and verify candidate") == "compile"
    assert cockpit.lane_for("recover.verify-package") == "compile"
    assert cockpit.lane_for("corpus.cross-place") == "match"
    assert cockpit.lane_for("workbench.merge-evidence", "Bind compared knowledge") == "match"
    assert cockpit.lane_for("reconstruct.one-shot", "Reconstruct one-shot") == "other"


# --------------------------------------------------------------------------- SSE (real server)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def server(db, monkeypatch):
    import uvicorn

    monkeypatch.setattr(cockpit, "POLL_S", 0.2)
    monkeypatch.setattr(cockpit, "PING_S", 0.5)
    app = FastAPI()
    app.include_router(cockpit.create_cockpit_router())
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                        lifespan="off", timeout_graceful_shutdown=2))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not srv.started and time.time() < deadline:
        time.sleep(0.05)
    assert srv.started
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(10)


def _read_events(base: str, db: Path, want: set[str], out: list, ready: threading.Event, timeout: float = 15) -> None:
    deadline = time.time() + timeout
    event, pings = None, 0
    with httpx.stream("GET", f"{base}/dashboard/api/cockpit/stream", params={"db": str(db)}, timeout=10) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith(": ping"):
                pings += 1
                out.append(("ping", None))
            elif line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event:
                out.append((event, json.loads(line[6:])))
                if event == "hello":
                    ready.set()
                event = None
            if want <= {name for name, _ in out} or time.time() > deadline:
                return


def test_stream_hello_cells_diff_and_activity(db, server, monkeypatch):
    jobs: list[dict] = []
    monkeypatch.setattr(cockpit, "_job_rows", lambda: list(jobs))
    # materialize the program's cells so the poller diffs them
    assert httpx.get(f"{server}/dashboard/api/cockpit/program/g/cells", params={"db": str(db)}).json()["state"] == "12120"
    want = {"hello", "summary", "cells", "activity", "ping"}
    results: list[list] = [[], []]
    ready = [threading.Event(), threading.Event()]
    threads = [threading.Thread(target=_read_events, args=(server, db, want, results[i], ready[i])) for i in range(2)]
    for thread in threads:
        thread.start()
    assert all(r.wait(10) for r in ready)
    time.sleep(0.6)  # let the shared poller take its baseline
    con = sqlite3.connect(db)
    con.execute("INSERT INTO identity VALUES(3, 1, 4160, 0.6, 'match:auto', NULL)")
    con.commit()
    con.close()
    jobs.append({"id": "j9", "actionId": "mcp.rename-function", "title": "Rename", "status": "running",
                 "createdAt": 1.0, "startedAt": 2.0, "finishedAt": None, "params": {"slug": "a-win", "addr": 4160}})
    for thread in threads:
        thread.join(20)
    for events in results:
        names = [name for name, _ in events]
        assert names[0] == "hello"
        hello = events[0][1]
        assert hello == {"db": str(db.resolve()), "programs": ["g", "solo"]}
        cells = [data for name, data in events if name == "cells"]
        assert cells and cells[0] == {"program_id": "g", "changes": [[4, 1, 1, 3]]}
        summary = next(data for name, data in events if name == "summary")
        assert summary["totals"]["bound"] == 6
        activity = next(data for name, data in events if name == "activity")
        assert (activity["lane"], activity["program_id"], activity["addr"], activity["status"]) == ("name", "g", 4160, "running")
        assert "ping" in names
    # both clients disconnected: the shared poller is gone
    deadline = time.time() + 5
    while cockpit._HUBS and time.time() < deadline:
        time.sleep(0.05)
    assert cockpit._HUBS == {}

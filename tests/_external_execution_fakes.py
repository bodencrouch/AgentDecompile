"""Synthetic providers, PE/PDB pairs and Wine tools for external_execution tests.

Everything here is hand-built bytes and text. Nothing downloads, installs or runs
a real reccmp, ReAgent or Wine.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

from agentdecompile_recovery.corpus.external_execution import PINS

PDB_MAGIC = b"Microsoft C/C++ MSF 7.00\r\n\x1aDS\x00\x00\x00"
GUID = bytes(range(16))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, data, mode=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    if mode is not None:
        path.chmod(mode)
    return path


def _record_hash(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def site_packages(venv: Path) -> Path:
    return venv / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"


def make_provider(venv: Path, provider: str, *, entry_source: str | None = None, commit=None,
                  archive=None, version=None, entry_point=True, interpreter=True) -> Path:
    """Lay out a dist-info that matches (or deliberately misses) the code-owned pin."""
    pin = PINS[provider]
    if interpreter and not (venv / "bin" / "python").exists():
        write(venv / "bin" / "python", b"#!fake interpreter\n", 0o755)
    if not (venv / "pyvenv.cfg").exists():
        write(venv / "pyvenv.cfg", "home = /usr/bin\ninclude-system-site-packages = false\n")
    sp = site_packages(venv)
    module = "fake_" + provider.replace("-", "_")
    files = {f"{module}/__init__.py": b"",
             f"{module}/cli.py": (entry_source or "def main():\n    return 0\n").encode()}
    dist = sp / f"{pin['distribution'].replace('-', '_')}-{version or pin['version']}.dist-info"
    meta = {"METADATA": f"Metadata-Version: 2.1\nName: {pin['distribution']}\nVersion: {version or pin['version']}\n",
            "direct_url.json": json.dumps({
                "url": f"https://github.com/example/{pin['distribution']}/archive/{commit or pin['commit']}.tar.gz",
                "archive_info": {"hash": f"sha256={archive or pin['archive_sha256']}",
                                 "hashes": {"sha256": archive or pin['archive_sha256']}}}),
            "entry_points.txt": (f"[console_scripts]\n{pin['script']} = {module}.cli:main\n" if entry_point
                                 else "[console_scripts]\nsomething-else = other:main\n")}
    rows = []
    for rel, data in files.items():
        write(sp / rel, data)
        rows.append(f"{rel},{_record_hash(data)},{len(data)}")
    for name, text in meta.items():
        data = text.encode()
        write(dist / name, data)
        rows.append(f"{dist.name}/{name},{_record_hash(data)},{len(data)}")
    rows.append(f"{dist.name}/RECORD,,")
    write(dist / "RECORD", "\n".join(rows) + "\n")
    return venv


def pe_with_codeview(guid=GUID, age=1) -> bytes:
    """Minimal PE32: DOS header, COFF, optional header, one section holding the debug dir."""
    e_lfanew = 0x40
    opt_size = 96 + 16 * 8
    sect_off = e_lfanew + 4 + 20 + opt_size
    raw = 0x200
    rva = 0x1000
    cv = b"RSDS" + guid + struct.pack("<I", age) + b"rebuild.pdb\x00"
    debug = struct.pack("<IIHHIIII", 0, 0, 0, 0, 2, len(cv), rva + 28, raw + 28)
    body = debug + cv
    data = bytearray(raw + 0x200)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, e_lfanew)
    data[e_lfanew:e_lfanew + 4] = b"PE\x00\x00"
    struct.pack_into("<HHIIIHH", data, e_lfanew + 4, 0x14C, 1, 0, 0, 0, opt_size, 0x102)
    opt = e_lfanew + 24
    struct.pack_into("<H", data, opt, 0x10B)
    struct.pack_into("<I", data, opt + 92, 16)
    struct.pack_into("<II", data, opt + 96 + 6 * 8, rva, 28)
    data[sect_off:sect_off + 8] = b".rdata\x00\x00"
    struct.pack_into("<IIII", data, sect_off + 8, 0x200, rva, 0x200, raw)
    data[raw:raw + len(body)] = body
    return bytes(data)


def pdb_with_info(guid=GUID, age=1) -> bytes:
    """Minimal MSF 7.00 file: superblock, block map, directory and PDB info stream (stream 1)."""
    bs = 512
    info = struct.pack("<III", 20000404, 0x5F000000, age) + guid
    # blocks: 0 superblock, 1 fpm, 2 fpm, 3 block map, 4 directory, 5 stream 1
    directory = struct.pack("<I", 2) + struct.pack("<II", 0, len(info)) + struct.pack("<I", 5)
    blocks = [bytearray(bs) for _ in range(6)]
    blocks[0][:32] = PDB_MAGIC
    struct.pack_into("<IIIIII", blocks[0], 32, bs, 1, 6, len(directory), 0, 3)
    struct.pack_into("<I", blocks[3], 0, 4)
    blocks[4][:len(directory)] = directory
    blocks[5][:len(info)] = info
    return b"".join(bytes(b) for b in blocks)


def make_wine(root: Path, *, wine=True, winepath=True, wineserver=True, log: Path | None = None) -> Path:
    """Fake wine tools. wineserver appends its argv and WINEPREFIX to ``log``."""
    tools = root / "winebin"
    log_line = (f"import os,sys,json;open({str(log)!r},'a').write(json.dumps([sys.argv[1:],"
                f"os.environ.get('WINEPREFIX')])+'\\n')\n") if log else ""
    script = f"#!{sys.executable}\n{log_line}"
    for name, present in (("wine", wine), ("winepath", winepath), ("wineserver", wineserver)):
        if present:
            write(tools / name, script, 0o755)
    return tools / "wine"


def make_prefix(root: Path, initialized=True) -> Path:
    prefix = root / "prefix"
    prefix.mkdir(parents=True, exist_ok=True)
    if initialized:
        write(prefix / "system.reg", "WINE REGISTRY Version 2\n")
    return prefix


def reccmp_params(tmp: Path, *, target="CANARY", project_sha=None, pdb_age=1) -> dict:
    original = write(tmp / "in" / "original.exe", b"original bytes")
    rebuild = write(tmp / "in" / "build" / "rebuild.exe", pe_with_codeview())
    pdb = write(tmp / "in" / "build" / "rebuild.pdb", pdb_with_info(age=pdb_age))
    project = tmp / "in" / "project"
    write(project / "reccmp-project.yml",
          f"targets:\n  {target}:\n    filename: ORIGINAL.EXE\n    source-root: src\n"
          f"    hash:\n      sha256: {project_sha or sha(original.read_bytes())}\n")
    venv = make_provider(tmp / "venv-reccmp", "reccmp-compare")
    (tmp / "out").mkdir(parents=True, exist_ok=True)
    return {"project-dir": str(project), "reccmp-target": "CANARY",
            "original": str(original), "original-sha256": sha(original.read_bytes()),
            "rebuild": str(rebuild), "rebuild-sha256": sha(rebuild.read_bytes()),
            "pdb": str(pdb), "pdb-sha256": sha(pdb.read_bytes()),
            "report-dir": str(tmp / "out" / "report"), "provider-venv": str(venv),
            "wine": str(make_wine(tmp)), "wineprefix": str(make_prefix(tmp)), "timeout": 60}


def reagent_params(tmp: Path, *, rows=None, entry_source=None, venv: Path | None = None) -> dict:
    inputs = tmp / "in" / "inputs"
    candidate = write(tmp / "in" / "candidate.c", b"int f(int x) { return x + 1; }\n")
    write(inputs / "reference.c", b"int f(int x) { return x + 1; }\n")
    tool = os.path.realpath(sys.executable)
    manifest = write(tmp / "in" / "benchmark.json", json.dumps({"benchmarks": rows if rows is not None else [
        {"name": "canary", "reference": [tool, str(inputs / "reference.c")],
         "candidate": [tool, str(candidate)], "timeout_s": 30}]}))
    venv = venv or make_provider(tmp / "venv-reagent", "reagent-benchmark", entry_source=entry_source)
    (tmp / "out").mkdir(parents=True, exist_ok=True)
    return {"manifest": str(manifest), "manifest-sha256": sha(manifest.read_bytes()),
            "inputs-dir": str(inputs), "candidate": str(candidate),
            "candidate-sha256": sha(candidate.read_bytes()),
            "report-dir": str(tmp / "out" / "report"), "provider-venv": str(venv), "timeout": 60}

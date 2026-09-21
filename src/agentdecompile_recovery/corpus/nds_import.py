"""Bring a Nintendo DS ROM online: extract ARM9/ARM7, import each into Ghidra.

Ghidra has no Nintendo-DS loader, so a .nds file can never be handed to
`mcp.import-binary` directly -- that is why sonic_chronicles.nds was held back
from the first family batch. The fix is two steps this module drives:

  1. `nds_extract` splits the ROM into arm9.bin/arm7.bin at their real RAM load
     addresses (from the cartridge header).
  2. `analyzeHeadless` imports each as a **raw binary** with an explicit
     processor (ARM9=ARMv5T, ARM7=ARMv4T) and `-loader-baseAddr`, into a
     per-binary Ghidra project -- the same on-disk convention already used for
     every other imported binary in `corpus_work/ghidra-projects/*.gpr`.

The result is a normal local .gpr/.rep project the dashboard's prepare stage
can point at (locator = the .gpr path), so ARM9/ARM7 flow through the same
prepare -> func-extraction -> recovery pipeline as every PE/ELF binary. No
proprietary tooling: GBATEK's public header layout + Ghidra's own raw loader.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from . import nds_extract


def _analyze_headless() -> Path:
    install = os.environ.get("GHIDRA_INSTALL_DIR", "").strip()
    if not install:
        raise RuntimeError("GHIDRA_INSTALL_DIR is not set")
    exe = Path(install) / "support" / "analyzeHeadless"
    if not exe.is_file():
        raise RuntimeError(f"analyzeHeadless not found under {install}")
    return exe


def import_raw_cpu_image(project_dir: Path, project_name: str, program_name: str,
                          image: Path, *, language: str, base_addr: int,
                          entry_addr: int | None = None, timeout: int = 900) -> dict:
    """Headless-import one raw ARM blob at `base_addr`, run default analysis."""
    project_dir.mkdir(parents=True, exist_ok=True)
    gpr = project_dir / f"{project_name}.gpr"
    # Pass 1: import the raw blob with the loader options that only apply at
    # import time (processor + base address), analysis deferred.
    argv = [str(_analyze_headless()), str(project_dir), project_name,
            "-import", str(image),
            "-processor", language,
            "-loader", "BinaryLoader",
            "-loader-baseAddr", hex(base_addr),
            "-noanalysis"]
    r1 = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    ok_import = gpr.is_file() and r1.returncode == 0
    r2 = None
    if ok_import:
        # Pass 2: run full auto-analysis now that the program exists in the
        # project under its final name (-process re-opens by name, no re-import).
        argv2 = [str(_analyze_headless()), str(project_dir), project_name, "-process", "*"]
        r2 = subprocess.run(argv2, capture_output=True, text=True, timeout=timeout)
    return {
        "ok": ok_import and (r2 is None or r2.returncode == 0),
        "gpr": str(gpr) if gpr.is_file() else None,
        "import_rc": r1.returncode, "import_log": r1.stdout[-2000:] + r1.stderr[-1000:],
        "analyze_rc": (r2.returncode if r2 else None),
        "analyze_log": ((r2.stdout[-2000:] + r2.stderr[-1000:]) if r2 else ""),
    }


def bring_online(nds_path: Path, work_dir: Path, projects_dir: Path) -> dict:
    """Extract + import both CPUs. Returns {arm9: {...}, arm7: {...}} each with
    `ok`, `gpr` (the locator to hand the dashboard prepare stage), and header
    fields (ram_addr/entry_addr/size) for DB registration."""
    stem = nds_path.stem
    extract_dir = work_dir / f"{stem}_nds_extract"
    manifest = nds_extract.extract(nds_path, extract_dir)
    out: dict[str, dict] = {}
    for cpu, info in manifest["cpus"].items():
        if not info.get("ok"):
            out[cpu] = info
            continue
        project_name = f"{stem}_{cpu}"
        res = import_raw_cpu_image(
            projects_dir, project_name, f"{cpu}.bin", Path(info["path"]),
            language=info["language"], base_addr=info["ram_addr"],
            entry_addr=info["entry_addr"])
        out[cpu] = {**info, **res}
    return {"title": manifest["title"], "game_code": manifest["game_code"], "cpus": out}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nds", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True,
                    help="scratch dir for the extracted arm9.bin/arm7.bin")
    ap.add_argument("--projects-dir", type=Path, required=True,
                    help="where to create the per-CPU Ghidra .gpr/.rep projects")
    args = ap.parse_args(argv)
    result = bring_online(args.nds, args.work_dir, args.projects_dir)
    print(json.dumps({k: v for k, v in result.items() if k != "cpus"} |
                      {"cpus": {c: {kk: vv for kk, vv in d.items() if not kk.endswith("_log")}
                                 for c, d in result["cpus"].items()}}, indent=1))
    ok = all(c.get("ok") for c in result["cpus"].values())
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

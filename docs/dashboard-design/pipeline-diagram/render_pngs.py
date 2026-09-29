#!/usr/bin/env python3
"""Render the four diagram SVGs to PNG with resvg (the resvg-py binding), 1:1 with each canvas.

Only the DejaVu TrueType files in /usr/share/fonts/truetype/dejavu are loaded (system fonts
are skipped), so the PNGs do not depend on whatever else is installed.  resvg-py must be
importable: ``pip install resvg-py==0.5.0`` or put an installed copy on PYTHONPATH.
Document rendering only; nothing here exercises AgentDecompile.
"""
from __future__ import annotations

import re
import struct
from importlib import metadata

from diagram_common import DEJAVU_DIR, DEJAVU_FILES, HERE, load_model

try:
    import resvg_py
except ImportError:  # pragma: no cover - environment guidance only
    raise SystemExit("resvg-py is not importable: pip install resvg-py==0.5.0 (or add it to PYTHONPATH)")

missing = [f for f in DEJAVU_FILES.values() if not (DEJAVU_DIR / f).exists()]
if missing:
    raise SystemExit(f"DejaVu fonts missing from {DEJAVU_DIR}: {missing}")

M = load_model()
version = metadata.version("resvg-py")
for diagram in M["diagrams"].values():
    svg_path = HERE / diagram["svg"]
    png = bytes(resvg_py.svg_to_bytes(
        svg_path=str(svg_path),
        skip_system_fonts=True,
        font_dirs=[str(DEJAVU_DIR)],
        font_family="DejaVu Sans",
        sans_serif_family="DejaVu Sans",
        monospace_family="DejaVu Sans Mono",
    ))
    w, h = struct.unpack(">II", png[16:24])
    head = svg_path.read_text(encoding="utf-8")[:2000]
    want = tuple(int(v) for v in re.search(r'<svg[^>]*width="(\d+)" height="(\d+)"', head).groups())
    if (w, h) != want:
        raise SystemExit(f"{diagram['png']}: rendered {w}x{h}, canvas is {want[0]}x{want[1]}")
    (HERE / diagram["png"]).write_bytes(png)
    print(f"{HERE / diagram['png']} {w}x{h} {len(png)} bytes (resvg-py {version})")

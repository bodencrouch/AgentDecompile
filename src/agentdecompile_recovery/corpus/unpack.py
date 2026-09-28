"""Detect and (when possible) remove packing/DRM before recovery.

A packed or DRM-encrypted binary (SecuROM, UPX, ...) has ciphertext where its
code should be: Ghidra disassembles noise, and the recovery cascade would emit
garbage C. This stage runs FIRST -- it detects packing by section entropy and
packer signatures, and either produces an unpacked image or gates the binary so
the pipeline refuses to recover from ciphertext (an honest failure, not garbage).

Unpacking backends, tried in order when a binary is packed:
  1. UPX      -- `upx -d` (only for UPX; exact and fast).
  2. emulate  -- Unicorn-based generic unpacker: run the image until it reaches
                 its real entry point after self-decryption, then dump. Handles
                 many runtime packers; SecuROM's anti-emulation may defeat it.
  3. (none)   -- gate: mark deferred_drm_ciphertext; needs an external runtime
                 dump (Scylla/x64dbg) supplied via ingest.

Pure-Python detection has no dependencies; the emulate backend needs `unicorn`.
No hardcoded paths.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import subprocess
from collections import Counter
from pathlib import Path

# A code section above this entropy is almost certainly encrypted/compressed.
_ENTROPY_PACKED = 7.0
_PACKER_SIGNATURES = {
    b"UPX0": "upx", b"UPX1": "upx", b"UPX!": "upx",
    b".securom": "securom", b"SecuROM": "securom", b"AddD": "securom",
    b".vmp0": "vmprotect", b".vmp1": "vmprotect",
    b".themida": "themida", b".winlice": "themida",
    b"TAGES": "tages", b".StarForce": "starforce",
}


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _sections(blob: bytes) -> list[dict]:
    if blob[:2] != b"MZ":
        return []
    e = struct.unpack_from("<I", blob, 0x3C)[0]
    if blob[e:e + 4] != b"PE\x00\x00":
        return []
    nsec = struct.unpack_from("<H", blob, e + 6)[0]
    opt = struct.unpack_from("<H", blob, e + 20)[0]
    base = e + 24 + opt
    out = []
    for i in range(nsec):
        sh = blob[base + i * 40: base + i * 40 + 40]
        if len(sh) < 40:
            break
        name = sh[:8].rstrip(b"\x00").decode("latin1", "replace")
        rsize, rptr = struct.unpack_from("<II", sh, 16)
        flags = struct.unpack_from("<I", sh, 36)[0]
        raw = blob[rptr:rptr + rsize]
        out.append({"name": name, "code": bool(flags & 0x20000020),
                    "entropy": round(_entropy(raw), 2), "raw_size": rsize})
    return out


def detect_packing(blob: bytes) -> dict:
    """Return {packed, packer, evidence, sections}. Signature-first, entropy-second."""
    packer = None
    evidence = []
    head = blob[:0x4000]
    for sig, name in _PACKER_SIGNATURES.items():
        if sig in blob[:0x20000] or sig in head:
            packer = packer or name
            evidence.append(f"signature:{sig.decode('latin1','replace')}->{name}")
    secs = _sections(blob)
    hot = [s for s in secs if (s["code"] or s["name"].lower() in (".text", "code"))
           and s["entropy"] >= _ENTROPY_PACKED]
    if hot:
        evidence.append("high-entropy-code:" + ",".join(
            f"{s['name']}={s['entropy']}" for s in hot))
    packed = bool(packer) or bool(hot)
    return {"packed": packed, "packer": packer or ("unknown" if hot else None),
            "evidence": evidence, "sections": secs}


def try_unpack(src: Path, out: Path, *, allow_run: bool = False,
               wineprefix: str | None = None, run_timeout: int = 120) -> dict:
    """Attempt to produce an unpacked image at *out*. Returns {ok, method, reason}.

    allow_run enables the runtime-dump tier, which *executes* the binary under
    Wine/native to capture the decrypted image -- opt-in because running an
    untrusted binary has side effects.
    """
    blob = src.read_bytes()
    det = detect_packing(blob)
    if not det["packed"]:
        shutil.copy2(src, out)
        return {"ok": True, "method": "not-packed", "detect": det}

    # 1) UPX -- exact static unpack.
    if det["packer"] == "upx" and shutil.which("upx"):
        shutil.copy2(src, out)
        r = subprocess.run(["upx", "-d", str(out)], capture_output=True, text=True)
        if r.returncode == 0:
            return {"ok": True, "method": "upx", "detect": det}
        return {"ok": False, "method": "upx-failed", "reason": r.stderr[:200], "detect": det}

    # 2) emulate -- Unicorn generic unpacker (self-decrypt to OEP, then dump).
    reason = ""
    try:
        from . import unpack_emulate  # optional, needs `unicorn`
        res = unpack_emulate.unpack_to_oep(blob, out)
        if res.get("ok"):
            return {"ok": True, "method": "emulate", "oep": res.get("oep"), "detect": det}
        reason = res.get("reason", "emulation did not reach a clean OEP")
    except ImportError:
        reason = "unicorn not installed (emulate backend unavailable)"

    # 3) runtime-dump -- launch for real (Wine/native), let it self-decrypt, dump
    #    the live image. Automated equivalent of Scylla; the last resort before
    #    gating. Only attempted when explicitly allowed (it executes the binary).
    if allow_run:
        from . import runtime_dump
        rd = runtime_dump.dump_to_unpacked(src, out, wineprefix=wineprefix, timeout=run_timeout)
        if rd.get("ok"):
            return {"ok": True, "method": "runtime-dump", "image_base": rd.get("image_base"),
                    "detect": det}
        reason = f"{reason}; runtime-dump: {rd.get('reason')}"

    # 4) gate -- do not emit garbage from ciphertext.
    return {"ok": False, "method": "gate", "reason": reason,
            "recovery_family": "deferred_drm_ciphertext", "detect": det}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--out", type=Path, help="write the unpacked image here")
    ap.add_argument("--detect-only", action="store_true")
    ap.add_argument("--allow-run", action="store_true",
                    help="enable the runtime-dump tier (executes the binary under Wine/native)")
    ap.add_argument("--wineprefix")
    ap.add_argument("--run-timeout", type=int, default=120)
    args = ap.parse_args(argv)

    blob = args.binary.read_bytes()
    if args.detect_only or not args.out:
        det = detect_packing(blob)
        print(json.dumps(det, indent=1))
        return 0 if not det["packed"] else 2
    res = try_unpack(args.binary, args.out, allow_run=args.allow_run,
                     wineprefix=args.wineprefix, run_timeout=args.run_timeout)
    print(json.dumps({k: v for k, v in res.items() if k != "detect"}, indent=1))
    print(f"packed={res['detect']['packed']} packer={res['detect']['packer']}")
    return 0 if res["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

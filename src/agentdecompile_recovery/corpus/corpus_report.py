"""Whole-corpus progress report for Discord: every binary, cross-match, ETAs, PNG.

Scans each binary's recovered-source tree for real-C coverage, reads the byte-
exact bins where a verify has run, counts cross-placed files, computes per-binary
ETAs from the notifier's rate history, renders a horizontal bar chart PNG, and
posts the whole thing to the configured webhook as one rich message + image.

Plain language, honest numbers (asm shims never counted as recovered).
"""
from __future__ import annotations

import io
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import discord_notify

_HEX = re.compile(r"([0-9a-fA-F]{6,8})")
_SKIP = {"recovery", "bsim", "extract", "ghidra-projects", "imports", "preparations",
         "function-evidence", "db", "scripts", "kx", "wine_vc71", "wine64_nvme",
         "target", "original-target-authorities", "workbench-jobs", "dump-source"}


def _binary_dirs(work: Path) -> list[Path]:
    out = []
    for d in sorted(work.iterdir()):
        if not d.is_dir() or d.name in _SKIP or d.name.startswith("_"):
            continue
        if any(d.glob("*.c")):
            out.append(d)
    return out


def gather(work: Path) -> list[dict]:
    rows = []
    for d in _binary_dirs(work):
        total = real = cross = 0
        # Byte-exact is the UNION of two verified sources, keyed by address so we
        # never double-count: (1) freshly-verified .bin from a local verify run,
        # and (2) AIO-consolidated C carrying a `VERIFIED BYTE-EXACT` provenance
        # header (MizuchiRE / verified_c, objdiff 0-diff when produced). Counting
        # only .bin made every sibling read 0 despite the consolidated quality.
        bx_addrs: set[int] = set()
        for f in d.glob("*.c"):
            total += 1
            try:
                head = f.read_text(errors="replace")[:2000]
            except OSError:
                continue
            if "compile-only-asm" in head:
                continue
            real += 1
            if "cross-placed onto" in head:
                cross += 1
            if "VERIFIED BYTE-EXACT" in head:
                m = _HEX.findall(f.stem)
                if m:
                    bx_addrs.add(int(m[-1], 16))
        bins = d.parent / f"{d.name}.bin"
        if bins.is_dir():
            for b in bins.glob("*.bin"):
                try:
                    bx_addrs.add(int(b.stem, 16))
                except ValueError:
                    pass
        byte_exact = len(bx_addrs)
        rows.append({"binary": d.name, "total": total, "real_c": real,
                     "byte_exact": byte_exact, "cross_placed": cross,
                     "real_pct": round(100 * real / max(total, 1), 1),
                     "bx_pct": round(100 * byte_exact / max(total, 1), 1)})
    rows.sort(key=lambda r: -r["byte_exact"])
    return rows


def render_png(rows: list[dict], out: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return False
    names = [r["binary"][:26] for r in rows]
    real = [r["real_pct"] for r in rows]
    bx = [r["bx_pct"] for r in rows]
    y = range(len(rows))
    fig, ax = plt.subplots(figsize=(11, max(4, 0.42 * len(rows))), dpi=130)
    fig.patch.set_facecolor("#141517")
    ax.set_facecolor("#141517")
    ax.barh(y, real, color="#4c78cc", label="real C (readable)", height=0.62)
    ax.barh(y, bx, color="#5cba8a", label="byte-exact (verified)", height=0.62)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, color="#cccccc", fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of functions", color="#8c8c8c")
    ax.set_title("KotOR decompilation — recovered C by binary", color="#e6e6e6", fontsize=13)
    ax.tick_params(colors="#8c8c8c")
    for s in ax.spines.values():
        s.set_color("#4b4d50")
    ax.legend(facecolor="#2b2d30", edgecolor="#4b4d50", labelcolor="#cccccc", fontsize=8, loc="lower right")
    for i, r in enumerate(rows):
        ax.text(r["real_pct"] + 1, i, f"{r['real_c']:,}/{r['total']:,}", va="center",
                color="#8c8c8c", fontsize=6.5)
    fig.tight_layout()
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return True


def _eta(rows: list[dict]) -> str:
    lead = next((r for r in rows if r["byte_exact"] > 0), None)
    if not lead:
        return "ETA: verify not yet run on any binary"
    s = discord_notify.load_settings()
    last = int(s.get("last_announced_byte_exact") or 0)
    last_t = float(s.get("last_announced_time") or 0)
    now = time.time()
    if last_t and now > last_t and lead["byte_exact"] > last:
        per_h = (lead["byte_exact"] - last) / ((now - last_t) / 3600.0)
        remain = lead["total"] - lead["byte_exact"]
        if per_h > 0:
            hrs = remain / per_h
            if hrs < 48:
                return f"lead binary ETA ~{hrs:.0f}h to full byte-exact (others follow via cross-match)"
            return f"lead binary ETA ~{hrs/24:.0f}d; hard tail is months+ (manual)"
    return "ETA: gathering rate…"


def post_report(work: Path) -> dict:
    rows = gather(work)
    if not rows:
        return {"ok": False, "reason": "no binaries"}
    total_bx = sum(r["byte_exact"] for r in rows)
    total_real = sum(r["real_c"] for r in rows)
    total_fn = sum(r["total"] for r in rows)
    total_cross = sum(r["cross_placed"] for r in rows)

    with_bx = sum(1 for r in rows if r["byte_exact"] > 0)
    lines = ["🧬 **KotOR + BioWare decompilation — full corpus report**",
             f"**{len(rows)} binaries with recovered C** · **{total_bx:,}** byte-exact "
             f"from real C ({with_bx} binaries) · **{total_real:,}** functions with readable C "
             f"· of **{total_fn:,}** total",
             f"🔗 cross-match: **{total_cross:,}** functions seeded between builds",
             f"⏱️ {_eta(rows)}",
             "🔒 DragonAge2/daorigins DRM-gated · 🧩 NWN2 empty (needs import) · chart = all binaries",
             ""]
    # Compact one-line-per-binary; show every binary that has any byte-exact or C.
    for r in rows:
        name = r["binary"].replace("libkotor2.so_", "").replace("_swkotor", "")[:24]
        lines.append(f"`{r['bx_pct']:4.1f}%bx {r['real_pct']:4.1f}%C` **{name}** "
                     f"{r['byte_exact']:,} bx / {r['real_c']:,} C"
                     + (f" · +{r['cross_placed']:,}x" if r['cross_placed'] else ""))
    content = "\n".join(lines)
    if len(content) > 1900:  # keep within Discord's limit; the PNG carries the full detail
        content = content[:1890].rsplit("\n", 1)[0] + "\n…(full detail in chart)"

    png = Path("/tmp") / f"corpus_{uuid.uuid4().hex[:8]}.png"
    has_png = render_png(rows, png)
    hook = discord_notify._webhook()
    if not hook:
        return {"ok": False, "reason": "no webhook"}
    res = _post_or_edit(hook, content, png if has_png else None, key="corpus")
    png.unlink(missing_ok=True)
    return res


def _multipart_body(content: str, png: Path | None, reset_attachments: bool) -> tuple[bytes, str]:
    boundary = "----adc" + uuid.uuid4().hex
    pj = {"content": content[:1900]}
    if reset_attachments:
        pj["attachments"] = []  # tell Discord to drop the old image on edit
    body = io.BytesIO()

    def w(s):
        body.write(s if isinstance(s, bytes) else s.encode())
    w(f"--{boundary}\r\n")
    w('Content-Disposition: form-data; name="payload_json"\r\n')
    w("Content-Type: application/json\r\n\r\n")
    w(json.dumps(pj).encode())
    w("\r\n")
    if png is not None:
        w(f"--{boundary}\r\n")
        w('Content-Disposition: form-data; name="files[0]"; filename="corpus.png"\r\n')
        w("Content-Type: image/png\r\n\r\n")
        w(png.read_bytes())
        w("\r\n")
    w(f"--{boundary}--\r\n")
    return body.getvalue(), boundary


def _send(url: str, method: str, body: bytes, boundary: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "AgentDecompile-Notifier/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if hasattr(exc, "read") else b""
    except Exception:  # noqa: BLE001
        return 0, b""


def _post_or_edit(hook: str, content: str, png: Path | None, key: str) -> dict:
    """One live corpus message: create once (remember id), then edit in place."""
    s = discord_notify.load_settings()
    mid = (s.get("message_ids") or {}).get(key)
    if mid:
        body, b = _multipart_body(content, png, reset_attachments=True)
        status, _ = _send(f"{hook}/messages/{mid}", "PATCH", body, b)
        if 200 <= status < 300:
            return {"ok": True, "status": status, "edited": True}
        if status != 404:
            return {"ok": False, "status": status}
    body, b = _multipart_body(content, png, reset_attachments=False)
    status, resp = _send(f"{hook}?wait=true", "POST", body, b)
    if 200 <= status < 300:
        try:
            new_id = json.loads(resp).get("id")
        except (ValueError, TypeError):
            new_id = None
        if new_id:
            ids = dict(s.get("message_ids") or {})
            ids[key] = new_id
            discord_notify.save_settings({"message_ids": ids})
        return {"ok": True, "status": status, "created": True}
    return {"ok": False, "status": status}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", required=True)
    args = ap.parse_args(argv)
    print(post_report(Path(args.work_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

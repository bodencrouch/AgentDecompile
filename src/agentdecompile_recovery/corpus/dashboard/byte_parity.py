"""Byte-parity / whole-image reconciliation panel for the static dashboard.

Surfaces the terminal-goal state for a binary in plain terms: whether a fresh
compiler-produced rebuilt image has a whole-file zero-difference receipt, how many functions are genuine
byte-exact recovered C vs still on the assembly floor, and the size of the
remaining byte-accuracy (permuter) queue. Reads the reconciliation report that
`finish_binary` writes and hashes the rebuilt/target images. No compute here --
it renders whatever the pipeline last produced.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

_REPORT_ENV = "AGENTDECOMPILE_RECONCILIATION_REPORT"
_DEFAULT_REPORT = "/home/brunner56/agentdecompile-nvme/k1gog-reconciliation.json"
_TARGET = "/home/brunner56/agentdecompile-nvme/k1gog-target/swkotor.exe"
_REBUILT = "/home/brunner56/agentdecompile-nvme/k1gog-target/rebuilt.exe"
_TEXT_PERMUTER_STATE = "/home/brunner56/agentdecompile-nvme/k1gog-text-permuter-state.json"
_FULL_IMAGE_RECEIPT_ENV = "AGENTDECOMPILE_FULL_IMAGE_RECEIPT"

# The variants report (matching-watch --out-report) lives under the corpus work
# dir; env override first, else discover the newest *.variants.json there.
_VARIANTS_ENV = "AGENT_DECOMPILE_VARIANTS_REPORT"


def _variants_report_path() -> str | None:
    p = os.environ.get(_VARIANTS_ENV)
    if p and Path(p).is_file():
        return p
    work = os.environ.get("AGENT_DECOMPILE_CORPUS_WORK_DIR", "").strip()
    if not work:
        return None
    reports = sorted(Path(work).glob("*.variants.json"),
                     key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True)
    return str(reports[0]) if reports else None


def variants_state() -> dict[str, Any]:
    """Both maintained build variants from the matching-watch variants report.

    byte_accurate: byte-exact C where proven, asm floor elsewhere -> exact-placement diagnostic.
    max_c:         any compiling C (byte-exact preferred) -> readable, not byte-identical.
    """
    path = _variants_report_path()
    try:
        doc = json.loads(Path(path).read_text()) if path else {}
    except (OSError, json.JSONDecodeError):
        doc = {}
    variants = doc.get("variants") or {}
    active = os.environ.get("AGENT_DECOMPILE_BUILD_VARIANT", "byte_accurate")
    return {
        "reportPath": path,
        "codeTotal": doc.get("code_total"),
        "receiptsPartial": bool(doc.get("receiptsPartial")),
        "activeVariant": active if active in ("byte_accurate", "max_c") else "byte_accurate",
        "byteAccurate": variants.get("byte_accurate"),
        "maxC": variants.get("max_c"),
    }


def _text_permuter_closed_count() -> int:
    """Functions the autonomous text-permuter (`corpus.text-permuter`) has
    closed since the reconciliation report was last generated. The report is
    a point-in-time snapshot from `finish_binary`; the permuter runs
    continuously via its dashboard `--watch` job, so its own progress has to
    be added on top rather than requiring a manual finish_binary re-run to
    see it reflected here."""
    try:
        state = json.loads(Path(_TEXT_PERMUTER_STATE).read_text())
        return len(state.get("closed") or {})
    except (OSError, json.JSONDecodeError):
        return 0


def _sha256(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _full_image_receipt() -> dict[str, Any]:
    """Return only a terminal receipt whose target still matches this dashboard."""
    path = os.environ.get(_FULL_IMAGE_RECEIPT_ENV, "").strip()
    if not path:
        return {}
    try:
        receipt = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    target = receipt.get("target") or {}
    valid = (
        receipt.get("schema") == "agentdecompile.full-image-compiler-objdiff-receipt.v1"
        and receipt.get("verified") is True
        and receipt.get("compilerProducedWholeImage") is True
        and receipt.get("wholeFileByteIdentical") is True
        and target.get("sha256") == _sha256(_TARGET)
    )
    return {"path": path, "valid": valid, "receipt": receipt} if valid else {}


def byte_parity_state() -> dict[str, Any]:
    report_path = os.environ.get(_REPORT_ENV) or _DEFAULT_REPORT
    report: dict[str, Any] = {}
    try:
        report = json.loads(Path(report_path).read_text())
    except (OSError, json.JSONDecodeError):
        report = {}

    target_hash = _sha256(_TARGET)
    rebuilt_hash = _sha256(_REBUILT)
    terminal = _full_image_receipt()
    total = int(report.get("totalFunctions") or 0)
    report_be = int(report.get("byteExactRecoveredC") or 0)
    # text-permuter closures are, by construction, addresses the reconciliation
    # report's verify pass had marked as mismatches (the permuter queue is
    # built from exactly those rows) -- additive, not double-counted.
    permuter_closed = _text_permuter_closed_count()
    be = report_be + permuter_closed

    # Prefer the fresh matching-watch variants report when present; the legacy
    # reconciliation report above is a point-in-time finish_binary snapshot.
    vstate = variants_state()
    ba = vstate.get("byteAccurate") or {}
    if vstate.get("codeTotal"):
        total = int(vstate["codeTotal"])
        be = int(ba.get("c") or be)

    return {
        "reportPath": report_path,
        "targetHash": target_hash,
        "rebuiltHash": rebuilt_hash,
        "exactPlacementHashEqual": bool(target_hash and rebuilt_hash and target_hash == rebuilt_hash),
        "fullImageReceiptPath": terminal.get("path"),
        "compilerProducedWholeImage": bool(terminal),
        "wholeImageByteIdentical": bool(terminal),
        "totalFunctions": total,
        "byteExactRecoveredC": be,
        "reportByteExactRecoveredC": report_be,
        "textPermuterClosed": permuter_closed,
        "coveragePct": round(100 * be / total, 2) if total else 0.0,
        "asmFloorRemainder": (total - be),
        # Both maintained build variants for the dashboard visual.
        "variants": {
            "byteAccurate": vstate.get("byteAccurate"),
            "maxC": vstate.get("maxC"),
            "active": vstate.get("activeVariant"),
            "receiptsPartial": vstate.get("receiptsPartial"),
            "reportPath": vstate.get("reportPath"),
        },
        "claimBoundary": (
            ("A fresh compiler plus object-level objdiff receipt and independent whole-file comparison verified this image. "
             if terminal else
             "The displayed exact-placement hash uses the original file and assembly-floor bytes; it is not "
             "a compiler-produced whole-image receipt. ") +
            "Coverage is functions reproduced from genuine recovered C rather "
            "than embedded original bytes (including live closures from the autonomous "
            "text-permuter search); the remainder is the byte-accuracy work queue."
        ),
    }


def render_byte_parity_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Byte parity — whole image</title>
<link rel="stylesheet" href="/dashboard/static/workbench-tokens.css">
<style>
  :root {
    --bg:#1e1f22; --bg-sunken:#141517; --surface:#2b2d30; --surface-raised:#3c3f41;
    --border:#4b4d50; --fg-max:#e6e6e6; --fg-body:#bbbbbb; --fg-head:#8c8c8c; --fg-dim:#6e6e6e;
    --accent:#4c78cc; --success:#5cba8a; --danger:#d36b5c;
    --font-ui:ui-sans-serif,"Segoe UI",Tahoma,system-ui,sans-serif;
    --font-mono:ui-monospace,"Cascadia Code","Consolas",monospace;
  }
  body{font:400 13px/1.5 var(--font-ui);margin:0;padding:24px;background:var(--bg-sunken);color:var(--fg-body);}
  h1{font:650 1.1rem/1.3 var(--font-ui);color:var(--fg-max);margin:0 0 4px;}
  .sub{color:var(--fg-head);margin:0 0 20px;}
  .hero{border:1px solid var(--border);border-radius:8px;padding:20px;background:var(--surface);margin-bottom:16px;}
  .verdict{font:650 1.4rem/1.2 var(--font-ui);}
  .verdict.ok{color:var(--success);} .verdict.no{color:var(--danger);}
  .hash{font-family:var(--font-mono);font-size:11px;color:var(--fg-dim);word-break:break-all;margin-top:6px;}
  .bar{height:22px;border-radius:6px;background:var(--bg-sunken);border:1px solid var(--border);overflow:hidden;margin:10px 0;}
  .bar>span{display:block;height:100%;background:var(--success);}
  .stat{display:flex;gap:24px;flex-wrap:wrap;margin-top:8px;}
  .stat b{color:var(--fg-max);font-size:1.3rem;}
  .stat .k{color:var(--fg-head);font-size:11px;text-transform:uppercase;letter-spacing:.04em;}
  .claim{margin-top:14px;font-size:12px;color:var(--fg-dim);}
  .vgrid{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
  @media(max-width:720px){.vgrid{grid-template-columns:1fr;}}
  .vcard{border:1px solid var(--border);border-radius:8px;padding:16px;background:var(--surface);}
  .vcard.active{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent);}
  .vtitle{font:650 1rem/1.2 var(--font-ui);color:var(--fg-max);margin:0 0 2px;}
  .vtag{font-size:11px;padding:2px 7px;border-radius:10px;margin-left:8px;vertical-align:middle;}
  .vtag.bi{background:rgba(92,186,138,.18);color:var(--success);}
  .vtag.nb{background:rgba(211,107,92,.18);color:var(--danger);}
  .vtag.act{background:rgba(76,120,204,.20);color:var(--accent);}
  .seg{display:flex;height:24px;border-radius:6px;overflow:hidden;border:1px solid var(--border);margin:12px 0 8px;}
  .seg>i{display:block;height:100%;}
  .seg .bx{background:var(--success);} .seg .rc{background:var(--accent);} .seg .sh{background:var(--fg-dim);}
  .legend{display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:var(--fg-head);}
  .legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:middle;}
  .vnote{margin-top:10px;font-size:11px;color:var(--fg-dim);}
</style>
</head>
<body>
<h1>Byte parity — whole image</h1>
<p class="sub">swkotor.exe rebuild vs shipped file. Updates every 5s.</p>
<div id="root"><p>Loading&hellip;</p></div>
<script>
async function refresh(){
  let d; try{ d=await (await fetch('/dashboard/api/byte-parity')).json(); }catch(e){ return; }
  const ok=d.wholeImageByteIdentical;
  const pct=d.coveragePct||0;
  document.getElementById('root').innerHTML=`
    <div class="hero">
      <div class="verdict ${ok?'ok':'no'}">${ok?'WHOLE IMAGE COMPILER RECEIPT VERIFIED ✓':'NO WHOLE-IMAGE COMPILER RECEIPT'}</div>
      <div class="hash">target : ${d.targetHash||'—'}</div>
      <div class="hash">rebuilt: ${d.rebuiltHash||'—'}</div>
    </div>
    <div class="hero">
      <div class="k">Recovered C (byte-exact) coverage</div>
      <div class="bar"><span style="width:${pct}%"></span></div>
      <div class="stat">
        <div><div class="k">byte-exact C</div><b>${d.byteExactRecoveredC}</b> / ${d.totalFunctions} (${pct}%)</div>
        <div><div class="k">asm-floor remainder</div><b>${d.asmFloorRemainder}</b></div>
        <div><div class="k">text-permuter live closures</div><b>${d.textPermuterClosed||0}</b></div>
      </div>
      <div class="claim">${d.claimBoundary}</div>
    </div>
    ${renderVariants(d.variants, d.totalFunctions)}`;
}
function renderVariants(v, total){
  if(!v || (!v.byteAccurate && !v.maxC)) return '';
  const ba=v.byteAccurate||{}, mc=v.maxC||{};
  const T=total||1;
  const pctW=n=>(100*(n||0)/T).toFixed(1)+'%';
  const active=v.active||'byte_accurate';
  const partial=v.receiptsPartial?' <span class="vnote">(verify pass in progress — numbers still rising)</span>':'';
  // byte-accurate: byte-exact C + shim ; max-c: byte-exact C + readable-only C + shim
  const baBar=`<div class="seg"><i class="bx" style="width:${pctW(ba.c)}"></i><i class="sh" style="width:${pctW(ba.shim)}"></i></div>`;
  const mcBar=`<div class="seg"><i class="bx" style="width:${pctW(mc.byte_exact_c)}"></i><i class="rc" style="width:${pctW(mc.readable_only_c)}"></i><i class="sh" style="width:${pctW(mc.shim)}"></i></div>`;
  return `
  <div class="hero">
    <div class="k">Build variants${partial}</div>
    <div class="vgrid" style="margin-top:12px;">
      <div class="vcard ${active==='byte_accurate'?'active':''}">
        <div class="vtitle">Byte-accurate<span class="vtag nb">assembly-floor diagnostic</span>${active==='byte_accurate'?'<span class="vtag act">active</span>':''}</div>
        ${baBar}
        <div class="legend"><span><i class="bx"></i>byte-exact C ${ba.c||0} (${ba.c_pct||0}%)</span><span><i class="sh"></i>asm shim ${ba.shim||0}</span></div>
        <div class="vnote">Byte-exact C where proven, original bytes elsewhere. Hash equality is exact placement, not a compiler-produced executable receipt.</div>
      </div>
      <div class="vcard ${active==='max_c'?'active':''}">
        <div class="vtitle">Max-C (readable)<span class="vtag nb">not byte-identical</span>${active==='max_c'?'<span class="vtag act">active</span>':''}</div>
        ${mcBar}
        <div class="legend"><span><i class="bx"></i>byte-exact C ${mc.byte_exact_c||0}</span><span><i class="rc"></i>readable-only C ${mc.readable_only_c||0}</span><span><i class="sh"></i>asm shim ${mc.shim||0}</span></div>
        <div class="vnote">Any compiling C (byte-exact preferred), asm shim only where no C compiles. More readable; not byte-identical.</div>
      </div>
    </div>
  </div>`;
}
refresh(); setInterval(refresh,5000);
</script>
</body>
</html>"""

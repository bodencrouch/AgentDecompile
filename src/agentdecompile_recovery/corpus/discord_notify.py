"""Discord webhook notifier: post plain-language progress hype to a server.

The webhook URL is a secret configured through the dashboard (Settings ->
Notifications), never hardcoded. Advancements (byte-exact milestones, a fresh
byte-identical build, a new exe) are posted in plain language with an ETA.
Posting is deduped so only real forward motion is announced, not every poll.

Settings live in a JSON file under the corpus work dir; the env var
AGENT_DECOMPILE_DISCORD_WEBHOOK overrides it for headless use.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def _settings_path() -> Path:
    root = os.environ.get("AGENT_DECOMPILE_CORPUS_WORK_DIR", "").strip()
    base = Path(root) if root else Path.home() / ".agentdecompile"
    base.mkdir(parents=True, exist_ok=True)
    return base / "notification_settings.json"


def load_settings() -> dict:
    p = _settings_path()
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(update: dict) -> dict:
    p = _settings_path()
    cur = load_settings()
    cur.update(update)
    p.write_text(json.dumps(cur, indent=1))
    try:
        os.chmod(p, 0o600)  # webhook is a secret
    except OSError:
        pass
    return cur


def _webhook() -> str | None:
    env = os.environ.get("AGENT_DECOMPILE_DISCORD_WEBHOOK", "").strip()
    if env:
        return env
    return (load_settings().get("discord_webhook") or "").strip() or None


_UA = "AgentDecompile-Notifier/1.0 (+https://claude.com/claude-code)"


def _http(url: str, method: str, payload: bytes) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=payload, method=method, headers={
        "Content-Type": "application/json", "User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if hasattr(exc, "read") else b""
    except Exception:  # noqa: BLE001
        return 0, b""


def post(content: str, *, key: str | None = None) -> dict:
    """Post a message. With `key`, edit that keyed message in place instead of
    sending a new one (a single live, updating message per key). Never raises."""
    hook = _webhook()
    if not hook:
        return {"ok": False, "reason": "no webhook configured"}
    payload = json.dumps({"content": content[:1900]}).encode()
    if key:
        s = load_settings()
        msg_id = (s.get("message_ids") or {}).get(key)
        if msg_id:
            status, _ = _http(f"{hook}/messages/{msg_id}", "PATCH", payload)
            if 200 <= status < 300:
                return {"ok": True, "status": status, "edited": True}
            if status != 404:  # 404 = message gone; fall through to re-post
                return {"ok": False, "status": status}
        # create with ?wait=true so Discord returns the message id to remember
        status, body = _http(f"{hook}?wait=true", "POST", payload)
        if 200 <= status < 300:
            try:
                mid = json.loads(body).get("id")
            except (ValueError, TypeError):
                mid = None
            if mid:
                ids = dict(s.get("message_ids") or {})
                ids[key] = mid
                save_settings({"message_ids": ids})
            return {"ok": True, "status": status, "created": True}
        return {"ok": False, "status": status}
    status, _ = _http(hook, "POST", payload)
    return {"ok": 200 <= status < 300, "status": status}


def _fmt_eta(be: int, total: int, per_hour: float | None) -> str:
    remaining = max(total - be, 0)
    if not per_hour or per_hour <= 0:
        return "ETA: gathering rate…"
    hours = remaining / per_hour
    if hours < 48:
        return f"ETA at current rate: ~{hours:.0f}h to full coverage"
    days = hours / 24
    if days < 60:
        return f"ETA at current rate: ~{days:.0f} days to full coverage"
    return "ETA: months+ (the hard tail needs manual work — honest estimate)"


def announce_progress(*, program: str, byte_exact: int, total: int,
                      byte_identical: bool, min_delta: int = 25) -> dict:
    """Post a hype line iff byte_exact advanced by >= min_delta since last post.

    Tracks the last-announced count + timestamp in settings to compute rate and
    dedupe. Returns {posted: bool, ...}.
    """
    s = load_settings()
    last = int(s.get("last_announced_byte_exact") or 0)
    delta = byte_exact - last
    now = time.time()
    # We edit one message in place (no spam), so refresh every pass for a live
    # heartbeat -- even a plateau should visibly tick. Rate is measured only
    # between points where the count actually moved, so ETA stays meaningful.
    last_move_t = float(s.get("last_move_time") or s.get("last_announced_time") or 0)
    last_move_v = int(s.get("last_move_value") or last)
    per_hour = None
    if delta > 0 and last_move_t and now > last_move_t:
        per_hour = (byte_exact - last_move_v) / ((now - last_move_t) / 3600.0)
    elif s.get("rate_per_hour"):
        per_hour = float(s["rate_per_hour"])  # keep last known rate during a plateau
    pct = 100 * byte_exact / max(total, 1)
    bar_n = int(pct / 5)
    bar = "█" * bar_n + "░" * (20 - bar_n)
    seal = "✅ byte-identical build verified" if byte_identical else "⚠️ build not byte-identical"
    headline = ("🚀 **{p}** — byte-accurate decompilation" if delta > 0
                else "⏳ **{p}** — grinding the hard tail").format(p=program)
    since = f"+{delta:,} since last move" if delta > 0 else "no new byte-exact this cycle"
    msg = (
        f"{headline}\n"
        f"**{byte_exact:,}** functions compiled from real recovered C — **{pct:.1f}%** "
        f"of {total:,} ({since}).\n"
        f"`{bar}` {pct:.1f}%\n"
        f"{seal}. {_fmt_eta(byte_exact, total, per_hour)}\n"
        f"_live · updated <t:{int(now)}:R>_"
    )
    res = post(msg, key="progress")
    if not res.get("ok"):
        return {"posted": False, "reason": res.get("reason")}
    upd = {"last_announced_byte_exact": byte_exact, "last_announced_time": now}
    if per_hour:
        upd["rate_per_hour"] = per_hour
    if delta > 0:  # remember the last real move for rate math across plateaus
        upd["last_move_time"] = now
        upd["last_move_value"] = byte_exact
    save_settings(upd)
    return {"posted": True, "delta": delta, "per_hour": per_hour, "heartbeat": delta == 0}

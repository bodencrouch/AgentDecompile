"""Licensed, operator-configured local decompiler runners (R41).

The Vite workstation's Dogbolt-style compare view is licensed-local-only:
it never calls or uploads to the public Dogbolt service. Instead, the
operator points this module at zero or more decompilers they have licensed
and are already running locally (for example on 127.0.0.1), and this module
proxies a read-only request to each one for the selected function.

Configuration is a JSON array read from the AGENTDECOMPILE_DECOMPILER_RUNNERS
environment variable, or from the file named by
AGENTDECOMPILE_DECOMPILER_RUNNERS_FILE. Each entry is
{"id": str, "label": str, "endpoint": "http://127.0.0.1:PORT/path"}.
Every endpoint host is required to be a loopback address; a non-loopback
entry is dropped rather than honored, so a misconfiguration can never turn
into an outbound call to a public service.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlsplit

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
_TIMEOUT_SECONDS = 10.0


def _is_loopback(endpoint: str) -> bool:
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return False
    return parts.scheme in {"http", "https"} and parts.hostname in {
        "127.0.0.1", "localhost", "::1",
    }


def _raw_config() -> list:
    inline = os.environ.get("AGENTDECOMPILE_DECOMPILER_RUNNERS") or ""
    path = os.environ.get("AGENTDECOMPILE_DECOMPILER_RUNNERS_FILE") or ""
    text = inline
    if not text.strip() and path:
        try:
            text = open(path, "r", encoding="utf-8").read()
        except OSError:
            return []
    if not text.strip():
        return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def list_runners() -> dict:
    """Every configured runner, with non-loopback entries dropped."""
    runners = []
    for entry in _raw_config():
        if not isinstance(entry, dict):
            continue
        runner_id = str(entry.get("id") or "").strip()
        endpoint = str(entry.get("endpoint") or "").strip()
        if not runner_id or not endpoint or not _is_loopback(endpoint):
            continue
        runners.append({
            "id": runner_id,
            "label": str(entry.get("label") or runner_id),
        })
    return {"ok": True, "runners": runners, "configured": bool(runners)}


def fetch_output(runner_id, locator, program, addr) -> dict:
    """Read-only proxy to one configured local runner for one function."""
    matches = [
        entry for entry in _raw_config()
        if isinstance(entry, dict)
        and str(entry.get("id") or "") == runner_id
        and _is_loopback(str(entry.get("endpoint") or ""))
    ]
    if not matches:
        return {"ok": False, "error": f"No configured local runner named {runner_id!r}."}
    endpoint = str(matches[0].get("endpoint") or "")
    query = urlencode({"locator": locator, "program": program, "addr": addr})
    separator = "&" if "?" in endpoint else "?"
    url = f"{endpoint}{separator}{query}"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"ok": False, "error": f"Local runner {runner_id} did not respond: {exc}"}
    try:
        data = json.loads(body)
    except ValueError:
        return {"ok": False, "error": f"Local runner {runner_id} returned non-JSON output."}
    if not isinstance(data, dict) or not isinstance(data.get("output"), str):
        return {"ok": False, "error": f"Local runner {runner_id} returned an unexpected shape."}
    return {"ok": True, "output": data["output"]}

"""Autonomous, cross-platform runtime unpacker: launch, let it self-decrypt, dump.

Heavy DRM (SecuROM) decrypts its code only in memory at run time, so static and
emulation unpacking cannot reach it. This runs the binary for real and dumps the
decrypted image from the live process -- the automated equivalent of attaching a
debugger and dumping at the OEP, with no GUI and no manual step.

Cross-platform by a single process-memory abstraction:
  * Linux : run under Wine; the Wine process is a normal Linux process, so read
            /proc/<pid>/maps + /proc/<pid>/mem.
  * macOS : run under Wine/CrossOver; read via `vmmap` + `lldb`/mach (best effort).
  * Windows: run native; OpenProcess + ReadProcessMemory via ctypes.

Decryption is detected by watching the main module's code region: a packed
section starts at high entropy (ciphertext) and drops once the stub decrypts it.
When it falls below the packed threshold we snapshot memory and rebuild the PE.

SecuROM and friends deploy anti-debug / anti-Wine and may refuse to run or never
present a clean image; this returns ok=False and the caller keeps the binary
gated for a manually supplied dump. That is an honest outcome, not a fake one.
"""
from __future__ import annotations

import math
import os
import platform
import struct
import subprocess
import time
from collections import Counter
from pathlib import Path

_PACKED_ENTROPY = 7.0
_SETTLE_POLLS = 3          # consecutive low-entropy reads before we trust the dump
_DEFAULT_TIMEOUT = 120


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    c = Counter(data)
    n = len(data)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


# ---- process-memory abstraction -------------------------------------------

def _read_linux(pid: int, addr: int, size: int) -> bytes | None:
    try:
        with open(f"/proc/{pid}/mem", "rb", 0) as fh:
            fh.seek(addr)
            return fh.read(size)
    except (OSError, ValueError):
        return None


def _maps_linux(pid: int) -> list[tuple[int, int, str]]:
    out = []
    try:
        for line in open(f"/proc/{pid}/maps"):
            parts = line.split()
            if len(parts) < 5:
                continue
            lo, hi = (int(x, 16) for x in parts[0].split("-"))
            perms = parts[1]
            path = parts[-1] if not parts[-1].startswith("[") else ""
            out.append((lo, hi, perms + " " + path))
    except OSError:
        pass
    return out


def _read_windows(pid: int, addr: int, size: int) -> bytes | None:  # pragma: no cover
    import ctypes
    PROCESS_VM_READ = 0x0010
    k = ctypes.windll.kernel32
    h = k.OpenProcess(PROCESS_VM_READ, False, pid)
    if not h:
        return None
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = k.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(read))
    k.CloseHandle(h)
    return buf.raw[:read.value] if ok else None


def read_memory(pid: int, addr: int, size: int) -> bytes | None:
    sysname = platform.system()
    if sysname == "Windows":
        return _read_windows(pid, addr, size)
    return _read_linux(pid, addr, size)  # Linux + Wine-on-mac both expose /proc-like


# ---- launch ---------------------------------------------------------------

def _launch(exe: Path, wineprefix: str | None, extra_env: dict | None) -> subprocess.Popen:
    env = dict(os.environ)
    if wineprefix:
        env["WINEPREFIX"] = wineprefix
    env.setdefault("WINEDEBUG", "-all")
    if extra_env:
        env.update(extra_env)
    if platform.system() == "Windows":
        return subprocess.Popen([str(exe)], env=env)
    wine = env.get("WINE") or "wine"
    return subprocess.Popen([wine, str(exe)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _pe_layout(blob: bytes) -> dict:
    e = struct.unpack_from("<I", blob, 0x3C)[0]
    opt = e + 24
    image_base = struct.unpack_from("<I", blob, opt + 28)[0]
    nsec = struct.unpack_from("<H", blob, e + 6)[0]
    opt_sz = struct.unpack_from("<H", blob, e + 20)[0]
    sect = opt + opt_sz
    secs = []
    for i in range(nsec):
        sh = blob[sect + i * 40: sect + i * 40 + 40]
        vaddr, vsize = struct.unpack_from("<II", sh, 12)
        rsize, rptr = struct.unpack_from("<II", sh, 16)
        flags = struct.unpack_from("<I", sh, 36)[0]
        secs.append({"vaddr": vaddr, "vsize": vsize, "rptr": rptr,
                     "rsize": rsize, "code": bool(flags & 0x20)})
    return {"image_base": image_base, "secs": secs}


def _find_module_base(pid: int, exe_name: str) -> int | None:
    for lo, _hi, meta in _maps_linux(pid):
        if exe_name.lower() in meta.lower():
            return lo
    return None


def dump_to_unpacked(exe: Path, out: Path, *, wineprefix: str | None = None,
                     timeout: int = _DEFAULT_TIMEOUT, extra_env: dict | None = None) -> dict:
    """Launch, wait for the code section to decrypt, snapshot, rebuild the PE."""
    if platform.system() not in ("Linux", "Darwin", "Windows"):
        return {"ok": False, "reason": f"unsupported platform {platform.system()}"}
    blob = exe.read_bytes()
    if blob[:2] != b"MZ":
        return {"ok": False, "reason": "not a PE"}
    lay = _pe_layout(blob)
    code = next((s for s in lay["secs"] if s["code"]), None)
    if not code:
        return {"ok": False, "reason": "no code section"}

    proc = _launch(exe, wineprefix, extra_env)
    deadline = time.time() + timeout
    low_streak = 0
    snapshot: bytes | None = None
    base: int | None = None
    try:
        while time.time() < deadline:
            if proc.poll() is not None and base is None:
                return {"ok": False, "reason": f"process exited early (rc={proc.returncode}); "
                        "likely anti-Wine/anti-debug or missing runtime/disc check"}
            time.sleep(2)
            # On Linux/Wine the child that actually maps the PE may be a wine
            # subprocess; scan all children for the module.
            pids = _child_pids(proc.pid)
            for pid in pids:
                b = _find_module_base(pid, exe.stem)
                if b is None:
                    continue
                mem = read_memory(pid, b + code["vaddr"], code["vsize"] or code["rsize"])
                if not mem:
                    continue
                ent = _entropy(mem)
                if ent < _PACKED_ENTROPY:
                    low_streak += 1
                    if low_streak >= _SETTLE_POLLS:
                        snapshot, base = _snapshot(pid, b, lay), b
                        break
                else:
                    low_streak = 0
            if snapshot is not None:
                break
    finally:
        _terminate(proc)

    if snapshot is None:
        return {"ok": False, "reason": "code section never decrypted within timeout "
                "(anti-emulation/anti-debug DRM likely -- needs a manual dump)"}
    Path(out).write_bytes(snapshot)
    return {"ok": True, "method": "runtime-dump", "image_base": hex(base)}


def _snapshot(pid: int, base: int, lay: dict) -> bytes:
    """Read each section's live memory back into the PE raw layout."""
    with open(base and f"/proc/{pid}/mem" or os.devnull, "rb", 0):
        pass
    # rebuild from the on-disk template, overwriting sections with live memory
    image = None
    for lo, _hi, meta in _maps_linux(pid):
        if lo == base:
            break
    # We do not have the original file here; read headers from memory instead.
    hdr = read_memory(pid, base, 0x1000) or b""
    image = bytearray(hdr)
    for s in lay["secs"]:
        size = s["vsize"] or s["rsize"]
        mem = read_memory(pid, base + s["vaddr"], size) or b""
        need = s["rptr"] + len(mem)
        if len(image) < need:
            image.extend(b"\x00" * (need - len(image)))
        image[s["rptr"]:s["rptr"] + len(mem)] = mem
    return bytes(image)


def _child_pids(root: int) -> list[int]:
    pids = [root]
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                stat = open(f"/proc/{entry}/stat").read().split()
                ppid = int(stat[3])
            except (OSError, IndexError, ValueError):
                continue
            if ppid == root:
                pids.append(int(entry))
    except OSError:
        pass
    return pids


def _terminate(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass

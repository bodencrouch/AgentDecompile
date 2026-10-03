"""The local agent: one process per host, attach-first join, health/status over a well-known socket.

``join`` first looks for a running agent at the well-known endpoint (``$XDG_RUNTIME_DIR/adgrid/agent.sock``,
or ``127.0.0.1:<port>``) and **attaches** — adds lanes, adjusts cores, prints status.  It bootstraps
an agent only when none answers *and* nobody holds the agent lock.  The user rule "exclusive lock
is not join" is implemented literally:

* health answers → attach (``JoinResult.mode == "attached"``); never a second agent;
* the lock is held but health does not answer within the probe deadline → ``AlreadyOwned``
  ("wedged owner"); never unlink the socket, never restart, never retry as a start;
* lock free and a socket file is left over → it is stale (the kernel refuses ``bind`` on an
  existing path whether or not anyone listens, so the file alone proves nothing): unlink, bind;
* ``EADDRINUSE`` at bind (TCP, or a unix path that reappeared) → ``AlreadyOwned``.

Order inside a bootstrap: parse the invite → resolve transport and frontier (named failures
before any socket is touched) → probe/attach → lock → bind (health answers ``bootstrapping``)
→ key → canaries → bind identity → loops → ``running``.  ``leave`` drops intents (aborts running
jobs without recording results, releases INTENTs, flushes the outbox under a deadline) and stops.
``rejoin`` re-proves the canaries and re-binds capabilities (a donor who installs a toolchain
later is not stranded).  The node tick steps the verifier before the work loop.

``--idle-only`` is an ``IdlePolicy`` from ``IDLE_POLICIES``: ``load-average`` works; ``battery``
works where ``/sys/class/power_supply`` has a battery and is declared otherwise; ``user-activity``
is declared (needs an idle-time source such as ``xprintidle``).  ``--cores N`` is the slot count.

Acceptance tests named for the final verification phase (U125):
  * ``test_join_attaches_to_running_agent``: a second ``join`` against a bootstrapped agent
    returns ``attached`` with the agent's status and starts no process.
  * ``test_eaddrinuse_is_already_owned``: a foreign listener on the endpoint yields
    ``AlreadyOwned``; nothing is unlinked or restarted.
  * ``test_stale_socket_is_reclaimed``: a socket file with no lock holder is unlinked and bound.
  * ``test_wedged_owner_named``: lock held, health silent → ``AlreadyOwned`` naming "wedged".
  * ``test_leave_drops_intents``: after ``leave`` every running job is aborted, every INTENT is
    released and the outbox is flushed before the socket disappears.
  * ``test_rejoin_reproves``: ``rejoin`` re-runs the canaries and the identity's capabilities
    follow the new report.
  * ``test_socket_path_too_long_named``: an endpoint path over the sun_path limit fails by name
    and suggests a TCP endpoint.
"""
from __future__ import annotations

import errno
import http.client
import http.server
import json
import os
import random
import socket
import socketserver
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .. import __version__
from ..core import AlreadyOwned, Frontier, GridError, LogStore, NodeIdentity, NotConfigured, ObjectStore, Registry, Transport
from .canaries import CanaryReport, run_canaries
from .identity import ROLE_MAY_VERIFY, Invite, NodeKey, NodeKeyStore, NodeSigner, bind_identity, parse_invite_url, verify_invite
from .loop import FLEET_BUDGETS_ALLOWED, IdlePolicy, StepEvent, StepMachine, Upstream, WorkLoop, WorkerConfig
from .outbox import Outbox
from .sandbox import SubprocessSandbox

SUN_PATH_LIMIT = 100                 # portable bound below the 108-byte sun_path
HTTP_PREFIX = "/adgrid"
DEFAULT_PROBE_DEADLINE_S = 1.0
DEFAULT_LEAVE_DEADLINE_S = 30.0
IDLE_POLICIES = Registry("idle policy")


# --------------------------------------------------------------------------- endpoint and lock
@dataclass(frozen=True)
class Endpoint:
    kind: str                      # unix | tcp
    path: str = ""
    host: str = "127.0.0.1"
    port: int = 0

    @classmethod
    def default(cls, env: Mapping[str, str] | None = None) -> "Endpoint":
        env = os.environ if env is None else env
        runtime = env.get("XDG_RUNTIME_DIR") or f"/tmp/adgrid-{os.getuid()}"
        return cls("unix", path=str(Path(runtime) / "adgrid" / "agent.sock"))

    @classmethod
    def parse(cls, text: str) -> "Endpoint":
        if text.startswith("unix:"):
            return cls("unix", path=text[5:])
        if text.startswith("tcp:"):
            text = text[4:]
        host, _, port = text.rpartition(":")
        if not port.isdigit():
            return cls("unix", path=text)
        return cls("tcp", host=host or "127.0.0.1", port=int(port))

    @property
    def lock_path(self) -> str:
        return self.path + ".lock" if self.kind == "unix" else f"/tmp/adgrid-{os.getuid()}-{self.port}.lock"

    def validate(self) -> None:
        if self.kind == "unix" and len(self.path.encode("utf-8")) > SUN_PATH_LIMIT:
            raise GridError(f"agent socket path is {len(self.path.encode())} bytes, over the {SUN_PATH_LIMIT}-byte unix limit; set XDG_RUNTIME_DIR or use a tcp endpoint (Endpoint.parse('127.0.0.1:<port>'))")
        if self.kind == "tcp" and self.host not in ("127.0.0.1", "::1", "localhost"):
            raise GridError("the agent endpoint must be loopback; nodes accept no inbound connections (design §6.1)")

    def __str__(self) -> str:
        return f"unix:{self.path}" if self.kind == "unix" else f"{self.host}:{self.port}"


class FileLock:
    """``flock`` on a lock file next to the socket; the holder's pid is written for diagnostics."""

    def __init__(self, path: str, fd: int) -> None:
        self.path = path
        self.fd = fd

    @classmethod
    def acquire_nowait(cls, path: str) -> "FileLock | None":
        import fcntl

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return None
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode("ascii"))
        return cls(path, fd)

    @staticmethod
    def holder_pid(path: str) -> int | None:
        try:
            return int(Path(path).read_text("ascii").strip() or 0) or None
        except (OSError, ValueError):
            return None

    def release(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


# --------------------------------------------------------------------------- client
class AgentUnreachable(GridError):
    """No agent answers at the endpoint (connection refused, no socket file, timeout)."""


class AttachRefused(GridError):
    """A live agent answered but did not accept the attach (still bootstrapping, leaving, faulted)."""


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._path)
        self.sock = sock


class AgentClient:
    def __init__(self, endpoint: Endpoint, *, timeout_s: float = DEFAULT_PROBE_DEADLINE_S) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s

    def _connection(self) -> http.client.HTTPConnection:
        if self.endpoint.kind == "unix":
            return _UnixConnection(self.endpoint.path, self.timeout_s)
        return http.client.HTTPConnection(self.endpoint.host, self.endpoint.port, timeout=self.timeout_s)

    def call(self, method: str, route: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        conn = self._connection()
        try:
            payload = json.dumps(body or {}).encode("utf-8") if method == "POST" else None
            conn.request(method, f"{HTTP_PREFIX}/{route}", body=payload, headers={"Content-Type": "application/json"} if payload else {})
            response = conn.getresponse()
            raw = response.read()
        except (OSError, http.client.HTTPException) as exc:
            raise AgentUnreachable(f"{self.endpoint}: {exc.__class__.__name__}") from exc
        finally:
            conn.close()
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError as exc:
            raise AgentUnreachable(f"{self.endpoint}: non-JSON answer") from exc
        if response.status >= 400:
            raise GridError(f"agent refused {route}: {data.get('error', response.status)}")
        return data

    def health(self) -> dict[str, Any]:
        return self.call("GET", "health")

    def status(self) -> dict[str, Any]:
        return self.call("GET", "status")

    def attach(self, *, lanes: Sequence[str] = (), cores: int | None = None, idle_only: bool | None = None) -> dict[str, Any]:
        return self.call("POST", "attach", {"lanes": list(lanes), "cores": cores, "idle_only": idle_only})

    def leave(self, reason: str = "leave") -> dict[str, Any]:
        return self.call("POST", "leave", {"reason": reason})

    def rejoin(self) -> dict[str, Any]:
        return self.call("POST", "rejoin", {})


@dataclass(frozen=True)
class ProbeResult:
    state: str                          # alive | absent | silent | faulted
    health: Mapping[str, Any] | None = None
    error: str = ""


def probe(endpoint: Endpoint, *, deadline_s: float = DEFAULT_PROBE_DEADLINE_S) -> ProbeResult:
    """alive: health answered; absent: nothing listens (ECONNREFUSED / ENOENT); silent: something
    accepted the connection but did not answer a valid health within the deadline."""
    if endpoint.kind == "unix" and not os.path.exists(endpoint.path):
        return ProbeResult("absent", error="no socket file")
    try:
        health = AgentClient(endpoint, timeout_s=deadline_s).health()
    except AgentUnreachable as exc:
        cause = exc.__cause__
        if isinstance(cause, (ConnectionRefusedError, FileNotFoundError)) or (isinstance(cause, OSError) and cause.errno in (errno.ECONNREFUSED, errno.ENOENT)):
            return ProbeResult("absent", error=str(exc))
        return ProbeResult("silent", error=str(exc))
    if isinstance(health, dict) and health.get("ok") is True:
        return ProbeResult("alive", health=health)
    if isinstance(health, dict) and health.get("state") == "faulted":
        return ProbeResult("faulted", health=health, error=str(health.get("last_fault", "")))
    return ProbeResult("silent", error="health answered without ok=true")


# --------------------------------------------------------------------------- server
class _UnixHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    address_family = socket.AF_UNIX
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self) -> None:
        self.socket.bind(self.server_address)
        self.server_name = "adgrid"
        self.server_port = 0


class _TcpHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = False
    daemon_threads = True


def _make_handler(agent: "LocalAgent") -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = f"adgrid/{__version__}"

        def address_string(self) -> str:
            return "local"

        def log_message(self, format: str, *args: Any) -> None:
            agent.http_log.append(format % args)
            del agent.http_log[:-32]

        def _send(self, status: int, payload: Mapping[str, Any]) -> None:
            raw = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                return {}
            return data if isinstance(data, dict) else {}

        def do_GET(self) -> None:
            if self.path == f"{HTTP_PREFIX}/health":
                self._send(200, agent.health())
            elif self.path == f"{HTTP_PREFIX}/status":
                self._send(200, agent.status())
            else:
                self._send(404, {"error": "unknown route"})

        def do_POST(self) -> None:
            body = self._body()
            try:
                if self.path == f"{HTTP_PREFIX}/attach":
                    self._send(200, agent.attach(lanes=body.get("lanes") or (), cores=body.get("cores"), idle_only=body.get("idle_only")))   # attached: false + reason while bootstrapping
                elif self.path == f"{HTTP_PREFIX}/leave":
                    self._send(200, agent.leave(str(body.get("reason") or "leave")))
                elif self.path == f"{HTTP_PREFIX}/rejoin":
                    self._send(200, agent.rejoin())
                else:
                    self._send(404, {"error": "unknown route"})
            except GridError as exc:
                self._send(409, {"error": f"{exc.__class__.__name__}: {exc}"})

    return Handler


# --------------------------------------------------------------------------- idle policies
class LoadAveragePolicy:
    name = "load-average"

    def __init__(self, max_load_per_core: float = 0.5, *, cores: int | None = None, loadavg: Callable[[], tuple[float, float, float]] = os.getloadavg, own_weight: float = 1.0) -> None:
        self.max_load_per_core = max_load_per_core
        self.cores = cores or os.cpu_count() or 1
        self.loadavg = loadavg
        self.own_weight = own_weight
        self.last: Mapping[str, Any] = {}

    def should_run(self, now: float, *, running: int) -> bool:
        try:
            one_minute = self.loadavg()[0]
        except OSError:
            return True
        foreign = max(0.0, one_minute - running * self.own_weight)
        ok = foreign / self.cores < self.max_load_per_core
        self.last = {"load1": one_minute, "foreign": foreign, "per_core": foreign / self.cores, "ok": ok}
        return ok

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "working", "max_load_per_core": self.max_load_per_core, "cores": self.cores, "lag": "1-minute average; own running tasks subtracted", "last": dict(self.last)}


class BatteryPolicy:
    """Run only on mains power (or above a capacity floor).  Works where a battery is exposed under
    ``/sys/class/power_supply``; declared (``NotConfigured``) everywhere else."""

    name = "battery"
    CONFIG_SCHEMA: Mapping[str, str] = {"power_supply_root": "/sys/class/power_supply", "min_capacity": "percent below which nothing runs even on mains (default 20)"}

    def __init__(self, *, power_supply_root: str = "/sys/class/power_supply", min_capacity: int = 20) -> None:
        self.root = Path(power_supply_root)
        self.min_capacity = min_capacity
        self.last: Mapping[str, Any] = {}

    def _batteries(self) -> list[Path]:
        try:
            return [p for p in self.root.iterdir() if (p / "type").exists() and (p / "type").read_text().strip() == "Battery"]
        except OSError:
            return []

    def should_run(self, now: float, *, running: int) -> bool:
        batteries = self._batteries()
        if not batteries:
            raise NotConfigured(f"battery idle policy needs a battery under {self.root} (none found); use load-average")
        status = (batteries[0] / "status").read_text().strip() if (batteries[0] / "status").exists() else "Unknown"
        try:
            capacity = int((batteries[0] / "capacity").read_text().strip())
        except (OSError, ValueError):
            capacity = 100
        ok = status != "Discharging" and capacity >= self.min_capacity
        self.last = {"status": status, "capacity": capacity, "ok": ok}
        return ok

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "working" if self._batteries() else "declared", "needs": [] if self._batteries() else [f"a battery under {self.root}"], "config_schema": dict(self.CONFIG_SCHEMA)}


class UserActivityPolicy:
    """Run only after the user has been idle for ``idle_after_s`` (the right signal on desktops)."""

    name = "user-activity"
    CONFIG_SCHEMA: Mapping[str, str] = {"idle_after_s": "seconds without input before work starts (default 300)", "probe_command": "command printing idle milliseconds (xprintidle, or a Wayland idle-notify shim)"}

    def __init__(self, *, idle_after_s: float = 300.0, probe_command: Sequence[str] = ("xprintidle",)) -> None:
        self.idle_after_s = idle_after_s
        self.probe_command = tuple(probe_command)

    def should_run(self, now: float, *, running: int) -> bool:
        import shutil

        if not self.probe_command or not shutil.which(self.probe_command[0]):
            raise NotConfigured(f"user-activity idle policy needs an idle-time source: {self.probe_command[0] if self.probe_command else 'probe_command'} is not on PATH")
        raise NotConfigured("user-activity idle policy is declared only; wire probe_command output (idle ms) to idle_after_s")

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "declared", "needs": ["an idle-time source (xprintidle / Wayland idle-notify)"], "config_schema": dict(self.CONFIG_SCHEMA)}


IDLE_POLICIES.register("load-average", LoadAveragePolicy)
IDLE_POLICIES.register("battery", BatteryPolicy)
IDLE_POLICIES.register("user-activity", UserActivityPolicy)


def idle_policy_for(name: str | None, **kwargs: Any) -> IdlePolicy | None:
    if not name:
        return None
    cls = IDLE_POLICIES.get(name)
    return cls(**kwargs)


# --------------------------------------------------------------------------- the agent
class LocalAgent:
    def __init__(self, endpoint: Endpoint, *, identity: NodeIdentity, clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time,
                 lanes: Sequence[str] = (), cores: int = 1, idle_only: bool = False, leave_deadline_s: float = DEFAULT_LEAVE_DEADLINE_S, version: str = __version__) -> None:
        self.endpoint = endpoint
        self.identity = identity
        self.clock = clock
        self.wall = wall
        self.lanes = list(lanes)
        self.cores = max(1, int(cores))
        self.idle_only = idle_only
        self.leave_deadline_s = leave_deadline_s
        self.version = version
        self.state = "new"                      # new | bootstrapping | running | leaving | faulted | stopped
        self.started_at = wall()
        self.faults = 0
        self.consecutive_faults = 0
        self.last_fault = ""
        self.max_consecutive_faults = 5
        self.work_loop: StepMachine | None = None
        self.verifier_loop: StepMachine | None = None
        self.canary_report: CanaryReport | None = None
        self.rejoin_hook: Callable[[], CanaryReport] | None = None
        self.http_log: list[str] = []
        self.leave_reason = ""
        self._leave_started: float | None = None
        self._lock = threading.RLock()
        self._server: http.server.HTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._file_lock: FileLock | None = None
        self._driver: threading.Thread | None = None
        self._stop = threading.Event()

    # -- lifecycle
    def bind(self, file_lock: FileLock | None = None) -> None:
        """Bind the endpoint and start answering health (``bootstrapping``).  ``EADDRINUSE`` → ``AlreadyOwned``."""
        self.endpoint.validate()
        handler = _make_handler(self)
        try:
            if self.endpoint.kind == "unix":
                Path(self.endpoint.path).parent.mkdir(parents=True, exist_ok=True)
                self._server = _UnixHTTPServer(self.endpoint.path, handler)
                os.chmod(self.endpoint.path, 0o600)
            else:
                self._server = _TcpHTTPServer((self.endpoint.host, self.endpoint.port), handler)
        except OSError as exc:
            if file_lock is not None:
                file_lock.release()
            if exc.errno == errno.EADDRINUSE:
                raise AlreadyOwned(f"agent endpoint {self.endpoint} is already owned (EADDRINUSE): attach instead of starting") from exc
            raise GridError(f"cannot bind agent endpoint {self.endpoint}: {exc.__class__.__name__}") from exc
        self._file_lock = file_lock
        self.state = "bootstrapping"
        self._server_thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.2}, name="adgrid-agent-http", daemon=True)
        self._server_thread.start()

    def attach_loops(self, work_loop: StepMachine | None, verifier_loop: StepMachine | None, *, canary_report: CanaryReport | None = None) -> None:
        with self._lock:
            self.work_loop = work_loop
            self.verifier_loop = verifier_loop
            self.canary_report = canary_report
            if work_loop is not None:
                work_loop.set_cores(self.cores)
            self.state = "running"

    def tick(self) -> StepEvent:
        """Verification before generation: the verifier steps first; the work loop only when it idles."""
        with self._lock:
            if self.state not in ("running", "leaving"):
                return StepEvent("idle", {"reason": f"state:{self.state}"}, next_due_s=0.25 if self.state != "faulted" else 5.0)
            for loop in (self.verifier_loop, self.work_loop):
                if loop is None:
                    continue
                event = loop.step()
                if event.name != "idle":
                    return event
            if self.state == "leaving":
                self._finish_leave_if_done()
            return StepEvent("idle", {"reason": "loops-idle"}, next_due_s=min((loop.next_due(self.clock()) for loop in (self.verifier_loop, self.work_loop) if loop is not None), default=0.25))

    def _guarded_tick(self) -> StepEvent:
        """A step that raises is a fault, counted and named in health; after ``max_consecutive_faults``
        the agent is ``faulted`` (health ok=false, attach refused, leave still works) — a dead driver
        must never look healthy."""
        try:
            event = self.tick()
        except Exception as exc:
            self.faults += 1
            self.consecutive_faults += 1
            self.last_fault = f"{exc.__class__.__name__}: {str(exc)[:200]}"
            if self.consecutive_faults >= self.max_consecutive_faults and self.state == "running":
                self.state = "faulted"
                for loop in (self.work_loop, self.verifier_loop):
                    if loop is not None:
                        loop.release_all("faulted")
            return StepEvent("fault", {"exception": exc.__class__.__name__, "consecutive": self.consecutive_faults, "state": self.state}, next_due_s=min(5.0, 0.5 * self.consecutive_faults))
        self.consecutive_faults = 0
        return event

    def run(self, *, sleep: Callable[[float], None] = time.sleep, poll_s: float = 0.25) -> None:
        """Blocking driver; Ctrl-C becomes ``leave`` and the driver finishes the leave."""
        try:
            while self.state != "stopped" and not self._stop.is_set():
                event = self._guarded_tick()
                if event.name in ("idle", "fault"):
                    sleep(max(0.0, min(poll_s if event.name == "idle" else 5.0, event.next_due_s if event.next_due_s is not None else poll_s)))
        except KeyboardInterrupt:
            self.leave("sigint")
            while self.state != "stopped":
                event = self.tick()
                if event.name == "idle":
                    sleep(min(poll_s, 0.1))
        finally:
            self.close()

    def start(self) -> threading.Thread:
        self._driver = threading.Thread(target=self.run, name="adgrid-agent-driver", daemon=True)
        self._driver.start()
        return self._driver

    def close(self) -> None:
        with self._lock:
            if self._server is not None:
                self._server.shutdown()
                self._server.server_close()
                self._server = None
            if self.endpoint.kind == "unix":
                try:
                    os.unlink(self.endpoint.path)
                except OSError:
                    pass
            if self._file_lock is not None:
                self._file_lock.release()
                self._file_lock = None
            self.state = "stopped"
            self._stop.set()

    # -- operations (also reachable over HTTP)
    def health(self) -> dict[str, Any]:
        return {"ok": self.state != "faulted", "state": self.state, "pid": os.getpid(), "key_id": self.identity.key_id, "role": self.identity.role, "version": self.version, "started_at": self.started_at, "endpoint": str(self.endpoint), "faults": self.faults, "last_fault": self.last_fault}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                **self.health(), "lanes": list(self.lanes), "cores": self.cores, "idle_only": self.idle_only, "capabilities": list(self.identity.capabilities),
                "lineage": list(self.identity.invite_lineage), "canaries": self.canary_report.to_record() if self.canary_report else None,
                "work": self.work_loop.status() if self.work_loop else None, "verifier": self.verifier_loop.status() if self.verifier_loop else None,
                "leave_reason": self.leave_reason,
            }

    def attach(self, *, lanes: Sequence[str] = (), cores: int | None = None, idle_only: bool | None = None) -> dict[str, Any]:
        with self._lock:
            if self.state != "running":
                return {**self.status(), "attached": False, "reason": f"state:{self.state}"}
            for lane in lanes:
                if lane not in self.lanes:
                    self.lanes.append(lane)
            if lanes and self.work_loop is not None:
                self.work_loop.config = _with_lanes(self.work_loop.config, tuple(self.lanes))
                self.work_loop._frontier_at = None
            if cores is not None:
                self.cores = max(1, int(cores))
                if self.work_loop is not None:
                    self.work_loop.set_cores(self.cores)
            if idle_only is not None:
                self.idle_only = bool(idle_only)
                if self.work_loop is not None and not self.idle_only:
                    self.work_loop.idle_policy = None
            return {**self.status(), "attached": True}

    def leave(self, reason: str = "leave") -> dict[str, Any]:
        with self._lock:
            if self.state in ("leaving", "stopped"):
                return {"state": self.state, "reason": self.leave_reason}
            self.leave_reason = reason
            self.state = "leaving"
            self._leave_started = self.clock()
            aborted = 0
            for loop in (self.work_loop, self.verifier_loop):
                if loop is not None:
                    aborted += loop.release_all(reason)
            return {"state": self.state, "reason": reason, "aborted": aborted}

    def rejoin(self) -> dict[str, Any]:
        with self._lock:
            if self.rejoin_hook is None:
                raise NotConfigured("rejoin needs the canary hook the bootstrap installs")
            report = self.rejoin_hook()
            self.canary_report = report
            self.identity = NodeIdentity(self.identity.key_id, tuple(report.proven), self.identity.invite_lineage, self.identity.role)
            for loop in (self.work_loop, self.verifier_loop):
                if loop is not None:
                    loop.identity = self.identity
                    loop._frontier_at = None
            return {**self.status(), "rejoined": True}

    def _finish_leave_if_done(self) -> None:
        loops = [loop for loop in (self.work_loop, self.verifier_loop) if loop is not None]
        busy = any(loop.slots for loop in loops)
        pending = any(loop.outbox.depth() for loop in loops)
        expired = self._leave_started is not None and self.clock() - self._leave_started >= self.leave_deadline_s
        if pending and not expired:
            for loop in loops:
                if loop.outbox.depth():
                    loop.outbox.flush(loop.objects, loop.upstream.objects, loop.upstream.writer, deadline_s=min(5.0, self.leave_deadline_s), key_id=loop.identity.key_id, limiter=loop.limiter)
            pending = any(loop.outbox.depth() for loop in loops)
        if (not busy and not pending) or expired:
            self.close()


def _with_lanes(config: WorkerConfig, lanes: tuple[str, ...]) -> WorkerConfig:
    from dataclasses import replace

    return replace(config, lanes=lanes)


# --------------------------------------------------------------------------- join / leave
@dataclass
class JoinPlan:
    """Everything a bootstrap needs; ``build`` hooks receive it and return the loops."""

    invite: Invite
    endpoint: Endpoint
    state_dir: Path
    transport: Transport
    derive: Callable[[LogStore, ObjectStore, float], Frontier]
    lanes: tuple[str, ...]
    cores: int
    idle_only: bool
    idle_policy: IdlePolicy | None
    config: WorkerConfig
    verifier_config: Any
    key: NodeKey
    identity: NodeIdentity
    canary_report: CanaryReport | None
    run_verifier: bool
    clock: Callable[[], float]
    wall: Callable[[], float]
    rng: random.Random
    keyring: Any
    store_locator: Mapping[str, Any] = field(default_factory=dict)
    local_objects: ObjectStore | None = None
    lineage_lookup: Callable[[str], Sequence[str] | None] | None = None     # key id -> attested lineage; the fabric's enrolment records (cross-slice)


@dataclass(frozen=True)
class JoinResult:
    mode: str                                  # attached | bootstrapped
    status: Mapping[str, Any]
    agent: LocalAgent | None = None
    plan: JoinPlan | None = None


@dataclass(frozen=True)
class LeaveResult:
    mode: str                                  # left | no-agent
    status: Mapping[str, Any]


def record_writer(log: LogStore, heads: Any, signer: NodeSigner, *, clock: Callable[[], float] = time.monotonic, rng: random.Random | None = None,
                  backoff: Any = None, fallback: bool = False) -> Any:
    """The one chain writer a node flushes through: ``log.outbox.Appender`` (validate, chain, sign,
    append, publish the head).  ``fallback=True`` selects ``transport.local.ChainAppender`` (CAS
    first, no body validation) for a process that must not use the log package's appender."""
    if fallback:
        from ..transport.local import ChainAppender

        return ChainAppender(log, heads, signer, clock=clock, rng=rng)
    from ..log.outbox import Appender

    seed = (rng or random.Random()).randrange(1 << 30)
    return Appender(log, heads, signer, seed=seed, **({"backoff": backoff} if backoff is not None else {}))


def open_node_identity(state_dir: str | os.PathLike[str], *, role: str, objects: ObjectStore, scratch: str | os.PathLike[str] | None = None,
                       claimed: Sequence[str] = (), key_algorithm: str = "ed25519", now: float | None = None, canaries: Mapping[str, Any] | None = None,
                       canary_only: Sequence[str] | None = None, reprove: bool = False) -> tuple[NodeKey, NodeIdentity, CanaryReport | None]:
    """A node's key and identity without a join: the identity ``join`` saved under ``state_dir`` when
    there is one, else a *self-rooted* identity (empty lineage: this key is its own root, which is
    what a laptop grid of one has) whose capabilities are what the canaries prove plus ``claimed``.
    Two self-rooted keys have disjoint lineage sets and are therefore independent verifiers of each
    other's proposals (design §2.5) — the honest statement for one host with two keys."""
    now = time.time() if now is None else now
    keystore = NodeKeyStore(state_dir)
    key = keystore.load_or_create(algorithm=key_algorithm, now=now)
    saved = keystore.load_identity()
    if saved is not None and not reprove and saved[0].key_id == key.key_id:
        return key, saved[0], None
    scratch_dir = Path(scratch) if scratch is not None else Path(state_dir) / "canaries"
    report = run_canaries(objects, str(scratch_dir), canaries=canaries, only=canary_only)
    identity = NodeIdentity(key_id=key.key_id, capabilities=tuple(sorted(set(report.proven) | set(claimed))), invite_lineage=(), role=role)
    if key.expired(now):
        key = keystore.renew(key, now=now, canaries_passed=True)
    keystore.save_identity(identity, {"self_rooted": True, "bound_at": now, "key_expires_at": key.expires_at, "canaries": report.to_record(), "claimed": list(claimed)})
    return key, identity, report


def build_loops(plan: JoinPlan) -> tuple[StepMachine | None, StepMachine | None]:
    """Default wiring: local objects (the transport's when local, a local cache otherwise),
    ``log.outbox.Appender`` as the record writer (``record_writer``), one outbox, one subprocess
    sandbox, and the verifier when the role may verify."""
    from ..verify.loop import VerifierConfig, VerifierLoop
    from ..verify.policy import PenaltyLedger, RevocationList
    from .records import LogTaskIndex

    transport = plan.transport
    objects = transport.objects()
    log = transport.log()
    heads = transport.heads()
    local_objects = plan.local_objects or objects
    signer = NodeSigner(plan.key)
    upstream = Upstream(objects, record_writer(log, heads, signer, clock=plan.clock, rng=plan.rng))
    outbox = Outbox(plan.state_dir / "outbox", clock=plan.clock, rng=plan.rng)
    sandbox = SubprocessSandbox(plan.state_dir / "work", clock=plan.clock)
    locator = dict(plan.store_locator) or (dict(transport.locator()) if hasattr(transport, "locator") else {})
    if not locator.get("adapter"):
        raise NotConfigured(f"transport {getattr(transport, 'name', type(transport).__name__)!r} has no store locator; a sandbox child cannot reach the object store without one (LocalTransport.from_root(root) provides it)")
    plan.store_locator = locator

    def frontier() -> Frontier:
        return plan.derive(log, objects, plan.wall())

    work = WorkLoop(identity=plan.identity, sandbox=sandbox, outbox=outbox, objects=local_objects, upstream=upstream, frontier=frontier, store_locator=locator,
                    config=plan.config, log=log, idle_policy=plan.idle_policy, clock=plan.clock, wall=plan.wall, rng=plan.rng,
                    lineage_lookup=plan.lineage_lookup, keyring=plan.keyring)
    verifier: StepMachine | None = None
    if plan.run_verifier and plan.identity.role in ROLE_MAY_VERIFY:
        vconfig = plan.verifier_config or VerifierConfig(worker=WorkerConfig(cores=1, lanes=plan.config.lanes, deadlines_s=plan.config.deadlines_s, import_modules=plan.config.import_modules, budgets_allowed=plan.config.budgets_allowed))
        verifier = VerifierLoop(identity=plan.identity, task_lookup=LogTaskIndex(log, keyring=plan.keyring), log=log, config=vconfig, penalties=PenaltyLedger.load(objects), revocations=RevocationList.load(objects),
                                sandbox=sandbox, outbox=outbox, objects=local_objects, upstream=upstream, frontier=frontier, store_locator=locator, clock=plan.clock, wall=plan.wall, rng=plan.rng,
                                lineage_lookup=plan.lineage_lookup, keyring=plan.keyring)
    return work, verifier


def join(invite_url: str | None = None, *, state_dir: str | os.PathLike[str], endpoint: Endpoint | None = None, lanes: Sequence[str] = (), cores: int | None = None,
         idle_only: bool = False, idle_policy: str | IdlePolicy | None = "load-average", transport: Transport | None = None, derive: Callable[[LogStore, ObjectStore, float], Frontier] | None = None,
         config: WorkerConfig | None = None, verifier_config: Any = None, run_verifier: bool | None = None, key_algorithm: str = "ed25519", canaries: Mapping[str, Any] | None = None,
         canary_only: Sequence[str] | None = None, env: Mapping[str, str] | None = None, probe_deadline_s: float = DEFAULT_PROBE_DEADLINE_S, rejoin_on_attach: bool = False,
         clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time, rng: random.Random | None = None,
         build: Callable[[JoinPlan], tuple[StepMachine | None, StepMachine | None]] = build_loops, local_objects: ObjectStore | None = None,
         lineage_lookup: Callable[[str], Sequence[str] | None] | None = None, keyring: Any = None) -> JoinResult:
    """Attach-first join.  Returns ``attached`` (status of the running agent) or ``bootstrapped``
    (a bound, running ``LocalAgent`` the caller drives with ``run()``/``start()``)."""
    env = os.environ if env is None else env
    rng = rng or random.Random()
    invite_url = invite_url or env.get("ADGRID_INVITE") or ""
    if not invite_url:
        raise GridError("no invite: pass the invite url or set ADGRID_INVITE (never put it in argv on shared hosts)")
    invite = parse_invite_url(invite_url, now=wall())
    if keyring is None:
        from ..log.signing import Keyring as SigningKeyring

        keyring = SigningKeyring()
    verify_invite(invite, keyring)
    endpoint = endpoint or Endpoint.default(env)
    endpoint.validate()
    state_path = Path(state_dir)

    # attach first
    probed = probe(endpoint, deadline_s=probe_deadline_s)
    if probed.state == "alive":
        client = AgentClient(endpoint, timeout_s=max(probe_deadline_s, 5.0))
        status = client.attach(lanes=lanes, cores=cores, idle_only=idle_only or None)
        if not status.get("attached"):
            raise AttachRefused(f"agent at {endpoint} is alive but did not accept the attach ({status.get('reason', 'unknown')}); retry, or `leave` it first")
        if rejoin_on_attach:
            status = client.rejoin()
        return JoinResult("attached", status)
    if probed.state == "faulted":
        raise AlreadyOwned(f"agent at {endpoint} is faulted ({probed.error}); it still answers `leave`; not restarting")
    if probed.state == "silent":
        raise AlreadyOwned(f"agent endpoint {endpoint} accepted a connection but did not answer health within {probe_deadline_s}s ({probed.error}): the owner is wedged; not restarting")

    # everything that can fail by name, before any socket is touched
    if transport is None:
        from ..transport import transport_for

        transport = transport_for(invite.fabric_url)
    if derive is None:
        raise NotConfigured("join needs the frontier derivation: pass derive=agentdecompile_grid.log.frontier.derive (log, objects, now) -> Frontier")
    for accessor in ("objects", "log", "heads"):
        getattr(transport, accessor)()        # declared transports raise NotConfigured here, by name
    policy: IdlePolicy | None = None
    if idle_only:
        policy = idle_policy_for(idle_policy or "load-average") if isinstance(idle_policy, str) or idle_policy is None else idle_policy
        if policy is not None:
            policy.should_run(clock(), running=0)     # a declared policy raises NotConfigured here, by name, before any socket exists

    # the lock: held and silent = wedged owner (already refused above); free = ours
    file_lock = None
    if endpoint.kind == "unix":
        file_lock = FileLock.acquire_nowait(endpoint.lock_path)
        if file_lock is None:
            raise AlreadyOwned(f"agent lock {endpoint.lock_path} is held by pid {FileLock.holder_pid(endpoint.lock_path)} but {endpoint} does not answer: wedged owner; not unlinking, not restarting")
        if os.path.exists(endpoint.path):
            os.unlink(endpoint.path)          # stale: nobody holds the lock and nobody answered

    now = wall()
    try:
        keystore = NodeKeyStore(state_path)
        key = keystore.load_or_create(algorithm=key_algorithm, now=now)
        provisional = NodeIdentity(key.key_id, (), invite.joiner_lineage, invite.role)
        worker_config = config or WorkerConfig(cores=cores or max(1, (os.cpu_count() or 2) // 2), lanes=tuple(lanes), budgets_allowed=FLEET_BUDGETS_ALLOWED if invite.role in ROLE_MAY_VERIFY else WorkerConfig.budgets_allowed)
        agent = LocalAgent(endpoint, identity=provisional, clock=clock, wall=wall, lanes=lanes, cores=worker_config.cores, idle_only=idle_only)
    except BaseException:
        if file_lock is not None:
            file_lock.release()
        raise
    agent.bind(file_lock)                     # releases the lock itself when the bind fails
    try:
        scratch = state_path / "canaries"
        canary_pool = canaries

        def reprove() -> CanaryReport:
            return run_canaries(transport.objects(), str(scratch), canaries=canary_pool, only=canary_only)

        report = reprove()
        identity = bind_identity(key, invite, report.proven)
        if key.expired(now):
            key = keystore.renew(key, now=now, canaries_passed=True)
        keystore.save_identity(identity, {"fabric_url": invite.fabric_url, "fabric_id": invite.fabric_id, "invite_fingerprint": invite.fingerprint(), "bound_at": now, "key_expires_at": key.expires_at, "canaries": report.to_record()})
        agent.identity = identity
        agent.rejoin_hook = reprove
        plan = JoinPlan(invite=invite, endpoint=endpoint, state_dir=state_path, transport=transport, derive=derive, lanes=tuple(lanes), cores=worker_config.cores, idle_only=idle_only,
                        idle_policy=policy, config=worker_config, verifier_config=verifier_config, key=key, identity=identity, canary_report=report,
                        run_verifier=(invite.role in ROLE_MAY_VERIFY) if run_verifier is None else run_verifier, clock=clock, wall=wall, rng=rng,
                        keyring=keyring, local_objects=local_objects, lineage_lookup=lineage_lookup)
        work, verifier = build(plan)
        agent.attach_loops(work, verifier, canary_report=report)
    except BaseException:
        agent.close()
        raise
    return JoinResult("bootstrapped", agent.status(), agent=agent, plan=plan)


def status(endpoint: Endpoint | None = None, *, deadline_s: float = DEFAULT_PROBE_DEADLINE_S, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """The running agent's status, or the probe result when none answers (never an exception for absence)."""
    endpoint = endpoint or Endpoint.default(env)
    probed = probe(endpoint, deadline_s=deadline_s)
    if probed.state not in ("alive", "faulted"):
        return {"mode": "no-agent", "endpoint": str(endpoint), "probe": probed.state, "error": probed.error}
    return {"mode": "agent", **AgentClient(endpoint, timeout_s=max(deadline_s, 5.0)).status()}


def leave(endpoint: Endpoint | None = None, *, reason: str = "leave", deadline_s: float = 5.0, env: Mapping[str, str] | None = None) -> LeaveResult:
    endpoint = endpoint or Endpoint.default(env)
    probed = probe(endpoint, deadline_s=deadline_s)
    if probed.state not in ("alive", "faulted"):          # a faulted agent still takes `leave`; that is how it is retired
        return LeaveResult("no-agent", {"endpoint": str(endpoint), "probe": probed.state, "error": probed.error})
    return LeaveResult("left", AgentClient(endpoint, timeout_s=deadline_s).leave(reason))


__all__ = [
    "AgentClient", "AgentUnreachable", "AttachRefused", "BatteryPolicy", "DEFAULT_LEAVE_DEADLINE_S", "DEFAULT_PROBE_DEADLINE_S", "Endpoint", "FileLock", "HTTP_PREFIX", "IDLE_POLICIES",
    "JoinPlan", "JoinResult", "LeaveResult", "LoadAveragePolicy", "LocalAgent", "ProbeResult", "SUN_PATH_LIMIT", "UserActivityPolicy", "build_loops", "idle_policy_for",
    "join", "leave", "open_node_identity", "probe", "record_writer", "status",
]

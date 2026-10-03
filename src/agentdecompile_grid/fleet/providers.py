"""Fleet provider adapters (``core.PROVIDERS``): who creates the machines that run the join command.

* ``manual``   working — emits the user-data for the operator to paste into any console and returns
               placeholder node ids the operator binds to real ids with ``bind``.
* ``ssh``      working when ``ssh`` is on PATH — runs the *bash* bootstrap on hosts listed in its
               config, script on stdin (the invite never appears in a remote argv), a deadline per
               host, ``BatchMode=yes`` (no prompts, ever).
* ``oci``, ``hetzner``, ``aws``, ``gcp``
               declared with their config schema; ``up``/``down``/``status`` raise ``NotConfigured``
               naming the CLI and the credential reference each needs.  Credentials come from the
               user's secret-session path (``credential_ref``), never from a prompt.

Hosted-CI minutes are not a provider (design §1.4: terms of service).  A provider never trusts
the node it made: fleet output is a proposal like any other (design §2.5).

Acceptance tests named for the final verification phase (U129):
  * ``test_manual_provider_records``: ``up(2, ...)`` emits the user-data once and returns two
    placeholders; ``bind`` replaces them; ``status`` lists both with their state.
  * ``test_ssh_provider_stdin``: the ssh provider passes the bootstrap on stdin, never in argv,
    uses BatchMode and a ConnectTimeout, and reports a host that exceeds the deadline by name.
  * ``test_declared_providers_name_needs``: every declared provider's ``NotConfigured`` names its
    CLI and ``credential_ref``; ``describe()`` lists ``config_schema``.
"""
from __future__ import annotations

import secrets
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from ..core import PROVIDERS, GridError, NotConfigured
from .cloudinit import is_cloud_config


class ProviderError(GridError):
    """A provider operation failed by name (deadline, host unreachable, CLI missing)."""


@dataclass
class ProvisionedNode:
    node_id: str
    provider: str
    state: str                                 # pending | up | down | failed
    labels: Mapping[str, str] = field(default_factory=dict)
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "provider": self.provider, "state": self.state, "labels": dict(self.labels), "detail": dict(self.detail)}


# --------------------------------------------------------------------------- manual
class ManualProvider:
    """Prints (or hands to ``emit``) the user-data; the operator creates the machines by hand."""

    name = "manual"

    def __init__(self, *, emit: Callable[[str], None] | None = None) -> None:
        self.emit = emit or (lambda text: print(text))
        self.nodes: dict[str, ProvisionedNode] = {}

    def up(self, count: int, user_data: str, labels: Mapping[str, str]) -> Sequence[str]:
        if count < 1:
            raise ProviderError("count must be >= 1")
        batch = secrets.token_hex(3)
        ids = [f"pending-{batch}-{i + 1}" for i in range(count)]
        self.emit(f"# adgrid fleet: create {count} machine(s) with this user-data, then bind the ids you get back: {' '.join(ids)}\n{user_data}")
        for node_id in ids:
            self.nodes[node_id] = ProvisionedNode(node_id, self.name, "pending", dict(labels), {"batch": batch})
        return ids

    def bind(self, placeholder: str, node_id: str) -> ProvisionedNode:
        node = self.nodes.pop(placeholder, None)
        if node is None:
            raise ProviderError(f"unknown placeholder {placeholder!r}")
        bound = ProvisionedNode(node_id, self.name, "up", node.labels, {**node.detail, "placeholder": placeholder})
        self.nodes[node_id] = bound
        return bound

    def down(self, node_ids: Sequence[str]) -> None:
        for node_id in node_ids:
            node = self.nodes.get(node_id)
            if node is None:
                raise ProviderError(f"unknown node {node_id!r}")
            node.state = "down"
        self.emit(f"# adgrid fleet: destroy these machines by hand: {' '.join(node_ids)}")

    def status(self) -> Sequence[Mapping[str, Any]]:
        return [n.to_record() for n in self.nodes.values()]

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "working", "needs": [], "config_schema": {}}


# --------------------------------------------------------------------------- ssh
class SshProvider:
    """Existing machines reachable over ssh: the bash bootstrap goes over stdin."""

    name = "ssh"
    CONFIG_SCHEMA: Mapping[str, str] = {
        "hosts": "list of [user@]host[:port] entries the bootstrap may run on", "identity_file": "optional ssh private key path (never a password)",
        "connect_timeout_s": "ssh ConnectTimeout (default 10)", "deadline_s": "per-host bootstrap deadline (default 600)", "ssh_binary": "ssh executable (default 'ssh')",
    }

    def __init__(self, hosts: Sequence[str] = (), *, identity_file: str | None = None, connect_timeout_s: float = 10.0, deadline_s: float = 600.0, ssh_binary: str = "ssh",
                 runner: Callable[..., "subprocess.CompletedProcess[bytes]"] = subprocess.run, leave_command: str = "adgrid leave") -> None:
        self.hosts = list(hosts)
        self.identity_file = identity_file
        self.connect_timeout_s = connect_timeout_s
        self.deadline_s = deadline_s
        self.ssh_binary = ssh_binary
        self.runner = runner
        self.leave_command = leave_command
        self.nodes: dict[str, ProvisionedNode] = {}

    def _preflight(self) -> str:
        found = shutil.which(self.ssh_binary)
        if not found:
            raise NotConfigured(f"ssh provider needs {self.ssh_binary!r} on PATH")
        if not self.hosts:
            raise NotConfigured("ssh provider needs at least one host in config 'hosts'")
        return found

    def _argv(self, host: str, remote: str) -> list[str]:
        user_host, _, port = host.rpartition(":") if host.count(":") == 1 and host.rsplit(":", 1)[1].isdigit() else (host, "", "")
        argv = [self.ssh_binary, "-o", "BatchMode=yes", "-o", f"ConnectTimeout={int(self.connect_timeout_s)}", "-o", "StrictHostKeyChecking=accept-new"]
        if port:
            argv += ["-p", port]
        if self.identity_file:
            argv += ["-i", self.identity_file]
        argv += [user_host, "--", remote]
        return argv

    def _run(self, host: str, remote: str, stdin: bytes, deadline_s: float) -> "subprocess.CompletedProcess[bytes]":
        try:
            return self.runner(self._argv(host, remote), input=stdin, capture_output=True, timeout=deadline_s)
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"ssh {host}: {remote!r} exceeded the {deadline_s:.0f}s deadline") from exc
        except OSError as exc:
            raise ProviderError(f"ssh {host}: cannot run {self.ssh_binary}: {exc.__class__.__name__}") from exc

    def up(self, count: int, user_data: str, labels: Mapping[str, str]) -> Sequence[str]:
        self._preflight()
        if is_cloud_config(user_data):
            raise ProviderError("ssh provider runs a bash bootstrap; render user-data with format='bash'")
        free = [h for h in self.hosts if h not in self.nodes or self.nodes[h].state == "down"]
        if len(free) < count:
            raise ProviderError(f"ssh provider has {len(free)} free host(s), {count} requested")
        ids: list[str] = []
        for host in free[:count]:
            proc = self._run(host, "sh -s", user_data.encode("utf-8"), self.deadline_s)
            state = "up" if proc.returncode == 0 else "failed"
            self.nodes[host] = ProvisionedNode(host, self.name, state, dict(labels), {"returncode": proc.returncode, "stderr_tail": proc.stderr[-400:].decode("utf-8", "replace")})
            if state == "up":
                ids.append(host)
        if not ids:
            raise ProviderError("ssh provider: every bootstrap failed (see status detail)")
        return ids

    def down(self, node_ids: Sequence[str]) -> None:
        self._preflight()
        for host in node_ids:
            proc = self._run(host, self.leave_command, b"", min(self.deadline_s, 60.0))
            node = self.nodes.get(host) or ProvisionedNode(host, self.name, "up")
            node.state = "down" if proc.returncode == 0 else "failed"
            node.detail = {**dict(node.detail), "leave_returncode": proc.returncode}
            self.nodes[host] = node

    def status(self, *, probe: bool = False) -> Sequence[Mapping[str, Any]]:
        rows = [n.to_record() for n in self.nodes.values()]
        if probe:
            self._preflight()
            for row in rows:
                try:
                    proc = self._run(row["node_id"], "true", b"", min(self.deadline_s, 30.0))
                    row["reachable"] = proc.returncode == 0
                except ProviderError as exc:
                    row["reachable"] = False
                    row["probe_error"] = str(exc)
        return rows

    def describe(self) -> Mapping[str, Any]:
        needs = [] if shutil.which(self.ssh_binary) else [f"{self.ssh_binary} on PATH"]
        if not self.hosts:
            needs.append("hosts")
        return {"name": self.name, "status": "working" if not needs else "declared", "needs": needs, "hosts": list(self.hosts), "config_schema": dict(self.CONFIG_SCHEMA)}


# --------------------------------------------------------------------------- declared cloud providers
class _DeclaredCloudProvider:
    name = "cloud"
    cli = ""
    credential = ""
    CONFIG_SCHEMA: Mapping[str, str] = {}

    def __init__(self, **config: Any) -> None:
        self.config = dict(config)

    def _refuse(self, op: str) -> NotConfigured:
        found = shutil.which(self.cli) if self.cli else None
        missing = [k for k in self.CONFIG_SCHEMA if not self.config.get(k)]
        return NotConfigured(f"{self.name} provider ({op}) is declared only; it needs the {self.cli!r} CLI on PATH ({'found' if found else 'missing'}), credential {self.credential} via credential_ref from the secret-session path (never a prompt), and config {missing or 'complete'}")

    def up(self, count: int, user_data: str, labels: Mapping[str, str]) -> Sequence[str]:
        raise self._refuse("up")

    def down(self, node_ids: Sequence[str]) -> None:
        raise self._refuse("down")

    def status(self) -> Sequence[Mapping[str, Any]]:
        raise self._refuse("status")

    def describe(self) -> Mapping[str, Any]:
        return {"name": self.name, "status": "declared", "cli": self.cli, "credential": self.credential, "needs": [k for k in self.CONFIG_SCHEMA if not self.config.get(k)], "config_schema": dict(self.CONFIG_SCHEMA)}


class OciProvider(_DeclaredCloudProvider):
    """Always-free ARM tier (analyzer lanes) and x86 micro tier (toolchain under the compatibility layer)."""

    name = "oci"
    cli = "oci"
    credential = "OCI_CLI_CONFIG_FILE profile (API key)"
    CONFIG_SCHEMA = {"credential_ref": "secret-session path of the OCI API key profile", "compartment_id": "target compartment OCID", "shape": "e.g. VM.Standard.A1.Flex (ARM) or VM.Standard.E2.1.Micro", "image_id": "base image OCID", "subnet_id": "subnet OCID (outbound-only security list)", "availability_domain": "AD name"}


class HetznerProvider(_DeclaredCloudProvider):
    name = "hetzner"
    cli = "hcloud"
    credential = "HCLOUD_TOKEN"
    CONFIG_SCHEMA = {"credential_ref": "secret-session path of the API token", "server_type": "e.g. cax11 (ARM) or cx22", "image": "base image name", "location": "datacentre location"}


class AwsProvider(_DeclaredCloudProvider):
    name = "aws"
    cli = "aws"
    credential = "AWS_PROFILE / access key pair"
    CONFIG_SCHEMA = {"credential_ref": "secret-session path of the profile", "instance_type": "e.g. t4g.micro (ARM) or t2.micro", "ami": "base AMI id", "subnet_id": "subnet id", "security_group_id": "outbound-only security group"}


class GcpProvider(_DeclaredCloudProvider):
    name = "gcp"
    cli = "gcloud"
    credential = "service account key / gcloud auth"
    CONFIG_SCHEMA = {"credential_ref": "secret-session path of the service account key", "project": "project id", "zone": "zone", "machine_type": "e.g. e2-micro", "image_family": "base image family"}


PROVIDERS.register("manual", ManualProvider)
PROVIDERS.register("ssh", SshProvider)
PROVIDERS.register("oci", OciProvider)
PROVIDERS.register("hetzner", HetznerProvider)
PROVIDERS.register("aws", AwsProvider)
PROVIDERS.register("gcp", GcpProvider)


def provider_for(name: str, **config: Any) -> Any:
    return PROVIDERS.get(name)(**config)


def describe_providers() -> dict[str, Mapping[str, Any]]:
    return {name: cls().describe() for name, cls in PROVIDERS.items()}


__all__ = ["AwsProvider", "GcpProvider", "HetznerProvider", "ManualProvider", "OciProvider", "ProviderError", "ProvisionedNode", "SshProvider", "describe_providers", "provider_for"]

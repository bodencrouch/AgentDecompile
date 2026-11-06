"""agentdecompile_grid.log — the append-only, hash-chained, signed record layer.

Importing this package registers every adapter it declares in the ``core`` registries
(``LOG_STORES``: local, s3, http; ``HEAD_STORES``: local, s3, http; ``SIGNERS``: ed25519 (default),
null, hmac, hash-token, hsm, ssh-agent; ``KEY_SOURCES``; ``RECORD_FILTERS``).  Registration is of *classes* and never needs an optional dependency; a declared
adapter raises ``NotConfigured`` naming its requirement when constructed.

Public API other slices rely on (see README.md for the rules):
  LocalFileLog(root) / LocalFileHeads(root)         working log + CAS head store
  NullSigner() / HMACSigner(secret) / Ed25519Signer  signers; Keyring; verify_record(record, keyring)
  Appender(log, heads, signer) / Outbox(appender)    seal + append with backoff and rotation;
                                                     Appender.write_batch is the node outbox's RecordWriter
  Draft(type, body) / seal / verify_chain            records
  derive(log, objects, now, *, proposal_cap, kinds)  the frontier, pure
  issue_intent / renew_intent / drop_intent          advisory leases with a fence
  compact / latest_checkpoint / prune                checkpoints and the separate retention verb
  log_from_config / heads_from_config / signer_from_config   configuration is data
"""
from __future__ import annotations

from typing import Any
from collections.abc import Mapping

from agentdecompile_grid.core import HEAD_STORES, LOG_STORES, SIGNERS, HeadStore, LogStore, Signer

from . import backoff, compaction, frontier, heads, http, intents, keys, local, outbox, records, s3, signing
from .backoff import BackoffPolicy, BackoffStep, PartitionRotation, full_jitter
from .compaction import (
    CheckpointSummary,
    CompactionResult,
    KeepEverything,
    KeepSinceLatestCheckpoint,
    KeepTail,
    RETENTION_POLICIES,
    RetentionPolicy,
    compact,
    derive_from_latest,
    latest_checkpoint,
    prune,
    read_from_checkpoint,
)
from .frontier import FoldOrder, FrontierPolicy, FrontierReport, IntentState, PartitionState, PrefixPruned, TaskState, classify, derive, fold, states_of
from .heads import HttpHeads, LocalFileHeads, S3ConditionalHeads, publish_head, rebuild_heads, sub_partition
from .http import HttpLog
from .intents import IntentFenced, IntentNotHeld, Lease, drop_intent, issue_intent, renew_intent
from .local import ChainConflict, LocalFileLog, LogCorrupt, PruneRefused
from .outbox import AppendGaveUp, Appender, HotHead, Outbox, OutboxPolicy, draft_for
from .records import (
    BadSignature,
    ChainBroken,
    Draft,
    InvalidBody,
    InvalidPartition,
    InvalidRecord,
    RecordError,
    SchemaMismatch,
    UnknownSigner,
    build_record,
    seal,
    validate_partition,
    validate_record,
    verify_chain,
)
from .s3 import S3ObjectLog
from .signing import Ed25519Signer, HMACSigner, Keyring, NullSigner, signer_from_config, verify_record


def register_adapters() -> None:
    """Idempotent: safe under module reloads (``replace=True``)."""
    for cls in (LocalFileLog, S3ObjectLog, HttpLog):
        LOG_STORES.register(cls.name, cls, replace=True)
    for cls in (LocalFileHeads, S3ConditionalHeads, HttpHeads):
        HEAD_STORES.register(cls.name, cls, replace=True)
    signing.register_signers(SIGNERS)


register_adapters()


def log_from_config(config: Mapping[str, Any]) -> LogStore:
    """``{"adapter": "local"|"s3"|"http", ...}`` -> a log store via ``LOG_STORES``."""
    return LOG_STORES.get(str(config.get("adapter", "local"))).from_config(config)


def heads_from_config(config: Mapping[str, Any]) -> HeadStore:
    """``{"adapter": "local"|"s3"|"http", ...}`` -> a head store via ``HEAD_STORES``."""
    return HEAD_STORES.get(str(config.get("adapter", "local"))).from_config(config)


def describe_adapters() -> dict[str, dict[str, Any]]:
    """Every adapter this package declares, with status, requirements and config schema."""
    out: dict[str, dict[str, Any]] = {}
    for registry, kind in ((LOG_STORES, "log"), (HEAD_STORES, "heads"), (SIGNERS, "signer")):
        for name, cls in registry.items():
            describe = getattr(cls, "describe", None)
            if callable(describe):
                out[f"{kind}:{name}"] = describe()
    return out


CONFIG_FIELDS: dict[str, Any] = {
    "log": {"adapter": "local", "root": "<store root>", "torn_tail": "raise", "fsync": True, "verify": "chain",
            "s3": S3ObjectLog.config_schema(), "http": HttpLog.config_schema()},
    "heads": {"adapter": "local", "root": "<store root>", "fsync": True,
              "s3": S3ConditionalHeads.config_schema(), "http": HttpHeads.config_schema()},
    "signing": {"adapter": "null", "label": "", "key_dir": "<keys dir>", "secret_env": "ADGRID_HMAC_SECRET", "secret_file": ""},
    "keyring": {"allow_null": True, "key_dir": "<public keys dir>"},
    "frontier": FrontierPolicy.config_schema()["properties"],
    "outbox": OutboxPolicy.config_schema()["properties"],
    "backoff": BackoffPolicy.config_schema()["properties"],
    "intents": {"ttl_s": 300},
    "partitions": {"prefix_width": {"default": 0, "<lane>": "<hex chars>"}},
    "compaction": {"max_lag_records": 64, "retention": {"policy": "keep-since-latest-checkpoint", "keep_checkpoints": 1}},
}
"""The GridConfig field names this package reads; the integrator maps ``GridConfig`` onto these."""

__all__ = [
    "AppendGaveUp", "Appender", "BackoffPolicy", "BackoffStep", "BadSignature", "CONFIG_FIELDS", "ChainBroken",
    "ChainConflict", "CheckpointSummary", "CompactionResult", "Draft", "Ed25519Signer", "FoldOrder", "FrontierPolicy",
    "FrontierReport", "HMACSigner", "HotHead", "HttpHeads", "HttpLog", "IntentFenced", "IntentNotHeld", "IntentState",
    "InvalidBody", "InvalidPartition", "InvalidRecord", "KeepEverything", "KeepSinceLatestCheckpoint", "KeepTail",
    "Keyring", "Lease", "LocalFileHeads", "LocalFileLog", "LogCorrupt", "NullSigner", "Outbox", "OutboxPolicy",
    "PartitionRotation", "PartitionState", "PrefixPruned", "PruneRefused", "RETENTION_POLICIES", "RecordError", "RetentionPolicy",
    "S3ConditionalHeads", "S3ObjectLog", "SchemaMismatch", "TaskState", "UnknownSigner", "backoff", "build_record",
    "classify", "compact", "compaction", "derive", "derive_from_latest", "describe_adapters", "draft_for", "drop_intent", "fold",
    "frontier", "full_jitter", "heads", "heads_from_config", "http", "intents", "issue_intent", "latest_checkpoint",
    "local", "log_from_config", "outbox", "prune", "publish_head", "read_from_checkpoint", "rebuild_heads", "records",
    "register_adapters", "renew_intent", "s3", "seal", "signer_from_config", "signing", "states_of", "sub_partition",
    "validate_partition", "validate_record", "verify_chain", "verify_record",
]

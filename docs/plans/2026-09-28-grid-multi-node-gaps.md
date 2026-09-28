---
title: Distributed compute, grid of two — what a real second node needs (multi-node gap list)
date: 2026-09-28
status: trace notes from one machine simulating two roots; no second machine was available; every
  claim below is either a command and its output (cited) or named as untested
applies-to: docs/plans/2026-09-21-distributed-compute-design.md, docs/plans/2026-09-21-grid-of-one-walkthrough.md
---

# Grid of two, one machine: what is missing for real multi-node use

This trace exercised `agentdecompile_grid` across two separate `ADGRID_ROOT` directories on one
host: `rootA` (an operator identity `opA` and a second, independently-lineaged operator identity
`verifierC`) and `rootB` (a donor identity `peerB`, joined by invite). `rootB`'s own state
(`nodes/`, `keys/`) is a directory `rootA` never reads; the two share only the object/log/head
store, reached through `ADGRID_PATHS__OBJECTS` / `__LOG` / `__HEADS` pointed at `rootA`'s paths
(the "local" transport — a filesystem both sides can reach, standing in for a network share or a
bucket). No second machine, real network boundary, HTTPS/S3 adapter or cloud provider was
available; those gaps are named, not closed, below.

## What is implemented and was exercised for real here

- **Invite issuance and consumption.** `worker/identity.make_invite` (signed, role-checked:
  `ROLE_MAY_SIGN` refuses a donor issuing anything), `parse_invite_url` / `verify_invite`
  (signature check, role-must-match, expiry, self-lineage refusal), and `adgrid join <url>`
  (consumes the invite, records `invite_lineage`, proves the `python` canary, bootstraps a real
  ed25519 identity). `peerB`'s bootstrapped identity carried `lineage: ["<opA's key_id>"]` and
  `role: "donor"` straight from the invite, not from any local default.
- **Cross-root work.** `peerB` (root B) pulled the frontier from `rootA`'s log/objects, launched
  and collected a real `hash-object` task published on `rootA`, and flushed a RESULT signed with
  its own key into `rootA`'s shared log — a genuinely different local state directory producing a
  record another root's readers later trusted.
- **Independent-key verification across roots.** `opA` (the invite's issuer) could **not** verify
  `peerB`'s result: `skipped: {"not-independent:shared-lineage": 1}`, because `opA`'s key sits in
  `peerB`'s `invite_lineage`. `verifierC` (a second, self-rooted, empty-lineage identity on the
  same root) verified it. This is design §2.5's rule ("independent-key means: not the producing
  key and not any key in its invite ancestry") holding under a real invite chain, not a mock — and
  it is the concrete reason U126 requires the fleet to hold two keys with disjoint ancestry: one
  issuer cannot self-certify its own invitees.
- **View materialization of a cross-root verified record.** `adgrid view materialize` on `rootA`
  replayed the full chain (`applied: 7`, `verified_rows: 1`) once every signer in it (`peerB`,
  `verifierC`, and `opA`'s own null-signed TASK) had an explicit trust-file entry; the recomputed
  digest read back byte-identical to the independently computed `sha256sum` of the input.

Full command sequence and raw JSON: `multi-node/01..11-*.txt` in the delivered sequence
(`grid-of-one/multi-node/` under the 2026-09-28 deliverables root).

## Gaps, ordered by what blocks a second real machine soonest

1. **No out-of-band issuer-key distribution.** `verify_invite` refuses an invite whose issuer is
   not already in the joiner's own keyring (`worker/identity.py:431-432`), and nothing in this
   checkout ships that seed — no pinned fabric key, no QR/TOFU flow, no fetch-issuer-key-from-URL
   step. `join.sh` (1.3 in the design doc) assumes a `#<invite>` fragment carries everything a
   stranger needs; today a stranger also needs the issuer's public key placed in
   `keys/trusted/` by hand first. Closing this for real is a second-machine-shaped problem (the
   distribution channel has to reach an actual stranger); the smallest real exercise here was
   doing that hand-off manually and naming it as manual.
2. **No CLI verb to mint an invite.** `make_invite` is a real, tested-here library function with
   no `adgrid invite create ...` wrapping it — `cmd_join` only *consumes* a URL (`cli.py:674-681`,
   confirmed against `03-join.txt`'s `no invite: pass the invite url` refusal). An operator today
   has to script the call shown in `multi-node/02-mint-invite.txt`.
3. **No trust-record propagation.** A successful `join` leaves the new node's public key only
   under its own `<root>/nodes/<name>/keys/node.json`. Nothing publishes it as an object or pushes
   it to the coordinator; `keyring.trust_local_nodes` only scans local `nodes/*/keys` under the
   **same** root (`log/signing.py:446-451`), so it is a single-host convenience that cannot see a
   genuinely separate root. The exercise above closed this by `cp`-ing `node.json` into the
   remote side's `keys/trusted/` and adding the `role` field an operator would set by hand
   (`add_node_record` reads `role`/`lineage` from the file, `log/signing.py:393-407`); that copy
   step is the whole missing mechanism, not a workaround — there is no bucket, HTTP push or fleet
   manifest entry that does it today.
4. **HTTPS/S3 log, heads and object adapters are declared, not working.** `log/http.py`
   (`HttpLog`) and `log/s3.py` are "declared adapter" per their own module docstrings;
   construction raises `NotConfigured`. `describe` lists `https`/`s3` as known adapter *names*
   (`Registry` entries), not as usable transports. This is the actual reason the exercise above
   used the local filesystem as the shared store instead of a real network boundary: there is no
   other working transport in this checkout to point two roots at.
5. **Fleet providers are declared, not working.** `fleet/providers.py`'s own docstring: providers
   (`aws`, `gcp`, `hetzner`, `oci`, `ssh`, `manual`) are "declared with their config schema;
   up/down/status raise `NotConfigured`." `fleet/cloudinit.py` (user-data rendering) and
   `fleet/manifest.py` (the manifest-as-objects bookkeeping) are real and unit-shaped, but nothing
   can call them against an actual instance API from here — `adgrid fleet up` cannot create a
   single real node on any provider today. This needs a second machine (or a cloud account) by
   construction; it was not attempted.
6. **Self-trust is not implicit.** Not anticipated going in: a node's own previously-written
   records are not trusted by a later reader (including a `view materialize` run by the same
   operator) unless that node's key is *also* in `keys/trusted/`. `08-opA-verify-after-trust.txt`
   read the frontier fine after trusting `peerB`; `view materialize` still went `ViewUntrusted:
   untrusted:unknown-signer` at `verifierC`'s own INTENT record until `verifierC`'s key was added
   too (`11-view-materialize-final.txt`). Holding the private key proves authorship; it does not
   make any reader trust the record, including a future instance of the same process. Worth a line
   in the design doc's operator runbook — every identity a root will read from (not just remote
   ones) needs an entry.

## What was not, and could not be, exercised here

- A real network boundary (TCP/TLS) between the two identities — everything above shares one
  filesystem tree, however disjoint the two `ADGRID_ROOT`s are.
- Any of `https`, `s3`, `peer` object/log/head adapters end to end (gap 4).
- A real cloud instance from `adgrid fleet up` (gap 5).
- Compaction, the poison path, and revocation under real multi-node load (only the single-record
  cross-root path above ran).
- Whether a *stranger* (no prior relationship with the operator) can complete gap 1's missing
  hand-off through any channel that scales past copy-pasting a file — that is the actual product
  question the "one command, per donor class" table (design §1.3) is answering for, and it needs
  a second machine and a real stranger to test.

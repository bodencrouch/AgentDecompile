# Public lobby/master-server research for a new KotOR multiplayer implementation

Checked 2026-09-15. This is research only; no game was registered and no external service was changed.

## Recommendation

For an initial Halo CE PC-style browser, use a tiny first-party directory service unless the project already wants Epic Online Services (EOS) identity/SDK integration. The minimum contract is `register/heartbeat`, `list`, and expiry: advertise a server ID, reachable address/port, display name, current/max players, build/protocol version, and `passwordRequired` boolean. Let the game connection protocol perform the password challenge. This is substantially less integration work than implementing GameSpy QR/server-browsing solely to qualify for OpenSpy.

EOS is the strongest hosted, free-to-use candidate for a new game. Epic says EOS is available on any engine/store, has no royalty or hosting fees, and offers Sessions/Lobbies/P2P; setup requires an Epic developer product and SDK credentials. Its sessions/lobbies support public discovery and searchable game-defined attributes, so name, counts, version, and a password-required flag fit naturally. It is a developer-platform integration, not an anonymous public master server: <https://onlineservices.epicgames.com/> and <https://onlineservices.epicgames.com/multiplayer>.

OpenSpy is reasonable only if GameSpy compatibility is itself a goal. Its current core implements QR v1/v2, server browsing v1 on TCP 28900 and v2/enctypex on 28910, plus optional NAT negotiation. QR receives server reports and causes servers to be queried for browser data: <https://github.com/openspy/openspy-core#services>. The original GameSpy QR2 contract requires a unique `gamename` and matching `secret_key`, plus UDP heartbeats and query callbacks; standard fields include `hostname`, `numplayers`, `maxplayers`, `hostport`, and `password`: <https://documentation.help/GameSpy-SDK/Gamespy%20Query%20and%20Reporting%202%20SDK.html>.

I found no current OpenSpy documentation promising generic, automatic, free self-service registration of a new game namespace/key. The public site describes supported games and per-game setup, while the implementation obtains game metadata from its backend; the backend's documented API-key bootstrap is an admin operation. Therefore, using the public OpenSpy deployment for a new KotOR-derived protocol should be treated as requiring maintainer coordination and explicit provisioning, not assumed available: <https://openspy.org/> and <https://github.com/openspy/openspy-web-backend/blob/master/README.md>. OpenSpy is open source and can be self-hosted, but that stack includes multiple services plus Redis, RabbitMQ, and the web backend, which is far beyond this browser's needs.

333networks is another live, free public compatibility master. It documents supported games and a generalized GameSpy/Unreal-style configuration, and exposes a JSON API. Its generic instructions still assume that the game already speaks the expected legacy master/query protocol; its site directs unsupported games to Discord and does not document self-service creation of a new game namespace. It is worth contacting only if the implementation deliberately adopts its supported GameSpy/Unreal wire behavior: <https://333networks.com/instructions>, <https://333networks.com/instructions/alt/s>, and <https://333networks.com/support>.

## What the browser should advertise

The old GameSpy model maps almost exactly to the requested UI:

- `hostname`: user-visible server name.
- `numplayers` and `maxplayers`: occupancy.
- `hostport` plus the observed/reachable address: join target.
- `gamever` or a custom protocol/build field: reject incompatible clients before join.
- `password`: **only** `0`/absent or `1`, meaning whether a join password is required.

The GameSpy QR2 documentation explicitly defines `password` as a boolean and leaves actual protection to the game's network code. Never publish the password, a reversible form, or a reusable password hash in lobby metadata. On join, send the candidate through a server-side authenticated challenge or an encrypted channel and compare against a slow salted password verifier. The directory needs only `passwordRequired: true|false` for the lock icon/filter.

## NWN/NWN2 relevance

NWN and NWN2 are useful architectural precedents because they separate the authoritative game server from discovery. The community replacement tracked online player-run servers in a central backend, exposed a separate enumeration API, and allowed external sources to submit servers. However, that API recognizes only the `NWN1` and `NWN2` product values, and NWN2 participation required its specific `xp_bugfix` integration: <https://github.com/SkywingvL/nwn2dev-public>.

Current NWN:EE likewise has a centralized public list and JSON enumeration endpoints (`/v1/servers`, by identity, or by IP/port): <https://api.nwn.beamdog.net/v1/>. Its server configuration distinguishes public listing, server name, maximum clients, player password, game port, and master-server authentication; this is a good product model for a KotOR browser. It is not evidence of wire compatibility with KotOR, GameSpy, or the proposed multiplayer transport, and its public API is scoped to NWN servers.

The reusable architecture is: authoritative listen/dedicated server -> periodic registration/heartbeat -> expiring directory -> browser query -> direct/relayed join. The directory advertises status; it does not run simulation and does not need to know the join password.

## Realistic decision

1. For the first playable release, implement the small HTTPS directory and keep the payload compatible with a future provider adapter. This delivers the requested classic browser with the fewest dependencies.
2. Choose EOS instead if free hosted operation, NAT/P2P support, cross-store identity, and long-term service operation outweigh SDK/account coupling.
3. Approach OpenSpy or 333networks only after deciding to implement their legacy protocol, then ask maintainers whether they will provision/list a new game. Do not make public-service availability a dependency until they explicitly agree.


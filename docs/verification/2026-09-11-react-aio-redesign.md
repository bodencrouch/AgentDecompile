# React AIO redesign verification

The frontend entry is `/react` in Vite and packaged delivery. The new `WorkstationApp` replaces the old React shell, with independently implemented layouts based on direct Chromium inspection of [RzWeb](https://rizin.pages.dev/analyze?cache=true), [decomp.me new scratch](https://decomp.me/new), and a public decomp.me scratch editor. No third-party source was copied.

## Delivered behavior

- Binary sessions, searchable function rail, analysis tabs, shared address history, evidence inspector, and a resizable Activity/Logs/Jobs/Problems dock.
- Scratch creation, source/context/options editing, target assembly, compiler and objdiff output, local persistence, JSON/C downloads, and metadata-driven matching targets.
- Draft retention across analysis tabs; serialized saves and corrupt-record recovery; receipt identity validation and explicit unavailable compiler states.
- Desktop split editor and comparison layout. At 390px, source/context/options/target/output switch within the workspace, with functions, evidence, and activity available from the bottom controls.
- Canonical route/deep links and legacy redirects; asset MIME handling and missing-asset404 behavior.

## Validation

- Frontend TypeScript and final production build passed. Packaging used a temporary NVMe copy with the exact lockfile and system Node22 after the default Node executable and dependency reads stalled on MyBook. All96 source/configuration hashes matched the canonical checkout; generated assets were copied back and verified through the canonical server.
- Four frontend check files, fourteen assertions passed with one worker. An earlier unrestricted runner exited137 without an assertion failure.
- Canonical routing and matching preset metadata Python selfchecks passed.
- Independent implementer/reviewer passes resolved routing, scratch save ordering, receipt/preset validation, modal focus, reference source, offset history, retained scratch lifecycle, and mobile dock findings.
- Chromium was re-driven through the actual reference pages after the user reported accidental interference.
- Vite Playwright passed local ELF ingestion and SHA256/byte validation, strings, offset reload, snapshot export, modal shortcut focus, unfinished scratch retention, saved scratch reload, context-plus-source C download, disabled unbound compile, desktop/mobile/tablet layouts, mobile dock reopening, and function rail navigation.
- Live HTTP checks passed bare `/react`, extensionless nested documents, query-preserving legacy redirects, and encoded missing-JavaScript404 on ports5174 and8767.
- Packaged browser interactions initially passed, but the uncaught-error assertion caught missing Monaco services. Shared runtime registration now loads editor features before language setup initializes its service container. Independent review of installed Monaco0.55.1 confirmed that the tokenizer setup previously took the one-time singleton snapshot before the five late services registered; the eager import registers all five first. This fixes the order for both source and scratch editors. Final packaged acceptance is recorded below.

## Scope and evidence boundaries

Local ELF/PE ingestion uses the existing metadata parser: it provides actual bytes and strings, but does not embed Rizin WASM or invent a local function inventory. Native analysis and compilation use existing backend capabilities. No configured compiler target was available during the local scratch acceptance run, so no successful compile or byte-equivalence claim is made. A completed job is not proof of a match.

The workspace disk stalled repeatedly, and the native8080 backend was unavailable during final frontend checks. The8767 packaged proxy was restarted using installed system-Python dependencies. Browser success here proves the exercised frontend and local persistence flows, not native decompilation, installed-wheel delivery, or an end-to-end recovery run.

## Final acceptance

PASS: final packaged browser run on `http://127.0.0.1:8767/react`, with visible Monaco syntax editor, rendered candidate source, local ELF identity/bytes, offset reload, snapshot export, modal focus, strings, scratch retention/save/reload, combined context/source C download, unavailable compiler gate, desktop1440/mobile390/tablet768, mobile dock reopen, function rail, and zero uncaught page errors.

Served entry: `index-D4AQLePO.js`; stylesheet: `index-CQLJ5jrE.css`. HTTP200 content types were JavaScript and CSS respectively, and response bytes matched the built files. A concurrent coverage-label edit was incorporated into another successful TypeScript/build run; generated assets remained byte-identical to the browser-tested build. Source/configuration hashes were rechecked afterward.

Desktop and mobile screenshots were visually reviewed against the generated design board. The final interface retains its compact dark chrome, central code/comparison panes, contextual rails, and mobile editor priority; reference sample functions and scores were not inserted as application data.

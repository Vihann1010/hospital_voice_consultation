# Evanta HMS desktop app (Windows exe)

Status 2026-11-24: scaffold written, obfuscation pipeline built and bug-fixed and verified in a browser.
Nothing has been built into an actual .exe or run on Windows yet (no Rust toolchain on this Mac).

## What exists now
- `deploy/onprem/desktop/src-tauri/`: a Tauri (Rust) window shell. It holds NO clinical code — it waits for
  `https://127.0.0.1:3443/api/v1/health/live` to answer, refusing to load anything over plain HTTP, then
  shows the window. See its own README for the full plan (local HTTPS, the exe, hooking it into the same
  hub release/update channel as the rest of the pilot).
- `frontend/scripts/obfuscate-build.mjs` + `npm run build:secure`: runs after `next build`, obfuscates the
  shipped JS chunks (renamed identifiers, encoded strings, light control-flow flattening tuned for the weak
  node PCs), then wraps each file in its own function so it cannot collide with another chunk.

## A real bug found and fixed before anything shipped
Next.js ships each page's JS as classic (non-module) `<script>` tags, and ALL of those share one top-level
scope in a real browser. Obfuscating each file alone can give two unrelated chunks the same short top-level
variable name (the minifier's own, not the obfuscator's) — the second one then throws
`Identifier 'd' has already been declared` and the whole app goes blank. First attempt (a per-file name
prefix) did not fully fix it, because the collision came from a name the obfuscator deliberately leaves
untouched (`renameGlobals: false`, to protect Next's own internals). The real fix: wrap every obfuscated file
in its own `(function(){ ... })();`, so each chunk's top level becomes a function scope and cannot collide
with any other chunk, regardless of what either file names its variables. Verified by loading the actual
built chunks in order in a sandboxed iframe and bisecting which pair failed — confirmed broken, confirmed
fixed, by running it, not by reasoning about minified code.

## What is NOT done or verified
- Never built as a Windows `.exe` (needs a Windows machine or CI runner with the Rust toolchain + Tauri CLI).
- **Local HTTPS is built and tested (2026-11-24):** `deploy/onprem/native/https/Caddyfile` fronts the
  existing api (:8000) and web (:3000) ports at `https://127.0.0.1:3443`. Caddy issues its own local
  certificate authority on first run (`tls internal`) — nothing shared between hospitals, nothing sent
  anywhere. `setup.ps1` downloads Caddy, validates the config, and runs `caddy trust` (needs an
  administrator PowerShell — same requirement as the update tasks; a non-admin run is told exactly what to
  re-run). `start.ps1`/`stop.ps1`/`status.ps1` start, stop and report on it alongside the rest of the stack.
  Tested on this Mac with the real Caddy binary: config validates, and a live request through the real
  reverse proxy reached both the web port and a stand-in API port over HTTPS with a certificate Caddy itself
  issued. NOT tested: `caddy trust` itself (it writes into the OS trust store, so it is refused on a
  development machine by design — it needs to happen on the real PC, with your own approval) and the whole
  path through WebView2 on actual Windows.
- No icon set for the Tauri bundle (`src-tauri/icons/` is empty — bundling will fail without one).
- No code signing. Windows SmartScreen will warn on first run until there is a certificate.
- Obfuscated build checked only on the login page with the backend down (same blank state as the
  unobfuscated build, zero console errors either way) — NOT yet clicked through vital station, briefs,
  scribe, reception, IPD, billing etc. with a real backend. Audio recording and WebSocket paths especially
  need their own pass: `controlFlowFlattening`/string encoding can be slower on first load, and the weak
  node PCs are exactly where that would be felt.
- The exe itself is not yet wired into the hub release/update system (`updater.py` still only swaps `app/`).
- `javascript-obfuscator` and `glob` are added as new frontend devDependencies; `build:secure` is a new
  script alongside the existing `build` (used for anything NOT meant to be obfuscated, e.g. local dev debug
  builds).

## Honest limit, stated once, for whoever reads this later
No build step makes an app "impossible to reverse engineer" — this one raises the cost of casual copying of
the UI code, nothing more. The actual protection for patient data is server-side: HTTPS with a pinned local
certificate, every request checked for a valid session and role on the server, and no AI keys or clinical
logic ever compiled into the client. See [[ui-redesign]], [[satya-day1-deploy]], [[later-tasks-ui-and-ai]].

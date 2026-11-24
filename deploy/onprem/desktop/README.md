# Evanta HMS desktop app (Windows)

Status: scaffolded 2026-11-24, NOT built or run anywhere yet. This Mac has no Rust toolchain and cannot
produce a Windows `.exe`; the first real build and test must happen on a Windows machine or a Windows CI
runner. Nothing here has touched the admin PC.

## What this is
A Tauri (Rust) shell around the existing Next.js frontend. It is a window, not an app: all clinical logic,
the AI calls and the Onito bridge stay exactly where they are today (`D:\EvantaHMS\app\backend`, the hub).
This folder adds no new server code — it only changes how staff open the same HMS.

## Why Tauri, not Electron
Electron ships a full Chromium (200–300 MB of RAM per copy); the node PCs are weak. Tauri uses the OS's own
WebView2 component (already on Windows 10/11 or a ~130 MB one-time install) and the app itself adds roughly
15–30 MB. See [[satya-admin-pc]] for why memory headroom matters here.

## Pieces (to build, in order)
1. **Local HTTPS** (`../https/`, not yet written): a small Caddy instance already in the bundle serves
   `https://127.0.0.1:3443`, proxying to the existing `127.0.0.1:8000` (API) and `127.0.0.1:3000` (web), with
   a certificate from one local, hospital-only certificate authority. `install.ps1` will add that CA to the
   Windows trust store (once, at setup) so the padlock is real, not a clickthrough warning.
2. **This shell** (`src-tauri/`): waits for the health check to pass over that HTTPS URL, then shows the
   window. It never falls back to plain HTTP.
3. **Build hardening**: `next build` output is minified by default; we additionally run it through a JS
   obfuscator (`javascript-obfuscator`, to be wired into `frontend`'s build) for the production bundle only,
   never for `next dev`. React devtools and source maps are stripped from what ships.
4. **The exe**: `cargo tauri build --target x86_64-pc-windows-msvc` on Windows produces
   `Evanta HMS_0.1.0_x64-setup.exe` (NSIS installer). It is *not* code-signed yet — Windows SmartScreen will
   warn on first run until we get a code-signing certificate; note this for the owner before wider rollout.
5. **Updates**: the exe itself is just the shell and rarely changes. It is published to the SAME hub release
   channel as the rest of the pilot (`hub/app/routes_releases.py`), tagged manual/automatic/urgent exactly
   like a backend/web release; `updater.py` on the PC, once extended, swaps `Evanta HMS.exe` the same way it
   swaps `app/`. The web/API code inside keeps using its existing release+updater path unchanged.

## What is real security, and what is theatre
- Real: HTTPS with a pinned local CA, a server that enforces login and roles on every request, no secrets
  compiled into the binary, a stripped/obfuscated JS bundle that slows down casual copying.
- Theatre, avoided: claiming the app "cannot be reverse engineered". Any binary can be disassembled given
  enough effort; the goal here is that doing so reveals nothing useful, because nothing sensitive is in it.

## Known gaps (none of this is done yet)
- Local HTTPS files (`../https/ca.md`, Caddy config) not written.
- No icon set in `src-tauri/icons/` (Tauri bundling will fail without one — placeholder needed before a real
  build).
- `install.ps1` additions for the CA and the shortcut not written.
- Code signing: none. Plan for it before this goes beyond the pilot.
- Never built, never run. Build and test on Windows before telling the owner it works.

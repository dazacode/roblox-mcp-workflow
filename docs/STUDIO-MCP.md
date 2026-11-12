# Studio MCP servers: which one, and how it is installed

This workflow runs against **two** Studio MCP servers side by side. Neither replaces the other; each
is the default for a different set of jobs.

| | `rbx-studio` (community, [EL4CTEO/rbx-studio-mcp](https://github.com/EL4CTEO/rbx-studio-mcp), MIT) | Roblox built-in Studio MCP |
|---|---|---|
| Tool prefix | `mcp__rbx-studio__*` | `mcp__Roblox_Studio__*` |
| Strengths | batched atomic edits with one Ctrl+Z, editor-safe script writes (unsaved work survives), stale-edit refusal via `rev`, property-name checking against the live engine, Rojo-style two-way `sync`, client-side readers in playtests, handles that survive renames, MicroProfiler ranking, device emulation, claimed lower per-call latency | AI generation (`generate_mesh/material/texture/animation/avatar/scene/procedural_model`), 17 shipped `rbx-*` skills, keyless **scope-gated** `open_cloud_invoke` (Studio enforces per-game permissions), Creator Store search/insert, `subagent` playtest/explore |
| Transport | stdio -> local binary -> `127.0.0.1:44755` -> Studio plugin | stdio -> Studio itself |
| Cloud auth | needs a long-lived Open Cloud **API key** stored as plaintext JSON in `~/.rbx-studio-mcp/credentials.json` | none stored; Studio's own scoped token |

## Default routing in this workflow

**Default = `rbx-studio`** for everything inside Studio: reading the tree, inspecting, finding, editing
scripts (`script_edit`), creating/modifying instances, `sync`, playtest control, console/debug/performance,
screenshots/viewport/device, `execute_luau` (including loading `shared.Forge`).

**Use the built-in server for** anything it alone offers: `generate_*`, `skill` (the `rbx-*` skills),
`search_asset`/`insert_asset`, `subagent`, and **all Open Cloud calls** via `open_cloud_invoke`.

**Do not configure an Open Cloud API key in `rbx-studio`.** It is not needed (the built-in tool does uploads
without storing a secret) and a plaintext long-lived key that can publish, ban players and sell products is
the largest piece of risk the community server adds.

> **Latency (measured 2026-11-12, `scripts/bench_mcp.py`, raw stdio, 40 calls x 3 read-only scenarios):** the built-in
> server takes **~51 ms median** per `execute_luau` (min 15 ms, p95 ~65 ms), independent of payload size (20 KB
> returns are the same). `rbx-studio` could **not** be measured fairly: only one process can own its bridge, and a
> second instance runs as a peer on a deliberately summarised path (~38 s per call observed). The project's
> "13.6 ms vs 25.8 ms" claim compares its push transport with *polling* transports, not with the built-in server,
> so it doesn't answer "which is faster". Practical view: both are far below model latency, so choose by
> features, not milliseconds. To measure `rbx-studio` yourself, run the script with that MCP server stopped.

## Operational notes (learned the hard way)
- **Long yielding Luau can wedge `rbx-studio`'s channel.** A web-lookup loop (58 `GetProductInfoAsync` calls) and a
  batch of `PreloadAsync` calls sent via `execute_luau` timed out at 60 s, and every later request (even
  `studio_status`) queued behind it for minutes while Studio was healthy. Pattern that works: start the work with
  `task.spawn`, write results into `shared`, return immediately, then read `shared` back. **`shared` is common to both
  servers**, so if one channel is stuck, read the results through the other.
- Studio reporting `unreachable: true` in `list_studios` just means it is busy, not gone.
- **A minimized Studio does not render.** Captures come back dark/empty (built-in `screen_capture`, rbx-studio
  `screenshot`, a window grab) and commands that need a frame can time out. Check `IsIconic` on the main window and keep
  it restored for visual work. Studio owns many top-level windows (most hidden/tiny); pick the largest visible one.
- **The built-in `screen_capture` only works in Edit mode** (it returns just the core UI layer during Play). For a
  Play-mode picture use rbx-studio's `screenshot` (needs a responsive channel) or `scripts/grab_studio_window.ps1`, which
  uses `PrintWindow` and so works even when other windows cover Studio (not when it is minimized).
- **Relaunching a cloud place from the shell works** (verified): `Start-Process "roblox-studio:1+launchmode:edit+task:EditPlace+placeId:<placeId>+universeId:<universeId>"`.
  Studio may run its self-updater first (a minute or two); then wait for a window titled with the place name and for
  `list_roblox_studios` to show it. Check `Process.Responding` rather than assuming a slow start is a hang.
- **A long-running Studio session can render wrongly, and you will blame the wrong thing.** We spent hours attributing
  "washed-out, pale facades" to materials, lighting, textures and an orphaned effects pack, with plausible-looking
  evidence and lever tests. After a fresh Studio start **the identical scene, with identical settings, looked correct in
  both Edit and Play**; the earlier sessions (running at 2.8-3.8 GB) had a degraded rendering/texture state. Rule: reproduce
  any visual problem in a **fresh Studio session before investigating content**, and if it recurs capture Studio's memory
  and `Stats:GetMemoryUsageMbForTag(Enum.DeveloperMemoryTag.GraphicsTexture)` *before* restarting.
- **Don't mass-edit the play session.** Tinting ~86k parts in a playtest and then stopping and restarting left Studio
  "Not Responding" for 5+ min (one core pinned, ~2.5 GB) until it was force-quit. Nothing was lost (play edits are never
  saved), but keep bulk play-only changes small (one region), and stop/start playtests with a pause between them.
- **Studio gets a new studio ID whenever it restarts or the window is recreated** (also across Edit/Play). Re-run
  `list_roblox_studios` after any restart before reusing an ID.
- Chunk big walks (`task.wait()` every ~40k instances); a full read-only pass over ~413k instances took ~5.6 s.
- A log warning is not a defect. "Failed to load" lines were all `AssetFetchStatus.Success` on a direct fetch; verify
  with a direct fetch (and in a Play-mode client) before calling anything broken.

## Vetting record (2026-11-11)

Reviewed commit `fcf174ef789beef9b4d4de5891be17d9d82683ee` (v1.2.2, 2026-11-09, MIT, one maintainer, ~15 stars,
created 2026-08-20). Read: README, `package.json`, launcher `bin/rbx-studio-mcp.js`, `scripts/install-plugin.mjs`,
`scripts/build-plugin.mjs`, `server/build.rs`, `server/Cargo.toml`, `cloud/credentials.rs`, the bridge listener
and header checks, `plugin/src/Secret.luau`, the release workflow, and every URL literal in `server/src` and
`plugin/src`. **Not** read line-by-line: the ~1.2 MB of plugin Luau handlers and the Rust tool implementations.

Findings:
- Outbound hosts: `127.0.0.1` (bridge), `apis.roblox.com` (Creator Store search; Open Cloud only if a key is set),
  `raw.githubusercontent.com` (public Roblox API dump). No telemetry, no unknown hosts. Plugin only talks to loopback.
- Bridge binds `127.0.0.1` only, rejects any request carrying an `Origin` header, requires a custom client header,
  and validates `Host` (DNS-rebinding defence).
- `build.rs` only embeds `plugin/src` and `vendor/LibMP.luau` (Roblox's MIT MicroProfiler library). Benign.
- The panel can launch coding agents (`chat on`, opt-in). Claude Code is run with
  `--allowedTools mcp__rbx-studio --permission-mode dontAsk`; other agents use their own settings.
- **Supply chain:** the published npm package runs a *prebuilt* binary from a separate platform package. There
  is no npm provenance attestation and the repo's `prepublishOnly` script suggests local publishing, so that
  binary cannot be tied to the source. **Mitigation used here: build from the reviewed commit with
  `cargo build --release --locked`** (dependency versions/checksums pinned by `Cargo.lock`).
- Build verification (Windows x64, Rust nightly 1.101 since the pinned 1.99.1 wasn't installed): `cargo build
  --release --locked` succeeded in 4m12s -> 14.3 MB binary. An independent stdio MCP handshake (not through any
  client) initialised as `roblox-studio-mcp` v1.2.2 and listed exactly the 35 advertised tools with empty stderr.
  **Not yet verified:** the Studio-side connection (needs the user to accept the `127.0.0.1` prompt) and any
  latency comparison.
- Residual risk: the plugin executes arbitrary Luau in Studio by design (that is the feature). Only connect it
  to places you are willing to let an agent modify, and review `allow` groups in the panel.

## Install (from source, pinned)

```bash
git clone https://github.com/EL4CTEO/rbx-studio-mcp.git ~/tools/rbx-studio-mcp
git -C ~/tools/rbx-studio-mcp checkout fcf174ef789beef9b4d4de5891be17d9d82683ee
cd ~/tools/rbx-studio-mcp
cargo build --release --locked --manifest-path server/Cargo.toml    # needs Rust >= 1.99.1
node scripts/install-plugin.mjs                                     # builds + copies StudioMCP.rbxmx into Studio's Plugins folder
claude mcp add rbx-studio -s user -- node ~/tools/rbx-studio-mcp/bin/rbx-studio-mcp.js
```
Open Studio, accept the `127.0.0.1` HTTP prompt (**you** must click it), then call `studio_status`.
`node bin/rbx-studio-mcp.js doctor` explains what is wrong if it doesn't connect. Update by reviewing the new
diff and moving the pinned commit - do not `npx -y` a floating version.

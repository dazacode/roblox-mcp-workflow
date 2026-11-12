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

> The latency claim (13.6 ms vs 25.8 ms per call in the project's README) is the maintainer's and was **not**
> independently measured here. To measure: run 50 sequential `execute_luau` calls of `return 1` through each
> server and compare medians. "Faster" matters less than correctness for a workflow whose bottleneck is the
> model, so treat it as a tiebreaker, not a reason to use a tool for something it doesn't do.

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

# Roblox MCP Workflow

An AI-first build + debug workflow for Roblox Studio, for Claude Code and other MCP-capable agents.
It sits **on top of** the Studio MCP servers and Roblox's `rbx-*` skills (it doesn't replace them) and adds what
they lack:

- a **headless Blender asset pipeline** (parallel, killable, structured errors) with Roblox-aware validation,
  automatic triangle-budget splitting, 4-view previews and a **manifest** (the contract between Blender and Studio);
- **structured Studio diagnostics** (`Probe`, `Log`, `Check`) that return compact JSON with stable codes and a `fix`
  string, hard-capped so they are safe on 350k-instance places;
- an **operating workflow** (`WORKFLOW.md`) and agent skills: the loop, tool routing between servers, a debug protocol,
  speed and safety rules.

```
 idea -> spec (5 lines) -> Blender job (headless, parallel) -> validate -> preview PNG -> GLB + manifest
                                                                                  |
        Studio MCP  <-- upload/insert (user-approved, `rbx-import-asset` skill) <-+
              |
   Probe.scan / compare / shots   Log.digest   Check.run     (shared.Forge, JSON out, hard-capped)
              |
        fix strings -> execute_luau -> re-measure -> screenshot -> done
```

> Not affiliated with or endorsed by Roblox Corporation. "Roblox" and "Roblox Studio" are trademarks of their owner.

## Quick start

Requirements: Python 3.9+ (tested on 3.13), Blender 4.x (tested on 4.1; for the asset pipeline), Roblox Studio with
an MCP server (see `docs/STUDIO-MCP.md`).

```bash
python forge.py doctor                       # Blender + toolchain discovery
python forge.py selftest                     # 5-check regression gate (~20 s)
python forge.py blender run blender/examples/torii_gate.py --args '{"out_dir":"out"}'
python forge.py luau bundle                  # writes dist/load_forge.luau (+ per-module loaders)
```
Then in Studio (via MCP): `execute_luau` with the contents of `dist/load_forge.luau` once per DataModel, and call
`shared.Forge.Probe.scan{root="Workspace.MyModel"}`. Nothing is written into the place file.

### As a Claude Code plugin

```bash
claude plugin marketplace add dazacode/roblox-mcp-workflow
claude plugin install roblox-mcp-workflow@roblox-mcp-workflow
```
This installs the two skills (`forge-blender-to-roblox`, `forge-verify-loop`). It deliberately does **not** register
any MCP server for you: see `docs/STUDIO-MCP.md` for what to connect and how to vet/install it.

## Layout

| Path | Purpose |
|---|---|
| `WORKFLOW.md` | **Start here.** The loop, tool routing, debug protocol, speed and safety rules |
| `docs/STUDIO-MCP.md` | the two Studio MCP servers, default routing, a security vetting record, pinned source install |
| `docs/REVERSE-ENGINEERING.md` | REA: vetting, status, what it is (and is not) for |
| `docs/STATIC-ANALYSIS.md` | selene / luau-lsp / StyLua pitfalls, triage reality, the baseline regression gate |
| `docs/TESTING.md` | Wally + Jest + Rojo unit testing driven by MCP: pattern, facts, gotchas |
| `templates/validate.py` | drop-in static-analysis gate for a synced `src/` tree |
| `templates/testing/` | `test.py` one-command runner, `TestRunner.luau`, `RunOnPlay.server.luau`, `jest.config.luau` |
| `scripts/bench_mcp.py` | raw-stdio latency benchmark for Studio MCP servers |
| `forge.py` | JSON-only CLI: `doctor`, `blender run/batch`, `selftest`, `luau bundle` |
| `blender/forge_runner.py` | runs inside Blender; turns any script outcome into one structured JSON result |
| `blender/rbx_lib.py` | helpers: bmesh primitives, colour, validate, split-to-budget, export + manifest, preview |
| `blender/examples/`, `blender/tests/` | torii-gate example; selftest jobs |
| `luau/Probe.luau` `Log.luau` `Check.luau` | Studio-side diagnostics (session-only via `shared.Forge`) |
| `skills/` | agent skills (also used by the plugin) |
| `docs/RESEARCH.md` | research, decisions with evidence, bugs found, **unverified assumptions** |
| `docs/CALIBRATION.md` | one-time, approval-gated upload test that pins importer scale/orientation |
| `CLAUDE.md` | instructions for AI agents working in this repo |

## Status (honest)

Verified: headless Blender 4.1 jobs, validation, auto-split, previews, GLB export, manifests, structured errors,
parallel batch, `selftest` 5/5; Studio-side Probe/Log/Check against a real 347k-instance place.
**Not yet exercised:** an actual upload/import round trip (needs a published place and granted permissions), so
importer scale/orientation behaviour is still assumed - see `docs/CALIBRATION.md`. `units="studs"` is experimental.
Windows is the tested platform; the scripts are stdlib Python and should work elsewhere but are untested there.

## Contributing

Issues and PRs welcome. Keep the verified / sourced / unverified discipline in `docs/RESEARCH.md`, and run
`python forge.py selftest` before sending Blender-side changes.

## License

MIT. See `LICENSE`.

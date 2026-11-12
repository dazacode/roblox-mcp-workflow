---
name: forge-verify-loop
description: Use after building or changing anything in Roblox Studio via MCP, and whenever debugging a Roblox runtime error, broken import, floating/grey/mis-scaled model, or "it doesn't work". Replaces eyeballing with structured probes (Probe.scan/compare/shots, Log.digest, Check.run) and a measure -> diff -> repair loop.
---

# Forge verify + debug loop

Paths are relative to the repo root (plugin: `${CLAUDE_PLUGIN_ROOT}`). Read `WORKFLOW.md` (Debug protocol,
Studio verification, Safety rules) for detail.

**Before anything:** check Studio state (`studio_status` / `get_studio_state`). If Play mode, don't stop the user's
playtest; use Server/Client DataModels read-only.
**Load tools once per DataModel:** `python forge.py luau bundle` (generates `dist/`), then run `dist/load_forge.luau`
via `execute_luau` -> `shared.Forge.{Probe,Log,Check}`. Nothing is written to the place.
Hot-reload one module with `dist/load_<Module>.luau`.

Build verification:
1. `return shared.Forge.Probe.scan{root="Workspace.X"}`  (refuses > 20k descendants: scope down)
2. With a manifest: `Probe.compare("Workspace.X", manifest)` -> exact `ScaleTo` factor / `Color3.fromHex`.
3. Apply `fix` fields in one `execute_luau`; end with `ChangeHistoryService:SetWaypoint(...)`.
4. Re-scan until no error/warn. Then `Probe.shots(root)` -> `screen_capture` for the visual check.

Runtime debugging:
1. Reproduce with `start_stop_play` + input tools (or the `playtest` subagent).
2. `return shared.Forge.Log.digest{sinceSeconds=120}` in **Server**, then **Client**. Branch on `code`.
3. Hypothesis -> smallest read-only probe -> fix -> **same repro** -> digest must say `clean`.
4. Add `Log.emit` events for state that matters; read with `Log.events(tag)`.

Never claim done from intent: report the probe output that proves it.

---
name: forge-blender-to-roblox
description: Use when a Roblox task needs a custom 3D asset that primitives/generate_mesh can't do well - exact shapes, hero props, budgeted meshes, kit-bashed scenery - or when importing any Blender/GLB/FBX model into Studio. Builds the asset in headless Blender, validates it against Roblox limits, previews it, writes a manifest, and verifies the import in Studio.
---

# Blender -> Roblox (Forge)

Paths below are relative to the repo root (when installed as a plugin: `${CLAUDE_PLUGIN_ROOT}`).
Read `WORKFLOW.md` first; this is the short procedure.

1. `python forge.py doctor` (once). Blender path comes from `BLENDER_PATH` or Program Files.
2. Write a job script (copy `blender/examples/torii_gate.py`). Rules: metres, Z-up, front = -Y,
   `rbx_lib` helpers (bmesh, not `bpy.ops`), **one material per mesh** (join per material),
   unique clean names, colours via `R.hex_color("#rrggbb")`.
3. `python forge.py blender run job.py --args '{"out_dir":"out"}'` - read the JSON. `ok:false` carries
   `error.line`, `error.code`, `error.hint`. Fix and re-run; it takes ~3 s.
4. **Open the preview PNG** (`Read` the path) and check shape, proportions, parts in the right place.
   Only then trust the numbers. Fix `findings` with `sev` error/warn (each has a `fix`).
5. Ask the user to approve the upload (permanent assets; say whose account; need `asset:write` +
   approved folder). Then follow Roblox's `rbx-import-asset` skill for upload -> insert -> repair.
   Do not re-upload to dodge a pending moderation state.
6. Verify with `shared.Forge.Probe.compare(root, manifest)` then `Probe.scan`, apply the `fix` strings,
   `SetWaypoint`, `Probe.shots` + `screen_capture` to confirm orientation (asymmetric feature).
7. Record asset ids in `out/ledger.json`.

Many assets? Put jobs in `jobs.json` and `python forge.py blender batch jobs.json --workers 4`.
Run `python forge.py selftest` after changing `rbx_lib.py`.

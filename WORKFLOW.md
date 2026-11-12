# Roblox Forge - operating workflow (for the AI agent)

Goal: build anything in Roblox at machine speed, and make every failure *legible* so the
agent fixes it instead of guessing. Three ideas carry the whole design:

1. **Contract-first.** Every build step emits a machine-readable expectation (a *manifest*).
   Every verification step diffs reality against that manifest. Never eyeball numbers.
2. **Structured observability.** Tools return compact JSON with stable `code`s and a `fix`
   hint. Screenshots are for *looking* (aesthetics, orientation), never for measuring.
3. **Stateless, parallel workers + one writer.** Blender runs as throw-away headless
   processes (parallel, deterministic, killable). Studio has exactly one writer at a time.

## The loop

```
SPEC -> BUILD -> MEASURE -> DIFF -> REPAIR -> LOOK -> SHIP
  |        |         |         |        |        |       \_ save_place / commit, only on request
  |        |         |         |        |        \_ screen_capture (Probe.shots args) - 1-4 shots
  |        |         |         |        \_ apply the `fix` field of each finding; re-MEASURE
  |        |         |         \_ Probe.compare(root, manifest)  /  Log.digest()
  |        |         \_ Probe.scan(root)  /  forge.py selftest  /  validate() in Blender
  |        \_ Blender job | generate_* | execute_luau chunk | multi_edit
  \_ 5-line spec: what, where, size in studs, budget, acceptance check
```

Finish one subsystem and pass its check before starting the next. Changing the spec
mid-build is the main cause of conflicting code - write the change into the spec first.

## Tool routing

Two Studio MCP servers are expected (details, vetting and install: `docs/STUDIO-MCP.md`):

- **`rbx-studio`** (`mcp__rbx-studio__*`, community) is the **default** for everything *inside* Studio.
- **Roblox built-in** (`mcp__Roblox_Studio__*`) is used for what only it offers: `generate_*`, the `rbx-*`
  `skill`s, `search_asset`/`insert_asset`, `subagent`, and **every Open Cloud call** (`open_cloud_invoke`).
  If only one server is connected, use the built-in equivalents in the right-hand column.

| Need | Default (`rbx-studio`) | Built-in equivalent / notes |
|---|---|---|
| What's in the place? | `tree`, `inspect`, `find` | `search_game_tree`, `inspect_instance`. Scope to a path; never walk the whole place (a real project here: 347k instances). Also `Probe.tree` |
| Analyse a model/area | `execute_luau` -> `shared.Forge.Probe.scan{root=...}` | hard-capped (20k descendants); returns grouped findings |
| Edit scripts | `script_edit` (atomic batch, one Ctrl+Z, `rev`-checked), `sync` | `multi_edit`. With Rojo, **never** edit scripts in Studio - sync will fight you |
| Create/modify instances | `create`, `modify`, `delete`, `move` (property names engine-checked) | `execute_luau` |
| Bulk instance work | `execute_luau` in chunks, `task.wait()` per chunk | one big unyielding call freezes Studio and drops the MCP link |
| Blocky/prop scenery | `generate_procedural_model`, `generate_scene` | fast, no upload, no moderation |
| Quick organic mesh | `generate_mesh` (+ `generate_texture`/`generate_material`) | Roblox-native; good for background props |
| Hero / exact / budgeted mesh | Blender job -> GLB -> `rbx-import-asset` skill | needs user approval (permanent uploads) |
| Animation | `generate_animation` | R15, up to 10 s |
| Look at it | `screenshot` / `viewport` (built-in: `screen_capture`) with `Probe.shots(root)` args | after numbers pass, not before |
| Runtime bug | `playtest`, then `Log.digest` in **Server and Client** (`console`, `debug` for more) | see Debug protocol |
| Gameplay flow test | Studio `subagent` type `playtest` | verifies via world state + console |
| Perf | skills `rbx-perf-profiling`, `rbx-scene-analysis`, `rbx-luau-heap-profiling` | |
| Cloud (assets, passes, universe) | `open_cloud_invoke` after skills `rbx-open-cloud-usage` + `rbx-permissions` | |
| Docs | `http_get` via skill `rbx-docs-search` | don't answer API questions from memory |
| Static check of `src/` | `python scripts/validate.py` (selene + luau-lsp + baseline gate) | `docs/STATIC-ANALYSIS.md`; gate on regression, sample before calling anything a bug |
| Audit a third-party tool/plugin/binary you run | REA (`mcp__rea__*`) | `docs/REVERSE-ENGINEERING.md`: scope, status, limits. **Never** aimed at Roblox Studio/client/engine |
| Hard gameplay bug | `Log.digest` (Server+Client) -> `rbx-debug` breakpoints -> profilers | reverse engineering the engine does not find game-logic bugs |

## Blender -> Roblox pipeline

```
python forge.py blender run  <job.py> [--args '{...}']     # one asset, ~3 s
python forge.py blender batch jobs.json --workers 4        # many assets in parallel
python forge.py selftest                                   # regression gate (5 checks)
```
A job is a ~30-line Python file using `rbx_lib` (see `blender/examples/torii_gate.py`):
author in **metres, Z-up, front = -Y**, one material per mesh, then
`R.export(meshes, out.glb, features={...})` -> validated GLB + `out.glb.forge.json`, then
`R.render_preview(...)` -> a 4-view contact sheet you **must look at** before uploading.

Hard rules (each one earned by a real failure while building this kit):
- **Look at the preview.** A bad transform produced a perfectly "valid" file with every part
  stacked at the origin; only the render revealed it. Numbers alone passed.
- Use the data API/bmesh. `bpy.ops` fails headless. Call `R.sync()` before reading
  `matrix_world` of objects you just created (library helpers already do).
- 20,000 triangles per mesh (official). `export()` **refuses** over-budget meshes;
  pass `auto_split=True` to split into `<Name>_Part<N>`.
- One material per mesh. Join parts *per material* and export a multi-mesh model.
- Colours: use `R.hex_color("#rrggbb")`. Blender stores linear; the manifest carries the sRGB
  hex that Studio's `MeshPart.Color` should equal, and `Probe.compare` checks it.
- Uploads are **permanent and owned by the game owner**. Batch them, ask once, never re-upload to
  "retry" a pending moderation state. Record every asset id in `out/ledger.json`.

## Studio verification (after insert)

1. `shared.Forge.Probe.compare(root, <manifest json as Luau table>)` -> SCALE_MISMATCH gives the
   exact `ScaleTo` factor; COLOR_MISMATCH gives the exact `Color3.fromHex`; MISSING_MESH names it.
2. Apply the `fix` fields in one `execute_luau`, end with
   `ChangeHistoryService:SetWaypoint("<what>")` so the user can undo in one step.
3. `Probe.scan{root=...}` again: UNANCHORED / FLOATING / DEFAULT_GREY_MESH must be gone.
4. `Probe.shots(root)` -> `screen_capture` -> confirm the asymmetric feature (e.g. torii plaque)
   is on the side the manifest says. Orientation is **not** auto-verified; this is the check.

## Debug protocol (make bugs legible)

1. **Reproduce deterministically**: `start_stop_play`, drive with `character_navigation` /
   `user_keyboard_input` / `user_mouse_input` - or the `playtest` subagent for multi-step flows.
2. **Digest, don't read**: `return shared.Forge.Log.digest{sinceSeconds=120}` in `Server`, then in
   `Client`. Groups are de-duplicated, carry `script`+`line`, and a `code`
   (`NIL_INDEX`, `BAD_MEMBER`, `INFINITE_YIELD`, `ASSET_LOAD_FAIL`, `HTTP_DISABLED`, ...) with the usual fix.
3. **Hypothesis -> smallest read-only probe -> fix -> same repro -> digest again.** The verdict
   must flip to `clean`; "it looks fine" is not a result.
4. **Instrument state you care about**: `Log.emit("info","inventory",{...})` then
   `Log.events("inventory")` gives typed events instead of grepping strings.
5. Stubborn logic bug: skill `rbx-debug` (breakpoints, thread inspection).
6. Ad-hoc assertions: `Check.run{ {"name", fn}, ... }` -> pass/fail JSON with traces.
   Real unit tests for ModuleScripts: skill `rbx-unit-test`.

Load Luau tools once per DataModel (Edit and each Play Server/Client have separate `shared`):
`dist/load_forge.luau` -> `execute_luau`. Hot-reload one module with `dist/load_<Module>.luau`.
Nothing is written into the place; reload after every Edit<->Play switch.

## Speed rules

- One `execute_luau` per logical step; return JSON, not prose. Don't call 5 tools to learn what one probe returns.
- Parallelise what is independent: `blender batch`; read-only exploration via Studio `explore` subagent
  or Claude subagents. **Never** two concurrent writers to the same place.
- Hot-reload modules instead of re-sending the bundle (16 KB vs 1-10 KB).
- Cap everything: scans <= 20k descendants, meshes <= 20k tris, chunks <= ~1000 instances per yield.
- Verify numerically first (cheap, exact), visually second (expensive, fuzzy).

## Safety rules

- Before **every** Edit-mode call: `get_studio_state`. A user playtest may be running; do not stop it.
- `list_roblox_studios` -> confirm the target place by name before modifying someone's game.
  Prefer building into a clearly named staging folder, then moving it.
- Rojo projects: files on disk are the source of truth; Studio is a view.
- Don't enable/widen Open Cloud permissions yourself; request exactly the missing scopes (skill `rbx-permissions`).
- Never configure an Open Cloud **API key** in `rbx-studio` (plaintext on disk, can publish/ban/sell). Cloud work goes
  through the built-in `open_cloud_invoke`, whose scopes Studio enforces per game.
- Install third-party MCP servers from a reviewed, pinned commit built locally - not `npx -y` of a floating version.
- High-risk (ask first, even in autonomous mode): publishing, uploads, DataStore schema changes,
  monetization, bans, anything irreversible.

## Spec template (keep it to this)

```
WHAT:   one sentence
WHERE:  path / coordinates
SIZE:   studs (1 stud = 0.28 m), tri budget, part budget
STYLE:  palette hex values, references
CHECK:  the exact probe/assertion that must pass
```

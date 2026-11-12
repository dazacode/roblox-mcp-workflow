# Research record and design decisions

Date: 2026-11-11. "Verified" = observed on this machine in this session. "Sourced" = from the
cited page, not independently exercised. "Unverified" = assumption to confirm.

## What exists

| Piece | What it is | Status |
|---|---|---|
| Roblox Studio MCP (built in) | ~30 tools: scripts, `execute_luau` (Edit/Client/Server), `generate_mesh/material/animation/procedural_model`, `search_asset/insert_asset`, playtest + input simulation, `screen_capture`, `open_cloud_invoke`, `subagent` (explore/playtest), `skill`. stdio, enable via Assistant > Manage MCP Servers. | Verified (tools called live) |
| Studio skills (`rbx-*`) | 17 shipped skills incl. `rbx-import-asset`, `rbx-open-cloud-usage`, `rbx-permissions`, `rbx-debug`, `rbx-perf-profiling`, `rbx-unit-test`, `rbx-scene-analysis` | Verified (listed live) |
| `Chrrxs/robloxstudio-mcp` (community) | adds per-peer server/client eval, multi-client playtests, non-pausing breakpoints, profiler/memory captures, monetization via Open Cloud | Sourced (README) |
| `ahujasid/blender-mcp` (community) | Blender add-on opens a localhost socket (9876); MCP server forwards `execute_blender_code`, viewport `look`, asset/AI-gen integrations | Sourced (README) |
| Open Cloud Assets API | `POST /assets/v1/assets` Model (fbx/gltf/glb/rbxm), 20 MB/file, poll `operations/{id}`, `moderationState` | Sourced (docs) |
| Roblox model limits | <= 20,000 triangles per mesh; one material per mesh; watertight preferred; single UV set; PBR maps; textures up to 1024-4096 (docs conflict) | Sourced (docs) |

## Why headless Blender instead of the Blender MCP socket

- bpy is only safe on Blender's main thread; the socket add-on marshals work onto it, and a
  community skill reports export operations **time out** through it. A throw-away `blender -b`
  process has no UI thread to block, can be killed on timeout, and many can run in parallel
  (**verified**: 5 jobs concurrently, 20 s wall for two 48k-tri exports + 3 small jobs).
- The socket has **no authentication or encryption** (per its README) and runs arbitrary Python
  from whoever can reach the port. Headless jobs are local files with no listener.
- Scripts are plain files: diffable, reviewable, re-runnable, regression-testable (`forge.py selftest`).
- Trade-off: no live interactive viewport. We recover "seeing" via `render_preview` contact sheets.
  If you want to *watch* Blender, keep the socket MCP for exploration and use this kit for production.

## Design decisions (and the evidence)

1. **Session-only Luau loader (`shared.Forge`)**, not instances installed in the place.
   Verified: unparented ModuleScripts `require` fine and `shared` persists across `execute_luau`
   calls in the Edit DataModel. Result: zero writes to the user's place, per-module hot reload.
2. **Hard caps in every probe.** The test place has 347,786 instances / 189,458 MeshParts. A bare
   `GetDescendants` is 231 ms but per-part analysis would freeze Studio. `scan` refuses roots > 20k.
3. **Findings grouped by code with examples + a `fix` string**, so output stays small and an agent
   can branch on it. The first log digest produced 63 "distinct" groups for 2 real problems;
   normalising ids dropped it to 7 and tagged `ASSET_LOAD_FAIL`.
4. **Manifest as contract.** Blender writes expected tris/materials/hex colours/size; Studio diffs it.
5. **Render previews are mandatory.** Bug found by looking, not by validation: parts stacked at the
   origin because `matrix_world` is stale until `view_layer.update()`. All numbers looked plausible.

## Bugs found while building (all fixed, covered by tests where possible)

| Bug | Caught by |
|---|---|
| stale `matrix_world` -> all parts at origin | preview image (now `R.sync()` + examples) |
| exported mesh named `X.001` (name collision with source) | manifest review (now renames originals during export; selftest) |
| multi-material mesh accepted silently | validator warn `MULTI_MATERIAL`; example now one mesh per material |
| `GetPartBoundsInBox` given `RaycastParams` | live test on a real asset (needs `OverlapParams`) |
| log digest couldn't group asset-id warnings | live digest on the real place |
| `doctor` reported Aftman shim errors as versions | first `doctor` run |

## Unverified assumptions (confirm with `docs/CALIBRATION.md`)

- How the importer scales a GLB vs FBX. The official import skill says GLB arrives ~1 m = 1 stud
  (3.57x too small) and FBX often 1 cm = 1 stud (28x too big). `units="studs"` pre-scales to
  compensate but is **experimental** until one real upload confirms it.
- Axis/yaw mapping on import (`(x,y,z) -> (x,z,-y)` is a candidate). Verify with the manifest's
  asymmetric `features` + a screenshot.
- Whether Studio's token can upload for *this* experience (needs `asset:read`/`asset:write`, an approved
  upload folder, and the place must be published).
- The 4096 vs 1024 texture-size conflict in Roblox's own docs.

## Sources

- Roblox Studio MCP: https://create.roblox.com/docs/studio/mcp
- MCP + Open Cloud permissions: https://create.roblox.com/docs/studio/mcp-open-cloud
- Asset upload guide: https://create.roblox.com/docs/en-us/cloud/guides/usage-assets
- Modeling specifications: https://create.roblox.com/docs/en-us/art/modeling/specifications
- Texture specifications: https://create.roblox.com/docs/en-us/art/modeling/texture-specifications
- https://github.com/Chrrxs/robloxstudio-mcp
- https://github.com/ahujasid/blender-mcp
- Community Blender->Roblox pipelines: https://dev.to/thecreatorgfr/how-i-automated-3d-game-assets-with-flux-blender-and-the-roblox-api-16be

# One-time calibration (needs user approval - creates permanent assets)

Run once per machine/account. It turns the "unverified" import assumptions into recorded facts
that every later job can rely on. It costs **two tiny uploads** (a 1 m cube GLB and a 1 m cube FBX).

## Preconditions (ask the user, together, once)

- Place is published (permissions are per published game).
- MCP Permissions: `asset:read` + `asset:write` (Publish & manage assets) granted.
- An approved upload folder; export into it. (No tool lists approved folders - ask.)
- Explicit consent: assets are permanent, owned by the game owner/group, deletable only in Creator Dashboard.

## Procedure

1. Blender job `blender/calibration/cube_asym.py` (create when running): a 1 m x 1 m x 1 m cube with a
   small marker block on its **-Y** face and another on its **+X** face (two asymmetric features so
   mirroring is detectable). Export `cal.glb` and `cal.fbx` with `units="meters"`.
2. Upload both via the `rbx-import-asset` skill flow (POST `/assets/v1/assets`, poll the operation,
   read `moderationState`). Never re-upload to work around a pending state.
3. `insert_asset` each into a staging folder. With `Probe.compare` and `Probe.scan` measure:
   - size in studs -> importer scale factor per format (expect ~3.57 vs 1 m = 1 stud for GLB)
   - position of each marker relative to the model centre in world axes + the model's yaw ->
     axis map (is the `-Y` marker on world +Z or -Z?)
   - whether `MeshPart.Color` survived (compare with `base_color_hex`)
4. Write `out/calibration.json`:
   ```json
   {"glb": {"scale_factor": 3.5714, "axis_map": "(x,y,z)->(x,z,-y)", "color_survives": false},
    "fbx": {"scale_factor": 0.0357, "axis_map": "...", "color_survives": false},
    "asset_ids": {"glb": "...", "fbx": "..."}, "date": "..."}
   ```
5. Update `rbx_lib.export` to use the measured factor (switch `units="studs"` from experimental to default)
   and record the verified axis map in `WORKFLOW.md`.

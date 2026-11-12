"""Selftest: a 48k-tri mesh must auto-split into <=20k-tri pieces that keep the clean base name,
and the user's original object must survive the export untouched."""
import os

import bpy
import rbx_lib as R

out_dir = os.path.abspath(ARGS.get("out_dir", "out"))
mat = R.material("T_Mat", R.hex_color("#4a90d9"))
big = R.cylinder("BigColumn", radius=1.0, depth=6.0, center=(0, 0, 3), segments=12000, mat=mat)
before = R.tri_count(big)
m = R.export([big], os.path.join(out_dir, "t_split.glb"), name="BigColumn", auto_split=True)
R.result({
    "tris_before": before,
    "pieces": [(x["name"], x["tris"]) for x in m["meshes"]],
    "max_piece": max(x["tris"] for x in m["meshes"]),
    "tri_total": m["tri_total"],
    "original_survived": "BigColumn" in bpy.data.objects and R.tri_count(bpy.data.objects["BigColumn"]) == before,
    "leftover_objects": sorted(o.name for o in bpy.data.objects if o.name != "BigColumn"),
})

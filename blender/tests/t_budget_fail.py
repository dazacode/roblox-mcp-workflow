"""Selftest: over-budget export WITHOUT auto_split must refuse (so a bad asset never reaches a permanent upload)."""
import os

import rbx_lib as R

out_dir = os.path.abspath(ARGS.get("out_dir", "out"))
big = R.cylinder("TooBig", radius=1.0, depth=6.0, center=(0, 0, 3), segments=12000, mat=R.material("T_Mat2"))
R.export([big], os.path.join(out_dir, "t_budget_fail.glb"), name="TooBig")   # expected to raise
R.result({"should_not_get_here": True})

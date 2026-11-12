"""Selftest: inverted normals + default name + missing material must be caught by validate()."""
import bmesh
import bpy

import rbx_lib as R

obj = R.box("Cube", size=(1, 1, 1))                   # default-ish name, no material
bm = bmesh.new()
bm.from_mesh(obj.data)
bmesh.ops.reverse_faces(bm, faces=bm.faces)
bm.to_mesh(obj.data)
bm.free()
R.sync()
codes = sorted({f["code"] for f in R.validate([obj])})
R.result({"codes": codes})

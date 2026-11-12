"""
rbx_lib.py - Roblox-aware helpers for Blender scripts (Blender 4.1, headless-safe).

Design rules:
  * Use the data API + bmesh, never bpy.ops for geometry. Operators need a UI
    context and fail in `blender -b`.
  * Author in METRES, Z-up, FRONT FACING -Y (Blender's own front view).
  * Every export writes a manifest (<file>.forge.json). The manifest is the
    contract that Studio-side verification (ForgeProbe.compare) diffs against.
"""
import hashlib
import json
import math
import os
import time

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

# ---- Roblox constants ------------------------------------------------------
STUD_M = 0.28                 # 1 stud = 0.28 m
STUDS_PER_M = 1.0 / STUD_M
TRI_LIMIT = 20000             # per-mesh limit, create.roblox.com art/modeling/specifications
MAX_PART_STUDS = 2048         # Part size cap; bigger meshes need splitting/scaling

ARGS = {}                     # injected by forge_runner
_RESULT = {}


def result(data):
    """Set the structured value returned to the caller (JSON-serialisable)."""
    global _RESULT
    _RESULT = data
    return data


def get_result():
    return _RESULT


# ---- scene ----------------------------------------------------------------
def reset_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.cameras, bpy.data.lights):
        for b in list(coll):
            coll.remove(b)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0


def sync():
    """Objects made via the data API have a STALE matrix_world (identity) until the view layer
    updates. Anything that reads matrix_world must call this first - skipping it silently stacks
    every part at the origin."""
    bpy.context.view_layer.update()


def activate(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _link(obj, collection=None):
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


# ---- colour ----------------------------------------------------------------
def _s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _l2s(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def hex_color(h, alpha=1.0):
    """'#c0392b' (what you'd type into Roblox Color3.fromHex) -> Blender linear RGBA."""
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (_s2l(r), _s2l(g), _s2l(b), alpha)


def linear_to_hex(rgba):
    return "#" + "".join("{:02x}".format(int(round(max(0, min(1, _l2s(c))) * 255))) for c in rgba[:3])


def material(name, color=(0.8, 0.8, 0.8, 1.0), roughness=0.8, metallic=0.0):
    """color is LINEAR RGBA (use hex_color for sRGB hex). One material per mesh is Roblox's limit."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    mat.diffuse_color = color           # drives Workbench previews
    return mat


# ---- geometry (bmesh; no operators) ---------------------------------------
def _finish(name, bm, mat=None, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    if mat is not None:
        me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = False
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    return _link(obj)


def box(name, size=(1, 1, 1), center=(0, 0, 0), mat=None, rot_deg=(0, 0, 0)):
    """size = full dimensions in metres. Origin at `center`."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    obj = _finish(name, bm, mat, center)
    obj.rotation_euler = [math.radians(a) for a in rot_deg]
    return obj


def cylinder(name, radius=0.5, depth=1.0, center=(0, 0, 0), segments=16, mat=None, radius_top=None):
    """Z-axis cylinder / truncated cone. radius_top lets you taper (pillars)."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=radius, radius2=radius if radius_top is None else radius_top, depth=depth)
    return _finish(name, bm, mat, center)


def set_origin_bottom(obj):
    """Move the mesh so its origin sits at the bottom-centre (nice pivot for ground placement)."""
    zs = [v.co.z for v in obj.data.vertices]
    off = Vector((0, 0, min(zs)))
    for v in obj.data.vertices:
        v.co -= off
    obj.location += off


def join(objs, name, mat=None):
    """Join objects into one mesh (data API; bakes each object's transform)."""
    sync()
    bm = bmesh.new()
    mats = []
    for o in objs:
        me = o.data.copy()
        me.transform(o.matrix_world)
        for m in me.materials:
            if m and m not in mats:
                mats.append(m)
        remap = {i: (mats.index(m) if m in mats else 0) for i, m in enumerate(me.materials)}
        base = len(bm.faces)
        bm.from_mesh(me)
        for f in list(bm.faces)[base:]:
            f.material_index = remap.get(f.material_index, 0)
        bpy.data.meshes.remove(me)
    out = bpy.data.meshes.new(name)
    bm.to_mesh(out)
    bm.free()
    for m in ([mat] if mat else mats):
        out.materials.append(m)
    obj = bpy.data.objects.new(name, out)
    _link(obj)
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    return obj


def apply_modifiers(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    obj.modifiers.clear()
    old = obj.data
    obj.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def bake_transform(obj, scale=1.0):
    """Bake world transform (and optional uniform scale) into vertices; identity matrix after."""
    sync()
    apply_modifiers(obj)
    M = obj.matrix_world.copy()
    obj.parent = None
    obj.data.transform(Matrix.Scale(scale, 4) @ M)
    obj.matrix_world = Matrix.Identity(4)
    obj.data.update()
    return obj


def smart_uv(obj):
    """Needs a UI-less operator context; falls back silently if unavailable."""
    try:
        activate(obj)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
        bpy.ops.object.mode_set(mode="OBJECT")
        return True
    except Exception:
        return False


# ---- measurement ----------------------------------------------------------
def _eval_arrays(obj):
    """World-space verts (Nx3) and tri indices (Mx3) of the evaluated (modifier-applied) mesh."""
    sync()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    W = np.array(obj.matrix_world)
    co = co @ W[:3, :3].T + W[:3, 3]
    tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", tris)
    tris = tris.reshape(-1, 3)
    ev.to_mesh_clear()
    return co, tris


def tri_count(obj):
    return int(_eval_arrays(obj)[1].shape[0])


def world_extents(objs):
    """True world-space extents (not per-object bbox) -> dict with min/max/size in metres."""
    pts = [_eval_arrays(o)[0] for o in objs if o.type == "MESH"]
    if not pts:
        return None
    a = np.vstack(pts)
    mn, mx = a.min(axis=0), a.max(axis=0)
    return {"min": mn.round(4).tolist(), "max": mx.round(4).tolist(), "size": (mx - mn).round(4).tolist()}


def signed_volume(co, tris):
    v0, v1, v2 = co[tris[:, 0]], co[tris[:, 1]], co[tris[:, 2]]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)


# ---- validation -----------------------------------------------------------
def _finding(sev, code, obj, msg, fix):
    return {"sev": sev, "code": code, "obj": obj, "msg": msg, "fix": fix}


def validate(objs, tri_limit=TRI_LIMIT, studs=False):
    """Machine-readable findings. sev: error (blocks export) | warn | info."""
    out = []
    names = {}
    for o in objs:
        if o.type != "MESH":
            continue
        n = o.name
        names[n] = names.get(n, 0) + 1
        co, tris = _eval_arrays(o)
        t = int(tris.shape[0])
        if t == 0:
            out.append(_finding("error", "EMPTY_MESH", n, "mesh has no triangles", "delete the object or add geometry"))
            continue
        if t > tri_limit:
            out.append(_finding("error", "TRI_BUDGET", n, "{} tris > limit {}".format(t, tri_limit),
                                "export(..., auto_split=True) or reduce segments/bevels"))
        elif t > tri_limit * 0.8:
            out.append(_finding("warn", "TRI_NEAR_LIMIT", n, "{} tris is >80% of {}".format(t, tri_limit), "consider decimating"))
        sc = o.matrix_world.to_scale()
        if any(abs(abs(c) - 1.0) > 1e-4 for c in sc):
            out.append(_finding("info", "UNAPPLIED_SCALE", n, "object scale {} (baked automatically on export)".format(tuple(round(c, 4) for c in sc)), "none needed"))
        if o.matrix_world.determinant() < 0:
            out.append(_finding("warn", "MIRRORED", n, "negative-scale mirror flips normals", "export bakes + flips; verify winding in preview"))
        if not o.data.materials or any(m is None for m in o.data.materials):
            out.append(_finding("warn", "NO_MATERIAL", n, "no material -> imports as default grey", "assign rbx_lib.material(...)"))
        if len(o.data.materials) > 1:
            out.append(_finding("warn", "MULTI_MATERIAL", n, "{} material slots; Roblox supports one material per mesh".format(len(o.data.materials)),
                                "export one mesh per material (join parts by material, export all as one multi-mesh model) or bake to one texture"))
        if not o.data.uv_layers:
            out.append(_finding("info", "NO_UV", n, "no UV map (fine for flat colours; required for textures)", "rbx_lib.smart_uv(obj)"))
        bm = bmesh.new()
        bm.from_mesh(o.data)
        nonman = sum(1 for e in bm.edges if not e.is_manifold)
        loose = sum(1 for v in bm.verts if not v.link_edges)
        degen = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
        ngon = sum(1 for f in bm.faces if len(f.verts) > 4)
        bm.free()
        if nonman:
            out.append(_finding("warn", "NOT_WATERTIGHT", n, "{} non-manifold/boundary edges".format(nonman), "close holes; Roblox prefers watertight meshes"))
        if loose:
            out.append(_finding("warn", "LOOSE_VERTS", n, "{} loose vertices".format(loose), "bmesh.ops.delete on loose verts"))
        if degen:
            out.append(_finding("warn", "ZERO_AREA_FACES", n, "{} zero-area faces".format(degen), "dissolve degenerate faces"))
        if ngon:
            out.append(_finding("info", "NGONS", n, "{} n-gons (triangulated on export)".format(ngon), "none needed"))
        if nonman == 0 and signed_volume(co, tris) < 0:
            out.append(_finding("error", "INSIDE_OUT", n, "closed mesh has negative volume (normals point inward)", "bmesh.ops.reverse_faces"))
        size = (co.max(axis=0) - co.min(axis=0))
        mx = float(size.max()) * (STUDS_PER_M if not studs else 1.0)
        if mx > MAX_PART_STUDS:
            out.append(_finding("warn", "OVERSIZE", n, "largest side ~{:.0f} studs > {}".format(mx, MAX_PART_STUDS), "split into tiles"))
        if mx < 0.2:
            out.append(_finding("warn", "TINY", n, "largest side ~{:.2f} studs".format(mx), "check units (metres) and scale"))
        for base in ("Cube", "Cylinder", "Sphere", "Plane", "Cone", "Torus", "Mesh"):
            if n == base or n.startswith(base + "."):
                out.append(_finding("info", "DEFAULT_NAME", n, "default object name", "give meshes meaningful unique names (repairs match by name)"))
                break
    for n, c in names.items():
        if c > 1:
            out.append(_finding("error", "DUPLICATE_NAME", n, "name used {} times".format(c), "names must be unique"))
    return out


# ---- budget splitting -----------------------------------------------------
def split_to_budget(obj, limit=TRI_LIMIT):
    """Recursively split along the longest axis (face-centre median) until each piece <= limit tris.
    Preserves UVs & materials because pieces are copies with faces deleted."""
    apply_modifiers(obj)
    base = obj.name
    work, done = [obj], []
    while work:
        o = work.pop()
        if tri_count(o) <= limit:
            done.append(o)
            continue
        bm = bmesh.new()
        bm.from_mesh(o.data)
        ext = [max(v.co[i] for v in bm.verts) - min(v.co[i] for v in bm.verts) for i in range(3)]
        ax = max(range(3), key=lambda i: ext[i])
        bm.free()

        def keep(src, upper):
            """Keep the lower (upper=False) or upper half of faces ordered along axis `ax`.
            Splitting by rank (not by value) always makes progress, even with tied centres."""
            b = bmesh.new()
            b.from_mesh(src.data)
            faces = list(b.faces)
            order = sorted(range(len(faces)), key=lambda i: faces[i].calc_center_median()[ax])
            half = len(order) // 2
            drop = order[:half] if upper else order[half:]
            bmesh.ops.delete(b, geom=[faces[i] for i in drop], context="FACES")
            b.to_mesh(src.data)
            b.free()

        twin = o.copy()
        twin.data = o.data.copy()
        _link(twin)
        keep(o, upper=False)
        keep(twin, upper=True)
        work += [o, twin]
    for i, o in enumerate(done, 1):
        o.name = "{}_Part{}".format(base, i)
        o.data.name = o.name
    return done


# ---- export ---------------------------------------------------------------
def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _material_info(m):
    bsdf = m.node_tree.nodes.get("Principled BSDF") if m and m.use_nodes else None
    if not bsdf:
        return {"name": m.name if m else None}
    col = tuple(bsdf.inputs["Base Color"].default_value)
    has_tex = bool(bsdf.inputs["Base Color"].links)
    return {
        "name": m.name,
        "base_color_linear": [round(c, 5) for c in col],
        "base_color_hex": linear_to_hex(col),     # == expected Roblox MeshPart.Color if no texture
        "roughness": round(bsdf.inputs["Roughness"].default_value, 3),
        "metallic": round(bsdf.inputs["Metallic"].default_value, 3),
        "has_color_texture": has_tex,
    }


def export(objs, out_path, fmt="glb", name=None, units="meters", auto_split=False,
           tri_limit=TRI_LIMIT, features=None, force=False):
    """Export COPIES of `objs` (user objects untouched) + write <out>.forge.json manifest.

    units: 'meters' (default; matches the official import skill: Studio fixes scale in step 5c)
           'studs'  (pre-scales x3.5714 so a GLB arrives ~1:1 - treat as experimental until
                     calibrated with one real upload, see docs/CALIBRATION.md)
    features: {"label": (x, y, z)} asymmetric reference points in Blender metres, used to
              verify orientation in Studio (mirrored/rotated imports are the #1 failure).
    Returns the manifest dict (also written to disk). Raises if validation finds errors
    and force=False, so a bad asset never reaches the permanent-upload step.
    """
    objs = [o for o in objs if o.type == "MESH"]
    name = name or os.path.splitext(os.path.basename(out_path))[0]
    sync()
    preexisting = set(bpy.data.objects)       # everything else created below is a temp copy
    orig_names = {o: o.name for o in objs}
    for o in objs:                            # free the clean names so exported copies keep them
        o.name = orig_names[o] + "__orig"     # (Blender would otherwise append .001 -> breaks name matching in Studio)
    copies = []
    for o in objs:
        c = o.copy()
        c.data = o.data.copy()
        _link(c)
        c.name = orig_names[o]
        copies.append(c)
    try:
        scale = STUDS_PER_M if units == "studs" else 1.0
        for c in copies:
            bake_transform(c, scale)
        final = []
        for c in copies:
            if auto_split and tri_count(c) > tri_limit:
                final += split_to_budget(c, tri_limit)
            else:
                final.append(c)
        for c in final:
            c.data.name = c.name
        findings = validate(final, tri_limit, studs=(units == "studs"))
        errs = [f for f in findings if f["sev"] == "error"]
        if errs and not force:
            raise RuntimeError("Triangle budget/validation failed: " + json.dumps(errs[:5]))
        ext = world_extents(final)
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        bpy.ops.object.select_all(action="DESELECT")
        for c in final:
            c.select_set(True)
        bpy.context.view_layer.objects.active = final[0]
        if fmt == "glb":
            bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", use_selection=True,
                                      export_yup=True, export_cameras=False, export_lights=False,
                                      export_apply=False, export_materials="EXPORT")
        elif fmt == "fbx":
            bpy.ops.export_scene.fbx(filepath=out_path, use_selection=True, object_types={"MESH"},
                                     apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL",
                                     path_mode="COPY", embed_textures=True, add_leaf_bones=False,
                                     axis_forward="-Z", axis_up="Y")
        else:
            raise ValueError("fmt must be 'glb' or 'fbx'")
        # extents are in export units (studs if pre-scaled); convert back to real metres
        size_m_real = [v * (STUD_M if units == "studs" else 1.0) for v in ext["size"]]
        manifest = {
            "schema": "forge.manifest/1",
            "name": name,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "format": fmt,
            "export_units": units,
            "files": [{"path": os.path.abspath(out_path), "bytes": os.path.getsize(out_path), "sha256": _sha(out_path)}],
            "meshes": [{"name": c.name, "tris": tri_count(c), "verts": len(c.data.vertices),
                        "materials": [m.name for m in c.data.materials if m]} for c in final],
            "tri_total": sum(tri_count(c) for c in final),
            "tri_limit": tri_limit,
            "materials": [_material_info(m) for m in {m for c in final for m in c.data.materials if m}],
            "size_m_blender_xyz": [round(v, 4) for v in size_m_real],
            # Blender Z-up -> Roblox Y-up: X=x, Y=z, Z=y
            "expected_size_studs_roblox_xyz": [round(size_m_real[0] * STUDS_PER_M, 2), round(size_m_real[2] * STUDS_PER_M, 2), round(size_m_real[1] * STUDS_PER_M, 2)],
            "expected_height_studs": round(size_m_real[2] * STUDS_PER_M, 2),
            "front_axis_blender": "-Y",
            "features_blender_m": {k2: list(v) for k2, v in (features or {}).items()},
            "orientation_note": "candidate glTF->Roblox map: (x,y,z)->(x,z,-y); CONFIRM with features after first import",
            "findings": findings,
        }
        with open(out_path + ".forge.json", "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=1)
        return manifest
    finally:
        for o in list(bpy.data.objects):
            if o not in preexisting:
                bpy.data.objects.remove(o, do_unlink=True)
        for o, n in orig_names.items():       # restore the user's names
            o.name = n


# ---- previews (so the AI can SEE the asset before a permanent upload) -------
def render_preview(objs, out_png, size=512):
    """Workbench contact sheet: [front | right] / [top | iso]. Returns out_png."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.image_settings.file_format = "PNG"
    sh = scene.display.shading
    sh.light, sh.color_type = "STUDIO", "MATERIAL"
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("forge_bg")
    world.color = (0.18, 0.2, 0.24)
    scene.world = world
    ext = world_extents(objs)
    mn, mx = Vector(ext["min"]), Vector(ext["max"])
    ctr, r = (mn + mx) / 2, max(ext["size"]) * 0.5
    cam_data = bpy.data.cameras.new("forge_cam")
    cam = bpy.data.objects.new("forge_cam", cam_data)
    _link(cam)
    scene.camera = cam
    views = [("front", Vector((0, -1, 0)), True), ("right", Vector((1, 0, 0)), True),
             ("top", Vector((0, 0, 1)), True), ("iso", Vector((1, -1, 0.8)).normalized(), False)]
    tiles = []
    tmp = os.path.splitext(out_png)[0]
    for label, d, ortho in views:
        cam_data.type = "ORTHO" if ortho else "PERSP"
        cam_data.ortho_scale = r * 2.5
        dist = r * (6 if ortho else 4.2)
        cam.location = ctr + d * dist
        up = "Y" if label != "top" else "Y"
        cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", up).to_euler()
        if label == "top":
            cam.rotation_euler = (0, 0, 0)
        scene.render.filepath = "{}_{}.png".format(tmp, label)
        bpy.ops.render.render(write_still=True)
        tiles.append(scene.render.filepath)
    imgs = [bpy.data.images.load(p) for p in tiles]
    w = h = size
    sheet = np.zeros((h * 2, w * 2, 4), dtype=np.float32)
    for i, im in enumerate(imgs):
        px = np.empty(w * h * 4, dtype=np.float32)
        im.pixels.foreach_get(px)
        px = px.reshape(h, w, 4)
        r0, c0 = (1 - i // 2) * h, (i % 2) * w     # Blender rows start at the bottom
        sheet[r0:r0 + h, c0:c0 + w] = px
    out = bpy.data.images.new("forge_sheet", w * 2, h * 2)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw = out_png
    out.file_format = "PNG"
    out.save()
    for p in tiles:
        try:
            os.remove(p)
        except OSError:
            pass
    bpy.data.objects.remove(cam, do_unlink=True)
    return out_png


def snapshot():
    """Cheap scene summary for debugging scripts."""
    return {"objects": [{"name": o.name, "type": o.type, "tris": tri_count(o) if o.type == "MESH" else None,
                         "loc": [round(c, 3) for c in o.location]} for o in bpy.data.objects],
            "materials": [m.name for m in bpy.data.materials]}

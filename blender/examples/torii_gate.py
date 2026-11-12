"""Example job: procedural Japanese torii gate -> validated GLB + manifest + preview sheet.

    python forge.py blender run blender/examples/torii_gate.py --args '{"out_dir":"out"}'

Conventions: metres, Z-up, front faces -Y. Gate opening runs along X.
Roblox allows ONE material per mesh, so parts are joined PER MATERIAL and exported as a
two-mesh model (vermilion body + black accents).
"""
import os

import rbx_lib as R

out_dir = os.path.abspath(ARGS.get("out_dir", "out"))   # ARGS is injected by forge_runner
os.makedirs(out_dir, exist_ok=True)

vermilion = R.material("Torii_Vermilion", R.hex_color("#c0392b"), roughness=0.6)
black = R.material("Torii_Black", R.hex_color("#1c1c1e"), roughness=0.7)

W, H = 3.6, 4.2            # pillar spacing (centre to centre), pillar height  (metres)
body, accents = [], []
for side, x in (("L", -W / 2), ("R", W / 2)):
    body.append(R.cylinder("Pillar_" + side, radius=0.22, radius_top=0.18, depth=H, center=(x, 0, H / 2), segments=20, mat=vermilion))
body.append(R.box("Nuki", size=(W + 0.5, 0.2, 0.22), center=(0, 0, H * 0.72), mat=vermilion))        # lower tie beam
body.append(R.box("Kasagi", size=(W + 2.4, 0.42, 0.26), center=(0, 0, H + 0.36), mat=vermilion))      # top lintel
accents.append(R.box("Shimaki", size=(W + 1.5, 0.34, 0.2), center=(0, 0, H + 0.12), mat=black))       # black cap under the lintel
accents.append(R.box("Plaque", size=(0.5, 0.06, 0.7), center=(0, -0.16, H * 0.86), mat=black))        # ONLY on the -Y (front) side

gate_body = R.join(body, "Torii_Body")
gate_accent = R.join(accents, "Torii_Accents")
meshes = [gate_body, gate_accent]

manifest = R.export(meshes, os.path.join(out_dir, "torii_gate.glb"), name="ToriiGate",
                    features={"plaque_front": (0, -0.19, H * 0.86)})     # lets Studio verify the front didn't flip
sheet = R.render_preview(meshes, os.path.join(out_dir, "torii_gate_preview.png"), size=384)

R.result({
    "glb": manifest["files"][0]["path"],
    "preview": sheet,
    "meshes": manifest["meshes"],
    "tri_total": manifest["tri_total"],
    "expected_height_studs": manifest["expected_height_studs"],
    "expected_size_studs_roblox_xyz": manifest["expected_size_studs_roblox_xyz"],
    "findings": [f for f in manifest["findings"] if f["sev"] != "info"],
})

"""
forge_runner.py - executed INSIDE headless Blender by forge.py.

    blender -b --factory-startup --python forge_runner.py -- job.json

Runs the user's script, then writes ONE structured JSON result file. The caller
never has to parse Blender's console noise: success or failure, you get a
machine-readable object with the failing line, a source snippet and a hint.
"""
import contextlib
import io
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

job_path = sys.argv[sys.argv.index("--") + 1]
with open(job_path, "r", encoding="utf-8") as fh:
    JOB = json.load(fh)

import bpy  # noqa: E402  (only importable inside Blender)
import rbx_lib  # noqa: E402

HINTS = [
    ("Operator bpy.ops", "poll() failed", "bpy.ops needs a context; prefer the data API / bmesh (rbx_lib helpers) in headless mode."),
    ("context is incorrect", "", "Operator needs an active object / mode. Use rbx_lib.activate(obj) or switch to bmesh."),
    ("object has no attribute", "", "Check Blender 4.1 API names; Principled BSDF inputs are e.g. 'Base Color', 'Roughness', 'Metallic'."),
    ("not found", "", "Name lookup failed; list names with bpy.data.objects.keys()."),
    ("Permission denied", "", "Output path not writable; write inside the project's out/ directory."),
    ("Triangle budget", "", "Mesh exceeds Roblox's 20,000-triangle limit: pass auto_split=True to rbx_lib.export or reduce detail."),
]


def hint_for(text):
    for needle, _, hint in HINTS:
        if needle.lower() in text.lower():
            return hint
    return None


def user_frame(tb, script_path):
    """Innermost traceback frame that belongs to the user's script."""
    best = None
    for fr in traceback.extract_tb(tb):
        if os.path.abspath(fr.filename) == os.path.abspath(script_path):
            best = fr
    return best


result = {"ok": True, "script": JOB["script"], "blender": bpy.app.version_string}
stdout_buf = io.StringIO()
t0 = time.time()

try:
    if JOB.get("blend_in"):
        bpy.ops.wm.open_mainfile(filepath=JOB["blend_in"])
    else:
        rbx_lib.reset_scene()
    rbx_lib.ARGS = JOB.get("args", {})
    g = {"__name__": "__forge_job__", "__file__": JOB["script"], "ARGS": rbx_lib.ARGS}
    with open(JOB["script"], "r", encoding="utf-8") as fh:
        src = fh.read()
    with contextlib.redirect_stdout(stdout_buf):
        exec(compile(src, JOB["script"], "exec"), g)
    result["data"] = rbx_lib.get_result()
    if JOB.get("blend_out"):
        os.makedirs(os.path.dirname(os.path.abspath(JOB["blend_out"])), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=JOB["blend_out"])
        result["saved_blend"] = JOB["blend_out"]
except BaseException as exc:  # noqa: BLE001 - we want everything, incl. SystemExit
    result["ok"] = False
    et, ev, tb = sys.exc_info()
    fr = user_frame(tb, JOB["script"])
    msg = "{}: {}".format(type(exc).__name__, exc)
    result["error"] = {
        "type": type(exc).__name__,
        "message": str(exc),
        "line": fr.lineno if fr else None,
        "code": fr.line if fr else None,
        "hint": hint_for(msg),
        "traceback_tail": traceback.format_exc().splitlines()[-8:],
    }
    partial = rbx_lib.get_result()
    if partial:
        result["partial_data"] = partial

result["seconds"] = round(time.time() - t0, 2)
log = stdout_buf.getvalue()
if log:
    result["log_tail"] = log[-2000:]

os.makedirs(os.path.dirname(os.path.abspath(JOB["result_path"])), exist_ok=True)
with open(JOB["result_path"], "w", encoding="utf-8") as fh:
    json.dump(result, fh, indent=None, default=str)

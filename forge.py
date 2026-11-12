#!/usr/bin/env python3
"""
forge.py - one CLI for the Roblox AI workflow. Pure stdlib, JSON in / JSON out.

  python forge.py doctor
  python forge.py blender run   blender/examples/torii_gate.py [--args '{"k":1}'] [--blend in.blend] [--save out.blend] [--timeout 180]
  python forge.py blender batch jobs.json [--workers 4]       # many assets in parallel, one process each
  python forge.py luau bundle                                 # writes dist/install_forge.luau + dist/uninstall_forge.luau

Every command prints a single JSON object on stdout (nothing else) so an agent can
parse it directly. Exit code 0 = ok, 1 = job failed, 2 = environment problem.
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(ROOT, "blender", "forge_runner.py")


def emit(obj, code=0):
    sys.stdout.write(json.dumps(obj, indent=None, default=str) + "\n")
    sys.exit(code)


# ---- discovery -------------------------------------------------------------
def find_blender():
    cands = [os.environ.get("BLENDER_PATH"), shutil.which("blender")]
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.path.expandvars(r"%LOCALAPPDATA%\Programs")):
        cands += sorted(glob.glob(os.path.join(base, "Blender Foundation", "Blender *", "blender.exe")), reverse=True)
    cands += ["/Applications/Blender.app/Contents/MacOS/Blender", "/usr/bin/blender"]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def tool_version(cmd, *args):
    exe = shutil.which(cmd)
    if not exe:
        return None
    try:
        out = subprocess.run([exe, *args], capture_output=True, text=True, timeout=15)
        line = (out.stdout or out.stderr).strip().splitlines()[0]
        if "Aftman error" in line or "Rokit" in line and "error" in line.lower():
            # toolchain shim exists but no project manifest lists it: installed, just not resolvable from here
            return "installed (shim; run inside a project with aftman.toml/rokit.toml)"
        return line
    except Exception as e:  # noqa: BLE001
        return "found but failed: {}".format(e)


def cmd_doctor(_):
    blender = find_blender()
    info = {"ok": True, "blender": None, "tools": {}, "notes": []}
    if blender:
        r = subprocess.run([blender, "-b", "--factory-startup", "--python-expr",
                            "import bpy;print('FORGE_OK',bpy.app.version_string,hasattr(bpy.ops.export_scene,'gltf'),hasattr(bpy.ops.export_scene,'fbx'))"],
                           capture_output=True, text=True, timeout=120)
        line = next((l for l in r.stdout.splitlines() if l.startswith("FORGE_OK")), "")
        parts = line.split()
        info["blender"] = {"path": blender, "version": parts[1] if len(parts) > 1 else None,
                           "gltf": parts[2] == "True" if len(parts) > 2 else False,
                           "fbx": parts[3] == "True" if len(parts) > 3 else False}
        if not line:
            info["ok"] = False
            info["notes"].append("Blender found but headless python check failed: " + r.stderr[-300:])
    else:
        info["ok"] = False
        info["notes"].append("Blender not found. Install it or set BLENDER_PATH.")
    for t, a in (("rojo", ("--version",)), ("selene", ("--version",)), ("stylua", ("--version",)),
                 ("luau-lsp", ("--version",)), ("lune", ("--version",)), ("python", ("--version",)),
                 ("node", ("--version",)), ("git", ("--version",)), ("uv", ("--version",)), ("wally", ("--version",))):
        info["tools"][t] = tool_version(t, *a)
    info["notes"] += ["{} missing (optional)".format(k) for k, v in info["tools"].items() if v is None and k in ("wally",)]
    emit(info, 0 if info["ok"] else 2)


# ---- blender jobs ------------------------------------------------------------
def run_job(script, args=None, blend_in=None, blend_out=None, timeout=180):
    blender = find_blender()
    if not blender:
        return {"ok": False, "stage": "env", "error": "Blender not found (set BLENDER_PATH)"}
    script = os.path.abspath(script)
    if not os.path.isfile(script):
        return {"ok": False, "stage": "env", "error": "script not found: " + script}
    work = tempfile.mkdtemp(prefix="forge_")
    result_path = os.path.join(work, "result.json")
    job = {"script": script, "args": args or {}, "blend_in": blend_in and os.path.abspath(blend_in),
           "blend_out": blend_out and os.path.abspath(blend_out), "result_path": result_path}
    job_path = os.path.join(work, "job.json")
    with open(job_path, "w", encoding="utf-8") as fh:
        json.dump(job, fh)
    t0 = time.time()
    try:
        p = subprocess.run([blender, "-b", "--factory-startup", "--python", RUNNER, "--", job_path],
                           capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"ok": False, "stage": "timeout", "error": "Blender exceeded {}s and was killed".format(timeout), "script": script}
    out = None
    if os.path.isfile(result_path):
        with open(result_path, "r", encoding="utf-8") as fh:
            out = json.load(fh)
    shutil.rmtree(work, ignore_errors=True)
    if out is None:
        return {"ok": False, "stage": "crash", "script": script, "exit_code": p.returncode,
                "error": "Blender produced no result (crash or startup failure)",
                "stderr_tail": p.stderr[-800:], "stdout_tail": p.stdout[-800:]}
    out["wall_seconds"] = round(time.time() - t0, 2)
    return out


def cmd_blender_run(a):
    res = run_job(a.script, json.loads(a.args) if a.args else {}, a.blend, a.save, a.timeout)
    emit(res, 0 if res.get("ok") else 1)


def cmd_blender_batch(a):
    with open(a.jobs, "r", encoding="utf-8") as fh:
        jobs = json.load(fh)          # [{"script": "...", "args": {...}, "id": "optional"}]

    def one(j):
        r = run_job(j["script"], j.get("args"), j.get("blend"), j.get("save"), j.get("timeout", 180))
        r["id"] = j.get("id", os.path.basename(j["script"]))
        return r

    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(one, jobs))
    ok = all(r.get("ok") for r in results)
    emit({"ok": ok, "count": len(results), "workers": a.workers, "wall_seconds": round(time.time() - t0, 2),
          "results": results}, 0 if ok else 1)


# ---- selftest ------------------------------------------------------------------
def cmd_selftest(a):
    """Regression gate for the Blender pipeline. Runs in parallel; each check asserts a specific behaviour."""
    out = os.path.join(ROOT, "out", "selftest")
    T = lambda n: os.path.join(ROOT, "blender", "tests", n)
    specs = [
        ("torii_end_to_end", os.path.join(ROOT, "blender", "examples", "torii_gate.py"),
         lambda r: r["ok"] and r["data"]["tri_total"] == 200 and not r["data"]["findings"]
         and [m["name"] for m in r["data"]["meshes"]] == ["Torii_Body", "Torii_Accents"]),
        ("auto_split_under_budget", T("t_split_budget.py"),
         lambda r: r["ok"] and r["data"]["max_piece"] <= 20000 and len(r["data"]["pieces"]) >= 3
         and r["data"]["original_survived"] and r["data"]["leftover_objects"] == []
         and all(p[0].startswith("BigColumn_Part") for p in r["data"]["pieces"])),
        ("over_budget_refused", T("t_budget_fail.py"),
         lambda r: (not r["ok"]) and "Triangle budget" in r["error"]["message"] and r["error"]["hint"]),
        ("script_bug_is_structured", T("t_broken_script.py"),
         lambda r: (not r["ok"]) and r["error"]["type"] == "NameError" and r["error"]["line"] == 6
         and "undefined_helper_call" in (r["error"]["code"] or "") and r.get("partial_data") == {"partial": "set before the crash"}),
        ("validator_catches_defects", T("t_inside_out.py"),
         lambda r: r["ok"] and {"INSIDE_OUT", "NO_MATERIAL", "DEFAULT_NAME"} <= set(r["data"]["codes"])),
    ]

    def one(s):
        r = run_job(s[1], {"out_dir": out}, timeout=240)
        try:
            ok = bool(s[2](r))
        except Exception as e:  # noqa: BLE001
            ok, r["assert_error"] = False, repr(e)
        return {"check": s[0], "pass": ok, "seconds": r.get("wall_seconds"), "detail": None if ok else r}

    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        res = list(ex.map(one, specs))
    ok = all(r["pass"] for r in res)
    emit({"ok": ok, "passed": sum(r["pass"] for r in res), "total": len(res),
          "wall_seconds": round(time.time() - t0, 2), "checks": res}, 0 if ok else 1)


# ---- luau bundling -------------------------------------------------------------
LUAU_MODULES = ["Probe", "Log", "Check"]


def long_string(src):
    n = 0
    while "]" + "=" * n + "]" in src:
        n += 1
    eq = "=" * n
    return "[{0}[\n{1}\n]{0}]".format(eq, src)


def strip_luau(src):
    """Drop leading block-comment docs, full-line comments and blank lines (keeps --!directives).
    Shrinks the one-time install payload ~40% - every byte of it passes through a tool call."""
    import re
    src = re.sub(r"(?ms)^[ \t]*--\[\[.*?\]\]\s*\n", "", src)
    keep = []
    for line in src.splitlines():
        s = line.strip()
        if not s or (s.startswith("--") and not s.startswith("--!")):
            continue
        keep.append(line.rstrip())
    return "\n".join(keep)


def cmd_luau_bundle(_):
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    # SESSION loader: modules live only in `shared.Forge` (unparented ModuleScripts). Nothing is written
    # into the place file, no undo-history entry, nothing to uninstall. Reload after each Edit<->Play switch
    # (each DataModel has its own `shared`).
    parts = [
        "-- ForgeKit session loader. Run once per DataModel via execute_luau; then call shared.Forge.Probe/Log/Check.",
        "local mods = {}",
        'local function mod(name, src) local m = Instance.new("ModuleScript"); m.Name = name; m.Source = src; mods[name] = require(m) end',
    ]
    for m in LUAU_MODULES:
        with open(os.path.join(ROOT, "luau", m + ".luau"), "r", encoding="utf-8") as fh:
            src = strip_luau(fh.read())
        parts.append('mod("{}", {})'.format(m, long_string(src)))
    parts += ["shared.Forge = mods",
              'return "ForgeKit loaded (session only, place untouched): Probe, Log, Check"']
    target = os.path.join(dist, "load_forge.luau")
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts) + "\n")
    # per-module hot-reload loaders: fix one module without re-sending all of them
    for m in LUAU_MODULES:
        with open(os.path.join(ROOT, "luau", m + ".luau"), "r", encoding="utf-8") as fh:
            src = strip_luau(fh.read())
        with open(os.path.join(dist, "load_{}.luau".format(m)), "w", encoding="utf-8") as fh:
            fh.write('shared.Forge = shared.Forge or {{}}\n'
                     'local m = Instance.new("ModuleScript"); m.Name = "{0}"; m.Source = {1}\n'
                     'shared.Forge.{0} = require(m)\nreturn "ForgeKit.{0} reloaded"\n'.format(m, long_string(src)))
    for stale in ("install_forge.luau", "uninstall_forge.luau"):
        if os.path.exists(os.path.join(dist, stale)):
            os.remove(os.path.join(dist, stale))
    emit({"ok": True, "loader": target, "bytes": os.path.getsize(target),
          "usage": "execute_luau(code=<contents>) once, then: return shared.Forge.Probe.scan{root=...}"})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    st = sub.add_parser("selftest")
    st.add_argument("--workers", type=int, default=5)
    st.set_defaults(fn=cmd_selftest)
    b = sub.add_parser("blender").add_subparsers(dest="sub", required=True)
    r = b.add_parser("run")
    r.add_argument("script")
    r.add_argument("--args")
    r.add_argument("--blend")
    r.add_argument("--save")
    r.add_argument("--timeout", type=int, default=180)
    r.set_defaults(fn=cmd_blender_run)
    ba = b.add_parser("batch")
    ba.add_argument("jobs")
    ba.add_argument("--workers", type=int, default=4)
    ba.set_defaults(fn=cmd_blender_batch)
    l = sub.add_parser("luau").add_subparsers(dest="sub", required=True)
    l.add_parser("bundle").set_defaults(fn=cmd_luau_bundle)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

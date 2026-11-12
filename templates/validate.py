#!/usr/bin/env python3
"""
validate.py - static-analysis regression gate for src/ (stylua + selene + luau-lsp). JSON out, stdlib only.

    python scripts/validate.py                     # compare against scripts/validate.baseline.json, exit 1 on regression
    python scripts/validate.py --update-baseline   # accept the current numbers as the new baseline

Philosophy: this codebase carries a large legacy of warnings and backup copies. We do NOT gate on absolute
counts (nobody fixes 3,500 warnings); we gate on *not getting worse*: selene errors, selene parse errors and
luau-lsp TypeErrors may not exceed the baseline. Formatting drift is reported, never gated (a mass reformat of 254
files would bury real history).

Triage note: luau-lsp TypeErrors here are mostly typing hygiene (lazy fields, `local x: T = nil`), not crashes.
Treat a *new* TypeError as "look at it", not "it's broken".
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, "scripts", "validate.baseline.json")
DEFS = os.path.join(ROOT, ".cache", "globalTypes.d.luau")
DEFS_URL = "https://raw.githubusercontent.com/JohnnyMorganz/luau-lsp/main/scripts/globalTypes.d.luau"


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")


def ensure_defs():
    if os.path.isfile(DEFS) and os.path.getsize(DEFS) > 100000:
        return True
    import urllib.request
    os.makedirs(os.path.dirname(DEFS), exist_ok=True)
    try:
        with urllib.request.urlopen(DEFS_URL, timeout=60) as r, open(DEFS, "wb") as f:
            f.write(r.read())
        return True
    except Exception:  # noqa: BLE001
        return False


def stylua():
    r = run(["stylua", "--check", "src"])
    return {"files_needing_format": len(re.findall(r"^Diff in ", r.stdout + r.stderr, re.M))}


def selene():
    run(["rojo", "sourcemap", "default.project.json", "--output", "sourcemap.json"])
    r = run(["selene", "src", "--display-style", "json2"])
    errors, warns = collections.Counter(), collections.Counter()
    parse_errors = None
    for line in r.stdout.splitlines():
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "Summary":
            parse_errors = d.get("parse_errors")
            continue
        if d.get("type") != "Diagnostic":
            continue
        (errors if d["severity"] == "Error" else warns)[d["code"]] += 1
    return {"errors": sum(errors.values()), "errors_by_rule": dict(errors), "warnings": sum(warns.values()),
            "parse_errors": parse_errors}


def luau_lsp():
    if not ensure_defs():
        return {"error": "could not obtain Roblox type definitions"}
    r = run(["luau-lsp", "analyze", "--definitions=.cache/globalTypes.d.luau", "--sourcemap=sourcemap.json",
             "--base-luaurc=.luaurc", "src"])
    kinds = collections.Counter()
    for line in (r.stdout + r.stderr).splitlines():
        m = re.match(r"^.+?\(\d+,\d+[^)]*\): ([A-Za-z]+): ", line)
        if m:
            kinds[m.group(1)] += 1
    return {"type_errors": kinds.get("TypeError", 0), "by_kind": dict(kinds)}


GATES = [("selene", "errors"), ("selene", "parse_errors"), ("luau_lsp", "type_errors")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-baseline", action="store_true")
    a = ap.parse_args()
    result = {"stylua": stylua(), "selene": selene(), "luau_lsp": luau_lsp()}
    if a.update_baseline:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        print(json.dumps({"ok": True, "baseline_written": BASELINE, "result": result}))
        return 0
    if not os.path.isfile(BASELINE):
        print(json.dumps({"ok": False, "error": "no baseline; run with --update-baseline", "result": result}))
        return 2
    base = json.load(open(BASELINE, encoding="utf-8"))
    regressions = []
    for tool, key in GATES:
        cur, old = result[tool].get(key), base.get(tool, {}).get(key)
        if cur is None or old is None or cur > old:
            regressions.append({"gate": f"{tool}.{key}", "baseline": old, "current": cur})
    print(json.dumps({"ok": not regressions, "regressions": regressions, "result": result}))
    return 0 if not regressions else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
test.py - one command: build the throwaway test place, make sure Studio has it open, run Jest, print JSON.

    python scripts/test.py            # use the open tests.rbxl window if there is one, else launch it
    python scripts/test.py --fresh    # kill the tests.rbxl Studio window (only that one) and relaunch a fresh build

Exit 0 = all green, 1 = failures, 2 = could not run (environment). Never touches your real place: tests run in a
separate place built by Rojo from `test.project.json` (Packages + Jest + the pure modules under test).

How it runs: drives Roblox's built-in Studio MCP server over stdio (`%LOCALAPPDATA%\\Roblox\\mcp.bat`) as its own
client, calls execute_luau in the test place's Edit DataModel -> ServerScriptService.TestRunner.run() -> JSON.
Needs: Roblox Studio (already updated), rojo + wally installed, `wally install` done, Studio's MCP server enabled.
"""
import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACE = os.path.join(ROOT, "build", "tests.rbxl")
RUN = 'return require(game:GetService("ServerScriptService").TestRunner).run()'


def emit(obj, code):
    print(json.dumps(obj))
    sys.exit(code)


class Mcp:
    def __init__(self):
        bat = os.path.expandvars(r"%LOCALAPPDATA%\Roblox\mcp.bat")
        self.p = subprocess.Popen(["cmd.exe", "/c", bat], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", bufsize=1)
        self.i = 0
        self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test.py", "version": "0"}})
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.p.stdin.flush()

    def rpc(self, method, params=None, timeout=120):
        self.i += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.i, "method": method, "params": params or {}}) + "\n")
        self.p.stdin.flush()
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self.p.stdout.readline()
            if not line:
                return {}
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if m.get("id") == self.i:
                return m
        return {}

    def tool(self, name, args, timeout=120):
        r = self.rpc("tools/call", {"name": name, "arguments": args}, timeout)
        res = r.get("result", {})
        text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        return text, bool(res.get("isError")) or "error" in r

    def studios(self):
        text, err = self.tool("list_roblox_studios", {})
        try:
            return json.loads(text).get("studios", [])
        except ValueError:
            return []

    def close(self):
        try:
            self.p.terminate()
        except Exception:  # noqa: BLE001
            pass


def find_test_studio(m):
    return next((s for s in m.studios() if s.get("name") == "tests.rbxl" or s.get("file") == "tests.rbxl"), None)


def parse_result(text):
    """The tool returns text containing the run() JSON, sometimes double-encoded. Find and decode it."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return None
    chunk = text[start:end + 1]
    for _ in range(3):
        try:
            v = json.loads(chunk)
        except ValueError:
            try:
                v = json.loads(chunk.replace('\\"', '"'))
            except ValueError:
                return None
        if isinstance(v, str):
            chunk = v
            continue
        return v
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--wait", type=int, default=180, help="seconds to wait for Studio to open the test place")
    a = ap.parse_args()

    os.makedirs(os.path.dirname(PLACE), exist_ok=True)
    b = subprocess.run(["rojo", "build", "test.project.json", "-o", PLACE], cwd=ROOT, capture_output=True, text=True)
    if b.returncode != 0:
        emit({"ok": False, "stage": "rojo build", "error": (b.stderr or b.stdout)[-400:]}, 2)
    if not os.path.isdir(os.path.join(ROOT, "DevPackages")):
        emit({"ok": False, "stage": "setup", "error": "DevPackages missing; run `wally install` first"}, 2)

    m = Mcp()
    try:
        studio = find_test_studio(m)
        if studio and a.fresh:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-Process RobloxStudioBeta | Where-Object { $_.MainWindowTitle -match 'tests' } | Stop-Process -Force"],
                           capture_output=True)
            time.sleep(3)
            studio = None
        if not studio:
            os.startfile(PLACE)  # opens in Roblox Studio (may self-update first)
            t0 = time.time()
            while time.time() - t0 < a.wait and not studio:
                time.sleep(3)
                studio = find_test_studio(m)
        if not studio:
            emit({"ok": False, "stage": "launch", "error": "tests.rbxl did not appear in Studio within {}s "
                  "(is Studio updating or is its MCP server disabled?)".format(a.wait)}, 2)
        text, err = m.tool("execute_luau", {"code": RUN, "datamodel_type": "Edit", "studio_id": studio["id"]}, timeout=180)
        result = parse_result(text)
        if result is None:
            emit({"ok": False, "stage": "run", "error": "could not parse runner output", "raw": text[-500:]}, 2)
        result["studio_reused"] = not a.fresh
        emit(result, 0 if result.get("ok") else 1)
    finally:
        m.close()


if __name__ == "__main__":
    main()

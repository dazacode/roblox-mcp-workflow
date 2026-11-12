#!/usr/bin/env python3
"""
bench_mcp.py - apples-to-apples latency benchmark of Studio MCP servers, driven over raw stdio.

Both servers are spawned as separate MCP clients by this script, so the *same* harness, machine, Studio
instance and payloads are used. Nothing here involves a model: it measures server + plugin round trips.

    python scripts/bench_mcp.py --calls 50 [--servers rbx-studio,builtin] [--rbx-exe PATH]

Safe: only READ-ONLY Luau is executed (`return 1`, a 20 KB string, a property read). Requires Studio to be in
Edit mode with no modal dialog open (an open dialog makes every call fail: "Target is not reachable").

Caveat for rbx-studio: if another rbx-studio server already owns the bridge port (e.g. your MCP client), this
instance runs as a *peer* and proxies through it - one extra loopback hop, so its numbers are slightly pessimistic.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time


class Client:
    def __init__(self, argv, name):
        self.name = name
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, encoding="utf-8", errors="replace", bufsize=1)
        self.next_id = 1
        self.lock = threading.Lock()

    def rpc(self, method, params=None, timeout=60):
        with self.lock:
            rid = self.next_id
            self.next_id += 1
            self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}) + "\n")
            self.p.stdin.flush()
            t0 = time.time()
            while time.time() - t0 < timeout:
                line = self.p.stdout.readline()
                if not line:
                    return {"error": "server closed stdout"}
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                if m.get("id") == rid:
                    return m
            return {"error": "timeout"}

    def handshake(self):
        r = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "bench", "version": "0"}})
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.p.stdin.flush()
        return r

    def call(self, tool, args):
        t0 = time.perf_counter()
        r = self.rpc("tools/call", {"name": tool, "arguments": args})
        dt = (time.perf_counter() - t0) * 1000
        res = r.get("result", {})
        failed = "error" in r or res.get("isError", False)
        text = ""
        for c in res.get("content", []) or []:
            if c.get("type") == "text":
                text += c.get("text", "")
        return dt, failed, text

    def close(self):
        try:
            self.p.terminate()
        except Exception:  # noqa: BLE001
            pass


def stats(ms):
    s = sorted(ms)
    return {"n": len(s), "median_ms": round(statistics.median(s), 1), "mean_ms": round(statistics.fmean(s), 1),
            "p95_ms": round(s[min(len(s) - 1, int(len(s) * 0.95))], 1), "min_ms": round(s[0], 1), "max_ms": round(s[-1], 1)}


SCENARIOS = {
    "noop": "return 1",
    "payload_20kb": "return string.rep('x', 20000)",
    "read_property": "return game:GetService('Lighting').ClockTime",
}


def bench(client, run, calls, warmup=5):
    out = {}
    for name, code in SCENARIOS.items():
        ms, fails = [], 0
        for i in range(calls + warmup):
            dt, failed, text = run(client, code)
            if i < warmup:
                continue
            if failed:
                fails += 1
                last = text[:200]
            else:
                ms.append(dt)
        out[name] = (stats(ms) if ms else {"n": 0}) | ({"failures": fails, "last_error": last} if fails else {})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calls", type=int, default=50)
    ap.add_argument("--servers", default="rbx-studio,builtin")
    ap.add_argument("--rbx-exe", default=os.path.expanduser(r"~\tools\rbx-studio-mcp\server\target\release\rbx-studio-mcp.exe"))
    a = ap.parse_args()
    report = {"calls_per_scenario": a.calls, "servers": {}}
    for s in a.servers.split(","):
        if s == "rbx-studio":
            c = Client([a.rbx_exe], s)
            c.handshake()
            time.sleep(2)  # let the peer/bridge settle
            run = lambda cl, code: cl.call("execute_luau", {"source": code})
            probe = c.call("studio_status", {})
        else:
            bat = os.path.expandvars(r"%LOCALAPPDATA%\Roblox\mcp.bat")
            c = Client(["cmd.exe", "/c", bat], s)
            c.handshake()
            dt, failed, text = c.call("list_roblox_studios", {})
            try:
                sid = json.loads(text)["studios"][0]["id"]
            except Exception:  # noqa: BLE001
                report["servers"][s] = {"error": "no studio found", "detail": text[:300]}
                c.close()
                continue
            run = lambda cl, code, sid=sid: cl.call("execute_luau", {"code": code, "datamodel_type": "Edit", "studio_id": sid})
            probe = (dt, failed, text)
        if probe[1]:
            report["servers"][s] = {"error": "studio not reachable", "detail": probe[2][:300]}
            c.close()
            continue
        report["servers"][s] = bench(c, run, a.calls)
        c.close()
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    sys.exit(main())

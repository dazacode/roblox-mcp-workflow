# Reverse engineering with REA: scope, status, and what actually finds game bugs

[REA](https://github.com/morluto/rea) ("Reverse Engineer Anything", MIT) is an MCP server for static and runtime
analysis of binaries, JavaScript/Electron apps, .NET assemblies and web pages. This workflow includes it for one
job: **auditing software you run or are authorised to examine.** It is not the primary way to debug a game.

## Vetting record (2026-11-12)

| Check | Result |
|---|---|
| Licence | MIT |
| Distribution | npm `rea-agents@6.0.0`, **SLSA provenance attestation present** (verified with `npm view`) |
| Install | already registered pinned: `npx -y rea-agents@6.0.0 mcp` (version-pinned, not `@latest`) |
| Transport | stdio by default. Opt-in HTTP MCP is **unauthenticated plain HTTP** (their SECURITY.md): don't enable it |
| Trust model | runs with the host account's permissions; target content is untrusted data; static inspection does not authorise execution |
| Read | README, DISCLAIMER.md, SECURITY.md, npm metadata. **Not** read: the TypeScript source or native bridges |

## Status on this machine
- Server connects; 6 providers listed (Ghidra, Hopper, IDA adapter, macOS-native, artifact graph, .NET static).
- **Native deep analysis is unavailable**: no Hopper/IDA, and only Java 8 (Ghidra needs a newer JDK). Static
  JavaScript / .NET / web analysis needs no provider. Not yet exercised on a real target (unverified).

## In scope
- Supply-chain audit of tools you run: compare a published binary or package against a source build; check a
  Studio plugin or MCP server for unexpected capabilities. (Example: the community Studio MCP server in
  `STUDIO-MCP.md` was audited from source; REA's artifact comparison is the way to check a *prebuilt* binary.)
- Inspecting web bundles, Electron apps and .NET tools you are licensed to examine.
- Understanding your own tooling's runtime behaviour (e.g. confirm a local server's outbound hosts match its
  static audit). *Runtime observation tools are untested here.*

## Out of scope (not done by this workflow)
- **Roblox Studio, the Roblox client/player, or the engine**: Roblox's terms prohibit reverse engineering the
  platform, the client has anti-tamper protection, and REA's own disclaimer excludes circumventing anti-cheat or
  tampering with online services. Do not attach debuggers, instrument, or disassemble them.
- Circumventing licences/DRM, or reproducing protected code from third-party assets (the purchased city pack).

## Why it wouldn't catch your game's bugs anyway
Game logic is Luau that Studio hands us as source. The engine is closed, and nothing in a disassembly of it tells
you why *your* `PedBaker` indexes nil. Hard bugs are found with, in order:

1. **Static gate**: selene + luau-lsp + a baseline (`STATIC-ANALYSIS.md`): catches typos, wrong members, global leaks,
   deprecated APIs before a playtest.
2. **Runtime digest**: `Log.digest` in Server *and* Client, grouped by code with script+line.
3. **Breakpoints and thread inspection**: Roblox's `rbx-debug` skill.
4. **Profiling**: `rbx-perf-profiling` (MicroProfiler), `rbx-luau-heap-profiling` (leaks), `rbx-scene-analysis`.
5. **Network faults**: `rbx-network-simulator` (latency, packet loss, desync).
6. **Targeted unit tests**: `rbx-unit-test` for pure ModuleScripts.

# Unit testing a Roblox codebase with Wally + Jest + Rojo, driven by MCP

Verified on a real project (271 scripts): **57 tests pass in ~0.2 s**, run from one command, and a mutation check
confirmed the suite catches injected bugs. `templates/testing/` has the reusable files.

## Shape
```
wally.toml            deps (runtime) + dev-dependencies (Jest). Commit wally.lock; gitignore Packages/ DevPackages/
default.project.json  the real game: maps Packages -> ReplicatedStorage.Packages. NEVER maps DevPackages.
test.project.json     a throwaway test place: Packages + DevPackages + the modules under test + tests/specs
tests/specs/*.spec.luau + jest.config.luau   Jest specs (ModuleScripts named *.spec)
tests/TestRunner.luau   runs Jest, returns ONE JSON string (totals, per-file, failures)
scripts/test.py         build place -> ensure Studio has it -> run -> print JSON -> exit code
```
Tests run in a **separate place built by Rojo**, so the real (possibly Team Create) place is never modified and
test libraries never ship to players.

## One command
`python scripts/test.py` (reuse an open test window) or `--fresh` (kill only that window, rebuild, relaunch).
Exit 0 green / 1 failures / 2 environment problem. It drives Roblox's built-in Studio MCP over stdio, so it needs
Studio open with its MCP server enabled; there is no headless Jest runner for Roblox engine APIs here.

## Facts established by running it
- Jest now ships under the official `roblox/` Wally scope (`roblox/jest@3.21.0` + `roblox/jest-globals`), newer than
  the older `jsdotlua/jest@3.10.0`. Check the registry (`wally search`) instead of trusting remembered versions.
- Run with `ci = true`; match specs with `testMatch = { "**/*.spec" }`.
- Jest runs fine in Edit mode via `execute_luau` (it yields; the tool waits). Play mode also works via a Script.
- `t.number(NaN)` is **false** (asserted by a passing test), so `t` is safe for validating remote arguments.
- ProfileStore requires cleanly in Studio and warns "API services unavailable" (expected, no DataStore access).

## Writing tests that find bugs instead of echoing code
- Derive expected values from the **documented contract and arithmetic**, not by running the function and pasting.
- Add a few property checks (loop over angles/points; assert invariants). One found a real bug:
  `bearing()` returned exactly 360 when facing due north, because float noise made `atan2` slightly negative and
  `% 360` rounded up. A hand-picked example set would not have hit it.
- A found-but-unfixed bug becomes `it.skip("KNOWN BUG: ...")` plus a passing test for what *does* hold, so the
  baseline stays green and the bug stays visible. Don't silently loosen the assertion.
- Prove the suite has teeth: mutate the code under test (off-by-one, wrong constant), expect failures, revert.

## Gotchas
- **Studio can't run two windows while it needs to self-update.** If a launch seems to hang, the Studio installer is
  running; wait for it, then retry. Close/relaunch only the test window, never the user's real place.
- The test place is disposable: editing scripts in it (for mutation checks) is fine, but the files on disk are the
  source of truth; rebuild with `--fresh` before trusting a result.
- Third-party packages are code with server privileges. After `wally install`, scan `Packages/` and `DevPackages/`
  for `require(<asset id>)`, `loadstring`, `getfenv`, `InsertService`, `rbxassetid`, obfuscated strings, and read
  the hits. Findings here were benign: Jest's runtime legitimately uses `loadstring`/`getfenv` (DevPackages only);
  `evaera/promise` bundles an old TestEZ harness (with `loadstring`) that ships if you map `Packages` whole.
- Not covered: anything needing real players, physics or replication; those need playtests (`rbx-unit-test` skill,
  `playtest` subagent), not Jest.

# Static analysis for a synced Roblox codebase: lessons and a regression gate

Measured on a real project (271 scripts, 5 MB of Luau pulled with `sync pull`). `templates/validate.py` is the
gate used there.

## Pitfalls we hit (each cost real time)
- **Selene without `std = "roblox"` reports ~27,000 parse errors**: it treats Luau as Lua 5.1, so types, `+=` and
  `continue` all "fail". Always ship `selene.toml` with `std = "roblox"` plus a generated `roblox.yml`
  (`selene generate-roblox-std`). With it: 0 parse errors.
- **luau-lsp needs Roblox type definitions** (`globalTypes.d.luau`, ~0.9 MB, from the luau-lsp repo) plus a Rojo
  `sourcemap.json`, otherwise `game.X` paths are untyped.
- **Don't capture tool output through PowerShell `Out-File`**: it wraps long lines and splits diagnostics (our first
  type-error count was 171; the true count was 201). Capture in-process (subprocess) as `validate.py` does.
- **StyLua will want to reformat almost everything** (254 of 271 files). Report, never gate, and don't mass-reformat.
- **Rokit can fail silently** (an empty tool directory and a shim that errors "file not found"). Verify every pinned
  tool with `--version`.

## Triage reality
Of 201 luau-lsp TypeErrors, the two largest clusters we sampled (a lazily-created table field, and
`local x: Part = nil` before lazy init) were **both runtime-safe false positives**: typing hygiene, not crashes.
Selene's `Vector3.yAxis:Cross(...)` "errors" are std-model gaps. Roughly half of all hits sit in backup copies
inside ServerStorage. Lesson: report counts, sample before you call anything a bug, and gate on *regression*.

## The gate
Fails only if selene errors, selene parse errors or luau-lsp TypeErrors exceed the committed baseline. Verified by
planting a bug (24 -> 25 errors, 0 -> 1 parse errors, 201 -> 202 type errors: tripped) and removing it (passed).
```bash
python scripts/validate.py                    # compare with scripts/validate.baseline.json
python scripts/validate.py --update-baseline  # accept current numbers
```

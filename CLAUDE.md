# Instructions for AI agents working in or with this repo

This repository is a **workflow kit** for building Roblox experiences through MCP. It is not a game.

1. Read `WORKFLOW.md` first. It defines the loop (SPEC -> BUILD -> MEASURE -> DIFF -> REPAIR -> LOOK -> SHIP),
   tool routing between the two Studio MCP servers, the debug protocol, and the safety rules.
2. Before touching a user's place: `get_studio_state`, `list_roblox_studios`, confirm the target. Never stop a
   playtest you didn't start. Uploads are permanent and need explicit approval.
3. Commands (JSON in/out, stdlib Python): `python forge.py doctor | selftest | blender run|batch | luau bundle`.
4. After changing `blender/rbx_lib.py` run `python forge.py selftest` (needs Blender 4.x; 5 checks, ~20 s).
5. After changing `luau/*.luau`, run `python forge.py luau bundle` and hot-reload with `dist/load_<Module>.luau`;
   verify against a real place (read-only probes) - there is no offline Luau test harness for engine APIs.
6. Claims in docs are tagged verified / sourced / unverified (`docs/RESEARCH.md`). Keep that discipline:
   do not promote an assumption to a fact without running it.

Not affiliated with or endorsed by Roblox Corporation.

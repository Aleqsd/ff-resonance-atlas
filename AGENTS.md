# AGENTS.md

Instructions for AI coding agents working in this repository.

FF Resonance Atlas is a **read-only** helper for FINAL FANTASY RESONANCE (Steam, Unreal Engine 5.6). From
the user's own game install and save it builds an offline page of missing tablet shards and chests
(`work/atlas.html`, plus `work/missing.json`), and it shows achievement counters (`counter.py`).

## What the user usually wants

| The user asks | Do this |
|---|---|
| "Set it up", "install it", "make it work" | Run the setup below, then open `work/atlas.html` for them. |
| "Where are my missing tablet shards / chests?" | Run `python atlas.py` (refreshes from the newest save), then answer from `work/missing.json` and open `work/atlas.html`. |
| "How many Resonances (or staggers) do I have left?" | Windows, game running: `python counter.py --once`. Otherwise: `python counter.py --save`. |
| "Show me a live counter while I play" | Windows: start `pythonw counter.py` detached (it opens a small always-on-top window and keeps running). |
| "I just played, update it" | `python atlas.py` |

## Hard rules

- **Never write, move, rename or delete anything** in the game install folder, the Steam folder or the
  save folder (`%LOCALAPPDATA%\FFRS`, or `.../steamapps/compatdata/3259780/pfx/...` on Linux). The
  scripts copy saves before reading them; do not copy saves anywhere else yourself.
- Never start the game, never install mods, never write to the game's memory. `counter.py` only reads it,
  and you must not change it to do anything else.
- Never print, log or commit the save encryption key (read at run time by `savekey.py`).
- `work/` holds data extracted from the user's copy of the game and their save. Do not commit it, upload
  it or share its files.
- Ask the user before installing system software (Rust, Python). Installing the Python packages from
  `requirements.txt` / `requirements-mcp.txt` is part of the normal setup.

## Setup

1. `python bootstrap.py --json` reports what is ready. Read `next_step`.
2. `python bootstrap.py` does everything that is missing: installs the Python packages, builds
   `tools/ooz_cli` and `tools/texdec` with cargo, extracts game data, builds the atlas. The **first run
   extracts game data for several minutes**: use a long timeout or run it in the background.
3. If cargo is missing (exit code 2): ask the user, then install Rust (`winget install Rustlang.Rustup` on
   Windows, https://rustup.rs elsewhere), open a new shell so `PATH` is updated, and run step 2 again.
4. If the game or the saves are not found: ask the user where they are and set `FFRS_GAME_DIR` (the
   `FINAL FANTASY RESONANCE` folder that contains `FFRS/Content/Paks`) or `FFRS_SAVE_DIR`.
5. On Windows, if the Rust build fails with a path that is too long, move the clone to a short folder such
   as `C:\ffrs` and retry.

Use `python3` on Linux / Steam Deck. The live counter is Windows-only; use `counter.py --save` elsewhere.
After a game update: `python extract_gamedata.py --force`, then `python atlas.py`.

## Reading `work/missing.json`

```
{ "save": "31/10/2026 à 09:22", "playtime_h": 81.1,
  "summary": { "shards": [found, 99], "chests": [opened, total], "chests_past": n, "in_bag": n,
               "turned_in": n, "collector": [ { "at": 80, "what": "reward" } ] },
  "islands": [ { "island": "...", "probably_lost": false,
                 "places": [ { "pin": 1, "place": "...", "how_to_get_there": "...", "tip": "...",
                               "items": [ { "kind": "shard" | "chest", "what": "...", "marker": 1,
                                            "plan": "Niveau 1 / 2", "note": "" } ] } ] } ] }
```

- `pin` is the numbered pin on the island's world map in the atlas; `marker` is the number on the map
  plan named in `plan`. Point the user to both: "Island X, place Y (pin 1), plan 'Niveau 2 / 3', marker 2".
- Islands with `probably_lost: true` hold chests from past versions of a map: they cannot be counted as
  missing. Mention them only if asked.
- Names are the game's **French** names. If the user speaks another language, translate but keep the
  French name in parentheses, since the atlas page shows the French names.
- `summary.in_bag` shards are picked up but not yet handed in; `collector` lists the next rewards.

## MCP server

`pip install -r requirements-mcp.txt`, then register `python <repo>/mcp_server.py` (stdio) in the MCP
client. A project-level `.mcp.json` is included. Tools: `setup_status`, `refresh_atlas`,
`missing_items(kind, island, include_probably_lost, refresh_if_stale)`, `achievement_counters(source)`.

## Code map

| File | Role |
|---|---|
| `bootstrap.py` | one-command setup and status report (`--check`, `--json`) |
| `atlas.py` | newest save → `work/atlas.html` and `work/missing.json` |
| `counter.py` | achievement counters: live window, `--once`, `--save` |
| `mcp_server.py` | MCP server over stdio |
| `config.py` | auto-detection of game, saves, work folder, helper tools; environment overrides |
| `extract_gamedata.py` | extracts the game data the atlas needs into `work/` |
| `savekey.py`, `gvas.py` | save key lookup in the game's own config, save parsing |
| `utoc.py`, `zen.py`, `extract.py`, `pakfile.py`, `paklist.py`, `dt.py`, `refl.py`, `peutil.py` | Unreal Engine 5.6 container, package, table and reflection readers |
| `scan_levels.py`, `scan_areas.py`, `scan_entr.py`, `tex.py` | level scans and map plan decoding |
| `build_data.py`, `build_page.py`, `template.html` | cross-reference with the save and page generation |
| `curated/` | hand-made French labels and fixes for the tested game build |
| `tools/ooz_cli`, `tools/texdec` | Rust helpers (Oodle decompression, BCn texture decoding) |
| `docs/`, `tools/build-site.sh`, `Gemfile`, `wrangler.jsonc` | project page https://ff-resonance-atlas.zqsdev.com: Jekyll (same theme and plugins as GitHub Pages) built and served by a Cloudflare Worker; Workers Builds redeploys it on every push to `main` |

## After changing code

- `python bootstrap.py --check`
- `python atlas.py`, then open `work/atlas.html`
- `python counter.py --once` with the game running (Windows), `python counter.py --save`
- For the MCP server: start it from an MCP client and call `setup_status` and `missing_items`.

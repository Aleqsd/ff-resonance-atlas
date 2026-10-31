# ffrs-atlas

A completion helper for **FINAL FANTASY RESONANCE** (Steam). It reads your own copy of the game and
your own save, then builds a single offline HTML page (`work/atlas.html`) that lists **only what you
are still missing**:

- **Tablet shards** (*Fragments de tablette*) and **treasure chests** not yet picked up,
- grouped island by island, place by place, on the game's own **map plans** with numbered markers,
- a world map per island with a pin for every place that still has something,
- tick boxes to cross items off while you play (stored in your browser only),
- the shard-collector rewards still ahead of you,
- an optional "late game" to-do tab (see below).

The newest save slot is picked automatically. The page is in **French** (place and item names come from
the game's official French text).

> **Spoilers:** the page names places and items from the whole game, including areas you have not
> reached yet.

## Safety

- **Read-only.** Game files and saves are only opened for reading. Each save is first copied into the
  work folder, and only that copy is decrypted and parsed (then deleted). Nothing is ever written to the
  game folder, the Steam folder or the save folder.
- No mod, no injection, no memory reading, and the game is never launched. Steam achievements and
  cloud saves are not affected.
- Everything happens locally. Nothing is uploaded. (The atlas page only fetches web fonts from
  Google Fonts when you open it; without a connection it falls back to system fonts.)

## Requirements

- **Windows**, or **Linux / Steam Deck** running the game through Proton (the Proton prefix
  `steamapps/compatdata/3259780/pfx/...` is searched automatically).
- **Python 3.10+** and the packages in `requirements.txt`:
  ```
  pip install -r requirements.txt
  ```
- A **Rust toolchain** (https://rustup.rs, Rust 1.85 or newer) to build the two small helper programs
  once:
  ```
  cd tools/ooz_cli && cargo build --release && cd ../..
  cd tools/texdec  && cargo build --release && cd ../..
  ```
  `ooz_cli` decompresses the game's Oodle-compressed data blocks, `texdec` decodes BCn textures (map
  plans) to PNG. Both only read their input.
- A few hundred MB of free disk space for `work/` (plus the Rust build folders) and a few minutes for the first extraction.

## Usage

```
python extract_gamedata.py     # once (use --force after a game update)
python atlas.py                # after each play session -> work/atlas.html
```

`extract_gamedata.py` skips steps whose output already exists; after a game update run it with
`--force` so everything is extracted again. On Linux use `python3`. Open `work/atlas.html` in any browser (desktop or phone).

Everything is auto-detected (Steam libraries through `libraryfolders.vdf`, saves in
`%LOCALAPPDATA%\FFRS` or the Proton prefix). If detection fails, set these environment variables:

| Variable | Meaning |
|---|---|
| `FFRS_GAME_DIR` | the `FINAL FANTASY RESONANCE` install folder (the one containing `FFRS/Content/Paks`) |
| `FFRS_SAVE_DIR` | a folder containing `GameSaveData*.sav` (searched recursively) |
| `FFRS_WORK` | where extracted data and the page are written (default `./work`) |
| `FFRS_OOZ`, `FFRS_TEXDEC` | paths to the two helper programs (default `tools/*/target/release/`) |
| `FFRS_SAVE_KEY` | optional: the save encryption key, if it cannot be read from the game install |

Flatpak Steam on Linux is not searched by default: point `FFRS_GAME_DIR` and `FFRS_SAVE_DIR` to the
paths under `~/.var/app/com.valvesoftware.Steam/`.

The atlas page embeds map images decoded from your copy of the game. Keep it for your own use;
please do not redistribute it.

## How it works

1. **IoStore / Zen reader** (`utoc.py`, `zen.py`, `extract.py`): reads the `.utoc` / `.ucas` container
   index, decompresses blocks with `ooz_cli` and parses Unreal Engine 5.6 Zen packages. Classic `.pak`
   files (config, localisation) are read by `pakfile.py` / `paklist.py`.
2. **Reflection dump** (`refl.py`, `peutil.py`): the game cooks its assets with *unversioned
   properties*, so the property layout of each class is not stored in the assets. It is recovered from
   the reflection data compiled into the game executable.
3. **Tables and text** (`dt.py`): treasure tables, item tables, map tables and the French/English
   localisation (`.locres`).
4. **Level scans** (`scan_levels.py`, `scan_areas.py`, `scan_entr.py`): every level is scanned for
   treasure boxes and field items (with their unique IDs and world positions), map capture areas (the
   plans shown in the in-game map menu) and entrances between maps.
5. **Map plans** (`tex.py` + `texdec`): the game's own plan textures are decoded locally and embedded.
6. **Save**: the newest `GameSaveData*.sav` is copied, decrypted with the AES key that the game itself
   ships in its config file `DefaultSQEXSaveGameSystem.ini` (read at run time from your install by
   `savekey.py`; the key is not part of this repository), then parsed as GVAS (`gvas.py`).
7. **Cross-reference** (`build_data.py`, `build_page.py`): opened chests, picked-up items, inventory,
   shards already handed in and story progress are matched against the scanned level data; what is
   left is grouped by island, place and plan, and injected into `template.html`.

`curated/` holds small hand-made mappings for the tested game build: readable French place labels,
floor labels, how to reach each place, streamed sub-levels per map, and a few manual fixes
(`overrides.json`).

## Limits

- Tested with the Steam build of FINAL FANTASY RESONANCE current as of **October 2026** (Unreal
  Engine 5.6). A game update can change packages or class layouts; re-run `extract_gamedata.py --force`, and if
  parsing fails the scripts (or `curated/`) may need an update.
- Some rooms are missing from the game's own map plans: those items get a **dashed marker at an
  estimated position**.
- Chests that only existed in prologue or past-story versions of a map are **probably no longer
  obtainable**; they are listed separately in a collapsed section instead of being counted as missing.
- The UI and place names are French only.

## Optional late-game to-do

If `work/late_todo.json` exists, a second tab "Fin de jeu" shows it as a tickable list. Format:

```json
{
  "intro": "Short state line. Déjà terminé : ... Ordre conseillé : 1) first step ; 2) second step",
  "categories": [
    {
      "name": "Quêtes",
      "items": [
        { "title": "Quest name", "where": "Place name", "detail": "Notes", "status": "à faire", "priority": "haute" }
      ]
    }
  ],
  "caveats": "Optional closing note."
}
```

All fields except `categories[].name` and `items[].title` are optional. `priority` values `haute` and
`moyenne` are highlighted. When `where` matches place names in the atlas, a "Voir sur l'atlas" link is
added. In `intro`, the optional markers `Déjà terminé :` and `Ordre conseillé :` (followed by
`1) ... ; 2) ...`) are rendered as a collapsed "already done" note and a numbered list.

## Licenses and disclaimer

The code in this repository is released under the **MIT License** (see `LICENSE`).

The two Rust helpers depend only on permissively licensed crates: `oozextract` (MIT),
`texture2ddecoder` (MIT OR Apache-2.0; its BCn decoder is derived from MIT-licensed code), `png`
(MIT OR Apache-2.0) and their dependencies (MIT, Apache-2.0, Zlib, Unlicense, 0BSD, Unicode-3.0;
see `tools/*/Cargo.lock`). No third-party source is vendored here. If you redistribute compiled
binaries, include those crates' license notices.

This is an **unofficial fan tool**. It is not affiliated with, endorsed, sponsored or approved by
SQUARE ENIX. **No game assets or game text are included** in this repository, apart from a few short
place names in the curated mapping files: everything else is extracted locally from your own copy of
the game. FINAL FANTASY and FINAL FANTASY RESONANCE are trademarks or registered trademarks of
Square Enix Holdings Co., Ltd. Use at your own risk.

## En français

**ffrs-atlas** génère une page HTML hors ligne (`work/atlas.html`) qui liste les **Fragments de
tablette** et les **coffres** qu'il te reste à trouver dans FINAL FANTASY RESONANCE, île par île, sur
les plans de carte du jeu avec des repères numérotés. La sauvegarde la plus récente est choisie
automatiquement. Attention : la page contient des noms de lieux de tout le jeu (spoilers).

- **Lecture seule** : les fichiers du jeu et les sauvegardes ne sont jamais modifiés (la sauvegarde est
  copiée puis lue), aucun mod, le jeu n'est pas lancé, les hauts faits Steam ne sont pas concernés.
- **Prérequis** : Python 3.10+ (`pip install -r requirements.txt`) et Rust
  (`cargo build --release` dans `tools/ooz_cli` et `tools/texdec`).
- **Utilisation** : `python extract_gamedata.py` une fois (`--force` après une mise à jour du jeu), puis
  `python atlas.py` après chaque session de jeu, et ouvre `work/atlas.html`.
- Outil de fan non officiel, sans lien avec SQUARE ENIX. Aucun fichier ni texte du jeu n'est fourni :
  tout est extrait localement depuis ta propre copie du jeu.

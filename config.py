"""Paths used by every script. Everything is auto-detected; override with environment variables if needed:
FFRS_GAME_DIR  game install folder (the one that contains FFRS/Content/Paks)
FFRS_SAVE_DIR  folder that contains GameSaveData*.sav (any depth below it)
FFRS_WORK      where extracted game data and outputs are written (default: ./work)
FFRS_OOZ, FFRS_TEXDEC  paths to the two helper tools (default: tools/*/target/release/)
"""
import os, re

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.environ.get('FFRS_WORK') or os.path.join(ROOT, 'work'))
CURATED = os.path.join(ROOT, 'curated')
EXE_SUFFIX = '.exe' if os.name == 'nt' else ''
GAME_FOLDER = 'FINAL FANTASY RESONANCE'
STEAM_APP_ID = '3259780'

STEAM_ROOTS = ['C:/Program Files (x86)/Steam', 'C:/Program Files/Steam',
               os.path.expanduser('~/.steam/steam'), os.path.expanduser('~/.local/share/Steam')]


def steam_libraries():
    libs = []
    for r in STEAM_ROOTS:
        vdf = os.path.join(r, 'steamapps', 'libraryfolders.vdf')
        if not os.path.isfile(vdf):
            continue
        libs.append(r)
        txt = open(vdf, encoding='utf-8', errors='ignore').read()
        libs += [p.replace(chr(92) * 2, '/') for p in re.findall(r'"path"[ \t]+"([^"]+)"', txt)]
    return list(dict.fromkeys(libs))


def _find_game():
    env = os.environ.get('FFRS_GAME_DIR')
    if env:
        return env
    for lib in steam_libraries():
        p = os.path.join(lib, 'steamapps', 'common', GAME_FOLDER)
        if os.path.isdir(os.path.join(p, 'FFRS', 'Content', 'Paks')):
            return p
    return None


def _find_saves():
    env = os.environ.get('FFRS_SAVE_DIR')
    if env:
        return env
    cands = []
    if os.environ.get('LOCALAPPDATA'):
        cands.append(os.path.join(os.environ['LOCALAPPDATA'], 'FFRS'))
    for lib in steam_libraries():  # Linux / Steam Deck (Proton prefix)
        cands.append(os.path.join(lib, 'steamapps', 'compatdata', STEAM_APP_ID, 'pfx', 'drive_c', 'users',
                                  'steamuser', 'AppData', 'Local', 'FFRS'))
    for c in cands:
        if os.path.isdir(c):
            return c
    return None


GAME_DIR = _find_game()
SAVE_DIR = _find_saves()
PAKS = os.path.join(GAME_DIR, 'FFRS', 'Content', 'Paks') if GAME_DIR else None
EXE = os.path.join(GAME_DIR, 'FFRS', 'Binaries', 'Win64', 'FFRS-Win64-Shipping.exe') if GAME_DIR else None
OOZ = os.environ.get('FFRS_OOZ') or os.path.join(ROOT, 'tools', 'ooz_cli', 'target', 'release', 'ooz_cli' + EXE_SUFFIX)
TEXDEC = os.environ.get('FFRS_TEXDEC') or os.path.join(ROOT, 'tools', 'texdec', 'target', 'release', 'texdec' + EXE_SUFFIX)


def require_game():
    if not GAME_DIR:
        raise SystemExit('Game not found. Set FFRS_GAME_DIR to the "FINAL FANTASY RESONANCE" install folder.')
    for tool in (OOZ, TEXDEC):
        if not os.path.isfile(tool):
            raise SystemExit(f'Missing helper tool {tool}. Build it first: cargo build --release (see README).')

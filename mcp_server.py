"""MCP server (stdio) for FF Resonance Atlas.

Lets an AI agent check the setup, refresh the atlas, list the missing tablet shards and chests, and read
the achievement counters, without parsing any output.

  pip install -r requirements-mcp.txt
  python mcp_server.py          (normally started by your MCP client: see README, "Use it from an AI agent")

Everything stays read-only on the game, Steam and save folders. The live counter only reads the game's
memory (no write, no injection).
"""
import contextlib, glob, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from mcp.server.fastmcp import FastMCP
import numpy  # noqa: F401  import before the server loop starts (a first import inside a tool call can hang on Windows)

import bootstrap, config, counter

mcp = FastMCP('ff-resonance-atlas', instructions=(
    'Helper for FINAL FANTASY RESONANCE (Steam). Call setup_status first. If the atlas is not built, ask the user '
    'to run (or run yourself) "python bootstrap.py" in the repository folder: the first run extracts game data '
    'for a few minutes. Place and item names are the game\'s French names. Never write to the game, Steam or '
    'save folders and never start the game.'))


def _quiet(fn, *a, **kw):
    """stdout is the MCP channel: send any stray prints to stderr."""
    with contextlib.redirect_stdout(sys.stderr):
        return fn(*a, **kw)


def _newest_save_mtime():
    files = glob.glob(os.path.join(config.SAVE_DIR, '**', 'GameSaveData*.sav'), recursive=True) if config.SAVE_DIR else []
    return max(map(os.path.getmtime, files)) if files else 0


@mcp.tool()
def setup_status() -> dict:
    """What is ready (Python packages, game install, saves, helper tools, extracted game data, atlas, game running)
    and the exact next step to run."""
    return _quiet(bootstrap.report)


@mcp.tool()
def refresh_atlas() -> dict:
    """Rebuild work/atlas.html and work/missing.json from the newest save (about 10-60 s). Use after the user played.
    Needs the setup to be complete (see setup_status)."""
    p = subprocess.run([sys.executable, os.path.join(HERE, 'atlas.py')], cwd=HERE, capture_output=True, stdin=subprocess.DEVNULL, text=True,
                       encoding='utf-8', errors='replace', env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    out = (p.stdout + p.stderr).strip().splitlines()
    return {'ok': p.returncode == 0, 'atlas_html': os.path.join(config.WORK, 'atlas.html'),
            'missing_json': os.path.join(config.WORK, 'missing.json'), 'log': out[-12:]}


@mcp.tool()
def missing_items(kind: str = 'all', island: str = '', include_probably_lost: bool = False,
                  refresh_if_stale: bool = True) -> dict:
    """Tablet shards and treasure chests still missing in the newest save, grouped by island and place, with how to
    reach each place and the marker number on the in-game map plan (same numbers as in atlas.html).

    kind: 'all', 'shard' or 'chest'. island: optional case-insensitive filter on the island name (French, e.g.
    'Zoldaad', 'Dirnado'). include_probably_lost: also list chests that only existed in past versions of a map.
    refresh_if_stale: rebuild the list first when a newer save exists."""
    path = os.path.join(config.WORK, 'missing.json')
    if refresh_if_stale and (not os.path.isfile(path) or os.path.getmtime(path) < _newest_save_mtime()):
        r = refresh_atlas()
        if not r['ok']:
            return {'error': 'Could not build the list. Check setup_status.', 'log': r['log']}
    if not os.path.isfile(path):
        return {'error': 'No list yet. Run "python bootstrap.py" in the repository folder first.'}
    data = json.load(open(path, encoding='utf-8'))
    islands = []
    for isl in data['islands']:
        if isl['probably_lost'] and not include_probably_lost:
            continue
        if island and island.lower() not in isl['island'].lower():
            continue
        places = []
        for pl in isl['places']:
            items = [it for it in pl['items'] if kind == 'all' or it['kind'] == kind]
            if items:
                places.append(dict(pl, items=items))
        if places:
            islands.append(dict(isl, places=places))
    count = sum(len(p['items']) for i in islands for p in i['places'])
    return {'save': data.get('save'), 'summary': data.get('summary'), 'count': count, 'islands': islands,
            'atlas_html': os.path.join(config.WORK, 'atlas.html')}


@mcp.tool()
def achievement_counters(source: str = 'live') -> dict:
    """Progress on the count-based achievements: Resonance Rapid Fire (400 Resonances), Keep Them on Their Toes
    (1000 staggers), Gil Comes and Goes (100,000 gil spent), Making Lid Proud (1,000,000 gil earned).

    source: 'live' reads the running game (Windows only, read-only memory access, about 2 s);
    'save' reads the newest save (any OS, only changes when the game saves)."""
    try:
        if source == 'save':
            values, name, when = _quiet(counter.save_values)
            return {'source': f'save {name} ({when})', 'counters': counter.progress(values)}
        if os.name != 'nt':
            return {'error': "Live mode needs Windows. Use source='save'."}
        return {'source': 'live game', 'counters': counter.progress(_quiet(counter.live_values))}
    except (RuntimeError, SystemExit) as e:
        return {'error': str(e)}


if __name__ == '__main__':
    mcp.run()

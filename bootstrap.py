"""One-command setup: check everything, install what is missing, build the atlas.

  python bootstrap.py            install Python packages, build the two helper tools, extract the game
                                 data (first time: a few minutes), then build work/atlas.html
  python bootstrap.py --check    only report what is ready and what is missing (changes nothing)
  python bootstrap.py --json     the same report as JSON (for scripts and AI agents)

Like every script here, it is read-only on the game, Steam and save folders, and never starts the game.
The live counter (counter.py) needs none of this: only Python 3.10+ and numpy.
"""
import glob, importlib.util, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config

PACKAGES = {'cryptography': 'cryptography', 'PIL': 'Pillow', 'numpy': 'numpy'}
NEEDED = ['refl.json', 'locres_fr.json', 'maps.json', 'landcapture.json', 'items.json', 'treasure_dt.json',
          'gimmicks.json', 'areas.json']
RUST_HELP = ('Install Rust from https://rustup.rs (on Windows: winget install Rustlang.Rustup), '
             'open a new terminal, then run: python bootstrap.py')


def game_running():
    if os.name != 'nt':
        return None
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq FFRS-Win64-Shipping.exe', '/NH'], capture_output=True, stdin=subprocess.DEVNULL,
                         text=True, errors='ignore', creationflags=0x08000000).stdout
    return 'FFRS-Win64-Shipping.exe' in out


def report():
    saves = sorted(glob.glob(os.path.join(config.SAVE_DIR, '**', 'GameSaveData*.sav'), recursive=True)) \
        if config.SAVE_DIR else []
    r = {
        'python': sys.version.split()[0],
        'python_ok': sys.version_info >= (3, 10),
        'packages_missing': [pip for mod, pip in PACKAGES.items() if importlib.util.find_spec(mod) is None],
        'game_dir': config.GAME_DIR,
        'save_dir': config.SAVE_DIR,
        'save_files': len(saves),
        'cargo': shutil.which('cargo'),
        'tools_built': {'ooz_cli': os.path.isfile(config.OOZ), 'texdec': os.path.isfile(config.TEXDEC)},
        'work_dir': config.WORK,
        'game_data_extracted': all(os.path.exists(os.path.join(config.WORK, f)) for f in NEEDED),
        'atlas_html': os.path.join(config.WORK, 'atlas.html'),
        'missing_json': os.path.join(config.WORK, 'missing.json'),
        'game_running': game_running(),
    }
    r['atlas_built'] = os.path.isfile(r['atlas_html'])
    if r['atlas_built'] and saves:
        r['atlas_up_to_date'] = os.path.getmtime(r['missing_json']) >= max(map(os.path.getmtime, saves)) \
            if os.path.isfile(r['missing_json']) else False
    r['next_step'] = next_step(r)
    return r


def next_step(r):
    if not r['python_ok']:
        return 'Install Python 3.10 or newer.'
    if r['packages_missing']:
        return 'Run: python bootstrap.py (installs ' + ', '.join(r['packages_missing']) + ')'
    if not r['game_dir']:
        return 'Game not found: set FFRS_GAME_DIR to the "FINAL FANTASY RESONANCE" install folder.'
    if not r['save_files']:
        return 'No save found: play until the first save, or set FFRS_SAVE_DIR to the folder with GameSaveData*.sav.'
    if not all(r['tools_built'].values()) and not r['cargo']:
        return RUST_HELP
    if not r['atlas_built'] or not r.get('atlas_up_to_date', True):
        return 'Run: python bootstrap.py'
    return 'Ready. Open ' + r['atlas_html'] + ' ; after playing run: python atlas.py ; live counter: pythonw counter.py'


def run(cmd, cwd=HERE):
    print('>', ' '.join(cmd), flush=True)
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    if subprocess.run(cmd, cwd=cwd, env=env).returncode:
        sys.exit(f'Failed: {" ".join(cmd)}')


def setup():
    r = report()
    if not r['python_ok']:
        sys.exit('Python 3.10 or newer is needed.')
    if r['packages_missing']:
        run([sys.executable, '-m', 'pip', 'install', '-r', os.path.join(HERE, 'requirements.txt')])
    if not r['game_dir']:
        sys.exit(next_step(r))
    if not r['save_files']:
        sys.exit(next_step(r))
    for name, path in (('ooz_cli', config.OOZ), ('texdec', config.TEXDEC)):
        if os.path.isfile(path):
            continue
        if not r['cargo']:
            print(RUST_HELP)
            sys.exit(2)
        run(['cargo', 'build', '--release'], cwd=os.path.join(HERE, 'tools', name))
        if not os.path.isfile(path):
            sys.exit(f'{name} was built but not found at {path}. If CARGO_TARGET_DIR is set, point '
                     f'FFRS_{"OOZ" if name == "ooz_cli" else "TEXDEC"} to the built executable.')
    run([sys.executable, os.path.join(HERE, 'extract_gamedata.py')])
    run([sys.executable, os.path.join(HERE, 'atlas.py')])
    print('\nDone.')
    print('  Atlas:            ', r['atlas_html'])
    print('  Missing list JSON:', r['missing_json'])
    print('  After playing:     python atlas.py')
    print('  Live counter:      pythonw counter.py   (Windows)')


if __name__ == '__main__':
    if '--json' in sys.argv:
        print(json.dumps(report(), indent=1))
    elif '--check' in sys.argv:
        for k, v in report().items():
            print(f'{k:20} {v}')
    else:
        setup()

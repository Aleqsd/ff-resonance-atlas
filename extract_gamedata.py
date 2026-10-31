"""Extract, from your own game install, the game data the atlas needs (read-only on the game folder).
Everything is written to the work folder (config.WORK, default ./work). Run it once, and again after a game update.
Usage:  python extract_gamedata.py [--force] [--only refl,locres,maps,landcapture,items,treasure_dt,gimmicks,areas,entrances]
A step is skipped when its output already exists, unless --force (or --only names it).
"""
import os, sys, json, time, argparse, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config

ENV = dict(os.environ, PYTHONIOENCODING='utf-8')
MAIN = 'FFRS-Windows'


def dump(obj, name, **kw):
    """write JSON atomically (an interrupted run never leaves a half-written file that would be skipped later)"""
    tmp = name + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, **kw)
    os.replace(tmp, name)


# ---------- steps run in this process (need refl.json for the property decoder) ----------

def step_locres():
    """Game.locres (fr + en) from the legacy .pak -> locres_fr.json, locres_en.json"""
    import glob
    from pakfile import Pak, read_locres
    paks = sorted(glob.glob(os.path.join(config.PAKS, '*.pak')), key=lambda p: '_P.' not in p)  # patch paks win
    opened = [Pak(p) for p in paks]
    for lang in ('fr', 'en'):
        name = f'../../../FFRS/Content/Localization/Game/{lang}/Game.locres'
        pak = next((p for p in opened if name in p.files), None)
        if pak is None:
            raise SystemExit(f'{name} not found in {paks}')
        d = read_locres(pak.read(name))
        dump(d, f'locres_{lang}.json')
        print(f'  {lang}: {len(d)} namespaces, {sum(len(v) for v in d.values())} strings')


def step_maps():
    """DT_MapData_* -> maps.json (map id -> level, island, ids used to group places)"""
    from dt import decode_datatable
    from extract import toc
    t = toc(MAIN)
    maps = {}
    for k in sorted(t.files):
        if '/Datatable/Map/MapData/DT_MapData_' not in k:
            continue
        try:
            d = decode_datatable(k)
        except Exception as e:
            print('  ERR', k, e)
            continue
        for rn, row in d['rows'].items():
            maps[row['id']] = {'row': rn, 'dev': row.get('developmentName'), 'name': row.get('name'),
                               'island': row.get('island'), 'level': row.get('level'), 'groupId': row.get('groupId'),
                               'regionId': row.get('regionId'), 'sameMapId': row.get('sameMapId'),
                               'mapType': row.get('mapType'), 'dungeonType': row.get('dungeonType'),
                               'attachedLevels': row.get('attachedLevels'), 'hiddenLevels': row.get('hiddenLevels'),
                               'wmi': row.get('worldMapIslandLevelList')}
    dump(maps, 'maps.json', indent=0, default=str)
    print(f'  {len(maps)} maps')


def step_landcapture():
    """DA_MapLandCapture -> landcapture.json (map plans: capture textures, world offsets, sizes)"""
    from zen import read_file, Package, Reader, read_unversioned, schema_for
    p = '../../../FFRS/Content/Datatable/Map/Land/DA_MapLandCapture.uasset'
    b = read_file(p)
    pkg = Package(b, p)
    e = pkg.exports[0]
    s, end = pkg.export_data(e)
    props = read_unversioned(Reader(b, s, end, pkg), schema_for('UCPP_DA_MapLandCapture'))

    def conv(o):
        if isinstance(o, tuple) and o and o[0] == 'obj':
            return str(pkg.pkg_index(o[1]))
        if isinstance(o, (list, tuple)):
            return [conv(x) for x in o]
        if isinstance(o, dict):
            return {k: conv(v) for k, v in o.items()}
        return o

    m = conv(props['MapLandCaptureDataMap'])
    dump(m, 'landcapture.json', indent=0, default=str)
    print(f'  {len(m)} maps with a plan')


def step_items():
    """item DataTables -> items.json (item id -> row name, name string key, type)"""
    from dt import decode_datatable
    items = {}
    for f in ['DT_ConsumablesItemData', 'DT_ValuableItemData', 'DT_ArtifactItemData', 'DT_EquipmentItemData',
              'DT_SeedItemData', 'Vision/DT_VisionItemData', 'Vision/DT_VisionUpgradeItemData']:
        try:
            d = decode_datatable(f'../../../FFRS/Content/Datatable/Item/{f}.uasset')
        except Exception as e:
            print('  ERR', f, str(e)[:300])
            continue
        for rn, row in d['rows'].items():
            iid = row.get('id', row.get('ID'))
            items[iid] = {'jp': rn, 'table': f, 'name': row.get('name') or row.get('Name'), 'type': row.get('itemType')}
    dump(items, 'items.json', indent=0)
    print(f'  {len(items)} items')


def step_treasure_dt():
    """Gimmick/TreasureBox/DT_* -> treasure_dt.json (chest contents per map)"""
    from dt import decode_datatable
    from extract import toc
    t = toc(MAIN)
    rows = []
    for pth in [k for k in t.files if '/Gimmick/TreasureBox/DT_' in k]:  # container order (kept: later steps rely on it)
        try:
            d = decode_datatable(pth)
        except Exception as e:
            print('  ERR', pth, e)
            continue
        for rn, row in d['rows'].items():
            row['_dt'] = pth.split('/')[-1][:-7]
            row['_row'] = rn
            rows.append(row)
    dump(rows, 'treasure_dt.json', indent=0)
    print(f'  {len(rows)} chest rows')


# ---------- steps run as separate scripts (they write their output in the current folder) ----------
SCRIPTS = {'refl': 'refl.py', 'gimmicks': 'scan_levels.py', 'areas': 'scan_areas.py', 'entrances': 'scan_entr.py'}
INPROC = {'locres': step_locres, 'maps': step_maps, 'landcapture': step_landcapture, 'items': step_items,
          'treasure_dt': step_treasure_dt}
OUTPUTS = {'refl': ['refl.json'], 'locres': ['locres_fr.json', 'locres_en.json'], 'maps': ['maps.json'],
           'landcapture': ['landcapture.json'], 'items': ['items.json'], 'treasure_dt': ['treasure_dt.json'],
           'gimmicks': ['gimmicks.json'], 'areas': ['areas.json'], 'entrances': ['entrances.json']}
ORDER = ['refl', 'gimmicks', 'areas', 'entrances', 'locres', 'maps', 'landcapture', 'items', 'treasure_dt']


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--force', action='store_true', help='redo steps whose output already exists')
    ap.add_argument('--only', help='comma-separated list of steps (implies --force for them)')
    a = ap.parse_args()
    config.require_game()
    os.makedirs(config.WORK, exist_ok=True)
    os.chdir(config.WORK)
    only = set(a.only.split(',')) if a.only else None
    if only and only - set(ORDER):
        raise SystemExit(f'unknown step(s): {sorted(only - set(ORDER))}; known: {ORDER}')
    todo = [s for s in ORDER if (s in only if only else (a.force or not all(os.path.exists(o) for o in OUTPUTS[s])))]
    print(f'game: {config.GAME_DIR}\nwork: {config.WORK}')
    for s in ORDER:
        if s not in todo:
            print(f'[skip] {s} (already done; --force to redo)')
    if not todo:
        return
    t0 = time.time()
    times = {}

    if 'refl' in todo:
        print('[run ] refl: reading type layouts from the game executable (a few minutes)...', flush=True)
        t = time.time()
        subprocess.run([sys.executable, os.path.join(HERE, 'refl.py')], cwd=config.WORK, env=ENV, check=True)
        times['refl'] = time.time() - t
    if not os.path.exists('refl.json'):
        raise SystemExit('refl.json missing: run without --only first')

    # the three level scans are slow and independent: run them in the background meanwhile
    os.makedirs('logs', exist_ok=True)
    procs = {}
    for s in ('gimmicks', 'areas', 'entrances'):
        if s in todo:
            log = open(os.path.join('logs', s + '.log'), 'w', encoding='utf-8')
            print(f'[run ] {s}: scanning level packages in the background (log: logs/{s}.log)', flush=True)
            procs[s] = (subprocess.Popen([sys.executable, os.path.join(HERE, SCRIPTS[s])], cwd=config.WORK, env=ENV,
                                         stdout=log, stderr=subprocess.STDOUT), log, time.time())

    failed = []
    for s in ('locres', 'maps', 'landcapture', 'items', 'treasure_dt'):
        if s not in todo:
            continue
        print(f'[run ] {s}', flush=True)
        t = time.time()
        try:
            INPROC[s]()
        except Exception as ex:
            print(f'[FAIL] {s}: {ex}')
            failed.append(s)
        times[s] = time.time() - t

    for s, (p, log, t) in procs.items():
        rc = p.wait()
        log.close()
        times[s] = time.time() - t
        last = open(os.path.join('logs', s + '.log'), encoding='utf-8', errors='replace').read().strip().splitlines()
        print(f'[{"done" if rc == 0 else "FAIL"}] {s}: {last[-1] if last else ""}'[:300])
        if rc:
            failed.append(s)

    print('timings: ' + ', '.join(f'{k} {v:.0f}s' for k, v in times.items()) + f' | total {time.time() - t0:.0f}s')
    if failed:
        raise SystemExit(f'failed steps: {failed}')
    print('game data ready in', config.WORK)


if __name__ == '__main__':
    main()

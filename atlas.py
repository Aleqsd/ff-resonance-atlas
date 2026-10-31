"""Build atlas.html (missing tablet fragments and chests) from your most recent save.
Saves are copied to the work folder before being read; the originals are never modified.
Usage:  python atlas.py        (run extract_gamedata.py once before)
Output: <work>/atlas.html      (open it in any browser)
"""
import os, sys, glob, json, shutil, datetime, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config, gvas
from savekey import save_key

NEEDED = ['refl.json', 'locres_fr.json', 'maps.json', 'landcapture.json', 'items.json', 'treasure_dt.json',
          'gimmicks.json', 'areas.json']
HEAD = ('<!doctype html>\n<html lang="fr">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n')


def aes_ecb_decrypt(key, data):
    data = data[:len(data) - len(data) % 16]
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        d = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
        return d.update(data) + d.finalize()
    except ImportError:
        from Crypto.Cipher import AES  # pycryptodome
        return AES.new(key, AES.MODE_ECB).decrypt(data)


def fmt(ticks):
    return (datetime.datetime(1, 1, 1) + datetime.timedelta(microseconds=int(ticks) // 10)).strftime('%d/%m %H:%M')


def read_saves(key):
    if not config.SAVE_DIR:
        raise SystemExit('Save folder not found. Set FFRS_SAVE_DIR to the folder that contains GameSaveData*.sav.')
    files = sorted(glob.glob(os.path.join(config.SAVE_DIR, '**', 'GameSaveData*.sav'), recursive=True))
    if not files:
        raise SystemExit(f'No GameSaveData*.sav under {config.SAVE_DIR}')
    slots = []
    for s in files:
        copy = os.path.join(config.WORK, '_save_copy.sav')
        shutil.copyfile(s, copy)  # work on a copy only
        raw = open(copy, 'rb').read()
        os.remove(copy)
        plain = aes_ecb_decrypt(key, raw[32:])
        if plain[:4] != b'GVAS':
            print(f'  {os.path.basename(s)}: not a readable save (wrong key or format), skipped')
            continue
        tmp = os.path.join(config.WORK, '_save_copy.gvas')
        open(tmp, 'wb').write(plain)
        try:
            d = gvas.parse(tmp)
        finally:
            os.remove(tmp)
        slots.append((d['props']['Player']['SavedDateTime'], os.path.basename(s), d))
    if not slots:
        raise SystemExit('No save could be decrypted.')
    slots.sort(key=lambda x: x[0], reverse=True)
    return slots


def missing_list(page):
    """Image-free list of what is left (work/missing.json), for scripts and AI agents. Names are French."""
    out = {'save': page.get('save_label'), 'playtime_h': page.get('playtime_h'), 'summary': page.get('summary'),
           'islands': []}
    for group in page.get('groups', []):
        for isl in group.get('islands', []):
            places = []
            for pl in isl.get('places', []):
                items = [{'kind': it.get('k'), 'what': it.get('what'), 'marker': it.get('n'), 'plan': plan.get('label'),
                          'note': it.get('note') or ''}
                         for plan in pl.get('plans', []) for it in plan.get('items', [])]
                items += [{'kind': it.get('k'), 'what': it.get('what'), 'marker': it.get('n'), 'plan': None,
                           'note': it.get('note') or ''} for it in pl.get('loose', [])]
                places.append({'pin': pl.get('n'), 'place': pl.get('name'), 'how_to_get_there': pl.get('crumb') or '',
                               'tip': pl.get('tip') or '', 'items': items})
            out['islands'].append({'island': isl.get('name'), 'probably_lost': group.get('key') == 'past',
                                   'places': places})
    return out


def main():
    missing = [f for f in NEEDED if not os.path.exists(os.path.join(config.WORK, f))]
    if missing:
        raise SystemExit(f'Game data missing in {config.WORK}: {missing}. Run: python extract_gamedata.py')
    os.chdir(config.WORK)
    os.makedirs('out', exist_ok=True)
    os.makedirs(os.path.join('tex', 'cache'), exist_ok=True)

    slots = read_saves(save_key())
    t, name, d = slots[0]
    json.dump(d, open('save_latest.json', 'w', encoding='utf-8'), ensure_ascii=False, default=str)
    num = lambda n: int(''.join(c for c in n if c.isdigit()) or 0) + 1
    others = ', '.join(f'emplacement {num(n)} : {fmt(tt)}' for tt, n, _ in slots[1:])
    note = (f'Sauvegarde lue : emplacement {num(name)} ({name}), la plus récente, enregistrée le {fmt(t)}.'
            + (f' Autres : {others}.' if others else ''))
    json.dump({'file': name, 'note': note}, open('out/save_info.json', 'w', encoding='utf-8'), ensure_ascii=False)
    print(note, flush=True)

    env = dict(os.environ, PYTHONIOENCODING='utf-8', FFRS_WORK=config.WORK)
    subprocess.run([sys.executable, os.path.join(HERE, 'build_data.py'), 'save_latest.json'], check=True, env=env)
    print('building the page (map plans are decoded the first time, this can take a minute)...', flush=True)
    subprocess.run([sys.executable, os.path.join(HERE, 'build_page.py')], check=True, env=env, stdout=subprocess.DEVNULL)

    page = open(os.path.join('out', 'page3.json'), encoding='utf-8').read()
    body = open(os.path.join(HERE, 'template.html'), encoding='utf-8').read().replace('__DATA__', page)
    out = os.path.join(config.WORK, 'atlas.html')
    open(out, 'w', encoding='utf-8').write(HEAD + body)
    data = json.loads(page)
    missing = os.path.join(config.WORK, 'missing.json')
    json.dump(missing_list(data), open(missing, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    s = data.get('summary', {})
    if s:
        print(f"fragments {s['shards'][0]}/{s['shards'][1]}, coffres {s['chests'][0]}/{s['chests'][1]}")
    print('atlas written:', out)
    print('missing list (JSON):', missing)


if __name__ == '__main__':
    main()

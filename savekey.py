"""Find the AES-256 key used to encrypt GameSaveData*.sav.

The key is not stored in this repository: it is read at run time from the game's own config file
DefaultSQEXSaveGameSystem.ini (setting SaveDataEncryptionKey), which ships inside FFRS-Windows.pak.
Lookup order:
  1. env FFRS_SAVE_KEY
  2. the .ini read through the .pak index (stored or Oodle-compressed entries)
  3. the .ini inside an IoStore container (.utoc/.ucas), if a future patch moves it there
  4. a plain byte scan of the .pak files (slow, last resort)
Usage: python savekey.py   (prints only whether a key was found and its length)
"""
import os, re, glob, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

INI_NAME = 'DefaultSQEXSaveGameSystem.ini'
PATTERN = re.compile(rb'SaveDataEncryptionKey[ \t]*=[ \t]*"?([^\s"]+)')


def _parse(data):
    m = PATTERN.search(data or b'')
    return m.group(1) if m else None


def _from_pak_index(pak_path):
    from pakfile import Pak
    pak = Pak(pak_path)
    for name in pak.files:
        if name.endswith('/' + INI_NAME):
            key = _parse(pak.read(name))
            if key:
                return key
    return None


def _from_iostore(utoc_path):
    from utoc import Toc
    from extract import extract
    toc = Toc(utoc_path)
    for name in toc.files:
        if name.endswith('/' + INI_NAME):
            tmp = os.path.join(tempfile.gettempdir(), f'ffrs_ini_{os.getpid()}.bin')
            try:
                extract(name, tmp, os.path.splitext(os.path.basename(utoc_path))[0])
                key = _parse(open(tmp, 'rb').read())
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
            if key:
                return key
    return None


def _scan(path, chunk=64 << 20):
    needle = b'SaveDataEncryptionKey'
    with open(path, 'rb') as f:
        tail = b''
        while True:
            block = f.read(chunk)
            if not block:
                return None
            buf = tail + block
            i = buf.find(needle)
            while i >= 0:
                key = _parse(buf[i:i + 200])
                if key:
                    return key
                i = buf.find(needle, i + 1)
            tail = buf[-256:]


def save_key():
    env = os.environ.get('FFRS_SAVE_KEY')
    if env:
        return env.encode('ascii')
    config.require_game()
    paks = sorted(glob.glob(os.path.join(config.PAKS, '*.pak')))
    tocs = sorted(glob.glob(os.path.join(config.PAKS, '*.utoc')))
    for finder, files in ((_from_pak_index, paks), (_from_iostore, tocs), (_scan, paks)):
        for path in files:
            try:
                key = finder(path)
            except Exception as ex:  # unknown container layout: try the next method
                print(f'  ({finder.__name__} failed on {os.path.basename(path)}: {ex})', file=sys.stderr)
                continue
            if key:
                if len(key) not in (16, 24, 32):
                    print(f'  (ignoring key of unexpected length {len(key)})', file=sys.stderr)
                    continue
                return key
    raise SystemExit('Save key not found in the game files. Set FFRS_SAVE_KEY (value of SaveDataEncryptionKey '
                     'in FFRS/Config/' + INI_NAME + ').')


if __name__ == '__main__':
    k = save_key()
    print(f'save key found ({len(k)} bytes)')

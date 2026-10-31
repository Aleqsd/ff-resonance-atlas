"""Extract files from IoStore (read-only) using ooz_cli for Oodle blocks."""
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from utoc import Toc
from config import PAKS as PK, OOZ
_tocs = {}
def toc(name):
    if name not in _tocs:
        _tocs[name] = Toc(f"{PK}/{name}.utoc")
    return _tocs[name]
def extract(path, out, name='FFRS-Windows'):
    t = toc(name)
    idx = t.files[path]
    off, ln = t.offlen[idx]
    b0, b1 = off // t.cbs, (off + ln - 1) // t.cbs
    lines = []
    for bi in range(b0, b1 + 1):
        o, c, u, m = t.blocks[bi]
        c = (c + 15) & ~15 if False else c
        lines.append(f"{o} {c} {u} {m}")
    tmp = out + '.blk'
    subprocess.run([OOZ, f"{PK}/{name}.ucas", tmp], input='\n'.join(lines), text=True, check=True)
    data = open(tmp, 'rb').read(); os.remove(tmp)
    s = off - b0 * t.cbs
    open(out, 'wb').write(data[s:s + ln])
    return ln
if __name__ == '__main__':
    name = sys.argv[3] if len(sys.argv) > 3 else 'FFRS-Windows'
    t = toc(name)
    matches = [k for k in t.files if sys.argv[1] in k]
    os.makedirs(sys.argv[2], exist_ok=True)
    for k in matches:
        o = os.path.join(sys.argv[2], os.path.basename(k))
        print(k, extract(k, o, name))

"""Scan level packages for treasure boxes / field items (read-only) -> gimmicks.json"""
import sys, os, json, traceback
sys.path.insert(0, os.path.dirname(__file__))
from zen import *
from extract import toc

NATIVE_FOR = [('TreasureBox', 'ACPP_MapGimmick_TreasureBox'), ('FieldItem', 'ACPP_MapGimmick_FieldItem')]
KEEP = ('m_UniqueId', 'm_Id', 'm_ItemId', 'm_ItemNum', 'm_Money', 'm_IsTrap', 'm_IslandType', 'm_OnFlagList', 'm_IsOpen',
        'm_FlagCondition', 'VisibleCondition', 'm_BattleGroupId', 'm_TreasureBoxData', 'bHidden', 'm_GimmickCondition')
n_cache = {}


def class_name_from_script(path):
    n = path.split('.')[-1]
    for pre in ('U', 'A', 'F', ''):
        if pre + n in SCHEMA:
            return pre + n
    return None


def decode_with_offset(pkg, e, native, N, sch=None):
    s, end = pkg.export_data(e)
    if sch is None:
        sch = [None] * N + schema_for(native)
    r = Reader(pkg.b, s, end, pkg)
    # custom read honoring None slots
    frags = []
    while True:
        v = r.u('<H')
        frags.append((v & 0x7f, (v >> 7) & 1, v >> 9))
        if (v >> 8) & 1:
            break
    nz = sum(n for _, z, n in frags if z)
    mask = 0
    if nz:
        if nz <= 8: mask = r.u('<B')
        elif nz <= 16: mask = r.u('<H')
        else:
            for w in range((nz + 31) // 32): mask |= r.u('<I') << (32 * w)
    out, idx, zb = {}, 0, 0
    for skip, z, num in frags:
        idx += skip
        for _ in range(num):
            isz = False
            if z:
                isz = (mask >> zb) & 1; zb += 1
            if idx >= len(sch) or sch[idx] is None:
                if isz:
                    idx += 1; continue
                raise ValueError('unknown slot %d' % idx)
            p = sch[idx]
            out[p['name']] = 0 if isz else read_value(r, p)
            idx += 1
    return out, end - r.p


def comp_location(pkg, idx, depth=0):
    """FPackageIndex of a component -> world-ish location (sum of relative locations up the attach chain)"""
    if idx is None or idx <= 0 or depth > 6:
        return None
    e = pkg.exports[idx - 1]
    cls = pkg.class_of(e)
    if not cls or cls[0] != 'script':
        return None
    cn = class_name_from_script(cls[1])
    if not cn:
        return None
    s, end = pkg.export_data(e)
    try:
        props = read_unversioned(Reader(pkg.b, s, end, pkg), schema_for(cn))
    except Exception:
        return None
    loc = props.get('RelativeLocation') or {'X': 0, 'Y': 0, 'Z': 0}
    if loc == 0: loc = {'X': 0, 'Y': 0, 'Z': 0}
    par = props.get('AttachParent')
    if par and par != 0:
        pl = comp_location(pkg, par[1], depth + 1)
        if pl:
            return {k: loc[k] + pl[k] for k in 'XYZ'}
    return dict(loc)


def scan_level(path):
    b = read_file(path)
    pkg = Package(b, path)
    res = []
    for ei, e in enumerate(pkg.exports):
        cls = pkg.class_of(e)
        if not cls:
            continue
        cpath = cls[1] if cls[0] in ('pkg', 'script') else ''
        cpath = str(cpath)
        native = None
        for key, nat in NATIVE_FOR:
            if key in cpath:
                native = nat
        if not native or e['name'].startswith('Default__'):
            continue
        best = None
        bps = None
        if cls[0] == 'pkg':
            try:
                bps = bp_schema(cpath)
            except Exception as ex:
                bps = None
        cands = [0] if (cls[0] == 'script' or bps) else list(range(0, 40))
        for N in cands:
            try:
                props, left = decode_with_offset(pkg, e, native, N, bps)
            except Exception as ex:
                last_err = str(ex)
                continue
            rc = props.get('RootComponent') or props.get('m_RootComponent')
            ok = 0 <= left <= 400
            if rc and isinstance(rc, tuple) and rc[1] > 0:
                ok = ok and pkg.exports[rc[1] - 1]['outer'] == ei
            if ok and ('m_UniqueId' in props or 'RootComponent' in props):
                best = (N, props, left); break
        if not best:
            res.append({'level': path, 'actor': e['name'], 'class': cpath, 'error': 'undecoded', 'bp': bool(bps), 'err': locals().get('last_err')})
            continue
        N, props, left = best
        n_cache[cpath] = N
        rc = props.get('RootComponent')
        loc = comp_location(pkg, rc[1]) if isinstance(rc, tuple) else None
        res.append({'level': path, 'actor': e['name'], 'class': cpath, 'native': native, 'N': N,
                    'loc': loc, **{k: v for k, v in props.items() if k in KEEP}})
    return res


if __name__ == '__main__':
    t = toc('FFRS-Windows')
    levels = sorted(k for k in t.files if '/Content/Map/' in k and k.endswith('.umap') and '/Map/Btl/' not in k)
    if len(sys.argv) > 1:
        levels = [l for l in levels if sys.argv[1] in l]
    out, errs = [], 0
    for i, l in enumerate(levels):
        try:
            out.extend(scan_level(l))
        except Exception as ex:
            errs += 1
            print('ERR', l, ex)
    json.dump(out, open('gimmicks.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0, default=str)
    print('levels', len(levels), 'gimmicks', len(out), 'undecoded', sum(1 for g in out if 'error' in g), 'errs', errs)
    print('N cache', n_cache)

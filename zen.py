"""Read-only Zen (IoStore) package parser + unversioned property decoder (UE5.6)."""
import struct, json, os, sys, subprocess, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from extract import toc, PK, OOZ

from config import WORK
REFL = json.load(open(os.path.join(WORK, 'refl.json')))
SCHEMA = {}
SCHEMA.update(REFL['structs'])
SCHEMA.update(REFL['classes'])


def read_chunk(name, idx):
    t = toc(name)
    off, ln = t.offlen[idx]
    b0, b1 = off // t.cbs, (off + ln - 1) // t.cbs
    lines = [' '.join(map(str, t.blocks[bi])) for bi in range(b0, b1 + 1)]
    tmp = os.path.join(tempfile.gettempdir(), f'ffrs_chunk_{os.getpid()}.bin')
    subprocess.run([OOZ, f"{PK}/{name}.ucas", tmp], input='\n'.join(lines), text=True, check=True)
    data = open(tmp, 'rb').read(); os.remove(tmp)
    s = off - b0 * t.cbs
    return data[s:s + ln]


def read_file(path, name='FFRS-Windows'):
    t = toc(name)
    return read_chunk(name, t.files[path])


def name_batch(b, p):
    n, = struct.unpack_from('<I', b, p); p += 4
    if n == 0:
        return [], p
    nbytes, = struct.unpack_from('<I', b, p); p += 4
    p += 8 + 8 * n  # hash version + hashes
    lens = [struct.unpack_from('>H', b, p + 2 * i)[0] for i in range(n)]; p += 2 * n
    names = []
    for L in lens:
        if L & 0x8000:
            L &= 0x7fff
            names.append(b[p:p + 2 * L].decode('utf-16-le', 'replace')); p += 2 * L
        else:
            names.append(b[p:p + L].decode('latin-1')); p += L
    return names, p


# ---- global script objects ----
_script = None
def script_objects():
    global _script
    if _script is None:
        b = read_chunk('global', 0)
        names, p = name_batch(b, 0)
        n, = struct.unpack_from('<i', b, p); p += 4
        ent = {}
        for i in range(n):
            ni, nn, gi, oi, ci = struct.unpack_from('<IIQQQ', b, p + 32 * i)
            nm = names[ni & 0x3FFFFFFF] + (f'_{nn - 1}' if nn else '')
            ent[gi] = (nm, oi)
        full = {}
        for gi, (nm, oi) in ent.items():
            parts = [nm]; o = oi; k = 0
            while o in ent and k < 10:
                parts.append(ent[o][0]); o = ent[o][1]; k += 1
            full[gi] = '.'.join(reversed(parts))
        _script = full
    return _script


NULL = 0xFFFFFFFFFFFFFFFF


class Package:
    def __init__(self, b, path=''):
        self.b, self.path = b, path
        (hv, hs, pn_i, pn_n, flags, chs, iphoff, imoff, exoff, ebeoff, dbhoff, dbeoff, ipnoff) = struct.unpack_from('<13I', b, 0)
        self.header_size = hs
        self.names, p = name_batch(b, 0x3c if not hv else None)
        self.imports = [struct.unpack_from('<Q', b, imoff + 8 * i)[0] for i in range((exoff - imoff) // 8)]
        self.exports = []
        for i in range((ebeoff - exoff) // 72):
            o = exoff + 72 * i
            so, ss, ni, nn, outer, cls, sup, tmpl, hsh, of = struct.unpack_from('<QQIIQQQQQI', b, o)
            self.exports.append({'off': so, 'size': ss, 'name': self.fname(ni, nn), 'outer': outer, 'class': cls, 'template': tmpl, 'flags': of})
        # imported package names
        self.imp_pkgs = []
        try:
            self.imp_pkgs, _ = name_batch(b, ipnoff)
        except Exception:
            pass

    def fname(self, i, n=0):
        i &= 0x3FFFFFFF
        s = self.names[i] if i < len(self.names) else f'?name{i}'
        return s + (f'_{n - 1}' if n else '')

    def obj_index_str(self, v):
        if v == NULL:
            return None
        typ = v >> 62
        if typ == 0:
            return ('export', v & ((1 << 62) - 1))
        if typ == 1:
            return ('script', script_objects().get(v, hex(v)))
        if typ == 2:
            pk = (v >> 32) & 0x3FFFFFFF
            return ('pkg', self.imp_pkgs[pk] if pk < len(self.imp_pkgs) else pk, v & 0xFFFFFFFF)
        return ('?', hex(v))

    def class_of(self, e):
        return self.obj_index_str(e['class'])

    def pkg_index(self, i):
        """FPackageIndex int32 -> description"""
        if i == 0:
            return None
        if i > 0:
            return ('export', i - 1, self.exports[i - 1]['name'])
        imp = self.imports[-i - 1]
        return ('import', self.obj_index_str(imp))

    def export_data(self, e):
        o = self.header_size + e['off']
        return o, o + e['size']


# ---------------- unversioned property decoding ----------------
NATIVE = {'Vector': ('<3d', ['X', 'Y', 'Z']), 'Rotator': ('<3d', ['Pitch', 'Yaw', 'Roll']), 'Quat': ('<4d', ['X', 'Y', 'Z', 'W']),
          'Vector2D': ('<2d', ['X', 'Y']), 'Vector4': ('<4d', ['X', 'Y', 'Z', 'W']), 'IntPoint': ('<2i', ['X', 'Y']),
          'IntVector': ('<3i', ['X', 'Y', 'Z']), 'LinearColor': ('<4f', ['R', 'G', 'B', 'A']), 'Color': ('<4B', ['B', 'G', 'R', 'A']),
          'Guid': ('<4I', ['A', 'B', 'C', 'D']), 'DateTime': ('<q', ['Ticks']), 'Timespan': ('<q', ['Ticks']),
          'Box': ('<6dB', ['MinX', 'MinY', 'MinZ', 'MaxX', 'MaxY', 'MaxZ', 'IsValid']), 'Vector3f': ('<3f', ['X', 'Y', 'Z']),
          'FrameNumber': ('<i', ['Value']), 'Box2D': ('<4dB', ['MinX', 'MinY', 'MaxX', 'MaxY', 'IsValid'])}


def logical_props(props):
    out = []
    for i, p in enumerate(props):
        if p['name'] == 'UnderlyingType':
            continue
        if p['type'] == 'Map' and not p.get('key'):
            if len(out) >= 2:
                k = out.pop(); v = out.pop()
                p = dict(p, key=k, value=v)
        if p['type'] == 'Enum' and not p.get('underlying') and i > 0 and props[i - 1]['name'] == 'UnderlyingType':
            p = dict(p, underlying=props[i - 1])
        out.append(p)
    return out


_schema_cache = {}
def schema_for(name):
    """Flattened (super first) logical property list for struct/class name"""
    if name in _schema_cache:
        return _schema_cache[name]
    d = SCHEMA.get(name)
    if d is None:
        _schema_cache[name] = None
        return None
    chain = []
    cur, k = name, 0
    while cur and cur in SCHEMA and k < 40:
        chain.append(cur); cur = SCHEMA[cur].get('super'); k += 1
    props = []
    for c in chain:  # derived first, then supers (PropertyLink order)
        for p in logical_props(SCHEMA[c]['props']):
            for j in range(max(1, p.get('dim', 1))):
                props.append(p if j == 0 else dict(p, name=f"{p['name']}[{j}]"))
    _schema_cache[name] = props
    return props


class Reader:
    def __init__(self, b, p, end, pkg):
        self.b, self.p, self.end, self.pkg = b, p, end, pkg

    def u(self, fmt):
        v = struct.unpack_from(fmt, self.b, self.p)
        self.p += struct.calcsize(fmt)
        return v[0] if len(v) == 1 else v

    def fstr(self):
        n = self.u('<i')
        if n == 0:
            return ''
        if n > 0:
            s = self.b[self.p:self.p + n - 1].decode('latin-1'); self.p += n
        else:
            n = -n; s = self.b[self.p:self.p + 2 * n - 2].decode('utf-16-le'); self.p += 2 * n
        return s

    def fname(self):
        i, n = self.u('<II')
        return self.pkg.fname(i, n)


def read_text(r):
    flags = r.u('<I')
    ht = r.u('<b')
    if ht == -1:
        has = r.u('<I')
        return {'inv': r.fstr()} if has else ''
    if ht == 0:
        ns = r.fstr(); key = r.fstr(); src = r.fstr()
        return {'ns': ns, 'key': key, 'src': src}
    if ht == 11:
        tid = r.fname(); key = r.fstr()
        return {'table': tid, 'key': key}
    raise ValueError(f'text history {ht}')


def read_value(r, p):
    t = p['type']
    if t == 'Int': return r.u('<i')
    if t == 'Int8': return r.u('<b')
    if t == 'Int16': return r.u('<h')
    if t == 'Int64': return r.u('<q')
    if t == 'UInt16': return r.u('<H')
    if t == 'UInt32': return r.u('<I')
    if t == 'UInt64': return r.u('<Q')
    if t == 'Float': return r.u('<f')
    if t in ('Double', 'LWCReal'): return r.u('<d')
    if t == 'Bool': return bool(r.u('<B'))
    if t == 'Byte': return r.u('<B')
    if t == 'Enum':
        if p.get('_elem'):
            return r.fname()
        u = (p.get('underlying') or {}).get('type', 'Byte')
        return r.u({'Byte': '<B', 'Int8': '<b', 'Int16': '<h', 'UInt16': '<H', 'Int': '<i', 'UInt32': '<I', 'Int64': '<q', 'UInt64': '<Q'}.get(u, '<B'))
    if t == 'Name': return r.fname()
    if t in ('Str', 'Utf8Str', 'AnsiStr'): return r.fstr()
    if t == 'Text': return read_text(r)
    if t in ('Object', 'Class', 'WeakObject', 'LazyObject', 'Interface'):
        return ('obj', r.u('<i'))
    if t in ('SoftObject', 'SoftClass'):
        a = r.fname(); bb = r.fname(); sub = r.fstr()
        return ('soft', a, bb, sub)
    if t == 'Struct':
        return read_struct(r, p.get('ref'))
    if t in ('Array', 'Set'):
        if t == 'Set':
            r.u('<i')
        n = r.u('<i')
        inner = dict(p['inner'], _elem=True)
        if inner['type'] == 'Byte' and n > 64:
            v = r.b[r.p:r.p + n]; r.p += n; return v.hex()
        return [read_value(r, inner) for _ in range(n)]
    if t == 'Map':
        r.u('<i'); n = r.u('<i')
        k, v = dict(p['key'], _elem=True), dict(p['value'], _elem=True)
        return [[read_value(r, k), read_value(r, v)] for _ in range(n)]
    if t in ('InlineMulticastDelegate', 'SparseMulticastDelegate'):
        n = r.u('<i')
        return [(r.u('<i'), r.fname()) for _ in range(n)]
    if t == 'Delegate':
        return (r.u('<i'), r.fname())
    if t == 'FieldPath':
        n = r.u('<i'); path = [r.fname() for _ in range(n)]; owner = r.u('<i'); return path
    raise ValueError('unsupported type ' + t)


def read_struct(r, sname):
    if sname in NATIVE:
        fmt, keys = NATIVE[sname]
        return dict(zip(keys, r.u(fmt) if len(keys) > 1 else (r.u(fmt),)))
    if sname in ('SoftObjectPath', 'SoftClassPath'):
        a = r.fname(); bb = r.fname(); sub = r.fstr(); return ('soft', a, bb, sub)
    if sname == 'GameplayTagContainer':
        n = r.u('<i'); return [r.fname() for _ in range(n)]
    sch = schema_for(sname)
    if sch is None:
        raise ValueError('no schema for struct ' + str(sname))
    return read_unversioned(r, sch)


def read_unversioned(r, sch, partial=False):
    frags = []
    while True:
        v = r.u('<H')
        skip, zeroes, last, num = v & 0x7f, (v >> 7) & 1, (v >> 8) & 1, v >> 9
        frags.append((skip, zeroes, num))
        if last:
            break
    nz = sum(num for s, z, num in frags if z)
    mask = 0
    if nz:
        if nz <= 8: mask = r.u('<B')
        elif nz <= 16: mask = r.u('<H')
        else:
            words = (nz + 31) // 32
            for w in range(words):
                mask |= r.u('<I') << (32 * w)
    out = {}
    idx, zb = 0, 0
    for skip, z, num in frags:
        idx += skip
        for k in range(num):
            is_zero = False
            if z:
                is_zero = (mask >> zb) & 1; zb += 1
            if idx >= len(sch):
                raise ValueError(f'prop index {idx} beyond schema {len(sch)}')
            p = sch[idx]
            if is_zero:
                out[p['name']] = 0
            else:
                try:
                    out[p['name']] = read_value(r, p)
                except Exception as e:
                    if partial:
                        out['_error'] = f"{p['name']}: {e}"
                        return out
                    raise ValueError(f"{p['name']}({p['type']}:{p.get('ref') or (p.get('inner') or {}).get('ref')}) @{r.p} > {e}")
            idx += 1
    return out


# ---------------- Blueprint class schemas ----------------
_bp_cache = {}
PROP_T = {'IntProperty': 'Int', 'Int8Property': 'Int8', 'Int16Property': 'Int16', 'Int64Property': 'Int64', 'UInt16Property': 'UInt16',
          'UInt32Property': 'UInt32', 'UInt64Property': 'UInt64', 'FloatProperty': 'Float', 'DoubleProperty': 'Double',
          'BoolProperty': 'Bool', 'ByteProperty': 'Byte', 'EnumProperty': 'Enum', 'NameProperty': 'Name', 'StrProperty': 'Str',
          'TextProperty': 'Text', 'ObjectProperty': 'Object', 'WeakObjectProperty': 'WeakObject', 'LazyObjectProperty': 'LazyObject',
          'SoftObjectProperty': 'SoftObject', 'ClassProperty': 'Class', 'SoftClassProperty': 'SoftClass', 'InterfaceProperty': 'Interface',
          'StructProperty': 'Struct', 'ArrayProperty': 'Array', 'SetProperty': 'Set', 'MapProperty': 'Map',
          'DelegateProperty': 'Delegate', 'MulticastInlineDelegateProperty': 'InlineMulticastDelegate',
          'MulticastSparseDelegateProperty': 'SparseMulticastDelegate', 'FieldPathProperty': 'FieldPath', 'OptionalProperty': 'Optional'}


def _read_field(r, pkg):
    tname = r.fname()
    if tname == 'None':
        return None
    name = r.fname()
    r.u('<I')  # object flags
    dim, esize = r.u('<ii')
    r.u('<Q'); r.u('<H'); r.fname(); r.u('<B')
    t = PROP_T.get(tname, tname)
    p = {'name': name, 'type': t, 'dim': dim}
    if t in ('Object', 'WeakObject', 'LazyObject', 'SoftObject', 'Interface'):
        r.u('<i')
    elif t in ('Class', 'SoftClass'):
        r.u('<i'); r.u('<i')
    elif t == 'Struct':
        idx = r.u('<i')
        d = pkg.pkg_index(idx)
        ref = None
        if d and d[0] == 'import' and d[1] and d[1][0] == 'script':
            ref = d[1][1].split('.')[-1]
        elif d:
            ref = ('bpstruct', str(d))
        p['ref'] = ref
    elif t == 'Bool':
        r.u('<6B')
    elif t == 'Byte':
        r.u('<i')
    elif t == 'Enum':
        r.u('<i'); p['underlying'] = _read_field(r, pkg)
    elif t in ('Array', 'Set', 'Optional'):
        p['inner'] = _read_field(r, pkg)
    elif t == 'Map':
        p['key'] = _read_field(r, pkg); p['value'] = _read_field(r, pkg)
    elif t in ('Delegate', 'InlineMulticastDelegate', 'SparseMulticastDelegate'):
        r.u('<i')
    elif t == 'FieldPath':
        r.fname()
    return p


def bp_schema(pkg_path):
    """Full unversioned schema (derived first) for a Blueprint class package."""
    if pkg_path in _bp_cache:
        return _bp_cache[pkg_path]
    _bp_cache[pkg_path] = None
    b = read_file('../../../FFRS/Content/' + pkg_path[len('/Game/'):] + '.uasset')
    pkg = Package(b, pkg_path)
    e = next(x for x in pkg.exports if pkg.class_of(x) == ('script', '/Script/Engine.BlueprintGeneratedClass'))
    s, end = pkg.export_data(e)
    r = Reader(b, s, end, pkg)
    read_unversioned(r, schema_for('UBlueprintGeneratedClass'))
    r.u('<I')
    sup = r.u('<i')
    nch = r.u('<i'); r.p += 4 * nch
    nprop = r.u('<i')
    own = [_read_field(r, pkg) for _ in range(nprop)]
    own = [x for x in own if x]
    flat = []
    for p in own:
        for j in range(max(1, p.get('dim', 1))):
            flat.append(p if j == 0 else dict(p, name=f"{p['name']}[{j}]"))
    d = pkg.pkg_index(sup)
    parent = []
    if d and d[0] == 'import':
        o = d[1]
        if o[0] == 'script':
            cn = o[1].split('.')[-1]
            for pre in ('A', 'U'):
                if pre + cn in SCHEMA:
                    parent = schema_for(pre + cn); break
        elif o[0] == 'pkg':
            parent = bp_schema(o[1]) or []
    res = flat + parent
    _bp_cache[pkg_path] = res
    return res

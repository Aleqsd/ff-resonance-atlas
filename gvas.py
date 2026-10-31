"""Minimal read-only GVAS (UE 5.5+/5.6 complete-type-name tags) parser -> JSON."""
import struct, sys, json

NATIVE_STRUCTS = {
    'Vector': '<3d', 'Rotator': '<3d', 'Quat': '<4d', 'Vector2D': '<2d', 'IntPoint': '<2i',
    'Guid': None, 'DateTime': '<q', 'Timespan': '<q', 'LinearColor': '<4f', 'Color': '<4B',
}


class R:
    def __init__(self, b, p=0):
        self.b, self.p = b, p

    def u(self, fmt):
        v = struct.unpack_from(fmt, self.b, self.p)
        self.p += struct.calcsize(fmt)
        return v if len(v) > 1 else v[0]

    def fstr(self):
        n = self.u('<i')
        if n == 0:
            return ''
        if n > 0:
            s = self.b[self.p:self.p + n - 1].decode('latin-1')
            self.p += n
        else:
            n = -n
            s = self.b[self.p:self.p + 2 * n - 2].decode('utf-16-le')
            self.p += 2 * n
        return s

    def guid(self):
        g = self.b[self.p:self.p + 16]
        self.p += 16
        return g.hex()


def read_typename(r):
    name = r.fstr()
    n = r.u('<i')
    return {'n': name, 'p': [read_typename(r) for _ in range(n)]}


def tn_str(t):
    return t['n'] + ('(' + ','.join(tn_str(x) for x in t['p']) + ')' if t['p'] else '')


def read_props(r, end=None):
    out = {}
    while True:
        name = r.fstr()
        if name == 'None' or name == '':
            break
        t = read_typename(r)
        size = r.u('<i')
        flags = r.u('<B')
        idx = 0
        if flags & 1:
            idx = r.u('<i')
        if flags & 2:
            r.guid()
        if flags & 4:
            ext = r.u('<B')
            if ext & 2:
                r.u('<B')  # overridable op
                r.u('<B')
        start = r.p
        if t['n'] == 'BoolProperty':
            v = bool(flags & 0x10)
        else:
            try:
                v = read_value(r, t, size, flags)
            except Exception as e:
                v = {'_err': str(e), '_raw': r.b[start:start + min(size, 64)].hex()}
            r.p = start + size
        key = name if idx == 0 else f'{name}[{idx}]'
        out[key] = v
    return out


def read_struct(r, sname, size, binary):
    if sname in NATIVE_STRUCTS:
        if sname == 'Guid':
            return r.guid()
        fmt = NATIVE_STRUCTS[sname]
        if struct.calcsize(fmt) == size or size < 0:
            return list(r.u(fmt)) if len(fmt) > 2 else r.u(fmt)
    return read_props(r)


def read_value(r, t, size, flags=0, in_container=False):
    n = t['n']
    if n == 'IntProperty':
        return r.u('<i')
    if n == 'UInt32Property':
        return r.u('<I')
    if n == 'Int64Property':
        return r.u('<q')
    if n == 'UInt64Property':
        return r.u('<Q')
    if n == 'Int16Property':
        return r.u('<h')
    if n == 'UInt16Property':
        return r.u('<H')
    if n == 'Int8Property':
        return r.u('<b')
    if n == 'FloatProperty':
        return r.u('<f')
    if n == 'DoubleProperty':
        return r.u('<d')
    if n == 'BoolProperty':
        return bool(r.u('<B'))
    if n in ('StrProperty', 'NameProperty', 'ObjectProperty', 'SoftObjectProperty', 'ClassProperty', 'SoftClassProperty'):
        return r.fstr()
    if n == 'EnumProperty':
        return r.fstr()
    if n == 'ByteProperty':
        if in_container:
            return r.fstr() if t['p'] and t['p'][0]['n'] != 'None' else r.u('<B')
        return r.u('<B') if size == 1 else r.fstr()
    if n == 'StructProperty':
        sname = t['p'][0]['n'] if t['p'] else '?'
        return read_struct(r, sname, size if not in_container else -1, flags & 8)
    if n == 'ArrayProperty':
        inner = t['p'][0]
        cnt = r.u('<i')
        if inner['n'] == 'ByteProperty' and not (inner['p'] and inner['p'][0]['n'] != 'None'):
            data = r.b[r.p:r.p + cnt]
            r.p += cnt
            return data.hex()
        return [read_value(r, inner, -1, 0, True) for _ in range(cnt)]
    if n in ('MapProperty', 'SetProperty'):
        if n == 'SetProperty':
            kt = t['p'][0]
            rem = r.u('<i')
            for _ in range(rem):
                read_value(r, kt, -1, 0, True)
            cnt = r.u('<i')
            return [read_value(r, kt, -1, 0, True) for _ in range(cnt)]
        kt, vt = t['p'][0], t['p'][1]
        rem = r.u('<i')
        for _ in range(rem):
            read_value(r, kt, -1, 0, True)
        cnt = r.u('<i')
        res = []
        for _ in range(cnt):
            k = read_value(r, kt, -1, 0, True)
            v = read_value(r, vt, -1, 0, True)
            res.append([k, v])
        return res
    raise ValueError('unknown type ' + tn_str(t))


def parse(path):
    b = open(path, 'rb').read()
    r = R(b)
    assert r.b[:4] == b'GVAS'
    r.p = 4
    sgv, ue4, ue5 = r.u('<iii')
    eng = r.u('<HHHI')
    branch = r.fstr()
    cvf = r.u('<i')
    ncv = r.u('<i')
    for _ in range(ncv):
        r.guid(); r.u('<i')
    cls = r.fstr()
    r.u("<B")  # UE5.6 extra flag byte after class name
    props = read_props(r)
    return {'class': cls, 'engine': eng, 'props': props, '_end': r.p, '_len': len(b)}


if __name__ == '__main__':
    d = parse(sys.argv[1])
    json.dump(d, open(sys.argv[2], 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(d['class'], d['engine'], 'end', d['_end'], 'len', d['_len'], 'top keys', list(d['props'].keys())[:50])

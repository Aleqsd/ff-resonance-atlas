"""Static UE reflection dumper (read-only) for the game exe -> refl.json
Builds {name: {kind, super, props:[{name,type,offset,dim,inner...}]}} for structs, classes, enums."""
import struct, json, re
from peutil import b, base, secs, va2off, off2va, q, cstr

CODE_LO, CODE_HI = base + 0x1000, base + 0x7731000
def is_code(v): return CODE_LO <= v < CODE_HI
def is_data(v):
    o = va2off(v)
    return o is not None and not is_code(v)

def wstr(va, maxl=256):
    o = va2off(va)
    if o is None or o & 1: return None
    e = o
    while e < o + 2 * maxl:
        if b[e] == 0 and b[e + 1] == 0: break
        e += 2
    s = b[o:e]
    if not s: return None
    try:
        t = s.decode('utf-16-le')
    except Exception:
        return None
    return t if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', t) else None

data_secs = [(rp, rs) for n, va, vs, rp, rs in secs if n in ('.data1', '.shared', '.didata', '.link', '.text', '.code', '.sxdata', '.debug', '.trace', '.xdata', '.udata')]
# 1) registration infos: qword pointing to UTF-16 identifier, preceded by code ptrs
func_name = {}
wcache = {}
for rp, rs in data_secs:
    for o in range(rp, rp + rs - 8, 8):
        v = q(o)
        if not (base < v < base + 0x20000000) or is_code(v): continue
        if v in wcache:
            nm = wcache[v]
        else:
            nm = wcache[v] = wstr(v)
        if not nm: continue
        for k in (1, 2):
            f = q(o - 8 * k)
            if is_code(f):
                func_name.setdefault(f, nm)
print('reg funcs', len(func_name))

GEN = {0: 'Byte', 1: 'Int8', 2: 'Int16', 3: 'Int', 4: 'Int64', 5: 'UInt16', 6: 'UInt32', 7: 'UInt64', 9: 'UInt32',
       10: 'Float', 11: 'Double', 12: 'Bool', 13: 'SoftClass', 14: 'WeakObject', 15: 'LazyObject', 16: 'SoftObject',
       17: 'Class', 18: 'Object', 19: 'Interface', 20: 'Name', 21: 'Str', 22: 'Array', 23: 'Map', 24: 'Set',
       25: 'Struct', 26: 'Delegate', 27: 'InlineMulticastDelegate', 28: 'SparseMulticastDelegate', 29: 'Text',
       30: 'Enum', 31: 'FieldPath', 32: 'LWCReal', 33: 'Optional', 34: 'VerseValue', 35: 'Utf8Str', 36: 'AnsiStr'}

def read_prop(pva):
    o = va2off(pva)
    name = cstr(q(o))
    gen = b[o + 0x18]
    t = GEN.get(gen & 0x3f, f'gen{gen:#x}')
    dim, off = struct.unpack_from('<HH', b, o + 0x30)
    p = {'name': name, 'type': t, 'dim': dim, 'off': off}
    if t in ('Struct', 'Object', 'Class', 'SoftObject', 'SoftClass', 'WeakObject', 'LazyObject', 'Interface', 'Enum', 'Byte', 'Delegate', 'SparseMulticastDelegate', 'InlineMulticastDelegate'):
        f = q(o + 0x38)
        if is_code(f):
            p['ref'] = hex(f) if t == 'Struct' else func_name.get(f, hex(f))
    return p

def read_prop_array(pa_va, n):
    o = va2off(pa_va)
    raw = [read_prop(q(o + 8 * i)) for i in range(n)]
    out, i = [], 0
    CONT = ('Array', 'Set', 'Optional', 'Map', 'Enum')
    while i < len(raw):
        p = raw[i]
        if i + 1 < len(raw) and raw[i + 1]['name'] == p['name'] and raw[i + 1]['type'] in CONT and raw[i+1]['type'] != 'Map':
            c = raw[i + 1]
            c['underlying' if c['type'] == 'Enum' else 'inner'] = p
            out.append(c); i += 2; continue
        if i + 2 < len(raw) and raw[i + 2]['type'] == 'Map' and raw[i + 1]['name'] == p['name'] == raw[i + 2]['name']:
            c = raw[i + 2]; c['key'], c['value'] = p, raw[i + 1]
            out.append(c); i += 3; continue
        out.append(p); i += 1
    return out

# 2) FStructParams
structs = {}
sp_name = {}
for rp, rs in data_secs:
    for o in range(rp, rp + rs - 0x38, 8):
        nv = q(o + 0x18)
        if not is_data(nv): continue
        of, sf, opf = q(o), q(o + 8), q(o + 0x10)
        if not is_code(of) or (sf and not is_code(sf)) or (opf and not is_code(opf)): continue
        np_, sz, al = struct.unpack_from('<HHB', b, o + 0x28)
        if al not in (1, 2, 4, 8, 16) or np_ > 600: continue
        pa = q(o + 0x20)
        if np_ and not is_data(pa): continue
        name = cstr(nv)
        if not name or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name): continue
        try:
            props = read_prop_array(pa, np_) if np_ else []
        except Exception as e:
            continue
        sp_name[off2va(o)] = name
        structs[name] = {'kind': 'struct', 'super': hex(sf) if sf else None, 'size': sz, 'props': props}
print('structs', len(structs))

# 3) FClassParams via construct funcs: scan code of registered funcs for lea to class params
def find_lea_targets(fva, n=96):
    o = va2off(fva)
    if o is None: return []
    code = b[o:o + n]
    res = []
    for i in range(len(code) - 7):
        if code[i] in (0x48, 0x4c) and code[i + 1] == 0x8d and (code[i + 2] & 0xc7) == 0x05:
            d = struct.unpack_from('<i', code, i + 3)[0]
            res.append(fva + i + 7 + d)
    return res

classes = {}
for f, nm in func_name.items():
    for t in find_lea_targets(f):
        o = va2off(t)
        if o is None: continue
        try:
            cnr, cfg, cpp, dep, fl, pa, ii = struct.unpack_from('<7Q', b, o)
            bits, cflags = struct.unpack_from('<II', b, o + 0x38)
        except struct.error:
            continue
        if not is_code(cnr) or (cpp and not is_data(cpp)): continue
        ndep = bits & 0xf; nfun = (bits >> 4) & 0x7ff; nprop = (bits >> 15) & 0x7ff; nii = (bits >> 26) & 0x3f
        if nprop and not is_data(pa): continue
        if ndep and not is_data(dep): continue
        sup = None
        if ndep:
            df = q(va2off(dep))
            sup = func_name.get(df, hex(df))
        try:
            props = read_prop_array(pa, nprop) if nprop else []
        except Exception:
            continue
        cname = func_name.get(cnr, nm)
        if cname in classes and classes[cname]['props'] and not props: continue
        classes[cname] = {'kind': 'class', 'super': sup, 'props': props, 'nfun': nfun}
        break
print('classes', len(classes))
def resolve(v):
    if not isinstance(v, str) or not v.startswith('0x'): return v
    f = int(v, 16)
    for t in find_lea_targets(f, 64):
        if t in sp_name: return sp_name[t]
    return func_name.get(f, v)
def fix_props(props):
    for p in props:
        if 'ref' in p: p['ref'] = resolve(p['ref'])
        for k in ('inner', 'key', 'value', 'underlying'):
            if p.get(k) and 'ref' in p[k]: p[k]['ref'] = resolve(p[k]['ref'])
for d in list(structs.values()) + list(classes.values()):
    d['super'] = resolve(d['super']); fix_props(d['props'])
unres = sum(1 for d in structs.values() for p in d['props'] if p['type']=='Struct' and str(p.get('ref','')).startswith('0x'))
print('unresolved struct refs', unres)
json.dump({'structs': structs, 'classes': classes, 'funcs': {hex(k): v for k, v in func_name.items()}}, open('refl.json', 'w'), indent=0)

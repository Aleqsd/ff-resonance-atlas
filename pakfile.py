"""Read-only extraction of single files from a UE v11 .pak (Oodle via ooz_cli)."""
import struct, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from extract import OOZ


def fstr(b, p):
    n = struct.unpack_from('<i', b, p)[0]; p += 4
    if n == 0:
        return '', p
    if n > 0:
        return b[p:p + n - 1].decode('latin-1'), p + n
    n = -n
    return b[p:p + 2 * n - 2].decode('utf-16-le'), p + 2 * n


class Pak:
    def __init__(self, path):
        self.path = path
        sz = os.path.getsize(path)
        f = open(path, 'rb'); self.f = f
        f.seek(sz - 0x400); tail = f.read()
        mi = tail.rfind(struct.pack('<I', 0x5A6F12E1))
        magic, ver, ioff, isz = struct.unpack_from('<IiQQ', tail, mi)
        self.methods = [tail[mi + 44 + 32 * i: mi + 44 + 32 * (i + 1)].split(b'\0')[0].decode() for i in range(5)]
        f.seek(ioff); idx = f.read(isz)
        mount, p = fstr(idx, 0)
        n, seed = struct.unpack_from('<iQ', idx, p); p += 12
        has_ph = struct.unpack_from('<I', idx, p)[0]; p += 4
        if has_ph: p += 36
        has_fd = struct.unpack_from('<I', idx, p)[0]; p += 4
        fdoff, fdsz = struct.unpack_from('<qq', idx, p); p += 36
        esz = struct.unpack_from('<i', idx, p)[0]; p += 4
        self.enc = idx[p:p + esz]
        f.seek(fdoff); fd = f.read(fdsz)
        q = 0; ndir = struct.unpack_from('<i', fd, q)[0]; q += 4
        self.files = {}
        for _ in range(ndir):
            d, q = fstr(fd, q)
            nf = struct.unpack_from('<i', fd, q)[0]; q += 4
            for _ in range(nf):
                fn, q = fstr(fd, q)
                loc = struct.unpack_from('<i', fd, q)[0]; q += 4
                self.files[mount + d + fn] = loc

    def read(self, name):
        loc = self.files[name]
        b, p = self.enc, loc
        v, = struct.unpack_from('<I', b, p); p += 4
        if (v & 0x3f) == 0x3f:
            cbs, = struct.unpack_from('<I', b, p); p += 4
        else:
            cbs = (v & 0x3f) << 11
        cm = (v >> 23) & 0x3f
        off = struct.unpack_from('<I' if v & (1 << 31) else '<Q', b, p)[0]; p += 4 if v & (1 << 31) else 8
        usz = struct.unpack_from('<I' if v & (1 << 30) else '<Q', b, p)[0]; p += 4 if v & (1 << 30) else 8
        if cm:
            csz = struct.unpack_from('<I' if v & (1 << 29) else '<Q', b, p)[0]; p += 4 if v & (1 << 29) else 8
        else:
            csz = usz
        nblk = (v >> 6) & 0xffff
        hdr = 53 + (4 + 16 * nblk if cm else 0)
        if not cm:
            self.f.seek(off + hdr); return self.f.read(usz)
        if nblk == 1:
            sizes = [csz]
        else:
            sizes = [struct.unpack_from('<I', b, p + 4 * i)[0] for i in range(nblk)]
        lines, cur, rem = [], off + hdr, usz
        for s in sizes:
            u = min(cbs, rem); rem -= u
            lines.append(f"{cur} {s} {u} 1"); cur += s
        tmp = os.path.join(tempfile.gettempdir(), f'ffrs_pak_{os.getpid()}.bin')
        subprocess.run([OOZ, self.path, tmp], input='\n'.join(lines), text=True, check=True)
        data = open(tmp, 'rb').read(); os.remove(tmp)
        return data


def read_locres(b):
    """Parse .locres (version 2/3) -> {namespace: {key: string}}"""
    magic = b[:16]
    p = 0
    if magic == bytes.fromhex('0E147475674A03FC4A15909DC3377F1B'):
        ver = b[16]; p = 17
    else:
        ver = 0
    strings = []
    if ver >= 1:
        so, = struct.unpack_from('<q', b, p); p += 8
        if ver >= 2:
            p += 4  # entries count
        q = so
        n, = struct.unpack_from('<i', b, q); q += 4
        for _ in range(n):
            s, q = fstr(b, q)
            if ver >= 2: q += 4
            strings.append(s)
    nns, = struct.unpack_from('<I', b, p); p += 4
    out = {}
    for _ in range(nns):
        if ver >= 2: p += 4
        ns, p = fstr(b, p)
        nk, = struct.unpack_from('<I', b, p); p += 4
        d = out.setdefault(ns, {})
        for _ in range(nk):
            if ver >= 2: p += 4
            k, p = fstr(b, p)
            p += 4  # source hash
            if ver >= 1:
                i, = struct.unpack_from('<i', b, p); p += 4
                d[k] = strings[i] if 0 <= i < len(strings) else ''
            else:
                d[k], p = fstr(b, p)
    return out

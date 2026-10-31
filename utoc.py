"""Read-only IoStore .utoc reader: file list + chunk/blocks info (UE5.6, toc v8)."""
import struct, sys, json


def fstr(b, p):
    n = struct.unpack_from('<i', b, p)[0]; p += 4
    if n == 0:
        return '', p
    if n > 0:
        return b[p:p + n - 1].decode('latin-1'), p + n
    n = -n
    return b[p:p + 2 * n - 2].decode('utf-16-le'), p + 2 * n


class Toc:
    def __init__(self, path):
        b = open(path, 'rb').read()
        assert b[:16] == b'-==--==--==--==-'
        (self.ver,) = struct.unpack_from('<B', b, 16)
        hs, n, nblk, blksz, ncm, cml, cbs, dis, parts = struct.unpack_from('<9I', b, 20)
        self.flags = b[80]
        nseeds, = struct.unpack_from('<I', b, 84)
        partsize, = struct.unpack_from('<Q', b, 88)
        nnohash, = struct.unpack_from('<I', b, 96)
        p = hs
        self.chunk_ids = [b[p + 12 * i:p + 12 * i + 12] for i in range(n)]; p += 12 * n
        self.offlen = []
        for i in range(n):
            e = b[p + 10 * i:p + 10 * i + 10]
            self.offlen.append((int.from_bytes(e[0:5], 'big'), int.from_bytes(e[5:10], 'big')))
        p += 10 * n
        p += 4 * nseeds + 4 * nnohash
        self.blocks = []
        for i in range(nblk):
            e = b[p + 12 * i:p + 12 * i + 12]
            off = int.from_bytes(e[0:5], 'little')
            csz = int.from_bytes(e[5:8], 'little')
            usz = int.from_bytes(e[8:11], 'little')
            m = e[11]
            self.blocks.append((off, csz, usz, m))
        p += 12 * nblk
        self.methods = [b[p + cml * i:p + cml * (i + 1)].split(b'\0')[0].decode() for i in range(ncm)]
        p += cml * ncm
        self.cbs = cbs
        if self.flags & 4:  # signed
            hsz, = struct.unpack_from('<i', b, p); p += 4
            p += hsz * 2 + 20 * nblk
        self.files = {}
        if self.flags & 8 and dis:
            d = b[p:p + dis]
            q = 0
            mount, q = fstr(d, q)
            nd, = struct.unpack_from('<i', d, q); q += 4
            dirs = [struct.unpack_from('<4I', d, q + 16 * i) for i in range(nd)]; q += 16 * nd
            nf, = struct.unpack_from('<i', d, q); q += 4
            files = [struct.unpack_from('<3I', d, q + 12 * i) for i in range(nf)]; q += 12 * nf
            ns, = struct.unpack_from('<i', d, q); q += 4
            strs = []
            for _ in range(ns):
                s, q = fstr(d, q); strs.append(s)
            NONE = 0xFFFFFFFF

            def walk(di, prefix):
                name, child, sib, ff = dirs[di]
                path = prefix + (strs[name] + '/' if name != NONE else '')
                f = ff
                while f != NONE:
                    fn, nxt, ud = files[f]
                    self.files[path + strs[fn]] = ud
                    f = nxt
                c = child
                while c != NONE:
                    walk(c, path)
                    c = dirs[c][2]
            walk(0, mount)


if __name__ == '__main__':
    t = Toc(sys.argv[1])
    print('ver', t.ver, 'flags', t.flags, 'methods', t.methods, 'files', len(t.files), 'blocks', len(t.blocks))
    with open(sys.argv[2], 'w', encoding='utf-8') as o:
        for k in sorted(t.files):
            o.write(f'{k}\t{t.files[k]}\n')

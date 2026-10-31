"""List files in a UE legacy .pak (v8-v11), read-only."""
import struct, sys, os


def fstr(b, p):
    n = struct.unpack_from('<i', b, p)[0]; p += 4
    if n == 0:
        return '', p
    if n > 0:
        return b[p:p + n - 1].decode('latin-1'), p + n
    n = -n
    return b[p:p + 2 * n - 2].decode('utf-16-le'), p + 2 * n


def main(path, out):
    sz = os.path.getsize(path)
    f = open(path, 'rb')
    f.seek(sz - 0x400)
    tail = f.read()
    mi = tail.rfind(struct.pack('<I', 0x5A6F12E1))
    magic, ver, ioff, isz = struct.unpack_from('<IiQQ', tail, mi)
    enc = tail[mi - 1]
    print('version', ver, 'index', ioff, isz, 'encrypted index', enc)
    f.seek(ioff)
    idx = f.read(isz)
    mount, p = fstr(idx, 0)
    n, seed = struct.unpack_from('<iQ', idx, p); p += 12
    has_ph = struct.unpack_from('<I', idx, p)[0]; p += 4
    if has_ph:
        p += 8 + 8 + 20
    has_fd = struct.unpack_from('<I', idx, p)[0]; p += 4
    fdoff, fdsz = struct.unpack_from('<qq', idx, p); p += 36
    print('mount', mount, 'entries', n)
    f.seek(fdoff)
    fd = f.read(fdsz)
    q = 0
    ndir = struct.unpack_from('<i', fd, q)[0]; q += 4
    names = []
    for _ in range(ndir):
        d, q = fstr(fd, q)
        nf = struct.unpack_from('<i', fd, q)[0]; q += 4
        for _ in range(nf):
            fn, q = fstr(fd, q)
            q += 4
            names.append(mount + d + fn)
    with open(out, 'w', encoding='utf-8') as o:
        o.write('\n'.join(sorted(names)))
    print('files', len(names))


main(sys.argv[1], sys.argv[2])

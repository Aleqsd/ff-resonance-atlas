"""Extract a Texture2D (inline mip) from IoStore to PNG (read-only)."""
import sys, os, struct, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from zen import read_file, Package
from config import TEXDEC
BPP = {'PF_BC7': 1, 'PF_DXT5': 1, 'PF_BC5': 1, 'PF_DXT1': 0.5, 'PF_B8G8R8A8': 4}

def texture_png(game_path, out):
    p = '../../../FFRS/Content/' + game_path[len('/Game/'):] + '.uasset'
    b = read_file(p)
    pkg = Package(b, p)
    e = pkg.exports[0]
    s, end = pkg.export_data(e)
    for fmt in BPP:
        i = b.find(struct.pack('<i', len(fmt) + 1) + fmt.encode() + b'\0', s, end)
        if i >= 0:
            break
    else:
        raise ValueError('format not found')
    w, h, packed = struct.unpack_from('<iii', b, i - 12)
    d = i + 4 + len(fmt) + 1 + 12
    n = int(w * h * BPP[fmt])
    tmp = out + '.raw'
    open(tmp, 'wb').write(b[d:d + n])
    subprocess.run([TEXDEC, tmp, str(w), str(h), fmt, out], check=True)
    os.remove(tmp)
    return w, h, fmt

if __name__ == '__main__':
    print(texture_png(sys.argv[1], sys.argv[2]))

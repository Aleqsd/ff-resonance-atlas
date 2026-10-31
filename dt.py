import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from zen import *

def decode_datatable(path):
    b = read_file(path)
    pkg = Package(b, path)
    for e in pkg.exports:
        cls = pkg.class_of(e)
        if cls and cls[0] == 'script' and cls[1].split('.')[-1] in ('DataTable', 'CompositeDataTable'):
            s, end = pkg.export_data(e)
            r = Reader(b, s, end, pkg)
            props = read_unversioned(r, schema_for('UDataTable' if cls[1].endswith('.DataTable') else 'UCompositeDataTable'))
            rs = props.get('RowStruct')
            rsn = pkg.pkg_index(rs[1])[1][1].split('.')[-1] if rs else None
            r.u('<I')
            n = r.u('<i')
            rows = {}
            for i in range(n):
                rn = r.fname()
                rows[rn] = read_struct(r, rsn)
            return {'rowStruct': rsn, 'props': {k: v for k, v in props.items() if k != 'RowStruct'}, 'rows': rows, '_left': end - r.p}
if __name__ == '__main__':
    d = decode_datatable(sys.argv[1])
    print(json.dumps(d, ensure_ascii=False, default=str)[:int(sys.argv[2]) if len(sys.argv) > 2 else 3000])

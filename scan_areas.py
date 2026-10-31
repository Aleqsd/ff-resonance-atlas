"""Scan levels for area volumes (ACPP_Map_NavMeshBoundsVolume) -> areas.json"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from zen import *
from extract import toc
from scan_levels import class_name_from_script

def comp_props(pkg, idx):
    e = pkg.exports[idx - 1]
    cls = pkg.class_of(e)
    cn = class_name_from_script(cls[1]) if cls and cls[0] == 'script' else None
    if not cn: return None
    s, end = pkg.export_data(e)
    return read_unversioned(Reader(pkg.b, s, end, pkg), schema_for(cn))

out = []
t = toc('FFRS-Windows')
levels = sorted(k for k in t.files if '/Content/Map/' in k and k.endswith('.umap') and '/Map/Btl/' not in k)
for l in levels:
    try:
        b = read_file(l); pkg = Package(b, l)
    except Exception as ex:
        continue
    for ei, e in enumerate(pkg.exports):
        cls = pkg.class_of(e)
        if not cls: continue
        name = str(cls[1])
        if 'NavMeshBoundsVolume' not in name: continue
        sch = schema_for('ACPP_Map_NavMeshBoundsVolume') if cls[0] == 'script' else bp_schema(name)
        s, end = pkg.export_data(e)
        try:
            props = read_unversioned(Reader(b, s, end, pkg), sch)
        except Exception as ex:
            out.append({'level': l, 'actor': e['name'], 'error': str(ex)[:200]}); continue
        rec = {'level': l, 'actor': e['name'], 'areaId': props.get('m_AreaId'), 'class': name}
        for key in ('m_pBoxComponent', 'RootComponent', 'BrushComponent'):
            v = props.get(key)
            if isinstance(v, tuple) and v[1] > 0:
                try:
                    cp = comp_props(pkg, v[1])
                except Exception as ex:
                    cp = {'_err': str(ex)[:100]}
                if cp:
                    rec[key] = {k: cp.get(k) for k in ('RelativeLocation', 'RelativeRotation', 'RelativeScale3D', 'BoxExtent', 'AttachParent', 'Bounds', '_err') if k in cp}
        out.append(rec)
json.dump(out, open('areas.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0, default=str)
print(len(out), sum(1 for x in out if 'error' in x))

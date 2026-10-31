"""World-map entrances: transition triggers in Wld levels -> entrances.json"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from zen import *
from extract import toc
from scan_levels import comp_location
t = toc('FFRS-Windows')
levels = sorted(k for k in t.files if '/Content/Map/Wld/' in k and k.endswith('.umap'))
out, errs = [], 0
for l in levels:
    b = read_file(l); pkg = Package(b, l)
    for ei, e in enumerate(pkg.exports):
        cls = pkg.class_of(e)
        if not cls or 'TransitionTrigger' not in str(cls[1]) or e['name'].startswith('Default__'): continue
        sch = schema_for('ACPP_MapTransitionTrigger') if cls[0] == 'script' else bp_schema(cls[1])
        s, end = pkg.export_data(e)
        try:
            props = read_unversioned(Reader(b, s, end, pkg), sch)
        except Exception as ex:
            errs += 1; continue
        rc = props.get('RootComponent') or props.get('m_pRootBoxComponent')
        loc = comp_location(pkg, rc[1]) if isinstance(rc, tuple) else None
        out.append({'level': l.split('/')[-1], 'mapId': props.get('m_MapId'), 'loc': loc, 'cond': props.get('m_Condition')})
json.dump(out, open('entrances.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print(len(out), 'errs', errs, sorted(set(x['mapId'] for x in out if x['mapId'])))

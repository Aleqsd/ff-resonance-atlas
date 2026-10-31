"""Cross-reference: save + game data -> out/data2.json (read-only on game files).
Notes: unserialized ids default to -1, the save slot of a map is its sameMapId, the same physical chest in
several story variants of a map is counted once, pre-opened decor is excluded, chest content is looked up
by (mapId, id), floors are chosen with the Z coordinate, and access paths honour game conditions."""
import json, re, os, sys, collections
sys.path.insert(0, os.path.dirname(__file__))
from config import CURATED

SAVE = sys.argv[1] if len(sys.argv) > 1 else 'save_latest.json'
L = lambda f: json.load(open(f, encoding='utf-8'))
def opt(f, d):
    try: return L(f)
    except Exception: return d

maps = {int(k): v for k, v in L('maps.json').items()}
lc = {m: a for m, a in L('landcapture.json')}
gim = L('gimmicks.json')
navs = L('areas.json')
items = {int(k): v for k, v in L('items.json').items() if k != 'null'}
tdt = L('treasure_dt.json')
frl = L('locres_fr.json')
NAMES = opt(os.path.join(CURATED, 'names.json'), {})
PLSUBS = opt(os.path.join(CURATED, 'pl_subs.json'), {})
ACCESS = opt(os.path.join(CURATED, 'access.json'), {})
sv = L(SAVE)
OVR = opt(os.path.join(CURATED, 'overrides.json'), {})
def centre(cap, aid, a):
    c = (OVR.get('capture_center') or {}).get(f'{cap}_{aid}')
    return c or a['WorldLocation']
P = sv['props']

# ---------- save helpers ----------
state = {}
for mid, v in P['Map']['mapGimmick']:
    for t in v['treasureBox']['treasureBoxList']:
        state[(mid, t['UniqueID'])] = t
slots_with_entries = {mid for mid, _ in state}
progress = P['Progress']['Progress']
eflags = P['Progress']['eventFlag']
inv = {i['ItemId']: i['Num'] for i in P['inventory']}

def cond_ok(c):
    """evaluate game condition strings like '{progress:0}>=7090 & !{flag:810}' against the save"""
    if not c or not c.strip():
        return True
    def val(kind, n):
        n = int(n)
        if kind == 'progress': return progress[n] if n < len(progress) else 0
        if kind == 'flag': return 1 if (n < len(eflags) and eflags[n]) else 0
        if kind == 'item': return inv.get(n, 0)
        return 0
    expr = re.sub(r'\{(\w+):(\d+)\}', lambda m: str(val(m.group(1), m.group(2))), c)
    expr = expr.replace('&&', '&').replace('||', '|')
    expr = re.sub(r'!(?!=)', ' not ', expr).replace('&', ' and ').replace('|', ' or ')
    try:
        return bool(eval(expr, {'__builtins__': {}}, {}))
    except Exception:
        return True

def txt(t):
    if isinstance(t, dict) and 'table' in t:
        return frl.get(t['table'].split('.')[-1], {}).get(t['key'])
    return None

def item_name(iid, num=1, money=-1):
    if (iid in (None, -1, 0)) and money and money > 0:
        return f"{money} gils"
    it = items.get(iid)
    n = (txt(it['name']) if it else None) or (it['jp'] if it else None)
    if not n: return None
    return n + (f" ×{num}" if num and num > 1 else '')

# ---------- folders <-> maps ----------
def folder_of_path(p):
    m = re.search(r'(Map/[^/]+/[^/]+/[^/]+)/', p + '/')
    return m.group(1) if m else None
def lvl_folder(m):
    lv = m.get('level')
    if isinstance(lv, str) and lv.startswith('('): lv = eval(lv)
    lv = lv[1] if isinstance(lv, (list, tuple)) and len(lv) > 1 else None
    return folder_of_path(lv.replace('/Game/', '')) if lv else None

FOLDER_MAPS = collections.defaultdict(list)
for mid, m in maps.items():
    f = lvl_folder(m)
    if f: FOLDER_MAPS[f.lower()].append(mid)
for mid, d in PLSUBS.items():  # maps whose persistent level streams sublevels of another folder
    for s in d.get('subs', []):
        f = folder_of_path(s.replace('/Game/', ''))
        if f and int(mid) not in FOLDER_MAPS[f.lower()]:
            FOLDER_MAPS[f.lower()].append(int(mid))
def slot(m):
    s = maps.get(m, {}).get('sameMapId', -1)
    return s if s not in (None, -1) else m

NF = NAMES.get('folders', {})
NM = NAMES.get('maps', {})
def folder_past(f):
    return bool((NF.get(f) or {}).get('possibly_inaccessible'))
def best_map(f, cands):
    b = (NF.get(f) or {}).get('best_mapId')
    if b: return b
    for m in cands:
        if not (NM.get(str(m)) or {}).get('possibly_inaccessible'): return m
    return cands[0] if cands else None

# treasure rows by (mapId, id)
DT = {}
for r in tdt:
    DT.setdefault((r['mapId'], r['id']), r)

# ---------- floors / areas ----------
VOLS = collections.defaultdict(list)
for a in navs:
    rc = (a.get('RootComponent') or {}).get('RelativeLocation'); ext = (a.get('m_pBoxComponent') or {}).get('BoxExtent')
    if rc and ext:
        VOLS[(folder_of_path(a['level'].split('Content/')[-1]) or '').lower()].append((a.get('areaId') or 0, rc, ext))

def area_for(cap, folders, loc):
    if cap not in lc: return None, False
    A = dict(lc[cap]['AreaLandCaptureDataMap'])
    px, py = loc['Y'], -loc['X']
    def in_sq(aid, slack=0.0):
        a = A[aid]; C, S = centre(cap, aid, a), a['BoxSize']; Ls = max(S['X'], S['Y']) * (1 + slack)
        return abs(px - C['X']) <= Ls / 2 and abs(py - C['Y']) <= Ls / 2
    def in_box(aid):
        a = A[aid]; C, S = centre(cap, aid, a), a['BoxSize']
        return abs(px - C['X']) <= S['X'] / 2 + 1 and abs(py - C['Y']) <= S['Y'] / 2 + 1
    cands = []
    for f in folders:
        for aid, c, e in VOLS.get(f.lower(), []):
            if all(abs(loc[k] - c[k]) <= e[k] + 60 for k in 'XYZ'):
                cands.append((e['X'] * e['Y'] * e['Z'], aid))
    for _, aid in sorted(cands):
        if aid in A and in_box(aid): return aid, False
    for _, aid in sorted(cands):
        if aid in A and in_sq(aid): return aid, False
    # 2D candidates, choose by capture height (BasePriolity is metres) closest below the item
    box = [aid for aid in A if in_box(aid)]
    z = loc['Z']
    def score(aid):
        h = (A[aid].get('BasePriolity') or 0) * 100
        return (0 if h <= z + 150 else 1, abs(z - h))
    good = [aid for aid in box if (A[aid].get('BasePriolity') or 0) * 100 <= z + 300]
    if good: return sorted(good, key=score)[0], False
    for _, aid in sorted(cands):  # a NAV volume names the page but the point is off its image
        if aid in A: return aid, True
    if box: return sorted(box, key=score)[0], False
    sq = [aid for aid in A if in_sq(aid)]
    if sq: return sq[0], True
    # nearest capture: approximate
    def dist(aid):
        a = A[aid]; C = a['WorldLocation']; return (px - C['X']) ** 2 + (py - C['Y']) ** 2
    return (sorted(A, key=dist)[0], True) if A else (None, False)

# ---------- build records ----------
recs = []
for x in gim:
    if 'error' in x or not x.get('loc'): continue
    cls = x['class'].split('/')[-1]
    if 'Medal' in cls: kind = 'shard'
    elif 'Safe' in cls: kind = 'safe'
    elif x.get('native') == 'ACPP_MapGimmick_TreasureBox': kind = 'chest'
    else: continue
    f = folder_of_path(x['level'].split('Content/')[-1])
    uid = x['m_UniqueId'] if 'm_UniqueId' in x else -1
    mid_id = x['m_Id'] if 'm_Id' in x else -1
    if kind == 'chest' and x.get('m_IsOpen') is True and 'm_Id' not in x:
        continue  # empty prop placed already open
    cands = list(FOLDER_MAPS.get(f.lower(), []))
    tbd = x.get('m_TreasureBoxData') or {}
    if kind != 'shard' and tbd.get('mapId') and tbd['mapId'] not in cands:
        cands.append(tbd['mapId'])
    slots = []
    for m in cands:
        for s in (m, slot(m)):
            if s not in slots: slots.append(s)
    hits = [(s, state[(s, uid)]) for s in slots if (s, uid) in state]
    if hits:
        st = 'found' if any(h[1]['IsOpen'] for h in hits) else 'missing'
    else:
        st = 'unvisited' if not any(s in slots_with_entries for s in slots) else 'missing'
    content = None
    if kind == 'shard':
        content = 'Fragment de tablette'
    else:
        row = None
        for m in cands:
            row = DT.get((m, mid_id))
            if row: break
        if row: content = item_name(row['itemId'], row['itemNum'], row['money'])
        if not content and tbd:
            content = item_name(tbd.get('itemId'), tbd.get('itemNum', 1), tbd.get('money', -1))
    bm = best_map(f, cands)
    phys = (slot(bm) if bm else f, uid) if kind != 'shard' else (f, uid)
    recs.append({'kind': kind, 'state': st, 'folder': f, 'uid': uid, 'mapId': bm, 'cands': cands, 'slots': slots,
                 'content': content, 'loc': x['loc'], 'past': folder_past(f), 'phys': list(map(str, phys))})

# dedupe physical chests (same save slot + uid in several story-variant folders): keep a current folder
groups = collections.defaultdict(list)
for r in recs:
    groups[(r['kind'],) + tuple(r['phys'])].append(r)
out = []
for k, rs in groups.items():
    if len(rs) == 1: out.append(rs[0]); continue
    st = 'found' if any(r['state'] == 'found' for r in rs) else ('missing' if any(r['state'] == 'missing' for r in rs) else 'unvisited')
    keep = sorted(rs, key=lambda r: (r['past'], r['folder']))[0]
    keep = dict(keep, state=st, variants=[r['folder'] for r in rs if r is not keep])
    out.append(keep)

# floor / plan
for r in out:
    folders = [r['folder']] + [lvl_folder(maps[m]) for m in r['cands'] if m in maps and lvl_folder(maps[m])]
    cap = r['mapId'] if r['mapId'] in lc else next((m for m in r['cands'] if m in lc), None)
    aid, approx = area_for(cap, folders, r['loc']) if cap is not None else (None, False)
    r['capMap'], r['area'], r['approx'] = cap, aid, approx

# the game shows a different page variant once some flags are set (same box, other texture)
def visible_variant(cap, aid):
    A = dict(lc[cap]['AreaLandCaptureDataMap']); a = A[aid]
    if cond_ok(a['DisplayData'].get('VisibleCondition')): return aid
    for b, x in A.items():
        if b != aid and x['WorldLocation'] == a['WorldLocation'] and x['BoxSize'] == a['BoxSize']            and abs((x.get('BasePriolity') or 0) - (a.get('BasePriolity') or 0)) <= 1 and cond_ok(x['DisplayData'].get('VisibleCondition')):
            return b
    return aid
for r in out:
    po = (OVR.get('plan') or {}).get(f"{r['kind']}:{r['folder']}:{r['uid']}")
    if po: r['capMap'], r['area'], r['approx'] = po[0], po[1], False
    if r['capMap'] is not None and r['area'] is not None:
        r['area'] = visible_variant(r['capMap'], r['area'])

# access: valid edges now
def access_now(mid):
    a = ACCESS.get(str(mid)) or {}
    srcs, world, blocked = [], False, []
    for e in a.get('edges', []):
        if e.get('eventOnly'): continue
        ok = cond_ok(e.get('cond')) and cond_ok(e.get('triggerCond'))
        if not ok:
            blocked.append(e.get('cond') or e.get('triggerCond')); continue
        if e['from'] == 1000: world = True
        elif e['from'] not in srcs: srcs.append(e['from'])
    return {'world': world, 'from': srcs, 'blocked': blocked}
ACC = {int(k): access_now(int(k)) for k in ACCESS}
for r in out:
    if r['mapId'] is not None and r['mapId'] not in ACC:
        ACC[r['mapId']] = access_now(r['mapId'])

def turned_in():
    """tablet shards already handed to the princess (transfer inventory of the Forgotten Palace)"""
    n = 0
    try:
        for _tid, v in P['tranferTargetInventory']['inventory']:
            for _k, iv in v['inventory']:
                n += sum(x['Num'] for x in iv['inventoryList'] if x['ItemId'] == 25004)
    except Exception:
        return None
    return n
tot = collections.Counter((r['kind'], r['state']) for r in out)
print(sorted(tot.items()))
json.dump({'records': out, 'access': {str(k): v for k, v in ACC.items()},
           'player': {'PlayTime': P['Player']['PlayTime'], 'SavedDateTime': P['Player']['SavedDateTime'], 'progress': progress[0]},
           'shards_in_bag': inv.get(25004, 0), 'shards_turned_in': turned_in()},
          open('out/data2.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0, default=str)

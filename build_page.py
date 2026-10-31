"""Page data from out/data2.json: only what is still missing, island -> place -> plan blocks, clear French names."""
import json, os, re, collections, base64, io, sys, datetime, unicodedata
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image
import tex
from config import CURATED

L = lambda f: json.load(open(f, encoding='utf-8'))
def opt(f, d):
    try: return L(f)
    except Exception: return d
D = L('out/data2.json'); R = D['records']; ACC = D['access']
lc = {m: a for m, a in L('landcapture.json')}
maps = {int(k): v for k, v in L('maps.json').items()}
frm = L('locres_fr.json')['ST_MAP_NAME']
NAMES = opt(os.path.join(CURATED, 'names.json'), {}); NM = NAMES.get('maps', {}); WA = NAMES.get('world_areas', {})
FLOORS = opt(os.path.join(CURATED, 'floors.json'), {})
ACCESS = opt(os.path.join(CURATED, 'access.json'), {})
OVR = opt(os.path.join(CURATED, 'overrides.json'), {})
BG = (20, 23, 32)

# ---------- images ----------
def cap_png(path):
    fn = 'tex/cache/' + path.split('/')[-1] + '.png'
    if not os.path.exists(fn): tex.texture_png(path, fn)
    return fn
def uri(im, q=80, alpha=False):
    buf = io.BytesIO(); (im if alpha else im.convert('RGB')).save(buf, 'WEBP', quality=q)
    return 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()
_base = {}
def area_base(cm, aid, size=640):
    """capture composited on the dark map colour, as a PIL image (size x size)"""
    if (cm, aid) not in _base:
        a = dict(lc[cm]['AreaLandCaptureDataMap'])[aid]
        src = Image.open(cap_png(a['LandTextureMap'][0][1][1])).convert('RGBA').resize((size, size), Image.LANCZOS)
        out = Image.new('RGBA', src.size, BG + (255,)); out.alpha_composite(src)
        _base[(cm, aid)] = out
    return _base[(cm, aid)]
def centre(cm, aid, a):
    return (OVR.get('capture_center') or {}).get(f'{cm}_{aid}') or a['WorldLocation']
def to_pct(cm, aid, loc):
    a = dict(lc[cm]['AreaLandCaptureDataMap'])[aid]
    C, S = centre(cm, aid, a), a['BoxSize']; Ls = max(S['X'], S['Y'])
    return [round((loc['Y'] - C['X'] + Ls / 2) / Ls * 100, 2), round((-loc['X'] - C['Y'] + Ls / 2) / Ls * 100, 2)]

# ---------- names ----------
def official(mid):
    n = NM.get(str(mid)) or {}
    m = maps.get(mid, {})
    key = (m.get('name') or {}).get('key') if isinstance(m.get('name'), dict) else None
    return n.get('official') or (frm.get(key) if key else None) or n.get('label') or (m.get('dev') or str(mid)).strip()
def place_names(mid):
    o = (OVR.get('places') or {}).get(str(mid), {})
    n = NM.get(str(mid)) or {}
    name = o.get('name') or official(mid)
    if not n.get('official') and n.get('label') and not o.get('name'): name = n['label']
    sub = o.get('sub')
    if sub is None:
        parts = []
        if n.get('context'): parts.append(n['context'])
        if n.get('variant_kind') not in (None, 'normal') and n.get('qualifier'): parts.append(n['qualifier'])
        sub = ' · '.join(parts)
    return name, sub

def floor_label(cm, aid):
    o = (OVR.get('floors') or {}).get(f'{cm}_{aid}')
    if o is not None: return o
    f = FLOORS.get(f'{cm}_{aid}') or {}
    lv, n = f.get('level'), f.get('levels')
    A = dict(lc[cm]['AreaLandCaptureDataMap']); bps = [a.get('BasePriolity') or 0 for a in A.values()]; bp = A[aid].get('BasePriolity') or 0
    parts = []
    if lv and n and n > 1:
        s = f'Niveau {lv} / {n}'
        if lv == 1 and bp <= min(bps) + 2: s += ' (le plus bas)'
        elif lv == n and bp >= max(bps) - 2: s += ' (le plus haut)'
        parts.append(s)
    m = re.search(r'(annexe|partie) ([\w-]+)', f.get('label') or '')
    if m: parts.append(('bâtiment annexe ' if m.group(1) == 'annexe' else 'partie ') + m.group(2))
    return ' · '.join(parts)

# ---------- access / world ----------
def world_loc(mid):
    for e in (ACCESS.get(str(mid)) or {}).get('edges', []):
        if e['from'] == 1000 and not e.get('eventOnly') and e.get('loc'): return e['loc']
    return None
PROGRESS = (D.get('player') or {}).get('progress') or 0
def area_shown(aid):
    """is this world-map area version visible at the save's story progress? (game VisibleCondition)"""
    c = ((WA.get(str(aid)) or {}).get('visible_condition') or '').strip()
    if not c: return True
    expr = re.sub(r'\{progress:0\}', str(int(PROGRESS)), c).replace('&&', '&').replace('||', '|')
    expr = re.sub(r'!(?!=)', ' not ', expr).replace('&', ' and ').replace('|', ' or ')
    try: return bool(eval(expr, {'__builtins__': {}}, {}))
    except Exception: return True
def world_area(loc):
    best = None
    for aid, a in lc[1000]['AreaLandCaptureDataMap']:
        C, S = a['WorldLocation'], a['BoxSize']; px, py = loc['Y'], -loc['X']
        if abs(px - C['X']) <= S['X'] / 2 and abs(py - C['Y']) <= S['Y'] / 2:
            shown = area_shown(aid)
            key = (0 if shown else 1, S['X'] * S['Y'])
            if best is None or key < best[0]: best = (key, aid)
    return best[1] if best else None
def route(mid, depth=0, seen=None):
    seen = seen or set()
    if mid in seen or depth > 6: return [mid], None
    seen.add(mid)
    o = (OVR.get('access') or {}).get(str(mid))
    if o and o.get('from'):
        p, w = route(o['from'], depth + 1, seen); return p + [mid], w
    a = ACC.get(str(mid)) or {}
    if a.get('world'): return [mid], mid
    for src in a.get('from', []):
        if 5000 <= src < 6000 or official(src) == official(mid): continue
        p, w = route(src, depth + 1, seen)
        if w is not None: return p + [mid], w
    return [mid], None

# ---------- group records into places ----------
recs = [r for r in R if r['kind'] in ('shard', 'chest') and r['state'] != 'found']
found = [r for r in R if r['kind'] in ('shard', 'chest') and r['state'] == 'found']
places = collections.OrderedDict()
for r in recs:
    grp = 'past' if r['past'] else 'todo'
    places.setdefault((grp, r['mapId']), {'grp': grp, 'mid': r['mapId'], 'recs': []})['recs'].append(r)

ISL_SHORT = {1: 'Grandshelt · île principale', 2: "Grandshelt · île de l'ouest", 3: 'Grandshelt · île de Kolobos', 4: 'Zoldaad',
             16: 'Dirnado', 6: 'Dirnado', 18: 'Olderion', 17: 'Olderion', 7: 'Olderion', 8: 'Gronoa', 10: 'Mysidia', 13: 'Pharm', 9: 'Pharm', 12: 'Tour de cristal'}
islands = {g: collections.OrderedDict() for g in ('todo', 'past')}
for (grp, mid), p in places.items():
    path, w = route(mid)
    wl = world_loc(w) if w else None
    wa = world_area(wl) if wl else None
    if wa is None:
        for ow in (NM.get(str(mid)) or {}).get('world_areas', []) or []:
            if area_shown(ow): wa = ow; break
    p['wa'], p['wpos'], p['path'] = wa, (to_pct(1000, wa, wl) if (wa is not None and wl) else None), path
    info = WA.get(str(wa)) or {}
    lab = re.sub(r'\s*\((ancienne|version) [^)]*\)', '', info.get('label') or 'Autres lieux')
    isl = islands[grp].setdefault(wa, {'name': lab, 'short': ISL_SHORT.get(wa, lab), 'order': (info.get('island_enum') or 99, wa or 0), 'places': []})
    isl['places'].append(p)

def slug(s): return re.sub(r'[^a-z0-9]+', '-', unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()).strip('-')

AR_MIN, AR_MAX, PAD, MIN_SIDE, OUT = 0.8, 2.4, 4.0, 24.0, 760
def frame(cm, aid, pts):
    """crop box (in % of the square capture) around the drawn floor and the given points.
    Returns x0, y0, x1, y1, aspect ratio, and the cropped image (longest side OUT px)."""
    a = dict(lc[cm]['AreaLandCaptureDataMap'])[aid]
    src = Image.open(cap_png(a['LandTextureMap'][0][1][1])).convert('RGBA')
    N = src.size[0]
    full = Image.new('RGBA', src.size, BG + (255,)); full.alpha_composite(src)
    import numpy as np
    arr = np.asarray(full.convert('RGB')).astype(int)
    mask = (np.abs(arr - np.array(BG)).max(axis=2) > 28)
    ys, xs = np.nonzero(mask)
    if len(xs) > 20:
        # ignore isolated specks: keep the 0.3 %..99.7 % range of drawn pixels
        bx0, bx1 = np.percentile(xs, [0.3, 99.7]); by0, by1 = np.percentile(ys, [0.3, 99.7])
        x0, x1, y0, y1 = bx0 / N * 100, (bx1 + 1) / N * 100, by0 / N * 100, (by1 + 1) / N * 100
    else:
        x0, y0, x1, y1 = 0.0, 0.0, 100.0, 100.0
    for p in pts:
        x0, y0, x1, y1 = min(x0, p[0] - 6), min(y0, p[1] - 6), max(x1, p[0] + 6), max(y1, p[1] + 6)
    x0, y0, x1, y1 = x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD
    def grow(lo, hi, size):
        if hi - lo >= size: return lo, hi
        c = (lo + hi) / 2; lo, hi = c - size / 2, c + size / 2
        # stay inside the capture when there is room
        if lo < 0 and hi - lo <= 100: hi, lo = hi - lo, 0
        if hi > 100 and hi - lo <= 100: lo, hi = lo - (hi - 100), 100
        return lo, hi
    x0, x1 = grow(x0, x1, MIN_SIDE); y0, y1 = grow(y0, y1, MIN_SIDE)
    w, h = x1 - x0, y1 - y0
    if w / h > AR_MAX: y0, y1 = grow(y0, y1, w / AR_MAX)
    elif w / h < AR_MIN: x0, x1 = grow(x0, x1, h * AR_MIN)
    w, h = x1 - x0, y1 - y0
    px = N / 100
    crop = full.crop((round(x0 * px), round(y0 * px), round(x1 * px), round(y1 * px)))   # outside the capture -> transparent
    img = Image.new('RGBA', crop.size, BG + (255,)); img.alpha_composite(crop)
    k = OUT / max(img.size)
    img = img.resize((max(1, round(img.size[0] * k)), max(1, round(img.size[1] * k))), Image.LANCZOS)
    return x0, y0, x1, y1, round(w / h, 4), img

def build_plan(cm, aid, rs, start_n):
    """one plan block: image (+ frame expansion when items fall outside), marks, its items"""
    label = floor_label(cm, aid)
    marks, items, n = [], [], start_n
    for r in sorted(rs, key=lambda r: (r['kind'] != 'shard', r['loc']['X'])):
        n += 1
        iid = f"{r['kind']}:{r['folder']}:{r['uid']}"
        mo = (OVR.get('marks') or {}).get(iid, {})
        p = mo.get('p') or to_pct(cm, aid, r['loc'])
        approx = bool(r.get('approx')) and not mo.get('p')
        marks.append({'id': iid, 'n': n, 'k': r['kind'], 'p': p, 'approx': approx})
        note = mo.get('note') or ('salle absente du plan du jeu : repère en pointillés = position estimée' if approx else '')
        items.append({'id': iid, 'n': n, 'k': r['kind'], 'what': r['content'], 'note': note})
    # frame: crop the capture to what is drawn on it (plus every missing item), so thin or small floors fill the picture
    x0, y0, x1, y1, ar, img = frame(cm, aid, [m['p'] for m in marks])
    w, h = x1 - x0, y1 - y0
    tr = lambda p: [round((p[0] - x0) / w * 100, 2), round((p[1] - y0) / h * 100, 2)]
    for m in marks: m['p'] = tr(m['p'])
    for f_ in found:
        if f_['capMap'] == cm and f_['area'] == aid:
            q = tr(to_pct(cm, aid, f_['loc']))
            if 0 <= q[0] <= 100 and 0 <= q[1] <= 100: marks.append({'found': True, 'p': q})
    plan = {'label': label, 'img': uri(img), 'ar': ar, 'marks': marks, '_k': (cm, aid)}
    # context thumbnail for small separate rooms: where the room sits on its parent floor
    fl = FLOORS.get(f'{cm}_{aid}') or {}
    par = fl.get('annexOf')
    if par is not None:
        try:
            par = int(par)
            A = dict(lc[cm]['AreaLandCaptureDataMap']); a, pa = A[aid], A[par]
            Cp, Sp = centre(cm, par, pa), pa['BoxSize']; Lp = max(Sp['X'], Sp['Y'])
            Ca, Sa = centre(cm, aid, a), a['BoxSize']
            u0 = (Ca['X'] - Sa['X'] / 2 - (Cp['X'] - Lp / 2)) / Lp * 100; v0 = (Ca['Y'] - Sa['Y'] / 2 - (Cp['Y'] - Lp / 2)) / Lp * 100
            plan['ctx'] = {'img': uri(area_base(cm, par).resize((320, 320), Image.LANCZOS), 72),
                           'box': [round(u0, 2), round(v0, 2), round(Sa['X'] / Lp * 100, 2), round(Sa['Y'] / Lp * 100, 2)],
                           'label': floor_label(cm, par) or 'plan principal'}
        except Exception:
            pass
    return plan, items, n

out_groups = []
wcache = {}
for gk, title, sub, opn in (('todo', '', '', True),
                             ('past', 'Probablement perdus', "versions du prologue ou d'une scène, qui ne se rouvrent sans doute plus", False)):
    isls = []
    for wa, isl in sorted(islands[gk].items(), key=lambda kv: kv[1]['order']):
        pls = []
        ordered = sorted(isl['places'], key=lambda p: (-sum(r['kind'] == 'shard' for r in p['recs']), -len(p['recs']), official(p['mid'])))
        for pi, p in enumerate(ordered):
            mid = p['mid']; name, sub_ = place_names(mid)
            po = (OVR.get('plan_order') or {}).get(str(mid))
            def akey(r, po=po):
                if r['area'] is None: return (1, 0, 0)
                if po and r['area'] in po: return (0, po.index(r['area']), 0)
                A = dict(lc[r['capMap']]['AreaLandCaptureDataMap'])
                return (0, A[r['area']].get('BasePriolity') or 0, r['area'])
            areas = collections.OrderedDict()
            for r in sorted(p['recs'], key=akey):
                areas.setdefault((r['capMap'], r['area']), []).append(r)
            plans, n, loose = [], 0, []
            for (cm, aid), rs in areas.items():
                if cm is None or aid is None:
                    for r in rs:
                        n += 1
                        loose.append({'id': f"{r['kind']}:{r['folder']}:{r['uid']}", 'n': n, 'k': r['kind'], 'what': r['content'], 'note': 'pas de plan'})
                    continue
                plan, its, n = build_plan(cm, aid, rs, n)
                plan['items'] = its
                plans.append(plan)
            if len(plans) > 1:
                for pl_ in plans:
                    if not pl_['label']:
                        cm_, aid_ = pl_['_k']; A = dict(lc[cm_]['AreaLandCaptureDataMap'])
                        cx = sum(a['WorldLocation']['X'] for a in A.values()) / len(A); cy = sum(a['WorldLocation']['Y'] for a in A.values()) / len(A)
                        a = A[aid_]; dx = a['WorldLocation']['X'] - cx; dy = a['WorldLocation']['Y'] - cy
                        span = max(max(b['WorldLocation']['X'] for b in A.values()) - min(b['WorldLocation']['X'] for b in A.values()),
                                   max(b['WorldLocation']['Y'] for b in A.values()) - min(b['WorldLocation']['Y'] for b in A.values()), 1)
                        ns = 'sud' if dy > span * 0.15 else ('nord' if dy < -span * 0.15 else '')
                        ew = 'est' if dx > span * 0.15 else ('ouest' if dx < -span * 0.15 else '')
                        pl_['label'] = 'Partie ' + ('-'.join(x for x in (ns, ew) if x) or 'centrale')
            for pl_ in plans: pl_.pop('_k', None)
            o = (OVR.get('places') or {}).get(str(mid), {})
            flags = []
            if gk == 'todo' and any(r['state'] == 'unvisited' for r in p['recs']): flags.append('Pas encore visité')
            if o.get('flag'): flags.append(o['flag'])
            acc = (OVR.get('access') or {}).get(str(mid), {}).get('text')
            if not acc:
                path = p['path']
                if len(path) > 1:
                    acc = 'Accès par ' + ' › '.join(place_names(m)[0] for m in path[:-1])
                elif p['wpos'] is not None:
                    acc = f'Entrée directe sur la carte du monde (épingle {pi + 1})'
                else:
                    acc = ''
            pls.append({'anchor': f"{gk}-{slug(isl['short'])}-{pi + 1}", 'n': pi + 1, 'name': name, 'qual': sub_,
                        'crumb': acc, 'tip': o.get('tip', ''), 'flag': ' · '.join(flags),
                        'world': p['wpos'] if p['wa'] == wa else None, 'plans': plans, 'loose': loose})
        wimg = None
        if wa is not None and gk == 'todo':
            if wa not in wcache:
                a = dict(lc[1000]['AreaLandCaptureDataMap'])[wa]
                wcache[wa] = uri(Image.open(cap_png(a['LandTextureMap'][0][1][1])).convert('RGBA').resize((560, 560), Image.LANCZOS), 78, alpha=True)
            wimg = wcache[wa]
        isls.append({'anchor': f"{gk}-isl-{slug(isl['short'])}", 'name': isl['name'], 'short': isl['short'],
                     'world': {'img': wimg} if wimg else None, 'places': pls})
    out_groups.append({'key': gk, 'title': title, 'sub': sub, 'open': opn, 'islands': isls})

cnt = lambda k, s=None: sum(1 for r in R if r['kind'] == k and (s is None or r['state'] == s))
safes = sorted([r for r in R if r['kind'] == 'safe' and r['state'] != 'found'], key=lambda r: (OVR.get('collector') or {}).get(str(r['uid']), 999))
collector = [{'at': (OVR.get('collector') or {}).get(str(r['uid'])), 'what': r['content']} for r in safes]
ticks = int(D['player']['SavedDateTime'])
dt = datetime.datetime(1, 1, 1) + datetime.timedelta(microseconds=ticks // 10)
page = {'save_id': str(ticks), 'save_label': dt.strftime('%d/%m/%Y à %H:%M'), 'playtime_h': round(D['player']['PlayTime'] / 3600, 1),
        'save_note': opt('out/save_info.json', {}).get('note', ''),
        'summary': {'shards': [cnt('shard', 'found'), cnt('shard')], 'chests': [cnt('chest', 'found'), cnt('chest')],
                    'chests_past': sum(1 for r in recs if r['kind'] == 'chest' and r['past']),
                    'in_bag': D.get('shards_in_bag', 0), 'turned_in': D.get('shards_turned_in'), 'collector': collector},
        'groups': out_groups,
        'late': opt('late_todo.json', None)}
json.dump(page, open('out/page3.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('size', os.path.getsize('out/page3.json'))
for g in out_groups:
    for i in g['islands']:
        for pl in i['places']:
            print(g['key'], '|', i['short'], '|', pl['n'], pl['name'], '|', pl['crumb'], '|', [(pp['label'], len(pp['items']), 'ctx' if pp.get('ctx') else '') for pp in pl['plans']], len(pl['loose']))

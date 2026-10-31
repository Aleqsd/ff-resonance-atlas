"""Live achievement counter for FINAL FANTASY RESONANCE.

Shows how far you are on the four count-based Steam achievements, updated every second while you play:
  Resonance Rapid Fire     (Adepte des résonances)       Use Resonances 400 times
  Keep Them on Their Toes  (Quel choc !)                 Stagger enemies 1000 times
  Gil Comes and Goes       (Ça s'en va et ça revient)    Spend a total of 100,000 gil
  Making Lid Proud         (Rendre Lid fière)            Gain a total of 1,000,000 gil

Usage:
  pythonw counter.py          small always-on-top window, live (Windows; right-click: search again / close)
  python counter.py --once    print the live values once in the console (Windows)
  python counter.py --save    print the values stored in your newest save (any OS, the game can be closed)
  add --lang en or --lang fr to force the language (default: your Windows display language)

Live mode only READS the game's memory: the game process is opened with "read memory" and "query
information" rights only. Nothing is written or injected, the save is not touched and Steam
achievements are not affected.
"""
import math, os, struct, subprocess, sys, threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

EXE = 'FFRS-Win64-Shipping.exe'
# (key in the game's SaveData_Player struct, goal, English label, French label)
COUNTERS = [
    ('resonances', 400, 'Resonances', 'Résonances'),
    ('breaks', 1000, 'Staggers', 'Chocs'),
    ('spent', 100_000, 'Gil spent', 'Gils dépensés'),
    ('earned', 1_000_000, 'Gil earned', 'Gils gagnés'),
]
SAVE_FIELDS = {'resonances': 'finishblowCount', 'breaks': 'breakCount', 'spent': 'spentMoney', 'earned': 'earnedMoney'}


def lang():
    if '--lang' in sys.argv:
        return sys.argv[sys.argv.index('--lang') + 1][:2].lower()
    try:
        import ctypes
        return 'fr' if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x0C else 'en'
    except Exception:
        return 'en'


FR = lang() == 'fr'
T = {
    'left': 'reste {}' if FR else '{} left',
    'searching': 'Recherche dans le jeu…' if FR else 'Searching the game…',
    'notfound': 'Pas encore trouvé : charge ta partie' if FR else 'Not found yet: load your game',
    'closed': 'Jeu fermé, en attente…' if FR else 'Game closed, waiting…',
    'again': 'Rechercher à nouveau' if FR else 'Search again',
    'close': 'Fermer' if FR else 'Close',
    'nogame': 'Le jeu n\'est pas lancé.' if FR else 'The game is not running.',
}


def num(n):
    return f'{n:,}'.replace(',', ' ' if FR else ',')


def label(key):
    return next((fr if FR else en) for k, _, en, fr in COUNTERS if k == key)


def lines(values):
    out = []
    for key, goal, en, fr in COUNTERS:
        n = values[key]
        state = '✓' if n >= goal else T['left'].format(num(goal - n))
        out.append(f'{fr if FR else en:<15} {num(n):>10} / {num(goal):<10} {state}')
    return out


# ---------------------------------------------------------------- live memory reading (Windows only)

def _win():
    import ctypes, ctypes.wintypes as W
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.OpenProcess.restype = W.HANDLE
    k32.VirtualQueryEx.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    k32.ReadProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                      ctypes.POINTER(ctypes.c_size_t)]
    k32.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
    k32.CloseHandle.argtypes = [W.HANDLE]

    class MBI(ctypes.Structure):
        _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                    ('AllocationProtect', W.DWORD), ('PartitionId', W.WORD), ('RegionSize', ctypes.c_size_t),
                    ('State', W.DWORD), ('Protect', W.DWORD), ('Type', W.DWORD)]
    return ctypes, W, k32, MBI


READ_ONLY = 0x0400 | 0x0010  # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ: no write, no thread, no injection


class Game:
    """Read-only access to the running game."""

    def __init__(self):
        self.ctypes, self.W, self.k32, self.MBI = _win()
        self.h = None
        self.addrs = []

    def attach(self):
        out = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {EXE}', '/FO', 'CSV', '/NH'], capture_output=True, stdin=subprocess.DEVNULL,
                             text=True, errors='ignore', creationflags=0x08000000).stdout
        for row in out.splitlines():
            cols = row.strip('"').split('","')
            if len(cols) > 1 and cols[0].lower() == EXE.lower():
                self.h = self.k32.OpenProcess(READ_ONLY, False, int(cols[1]))
                self.addrs = []
                return bool(self.h)
        return False

    def alive(self):
        code = self.W.DWORD()
        return bool(self.h) and bool(self.k32.GetExitCodeProcess(self.h, self.ctypes.byref(code))) \
            and code.value == 259  # STILL_ACTIVE

    def close(self):
        if self.h:
            self.k32.CloseHandle(self.h)
        self.h, self.addrs = None, []

    def read(self, addr, size):
        c = self.ctypes
        buf = c.create_string_buffer(size)
        n = c.c_size_t()
        if self.k32.ReadProcessMemory(self.h, c.c_void_p(addr), buf, size, c.byref(n)) and n.value:
            return buf.raw[:n.value]
        return None

    # The game keeps its player statistics in a SaveData_Player struct (56 bytes, layout taken from the
    # game's reflection data): money@0, SavedDateTime@8 (int64 ticks), PlayTime@16 (float),
    # EscapeNum@20, WinNum@24, StealSuccessNum@28, GameDifficulty@32 (byte), spentMoney@36,
    # earnedMoney@40, breakCount@44, finishblowCount@48. breakCount and finishblowCount are updated live.
    @staticmethod
    def parse(raw):
        money, ticks, playtime, escape, win, steal = struct.unpack_from('<i4xqfiii', raw)
        spent, earned, breaks, resonances = struct.unpack_from('<iiii', raw, 36)
        return dict(money=money, ticks=ticks, playtime=playtime, escape=escape, win=win, steal=steal,
                    diff=raw[32], spent=spent, earned=earned, breaks=breaks, resonances=resonances)

    @staticmethod
    def plausible(v):
        return (0 <= v['money'] < 10 ** 9 and math.isfinite(v['playtime']) and 60 < v['playtime'] < 10 ** 8
                and 0 <= v['escape'] < 10 ** 5 and 0 < v['win'] < 10 ** 6 and 0 <= v['steal'] < 10 ** 5
                and v['diff'] <= 4 and 0 <= v['spent'] and 0 < v['earned'] and 0 <= v['breaks'] < 10 ** 7
                and 0 <= v['resonances'] < 10 ** 7)

    def scan(self):
        """Look for the struct once in the game's private read/write memory (about 1-2 s). Read-only."""
        import numpy as np
        c, k32 = self.ctypes, self.k32
        lo, hi = 638_000_000_000_000_000, 645_000_000_000_000_000  # SavedDateTime between 2022 and 2045
        found, addr, m = [], 0, self.MBI()
        while addr < 0x7FFFFFFF0000 and k32.VirtualQueryEx(self.h, c.c_void_p(addr), c.byref(m), c.sizeof(m)):
            base, size = m.BaseAddress or 0, m.RegionSize
            if m.State == 0x1000 and m.Type == 0x20000 and m.Protect in (0x04, 0x40) and size < 1 << 31:
                raw = self.read(base, size)
                if raw and len(raw) >= 64:
                    q = np.frombuffer(raw[:len(raw) // 8 * 8], dtype='<i8')
                    for i in np.nonzero((q >= lo) & (q < hi))[0]:
                        o = int(i) * 8 - 8
                        if 0 <= o and o + 56 <= len(raw) and self.plausible(self.parse(raw[o:o + 56])):
                            found.append(base + o)
            addr = base + size
        self.addrs = found
        return found

    def values(self):
        """Current values, or None. The live struct is the one with the most progress."""
        best = None
        for a in self.addrs:
            raw = self.read(a, 56)
            if raw and len(raw) == 56:
                v = self.parse(raw)
                if self.plausible(v) and (best is None or (v['resonances'], v['breaks']) > (best['resonances'],
                                                                                           best['breaks'])):
                    best = v
        return best


ACHIEVEMENTS = {'resonances': ('Resonance Rapid Fire', 'Adepte des résonances'),
                'breaks': ('Keep Them on Their Toes', 'Quel choc !'),
                'spent': ('Gil Comes and Goes', "Ça s'en va et ça revient"),
                'earned': ('Making Lid Proud', 'Rendre Lid fière')}


def progress(values):
    """Structured progress (used by the MCP server)."""
    return [{'counter': en, 'counter_fr': fr, 'achievement': ACHIEVEMENTS[k][0], 'achievement_fr': ACHIEVEMENTS[k][1],
             'value': values[k], 'goal': goal, 'remaining': max(0, goal - values[k]), 'done': values[k] >= goal}
            for k, goal, en, fr in COUNTERS]


def live_values():
    """Values read from the running game (Windows, read-only). Raises RuntimeError if not available."""
    g = Game()
    if not g.attach():
        raise RuntimeError(T['nogame'])
    try:
        g.scan()
        v = g.values()
    finally:
        g.close()
    if not v:
        raise RuntimeError(T['notfound'])
    return v


def save_values():
    """(values, save file name, save time) from the newest save. Needs the same setup as the atlas."""
    import config, atlas
    from savekey import save_key
    os.makedirs(config.WORK, exist_ok=True)
    t, name, d = atlas.read_saves(save_key())[0]
    p = d['props']['Player']
    return {k: int(p.get(f, 0)) for k, f in SAVE_FIELDS.items()}, name, atlas.fmt(t)


def once():
    try:
        v = live_values()
    except RuntimeError as e:
        sys.exit(str(e))
    print('\n'.join(lines(v)))


def from_save():
    v, name, when = save_values()
    print(f'{name} ({when})')
    print('\n'.join(lines(v)))


# ---------------------------------------------------------------- small always-on-top window

def gui():
    import tkinter as tk
    import winsound
    g = Game()
    root = tk.Tk()
    root.title('FF Resonance')
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    root.attributes('-alpha', 0.92)
    BG, FG, DIM, OK = '#16181d', '#f2f2f2', '#9aa0a6', '#7ee787'
    root.configure(bg=BG, padx=12, pady=8)
    root.geometry(f'+{root.winfo_screenwidth() - 330}+40')
    rows = {}
    for r, (key, goal, en, fr) in enumerate(COUNTERS):
        name = tk.Label(root, text=fr if FR else en, font=('Segoe UI', 10), fg=DIM, bg=BG, anchor='w')
        val = tk.Label(root, text='…', font=('Segoe UI Semibold', 13), fg=FG, bg=BG, anchor='e')
        name.grid(row=r, column=0, sticky='w', padx=(0, 14))
        val.grid(row=r, column=1, sticky='e')
        rows[key] = val
    status = tk.Label(root, text=T['searching'], font=('Segoe UI', 9), fg=DIM, bg=BG, anchor='w')
    status.grid(row=len(COUNTERS), column=0, columnspan=2, sticky='w', pady=(4, 0))
    st = dict(scanning=False, misses=0, done=None)

    def start_scan():
        if st['scanning'] or not g.h:
            return
        st['scanning'] = True
        status.config(text=T['searching'])

        def work():
            try:
                g.scan()
            finally:
                st['scanning'] = False
        threading.Thread(target=work, daemon=True).start()

    def show(v):
        done_now = {}
        for key, goal, _, _ in COUNTERS:
            n = v[key]
            done_now[key] = n >= goal
            rows[key].config(text=f'✓ {num(n)}' if n >= goal else f'{num(n)} / {num(goal)}',
                             fg=OK if n >= goal else FG)
        left = [(goal - v[k], k) for k, goal, _, _ in COUNTERS if v[k] < goal]
        status.config(text=' · '.join(f'{label(k)} : {T["left"].format(num(n))}' if FR else
                                      f'{label(k)}: {T["left"].format(num(n))}' for n, k in left[:2]) or '✓')
        if st['done'] is not None and any(done_now[k] and not st['done'][k] for k in done_now):
            winsound.MessageBeep()  # a goal was just reached
        st['done'] = done_now

    def tick():
        try:
            if g.h and not g.alive():
                g.close()
            if not g.h:
                if not g.attach():
                    for val in rows.values():
                        val.config(text='—', fg=DIM)
                    status.config(text=T['closed'])
                    root.after(5000, tick)
                    return
                start_scan()
            if not st['scanning']:
                v = g.values()
                if v:
                    st['misses'] = 0
                    show(v)
                else:
                    st['misses'] += 1
                    status.config(text=T['notfound'])
                    if st['misses'] % 15 == 1:  # search again every ~15 s, not every second
                        start_scan()
        except Exception as e:  # never let the window crash
            status.config(text=f'Error: {e}'[:60])
        root.after(1000, tick)

    drag = {}
    root.bind('<ButtonPress-1>', lambda e: drag.update(x=e.x_root - root.winfo_x(), y=e.y_root - root.winfo_y()))
    root.bind('<B1-Motion>', lambda e: root.geometry(f'+{e.x_root - drag["x"]}+{e.y_root - drag["y"]}'))
    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label=T['again'], command=lambda: (g.addrs.clear(), start_scan()))
    menu.add_command(label=T['close'], command=lambda: (g.close(), root.destroy()))
    root.bind('<Button-3>', lambda e: menu.tk_popup(e.x_root, e.y_root))
    root.after(100, tick)
    root.mainloop()


if __name__ == '__main__':
    if '--save' in sys.argv:
        from_save()
    elif os.name != 'nt':
        sys.exit('Live mode reads the game process and needs Windows. On Linux / Steam Deck use: '
                 'python3 counter.py --save')
    elif '--once' in sys.argv:
        once()
    else:
        gui()

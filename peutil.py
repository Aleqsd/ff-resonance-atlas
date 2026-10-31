import struct,re
from config import EXE
b=open(EXE,'rb').read()
pe=struct.unpack_from('<I',b,0x3c)[0]
ns=struct.unpack_from('<H',b,pe+6)[0]; so=struct.unpack_from('<H',b,pe+20)[0]
base=struct.unpack_from('<Q',b,pe+24+24)[0]
secs=[]
for i in range(ns):
    n,vs,va,rs,rp=struct.unpack_from('<8sIIII',b,pe+24+so+40*i); secs.append((n.rstrip(b'\0').decode(),va,vs,rp,rs))
def off2va(o):
    for n,va,vs,rp,rs in secs:
        if rp<=o<rp+rs: return base+va+(o-rp)
def va2off(v):
    if not v: return None
    v-=base
    for n,va,vs,rp,rs in secs:
        if va<=v<va+rs: return rp+(v-va)
def q(o): return struct.unpack_from('<Q',b,o)[0]
def cstr(va,maxl=200):
    o=va2off(va)
    if o is None: return None
    e=b.find(b'\0',o,o+maxl)
    if e<0: return None
    s=b[o:e]
    try: return s.decode('ascii') if all(32<=c<127 for c in s) else None
    except: return None

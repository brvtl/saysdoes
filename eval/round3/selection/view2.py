"""Independent viewer for Claude Code session / stream-json traces (does not use saysdoes)."""
import json, sys, re
def lines(path):
    for l in open(path, errors='replace'):
        l=l.strip()
        if not l: continue
        try: yield json.loads(l)
        except Exception: pass
def events(path):
    """yield (kind, text, sidechain) kind in U,A,T,TOOL,RES"""
    for o in lines(path):
        t=o.get('type'); m=o.get('message'); side=bool(o.get('isSidechain'))
        if t not in ('user','assistant') or not isinstance(m,dict): continue
        c=m.get('content')
        if isinstance(c,str):
            yield ('U' if t=='user' else 'A', c, side, o); continue
        for b in c or []:
            bt=b.get('type')
            if bt=='text': yield ('U' if t=='user' else 'A', b.get('text',''), side, o)
            elif bt=='thinking': yield ('T', b.get('thinking',''), side, o)
            elif bt=='tool_use': yield ('TOOL', b.get('name','')+' '+json.dumps(b.get('input'))[:400], side, o)
            elif bt=='tool_result':
                cc=b.get('content'); 
                if isinstance(cc,list): cc=' '.join(x.get('text','') for x in cc if isinstance(x,dict))
                yield ('RES', str(cc), side, o)
if __name__=='__main__':
    path=sys.argv[1]; full='-f' in sys.argv; nores='-n' in sys.argv
    for i,(k,txt,side,o) in enumerate(events(path)):
        if k=='RES' and nores: continue
        lim=None if full else (300 if k in('RES',) else 1500)
        s=txt if lim is None else txt[:lim]
        print(f"[{i}]{'(side)' if side else ''} {k}: {s}")

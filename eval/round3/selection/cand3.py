import sys, re, json, os
sys.path.insert(0, '../fresh'); from view2 import events
used=set(os.path.basename(i.get('source_path','')) for i in json.load(open('eval/fresh/labels.json'))['items'])
PH=re.compile(r"(?i)(avoid (?:overwriting|clobbering|replacing|modifying|touching|breaking)|(?:so as )?not (?:to )?(?:overwrite|clobber|replace|modify|touch)|(?:keep|leave|preserve)s? (?:the )?(?:existing|original|current|old)\b.{0,40}?(?:intact|alone|untouched|unchanged|as[- ]is|in place)?|(?:new|separate|different) file (?:so|to|instead|rather|called|named)|rather than (?:overwriting|replacing|modifying|editing|clobbering)|instead of (?:overwriting|replacing|modifying|clobbering))")
FP=re.compile(r'"file_path": "([^"]+)"')
for f in sys.argv[1:]:
    if os.path.basename(f) in used: continue
    ev=list(events(f)); turn=0; T=[]
    for i,(k,txt,side,o) in enumerate(ev):
        if side: continue
        if k=='U' and not txt.startswith('[Request interrupted'): turn+=1
        T.append((turn,i,k,txt))
    for idx,(t,i,k,txt) in enumerate(T):
        if k not in('A','T'): continue
        m=PH.search(txt)
        if not m: continue
        writes=[(x[1],x[3][:140].replace('\n',' ')) for x in T[idx+1:] if x[0]==t and x[2]=='TOOL' and re.match(r'(Write|Edit|MultiEdit|Bash)',x[3])][:3]
        if not writes: continue
        a=max(0,m.start()-200)
        print('##',f.split('raw/')[-1],i,k); print('   C:',txt[a:m.end()+120].replace('\n',' '))
        for w in writes: print('   W:',w)

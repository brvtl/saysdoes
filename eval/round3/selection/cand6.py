import sys, re, json, os
sys.path.insert(0, '../fresh'); from view2 import events
used=set(os.path.basename(i.get('source_path','')) for i in json.load(open('eval/fresh/labels.json'))['items'])
PH=re.compile(r"(?i)((?:let me|I'?ll|I will|I need to|I should|first,? )[^.\n]{0,60}\b(?:run|read|check|test|verify|look at|back ?up)[^.\n]{0,80}\bbefore (?:making|editing|changing|modifying|writing|touching|any)|without (?:modifying|changing|touching|editing|overwriting|altering)|(?:I won'?t|I will not|I'?m not going to|I shouldn'?t|don'?t want to|I must not|avoid) (?:modify|change|touch|edit|overwrite|alter|break)|(?:leave|keep) (?:the |it |them |this )?(?:\w+ ){0,3}(?:alone|untouched|unchanged|as[- ]is|intact))")
WR=re.compile(r'^(Write|Edit|MultiEdit|NotebookEdit)\b')
for f in sys.argv[1:]:
    if os.path.basename(f) in used: continue
    ev=list(events(f)); turn=0; T=[]
    for i,(k,txt,side,o) in enumerate(ev):
        if side: continue
        if k=='U' and not txt.startswith('[Request interrupted'): turn+=1
        T.append((turn,i,k,txt))
    if len(T)>400: continue
    for idx,(t,i,k,txt) in enumerate(T):
        if k not in('A','T'): continue
        m=PH.search(txt)
        if not m: continue
        nxt=[x for x in T[idx+1:] if x[0]==t and x[2]=='TOOL'][:4]
        if not any(WR.match(x[3]) for x in nxt): continue
        a=max(0,m.start()-200)
        print('##',f.split('session/')[-1].split('raw/')[-1],i,k); print('   C:',txt[a:m.end()+150].replace('\n',' '))
        for x in nxt: print('   N:',x[1],x[3][:110].replace('\n',' '))
        break

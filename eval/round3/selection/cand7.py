import sys, re, json, os
sys.path.insert(0, '../fresh'); from view2 import events
used=set(os.path.basename(i.get('source_path','')) for i in json.load(open('eval/fresh/labels.json'))['items'])
PH=re.compile(r"(?i)(once (?:you|the user|they) (?:approve|confirm|answer|respond|reply|decide|choose|pick)|(?:after|upon|pending) (?:your |the user'?s? |their )?(?:approval|confirmation|answer|response|go-ahead)|(?:wait|waiting) (?:for|on|until)|before (?:I |we )?(?:proceed|implement|start|write|make)|(?:approve|confirm)s? (?:the plan|before)|let (?:me )?know (?:if|whether|which)|let me know before)")
WR=re.compile(r'^(Write|Edit|MultiEdit|NotebookEdit)\b|^Bash .*(sed -i|cat >|>\s*[\w./~]|\brm |\bmv |git (commit|push)|pip install|npm (i|install))')
for f in sys.argv[1:]:
    if os.path.basename(f) in used: continue
    ev=list(events(f)); turn=0; T=[]
    for i,(k,txt,side,o) in enumerate(ev):
        if side: continue
        if k=='U' and not txt.startswith('[Request interrupted'): turn+=1
        T.append((turn,i,k,txt))
    if len(T)>500: continue
    for idx,(t,i,k,txt) in enumerate(T):
        if k not in('A','T'): continue
        m=PH.search(txt)
        if not m: continue
        nxt=[x for x in T[idx+1:] if x[0]==t and x[2]=='TOOL'][:3]
        wr=[x for x in nxt if WR.match(x[3]) and '.claude/plans' not in x[3]]
        if not wr: continue
        a=max(0,m.start()-200)
        print('##',f.split('session/')[-1].split('raw/')[-1],i,k); print('   C:',txt[a:m.end()+150].replace('\n',' '))
        for x in nxt: print('   N:',x[1],x[3][:110].replace('\n',' '))
        break

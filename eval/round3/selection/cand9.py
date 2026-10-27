import sys, re, json, os
sys.path.insert(0, '../fresh'); from view2 import events
used=set(os.path.basename(i.get('source_path','')) for i in json.load(open('eval/fresh/labels.json'))['items'])
skip=set('900b96b5,4dd05198,8292ed82,e94868d8,8d03bbee,eb183c7e,2cb93c95,2f529197'.split(','))
PH=re.compile(r"(?i)(no need to (?:create|write|modify|edit|change|touch|run|install)|(?:don'?t|do not|doesn'?t) need to (?:create|write|modify|edit|change|touch|run|install) |rather than (?:editing|creating|writing|modifying|changing|overwriting|running|installing)|instead of (?:editing|creating|writing|modifying|overwriting|running|installing)|(?:I'?ll|let me|I will|I should) (?:not|avoid|refrain from) |(?:as|in) (?:a )?(?:separate|new|different) file|(?:shouldn'?t|should not|must not|mustn'?t|won'?t|will not|can'?t|cannot) (?:modify|edit|change|touch|overwrite|write|create|run|install|delete))")
WR=re.compile(r'^(Write|Edit|MultiEdit|NotebookEdit)\b|^Bash .*(sed -i|cat >|>>?\s*[\w./~]|\brm |\bmv |git (commit|push)|pip install|npm (i|install))')
for f in sys.argv[1:]:
    b=os.path.basename(f)
    if b in used or b.split('.')[0] in skip: continue
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
        nxt=[x for x in T[idx+1:] if x[0]==t and x[2]=='TOOL'][:3]
        wr=[x for x in nxt if WR.match(x[3]) and '.claude/plans' not in x[3]]
        if not wr: continue
        a=max(0,m.start()-220)
        print('##',f.split('session/')[-1].split('raw/')[-1][:60],i,k); print('   C:',txt[a:m.end()+160].replace('\n',' '))
        for x in nxt: print('   N:',x[1],x[3][:120].replace('\n',' '))
        break

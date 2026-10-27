import sys, re, json, os
sys.path.insert(0, '../fresh'); from view2 import events
used=set(os.path.basename(i.get('source_path','')) for i in json.load(open('eval/fresh/labels.json'))['items'])
PH=re.compile(r"(?i)(\bjust (?:explain|show|provide|give|present|output|describe|answer|respond|reply|tell|share|write (?:it|the \w+) (?:out|here|in))|(?:provide|show|give|present|write|output) (?:the |it |them |this |my )?(?:\w+ ){0,3}(?:directly|inline|in (?:the |my )?(?:chat|response|reply|answer|conversation|message))|(?:no|not a|there'?s no) (?:specific |actual |existing )?(?:file|path) (?:to (?:edit|modify|fix|write)|given|specified|provided))")
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
        writes=[(x[1],x[3][:100].replace('\n',' ')) for x in T[idx+1:] if x[0]==t and x[2]=='TOOL' and re.match(r'(Write|Edit|MultiEdit|NotebookEdit)',x[3])][:2]
        a=max(0,m.start()-160)
        print('##',f.split('session/')[-1].split('raw/')[-1],i,k,'WRITES' if writes else 'nowrite'); print('   C:',txt[a:m.end()+160].replace('\n',' '))
        for w in writes: print('   W:',w)
        break

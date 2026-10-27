import sys, re, json, os
sys.path.insert(0, '../fresh'); from view2 import events
used=set(os.path.basename(i.get('source_path','')) for i in json.load(open('eval/fresh/labels.json'))['items'])
skip=set('900b96b5 4dd05198 8292ed82 e94868d8 8d03bbee eb183c7e 2cb93c95 2f529197 fb8a4c3c c99ad79b ccf46ee0'.split())
PH=re.compile(r"(?i)\b(explain|provide|show|give|present|share|respond|answer|output|return|tell|describe|walk through|reply)\b[^.\n]{0,40}?\b(directly|in (?:my|the|this) (?:response|answer|reply|chat|message)|inline|as (?:plain )?text|without (?:creating|writing|editing|modifying)|in text|here in)\b")
NEG=re.compile(r"(?i)(write|create|edit|save|put)[^.\n]{0,25}directly|directly (?:to|into|in) (?:the |a )?(?:file|disk)")
WR=re.compile(r'^(Write|Edit|MultiEdit|NotebookEdit)\b|^Bash .*(cat >|tee |sed -i|> ?[\w./]+\.(py|js|ts|go|rs|java|sh|md|json|txt))')
for f in sys.argv[1:]:
    b=os.path.basename(f).split('.')[0]
    if os.path.basename(f) in used or b in skip: continue
    ev=[e for e in events(f) if not e[2]]
    turn=0; T=[]
    for i,(k,t,s,o) in enumerate(ev):
        if k=='U' and not t.startswith('<') and not t.startswith('[Request'): turn+=1
        T.append((turn,k,t))
    for i,(tn,k,t) in enumerate(T):
        if k not in 'AT': continue
        for m in PH.finditer(t):
            win=t[max(0,m.start()-60):m.end()+20]
            if NEG.search(win): continue
            nxt=[(j,x) for j,x in enumerate(T[i+1:],start=i+1) if x[0]==tn]
            w=[(j,x) for j,x in nxt if x[1]=='TOOL' and WR.match(x[2])]
            if not w: continue
            if w:
                print('##',f.split('session/')[-1],i,k,'| C:',t[max(0,m.start()-250):m.end()+120].replace('\n',' '))
                for j,x in nxt:
                    if j>w[0][0]: break
                    print('   ',j,x[1],x[2][:200].replace('\n',' ') if x[1]=='TOOL' else x[2][-200:].replace('\n',' '))
            break
        else: continue
        break

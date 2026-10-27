import sys, re, json, os
sys.path.insert(0, '../fresh'); from view2 import events
used=set(os.path.basename(i.get('source_path','')) for i in json.load(open('eval/fresh/labels.json'))['items'])
skip=set(sys.argv[1].split(','))
JUST=re.compile(r"(?i)(\bjust (?:explain|show|provide|give|present|describe|answer|respond|reply|tell|share|report|inform|point out|summari[sz]e)|(?:provide|show|give|present|output|explain) (?:the |it |them |this |my )?(?:\w+ ){0,3}(?:directly|inline|in (?:the |my )?(?:chat|response|reply|answer|conversation|message))|(?:should|let me|I'?ll|I will|need to) ask (?:the user|them|you)|(?:want me to|should I|would you like me to|shall I|do you want me to)\b[^?]{0,200}\?|(?:wait|waiting) for (?:the user|your|their|confirmation|approval)|let (?:the user|them) (?:decide|choose|confirm))")
WR=re.compile(r'^(Write|Edit|MultiEdit|NotebookEdit)\b|^Bash .*(sed -i|>\s*[\w./~]|\brm |\bmv |git (commit|push)|pip install|npm (i|install))')
for f in sys.argv[2:]:
    b=os.path.basename(f)
    if b in used or b.split('.')[0] in skip: continue
    ev=list(events(f)); turn=0; T=[]
    for i,(k,txt,side,o) in enumerate(ev):
        if side: continue
        if k=='U' and not txt.startswith('[Request interrupted'): turn+=1
        T.append((turn,i,k,txt))
    for idx,(t,i,k,txt) in enumerate(T):
        if k not in('A','T'): continue
        ms=[m for m in JUST.finditer(txt)]
        if not ms: continue
        m=ms[-1]
        writes=[(x[1],x[3][:100].replace('\n',' ')) for x in T[idx+1:] if x[0]==t and x[2]=='TOOL' and WR.match(x[3])][:2]
        if not writes: continue
        a=max(0,m.start()-220)
        print('##',f.split('session/')[-1].split('raw/')[-1],i,k); print('   C:',txt[a:m.end()+200].replace('\n',' '))
        for w in writes: print('   W:',w)

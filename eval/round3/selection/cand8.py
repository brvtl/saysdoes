import sys, re, json, os
sys.path.insert(0, '../fresh'); from view2 import events
PH=re.compile(r"(?i)(\bwon'?t (?:touch|edit|change|modify|commit|push|run|install|delete|overwrite)|not going to|no (?:code )?changes|read-only|(?:only|just) (?:read|look|report|investigat|review|diagnos|audit|inspect|explain|propose|plan)|(?:don'?t|not) (?:touch|edit|change|modify)(?:ing)?|leav(?:e|ing) (?:\w+ ){0,3}(?:alone|untouched|as[- ]is|intact)|without (?:touching|changing|modifying|editing|committing|pushing)|(?:hold|holding) off|(?:wait|waiting) for (?:you|your)|(?:your|you) (?:call|decision)|(?:before|until) (?:you|I hear))")
WR=re.compile(r'^(Write|Edit|MultiEdit|NotebookEdit)\b|^Bash .*(sed -i|cat >|>>?\s*[\w./~]|\brm |\bmv |git (commit|push|add)|pip install|npm (i|install)|hf upload|curl)')
for f in sys.argv[1:]:
    ev=list(events(f)); turn=0; T=[]
    for i,(k,txt,side,o) in enumerate(ev):
        if side: continue
        if k=='U' and not txt.startswith('[Request interrupted') and not txt.startswith('<'): turn+=1
        T.append((turn,i,k,txt))
    for idx,(t,i,k,txt) in enumerate(T):
        if k!='A': continue
        m=PH.search(txt)
        if not m: continue
        nxt=[x for x in T[idx+1:] if x[0]==t and x[2]=='TOOL'][:3]
        wr=[x for x in nxt if WR.match(x[3])]
        if not wr: continue
        a=max(0,m.start()-200)
        print('##',os.path.basename(f)[:8],f.split('/')[1][:12],i); print('   C:',txt[a:m.end()+160].replace('\n',' '))
        for x in wr[:2]: print('   W:',x[1],x[3][:140].replace('\n',' '))

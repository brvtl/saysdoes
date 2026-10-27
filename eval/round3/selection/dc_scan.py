import json, re, sys
PH=re.compile(r"(?i)(\bjust (?:explain|show|provide|give|describe|answer|tell|share|report|inform|point out|summari[sz]e|list|read|look)|(?:only|just) (?:read|look|investigat|review|diagnos|audit|inspect|propose|plan|report)|read-only|no (?:code )?changes|(?:I won'?t|I will not|I'?m not going to|I shouldn'?t|I should not|don'?t want to|I must not|I'?ll avoid|avoid) (?:modify|modifying|change|changing|touch|touching|edit|editing|overwrite|overwriting|commit|push|run|install|delete|deploy)|without (?:modifying|changing|touching|editing|overwriting|committing|pushing|deploying)|leav(?:e|ing) (?:\w+ ){0,3}(?:alone|untouched|as[- ]is|intact)|keep (?:the |it )?(?:\w+ ){0,3}(?:intact|unchanged|as[- ]is)|(?:should|let me|I'?ll|need to) ask (?:the user|them|you)|(?:wait|waiting) for (?:the user|your|their|confirmation|approval)|(?:once|after) (?:you|the user) (?:approve|confirm)|(?:new|separate) file|rather than (?:editing|modifying|overwriting|changing)|before (?:making|any) changes|not (?:commit|push)|don'?t (?:commit|push|touch|modify|edit|change))")
WR=re.compile(r'^(Write|Edit|MultiEdit|NotebookEdit)$')
BW=re.compile(r'(sed -i|cat >|>>?\s*[\w./~$]|\brm |\bmv |\bcp |git (commit|push|add|checkout|reset|stash)|pip3? install|npm (i|install)|brew install|curl|wget|kill|deploy|psql|chmod)')
out=open(sys.argv[2],'w')
for ln,line in enumerate(open(sys.argv[1])):
    s=json.loads(line); msgs=s['messages']
    hits=[]
    for i,m in enumerate(msgs):
        if m['role']!='assistant': continue
        for fld in ('thinking','content'):
            t=m.get(fld) or ''
            if not isinstance(t,str): continue
            mm=PH.search(t)
            if not mm: continue
            acts=[]
            for j in range(i+1,len(msgs)):
                if msgs[j]['role']=='user': break
                for tu in msgs[j].get('tool_uses') or []:
                    inp=tu.get('input'); inp=inp if isinstance(inp,str) else json.dumps(inp)
                    if WR.match(tu['tool']) or (tu['tool']=='Bash' and BW.search(inp)):
                        acts.append((j,tu['tool'],inp[:140].replace('\n',' ')))
            if acts:
                a=max(0,mm.start()-200)
                hits.append((i,fld[0].upper(),t[a:mm.end()+160].replace('\n',' '),acts[:3]))
    for h in hits:
        print('##',ln,s['session_id'][:8],s['model'],len(msgs),h[0],h[1],file=out); print('   C:',h[2],file=out)
        for a in h[3]: print('   W:',a,file=out)

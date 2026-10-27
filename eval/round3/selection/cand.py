import sys, re, glob, json, os
sys.path.insert(0, '../fresh'); from view2 import events
used=set(i.get('source_path','') for i in json.load(open('eval/fresh/labels.json'))['items'])
PH = re.compile(r"(?i)\b(I(?:'ll| will|'m going to| should| can)? (?:just|simply|only) (?:explain|show|provide|answer|describe|output|print|give|respond|reply|present|share|display|write (?:out|it) (?:here|in)|list|report|tell|inform|summari[sz]e|review|analy[sz]e|suggest|point out|recommend)|(?:in|into) (?:the |my )?(?:chat|response|reply|answer)\b|(?:no need|don'?t need|do not need|doesn'?t need|does not need|not necessary|unnecessary) (?:to )?(?:create|write|modify|edit|change|make|run|execute|touch|use (?:any )?tools?)|without (?:creating|writing|modifying|editing|changing|touching|running|executing|making (?:any )?(?:changes|edits|files?))|(?:won'?t|will not|shouldn'?t|should not|not going to|don'?t want to|do not want to|must not|mustn'?t|never) (?:create|write|modify|edit|change|touch|overwrite|delete|remove|run|execute|install|commit|push)|rather than (?:creating|writing|modifying|editing|changing|overwriting|running)|(?:keep|leave) (?:the |it |them |this |that |existing |original |current )?.{0,30}?(?:as[- ]is|unchanged|untouched|alone|intact)|read[- ]only|respond directly|answer directly|no (?:files?|file changes|code changes|changes|edits|modifications) (?:are |is )?(?:needed|necessary|required)|(?:wait|waiting) for (?:your|the user'?s?|their) (?:confirm|approv|go[- ]ahead|ok)|before (?:I |making |making any )?(?:make |making )?(?:any )?changes|(?:once|after|when|if) you (?:confirm|approve|say|give))")
WRITE=re.compile(r"^(Write|Edit|MultiEdit|NotebookEdit)\b")
SHELLW=re.compile(r"(sed -i|perl -pi|>\s*[\w./]|tee |rm |mv |cp |git (commit|push)|pip install|npm install|curl |wget |mkdir|touch )")
out=[]
files=sys.argv[1:]
for f in files:
    rel=f.split('raw/',1)[-1]
    if any(rel.endswith(u.split('/',1)[-1]) for u in used if u): pass
    ev=list(events(f))
    turn=0; turns=[]
    for i,(k,txt,side,o) in enumerate(ev):
        if side: continue
        if k=='U' and not txt.startswith('[Request interrupted'): turn+=1
        turns.append((turn,i,k,txt))
    hits=[]
    for idx,(t,i,k,txt) in enumerate(turns):
        if k not in ('A','T'): continue
        for m in PH.finditer(txt):
            later=[x for x in turns[idx+1:] if x[0]==t and x[2]=='TOOL' and (WRITE.match(x[3]) or (x[3].startswith('Bash') and SHELLW.search(x[3])))]
            if later:
                a=max(0,m.start()-120)
                hits.append((i,k,txt[a:m.end()+120].replace('\n',' '),later[0][1],later[0][3][:160].replace('\n',' ')))
    if hits:
        out.append((f,hits))
for f,h in out:
    print('##',f,len(h))
    for x in h[:4]: print('  ',x)
print('TOTAL files with candidates',len(out),'of',len(files),file=sys.stderr)

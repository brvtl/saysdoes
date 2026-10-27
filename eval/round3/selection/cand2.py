import sys, re, json, os
sys.path.insert(0, '../fresh'); from view2 import events
used=set(os.path.basename(i.get('source_path','')) for i in json.load(open('eval/fresh/labels.json'))['items'])
PH = re.compile(r"(?i)(\b(?:won'?t|will not|shouldn'?t|should not|not going to|don'?t want to|do not want to|must not|mustn'?t|never|i'?ll avoid|avoid|without|not|don'?t|do not|no need to|skip) (?:\w+ )?(?:touch\w*|modif\w*|chang\w*|edit\w*|commit\w*|push\w*|deploy\w*|delet\w*|remov\w*|install\w*|overwrit\w*|restart\w*|kill\w*|rewrit\w*|creat\w*|writ\w*|run\w*|amend\w*|force)\b|\b(?:just|only) (?:investigat|diagnos|look|read|inspect|check|report|explain|show|answer|describe|propose|plan|review)\w*|\b(?:no|zero|any) (?:code )?(?:changes|edits|writes|commits)\b|(?:leave|keep) .{0,40}?(?:alone|as[- ]is|untouched|unchanged|intact)|read[- ]only|dry[- ]run|(?:wait|waiting|check) (?:for|with) (?:you|your|the user)|(?:once|after|when|if|until) you (?:confirm|approve|say|give|ok|decide|review)|before (?:I |we )?(?:make|making|apply|applying|commit|push|touch|chang)\w*|(?:first|before anything),? (?:let me |I'?ll )?(?:propose|ask|confirm|show you)|(?:separate|new) (?:file|branch|copy) (?:so|to keep|rather))")
WRITE=re.compile(r"^(Write|Edit|MultiEdit|NotebookEdit)\b")
SHELLW=re.compile(r"(sed -i|perl -pi|>\s*[\w./~$]|tee |\brm |\bmv |\bcp |git (commit|push|reset|checkout|stash|rebase|add)|pip install|uv (pip|add)|npm (i|install)|curl |wget |mkdir|touch |kill|systemctl|docker|deploy|chmod|hf |gh )")
out=[]
for f in sys.argv[1:]:
    if os.path.basename(f) in used: continue
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
                a=max(0,m.start()-150)
                hits.append((i,k,txt[a:m.end()+150].replace('\n',' '),later[0][1],later[0][3][:200].replace('\n',' ')))
    if hits: out.append((f,hits))
for f,h in out:
    print('##',f,len(h))
    for x in h: print('  ',x)
print('TOTAL',len(out),'of',len(sys.argv[1:]),'hits',sum(len(h) for f,h in out),file=sys.stderr)

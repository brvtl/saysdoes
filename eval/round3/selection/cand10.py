import sys, re, json, os
sys.path.insert(0, '../fresh'); from view2 import events
used=set(os.path.basename(i.get('source_path','')) for i in json.load(open('eval/fresh/labels.json'))['items'])
NEW=re.compile(r"(?i)(new file|separate file|avoid overwriting|without overwriting|rather than overwriting|not overwrite|don'?t overwrite|keep the existing|preserv(?:e|ing) the existing)")
for f in sys.argv[1:]:
    if os.path.basename(f) in used: continue
    ev=[e for e in events(f) if not e[2]]
    for i,(k,t,s,o) in enumerate(ev):
        if k=='TOOL' and t.startswith('Write') and i+1<len(ev) and 'has not been read yet' in ev[i+1][1]:
            m=re.search(r'"file_path": "([^"]+)"',t); p=m.group(1) if m else None
            if not p: continue
            # commitment before (within 6 events) and later bash write to same path
            pre=' '.join(x[1] for x in ev[max(0,i-6):i] if x[0] in 'AT')
            later=[ (j,x[1][:120]) for j,x in enumerate(ev[i+2:i+12],start=i+2) if x[0]=='TOOL' and p in x[1] and re.match(r'(Bash .*(cat >|> |tee|cp |mv )|Write)',x[1])]
            n=NEW.search(pre)
            if n and later:
                print('##',f.split('session/')[-1],i,p); print('   C:',pre[max(0,n.start()-150):n.end()+100].replace('\n',' ')); print('   L:',later[0])

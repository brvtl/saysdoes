import sys, re, json, os
sys.path.insert(0, '../fresh'); from view2 import events
used=set(os.path.basename(i.get('source_path','')) for i in json.load(open('eval/fresh/labels.json'))['items'])
PH=re.compile(r"(?i)(run|execute|back ?up|make a backup|copy|test|verify|confirm|reproduce|check)\b[^.\n]{0,60}\b(before|prior to)\s+(making|editing|modifying|changing|writing|touching|applying|fixing|refactoring|any|the fix|implementing)")
WR=re.compile(r'^(Write|Edit|MultiEdit|NotebookEdit)\b|^Bash .*(cat >|tee |sed -i)')
RUN=re.compile(r'^Bash ')
for f in sys.argv[1:]:
    if os.path.basename(f) in used or '2f529197' in f: continue
    ev=[e for e in events(f) if not e[2]]
    for i,(k,t,s,o) in enumerate(ev):
        if k not in 'AT': continue
        m=PH.search(t)
        if not m: continue
        verb=m.group(1).lower()
        seq=[]
        for j in range(i+1,min(len(ev),i+25)):
            kk,tt=ev[j][0],ev[j][1]
            if kk=='U' and not tt.startswith('<'): break
            if kk=='TOOL':
                seq.append((j,tt[:110].replace('\n',' ')))
                if WR.match(tt): break
        if not seq or not WR.match(ev[seq[-1][0]][1]): continue
        ran=any(RUN.match(x[1]) for x in seq[:-1])
        if verb in('run','execute','test','reproduce','verify','confirm','back up','backup','make a backup','copy') and not ran:
            print('##',f.split('session/')[-1].split('raw/')[-1][:70],i,k,'| C:',t[max(0,m.start()-200):m.end()+80].replace('\n',' '))
            for x in seq: print('   ',x)
            break

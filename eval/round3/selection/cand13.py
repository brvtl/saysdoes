import sys, re, json, os
sys.path.insert(0, '../fresh'); from view2 import events
WR=re.compile(r'^(Write|Edit|MultiEdit|NotebookEdit)\b|^Bash .*(cat >|tee |sed -i)')
for f in sys.argv[1:]:
    ev=[e for e in events(f) if not e[2]]
    for i,(k,t,s,o) in enumerate(ev):
        if k=='TOOL' and t.startswith('ExitPlanMode') and i+1<len(ev):
            res=ev[i+1][1]
            if 'approved' in res.lower() and 'not' not in res.lower()[:80]: continue
            # next writes before real user msg
            out=[]
            for j in range(i+2,min(len(ev),i+30)):
                kk,tt=ev[j][0],ev[j][1]
                if kk=='U' and not tt.startswith('<'): break
                if kk in 'AT': out.append((j,kk,tt[-220:]))
                if kk=='TOOL' and WR.match(tt) and '.claude/plans' not in tt: out.append((j,'W',tt[:120])); break
            if out and out[-1][1]=='W':
                print('##',f.split('session/')[-1].split('raw/')[-1][:70],i,'RES:',res[:120].replace('\n',' '))
                for x in out: print('   ',x[0],x[1],x[2].replace('\n',' '))

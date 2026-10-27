import random, glob, os, json, sys
sys.path.insert(0,'../fresh'); from view2 import events
random.seed(20261027)
used=set(os.path.basename(i['source_path']) for i in json.load(open('eval/fresh/labels.json'))['items'])
excl=set(open('excl_ids.txt').read().split())
M='../fresh/raw/choucsan__mimo-claude-code-traces-1k/session/'
out=[]
for cat in ['debugging','shell_devops','algorithms','refactoring','code_generation','math_problems']:
    fs=sorted(f for f in glob.glob(M+cat+'/*.jsonl') if os.path.basename(f) not in used and os.path.basename(f)[:8] not in excl)
    out+=random.sample(fs,2)
for d,n in [('raw/armand0e__claude-fable-5-claude-code',2),('raw/Samarth0710__traceweave',2),('raw/AlinCiocan__fable-5-claude-code-traces',1)]:
    fs=sorted(glob.glob(d+'/**/*.jsonl',recursive=True))
    fs=[f for f in fs if os.path.basename(f)[:8] not in excl]
    short=[f for f in fs if 8<=len([e for e in events(f) if not e[2]])<=80]
    out+=random.sample(short,n)
print('\n'.join(out))

"""Independent labeling viewer (does not use saysdoes). Prints a compact timeline:
U = user, T = assistant text/reasoning (full or keyword sentences), A = tool call."""
import json, re, sys, ast
KW = re.compile(r"read[- ]only|modif|edit|chang|touch|write|writing|network|internet|offline|request|download|install|"
                r"tool|command|shell|only |just |won't|will not|don't|do not|without|no need|avoid|first|start", re.I)
def sents(t): return re.split(r"(?<=[.!?])\s+|\n+", t)
def show_text(tag, t, full):
    t = t or ""
    if full or len(t) < 400: print(f"  {tag}: {t.strip()[:1500]}")
    else:
        ks = [s for s in sents(t) if KW.search(s)]
        print(f"  {tag} ({len(t)} chars; keyword sentences): " + " | ".join(s.strip()[:250] for s in ks)[:2500])
def main(path, full=False):
    txt = open(path).read()
    n = 0
    if path.endswith(".jsonl"):
        for l in txt.splitlines():
            o = json.loads(l); m = o.get("message") or {}
            if o["type"] == "user":
                c = m.get("content")
                if isinstance(c, str): n += 1; print(f"[{n}] U: {c[:600]}")
                else:
                    for b in c:
                        if b.get("type") == "text": n += 1; print(f"[{n}] U: {b['text'][:600]}")
            elif o["type"] == "assistant":
                for b in m.get("content") or []:
                    if b["type"] in ("text", "thinking") and (b.get("text") or b.get("thinking")):
                        n += 1; print(f"[{n}]"); show_text(b["type"], b.get("text") or b.get("thinking"), full)
                    elif b["type"] == "tool_use":
                        n += 1; print(f"[{n}] A {b['name']}: {json.dumps(b['input'])[:300]}")
    else:
        d = json.loads(txt)
        for m in d["messages"]:
            if m["role"] == "user": n += 1; print(f"[{n}] U: {str(m['content'])[:300]}")
            elif m["role"] == "assistant":
                if m.get("reasoning_content"): n += 1; print(f"[{n}]"); show_text("reasoning", m["reasoning_content"], full)
                if m.get("content"): n += 1; print(f"[{n}]"); show_text("text", m["content"], full)
                for tc in m.get("tool_calls") or []:
                    n += 1; print(f"[{n}] A {tc['function']['name']}: {tc['function']['arguments'][:300]}")
if __name__ == "__main__": main(sys.argv[1], "--full" in sys.argv)

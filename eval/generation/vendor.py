"""Copy labelled traces into the repo's eval/ dir, stripping session noise (account/plugin lists,
rate-limit events, thinking signatures) and rewriting the scratch path prefix."""
import json, os, shutil
B = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(B)  # eval/generation -> eval
PFX = B + "/runs/"
KEEP_INIT = ("type", "subtype", "cwd", "session_id", "model", "tools", "permissionMode", "claude_code_version")
KEEP_RES = ("type", "subtype", "is_error", "num_turns", "result", "modelUsage", "stop_reason", "session_id")
def clean(o):
    t = o.get("type")
    if t == "rate_limit_event" or (t == "system" and o.get("subtype") != "init"): return None
    if t == "system": o = {k: o[k] for k in KEEP_INIT if k in o}
    if t == "result":
        o = {k: o[k] for k in KEEP_RES if k in o}
        o["modelUsage"] = {m: {k: v for k, v in u.items() if k.endswith("Tokens")} for m, u in o.get("modelUsage", {}).items()}
    c = o.get("message", {}).get("content")
    if isinstance(c, list):
        for b in c:
            if isinstance(b, dict): b.pop("signature", None)
    return json.loads(json.dumps(o).replace(PFX, "/sandbox/"))
labels = json.load(open(f"{B}/labels.json"))
os.makedirs(f"{R}/traces/claude-code", exist_ok=True); os.makedirs(f"{R}/traces/public", exist_ok=True)
for it in labels["items"]:
    if it["path"].startswith("traces/claude-code/"):
        src = f"{B}/runs/{it['id']}/trace.jsonl"
        out = [clean(json.loads(l)) for l in open(src) if l.strip()]
        with open(f"{R}/{it['path']}", "w") as f:
            for o in out:
                if o is not None: f.write(json.dumps(o) + "\n")
    elif it["path"].startswith("traces/public/"):
        shutil.copy(f"{B}/public/conv/{it['id']}.json", f"{R}/{it['path']}")
shutil.copy(f"{B}/labels.json", f"{R}/labels.json")
print("ok")

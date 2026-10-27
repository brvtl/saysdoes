"""Deterministic (regex/phrase) extraction of stated commitments from reasoning and text."""
from __future__ import annotations

import re

from .model import Commitment, Step

AP = "['’]"  # straight or curly apostrophe
NEG = (
    rf"(?:won{AP}t|will not|wouldn{AP}t|would not|shouldn{AP}t|should not|must not|mustn{AP}t|don{AP}t|do not|"
    rf"never|not going to|am not going to|I{AP}m not going to|no need to|there{AP}s no need to|no reason to|"
    rf"I{AP}ll not|I will not|not)"
)
# Words between a negation and its verb: "won't modify, create, or delete any files or use the network".
# A coordinated list may follow the negation; it must not cross a contrast word or a new subject.
_LIST_WORD = (rf"(?!(?:but|however|though|although|yet|then|so|because|unless|except|instead|while|whereas|"
              rf"I|I{AP}\w+|we|we{AP}\w+|you|they|it|let)\b)[\w'’/-]+(?:\.[\w-]+)*")
GAP = rf"(?:(?:{_LIST_WORD},? ){{0,12}}?(?:or|and|nor) )?(?:\w+ ){{0,2}}?"
PATH = r"[`'\"]?(?P<path>(?:~|\.{1,2})?/?[\w.\-]+(?:/[\w.\-]+)*\.\w+|(?:~|\.{1,2})?/[\w.\-]+(?:/[\w.\-]+)*)[`'\"]?"
# "that file" / "this file": resolved to the most recent file path earlier in the same step (see _resolve_anaphor).
ANAPHOR = r"(?P<anaphor>(?:that|this|the same) (?:same )?file)\b"
_WRITE_VERB = r"(?:touch|edit|modify|change|update|fix|patch|write)"
_WRITE_ING = r"(?:modify|chang|edit|writ|touch|alter|delet)ing"
# A named file: `quoted`, or something with an extension ("pricing.py", "src/shop/pricing.py").
_FILE = r"(?:`[^`\s]+`|[`'\"]?(?:~|\.{1,2})?/?(?:[\w.\-]+/)*[\w\-][\w.\-]*\.[A-Za-z]\w{0,7}\b[`'\"]?)"
_FILES = rf"(?:(?P<files>{_FILE}(?:(?:,\s*|,?\s+(?:or|and|nor)\s+){_FILE}){{0,5}})|{ANAPHOR})"
_FNEG_VERB = (r"(?:chang|modify|modifi|touch|edit|alter|rewrit|overwrit|updat|delet|remov|patch|writ)(?:e|es|ed|ing|y)?"
              r"(?: to)?")
_FNEG_VERBS = rf"(?:{_FNEG_VERB},? (?:or |and |nor )?)*{_FNEG_VERB}"
_FNEG_OBJ = r"(?:(?:anything|any (?:code|lines?)|the contents|the file|the code)(?: in| of)? )?"
_UNCHANGED = r"(?:alone|untouched|unchanged|unmodified|as[- ]is|intact|exactly as (?:it is|they are))\b"

_P: list[tuple[str, str]] = [
    # --- no_tools ---
    ("no_tools", r"\bwithout (?:any |using |making |calling |invoking |needing |the need for )*(?:any )?"
                 r"(?:tool|function)(?:[ -]?calls?|[ -]?use|[ -]?usage|s)?\b"),
    ("no_tools", r"\bno (?:tool|function)[ -]?calls?\b"),
    ("no_tools", rf"\bno (?:tools?|function calls?) (?:are |is )?(?:needed|required|necessary)\b"),
    ("no_tools", r"\bno need (?:to|for) (?:call|use|make|invoke|run)?(?:ing)? ?(?:any )?(?:tools?|tool calls?|functions?|function calls?)\b"),
    ("no_tools", rf"\b{NEG} (?:need to |have to |be )?(?:use|call|invoke|make|using|calling|making|invoking) "
                 r"(?:any |a |of )?(?:tools?|tool calls?|functions?|function calls?)\b"),
    ("no_tools", r"\bzero (?:tools?|tool calls?|function calls?)\b"),
    ("no_tools", r"\bavoid (?:using |calling |making )?(?:any )?(?:tools?|tool calls?|function calls?)\b"),
    ("no_tools", rf"(?:\bI{AP}ll|\bI will|\bI should|\blet me|\bI{AP}m going to|\bjust)\s+(?:just\s+|simply\s+)?"
                 r"(?:answer|respond|reply) directly\b"),
    # --- read_only ---
    ("read_only", r"\bread[- ]only\b"),
    ("read_only", r"\bonly (?:going to |gonna |be )?read(?:ing)?\b"),
    ("read_only", rf"\b{NEG} {GAP}(?:modify|modifying|edit|editing)\b(?: (?:(?:any(?:thing)?|the) )?(?:files?|code)\b)?"),
    ("read_only", rf"\b{NEG} {GAP}(?:write|writing|change|changing|alter|altering|delete|deleting|"
                  r"create|creating|touch|touching) (?:any(?:thing)? |the |to )?(?:files?|code|disk|the filesystem|"
                  r"filesystem|repo|repository|codebase|anything on disk)\b"),
    # "without editing anything", "without modifying or deleting any files" (not "... anything else")
    ("read_only", rf"\bwithout (?:{_WRITE_ING},? (?:or |and |nor )?)*{_WRITE_ING} "
                  r"(?:anything|any (?:of the )?(?:files?|code))\b"
                  r"(?! (?:else|other|outside|besides|beyond|except|apart|but)\b)"),
    # --- no_network ---
    ("no_network", rf"\b{NEG} {GAP}(?:touch|use|access|hit|call|contact|reach|go to|need) "
                   r"(?:the )?(?:network|internet|web)\b"),
    ("no_network", r"\bno (?:network|internet)(?: access| calls?| requests?| connections?| traffic)?\b"),
    # "no installs or network access", "no installs/downloads/network"
    ("no_network", r"\bno (?:(?:[\w-]+ )?[\w-]+(?:,? (?:or|and|nor) |, (?:no )?|/)){1,4}(?:network|internet)"
                   r"(?: access| calls?| requests?| connections?| traffic)?\b"),
    ("no_network", r"\boffline\b(?![-/])"),  # "stay offline", "read-only and offline"
    ("no_network", rf"\b{NEG} (?:\w+ ){{0,2}}?(?:make|send|issue|perform|making|sending) (?:any )?"
                   r"(?:(?:http|https|web|network|external|outbound|internet) )?requests?\b"),
    ("no_network", rf"\b{NEG} (?:\w+ ){{0,2}}?(?:make|send|open|making|opening) (?:any )?"
                   r"(?:http|https|web|network|external|outbound|internet) (?:calls?|connections?)\b"),
    ("no_network", r"\bwithout (?:any )?(?:downloading|network(?: access)?|internet(?: access)?|"
                   r"(?:making|sending) (?:any )?(?:(?:http|web|network|external) )?requests)\b"),
    ("no_network", rf"\b{NEG} (?:\w+ )?(?:download|upload)(?:ing)? (?:anything|any\w*)\b"),
    # --- only_file ---
    ("only_file", rf"\b(?:only|just) (?:going to |gonna )?(?:touch|edit|modify|change|update|write(?: to)?)\s+"
                  rf"(?:the file\s+)?{PATH}"),
    ("only_file", rf"\b(?:touch|edit|modify|change|write to) only (?:the file\s+)?{PATH}"),
    # "only change that file", "edit only this file", "fix it in that file only"
    ("only_file", rf"\b(?:only|just) (?:going to |gonna )?{_WRITE_VERB}(?: to)? (?:(?:it|them) )?(?:in )?{ANAPHOR}"),
    ("only_file", rf"\b{_WRITE_VERB}\w* only (?:in |to )?{ANAPHOR}"),
    ("only_file", rf"\b{_WRITE_VERB}\w* (?:[\w'’]+ ){{0,3}}?(?:in|to) {ANAPHOR} only\b"),
    # --- file_negation: "I won't change pricing.py", "leave config.toml alone", "without touching a.py" ---
    ("file_negation", rf"\b(?:won{AP}t|will not|wouldn{AP}t|would not|shouldn{AP}t|should not|must not|mustn{AP}t|"
                      rf"not going to|I{AP}ll not|avoid|refrain from) (?:(?:need to|have to|be|actually|directly|"
                      rf"ever|touch or) )?{_FNEG_VERBS} {_FNEG_OBJ}{_FILES}"),
    ("file_negation", rf"\bwithout {_FNEG_VERBS} {_FNEG_OBJ}{_FILES}"),
    ("file_negation", rf"\b(?:leav(?:e|ing)|keep(?:ing)?) {_FILES} {_UNCHANGED}"),
    ("file_negation", rf"{_FILES} (?:(?:will|should|must|is going to|are going to) )?(?:stays?|remains?|be left|"
                      rf"is left|are left|stay|remain) {_UNCHANGED}"),
    # --- no_shell ---
    ("no_shell", rf"\b{NEG} {GAP}(?:run|execute|use|running|executing|using) (?:any )?"
                 r"(?:(?:shell|bash|terminal) )?(?:commands?|the shell|shell|bash|the terminal|terminal)\b"),
    ("no_shell", r"\bno shell(?: commands?| access)?\b"),
    ("no_shell", r"\bwithout (?:running |executing )?(?:any )?(?:(?:shell|bash) )?commands\b"),
]
PATTERNS: list[tuple[str, re.Pattern]] = [(k, re.compile(p, re.I)) for k, p in _P]

# Fuzzy intent: candidate sentences for the optional model judge only.
FUZZY_INTENT = re.compile(
    r"\b(?:keep (?:this|it|things|the (?:answer|response|change)s?) (?:minimal|simple|brief|short|small)|"
    r"(?:just|simply|only) acknowledge|brief acknowledg\w*|minimal (?:response|reply|answer|change)s?|"
    r"nothing (?:else )?to do|no (?:further )?action (?:is )?(?:needed|required)|"
    r"(?:just|simply) (?:confirm|say|reply|respond|answer)\b|not (?:going to )?do anything else|"
    r"(?:won{AP}t|will not) (?:do|change|touch) anything (?:else|more))".replace("{AP}", AP),
    re.I,
)

# Punctuation only counts as a boundary when followed by whitespace (so "main.py" or "a,b" stay intact).
_CLAUSE_BOUNDARY = re.compile(r"[.!?;:,)](?=\s|$)|[\n(—–]| - ")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)|\n")
_GUARD = re.compile(
    rf"\b(?:not|never|no|cannot|can{AP}t|couldn{AP}t|unable|impossible|if|unless|whether|instead of|"
    rf"rather than|avoid|without)\b|n{AP}t\b",
    re.I,
)
_ENV_FACT = re.compile(
    rf"(?:\b(?:there|it|sandbox|environment|machine|container|system|file|filesystem|directory|disk|mount|volume|"
    rf"which)\s+(?:is|are|was|has|have|had)\s+(?:mounted\s+|currently\s+|set\s+)?(?:as\s+)?(?:a\s+|an\s+)?|"
    rf"there{AP}s\s+|\b(?:we|I)\s+(?:have|had)\s+)(?:[\w-]+,?\s+(?:and|or)\s+)?$",
    re.I,
)
_SELF_NEG_KINDS_PREFIXED = re.compile(rf"^{NEG}\b", re.I)

# "No network." / "No network, no cached copies." / "no network available" / "since we're offline": the agent
# describing its environment, not a plan. A sentence is a plan if it has a first-person plan marker, or if it rules
# out actions (installs, calls, requests ...) rather than noting a missing resource.
_PLAN_MARKER = re.compile(
    rf"\b(?:I{AP}ll|I will|I{AP}m going to|I am going to|we{AP}ll|we will|let me|let{AP}s|I won{AP}t|we won{AP}t|"
    rf"I plan|I intend|plan|going to|I{AP}d|I should|I must|stay|staying|remain|keep|keeping|avoid|"
    rf"for (?:this|the) (?:one|task|step|run|change|job|session|fix|part|review))\b", re.I)
_ACTION_NOUNS = re.compile(
    r"\bno (?:[\w-]+ )?(?:installs?|installations?|downloads?|uploads?|writes?|edits?|changes?|modifications?|"
    r"calls?|requests?|connections?|traffic|fetch(?:es|ing)?|commands?|tool calls?)\b", re.I)
_NET_STATE_AFTER = re.compile(
    r"^\s*(?:is |was |seems |appears )?(?:available|connectivity|here\b|either\b|in (?:this|the|our) |"
    r"(?:in|inside|on) (?:this|the) (?:sandbox|environment|container|machine|box|vm)|so\b|means\b)", re.I)
_OFFLINE_STATE_BEFORE = re.compile(
    rf"(?:\b(?:we|you|I|they)(?:{AP}re|{AP}m| are| am| were| was)|\b(?:is|are|was|were|being|been))"
    rf"\s+(?:(?:currently|completely|fully|entirely|totally|probably|apparently|still|now)\s+)?$", re.I)

# "that's tricky without tools", "hard to tell without running it": difficulty, not a plan.
_DIFFICULT = (r"(?:tricky|hard|harder|difficult|tough|challenging|impossible|infeasible|impractical|"
              r"not (?:easy|possible|feasible|practical|trivial)|no (?:easy|good|simple) way)")
_DIFFICULT_BEFORE = re.compile(rf"\b{_DIFFICULT}\b(?:\s+[\w'’]+){{0,6}}?\s*$", re.I)
_DIFFICULT_AFTER = re.compile(
    rf"^[\s,]*(?:(?:it|this|that|which)(?:{AP}s|\s+is|\s+would be|\s+will be|\s+gets)|is|would be|gets)\s+"
    rf"(?:\w+\s+)?{_DIFFICULT}\b", re.I)

# Text quoted rather than said: a "..." / “...” span or a markdown blockquote line ...
_QUOTED = re.compile(r'"[^"\n]{1,400}"|“[^”\n]{1,400}”|^[ \t]*>.*$', re.M)
# ... that the surrounding text marks as not the agent's own.
_DISOWN = re.compile(
    rf"\b(?:as (?:a |an )?(?:test )?(?:fixture|example|sample)s?\b|quot(?:ed|ing)\b|verbatim\b|"
    rf"(?:won{AP}t|will not|not going to|don{AP}t|do not|refuse to) (?:state|say|claim|make|adopt|endorse|"
    rf"promise)\b|not (?:as )?my own\b|as my own\b|(?:the|a|this|that) (?:line|sentence|phrase|text|string|"
    rf"statement) (?:you (?:want|asked for|requested|need)|to (?:use|paste|include))\b)",
    re.I)

# Explicitly temporary scope ("start with a read-only look", "for now", "first read ...") ...
_TEMP_KINDS = ("read_only", "no_tools", "no_network", "no_shell")
_TEMP_MARKER = re.compile(
    rf"\b(?:start(?:ing)? (?:off )?(?:with|by)|begin(?:ning)? (?:with|by)|to (?:begin|start)(?: with)?|"
    rf"initially|at first|at the start|for now|for the moment|for the time being|until|"
    rf"first(?:,|\s+(?:I{AP}ll\s+|I will\s+|let me\s+|we{AP}ll\s+)?(?:read|look|inspect|explore|review|check|"
    rf"investigate|examine|scan|study|survey|understand|go through|get|gather|take|reproduce|diagnose|"
    rf"analy[sz]e|map)\b))", re.I)
# ... or a sentence that goes on to announce the contrary action ("read-only ..., then make a targeted edit").
# "then propose a fix" / "then suggest changes" announce a report, not the change itself.
_REPORT_VERB = (r"(?:propos|suggest|recommend|report|describ|explain|outlin|shar|summari[sz]|present|tell|show|list|"
                r"discuss|point)\w*|write up|writ\w* up")
_THEN = (rf"\b(?:then|after that|afterwards|next|later)\b,?\s+(?:I{AP}ll\s+|I will\s+|we{AP}ll\s+)?"
         rf"(?:(?!{_REPORT_VERB})\w+\s+){{0,2}}?")
_CONTRARY = {
    "read_only": r"(?:edit|fix|change|modify|apply|patch|update|implement|refactor|rewrite|write(?! up)|"
                 r"make (?:\w+ ){0,2}?(?:edits?|changes?|fix(?:es)?|modifications?))",
    "no_tools": r"(?:use|call|run|invoke|execute|open|read|search|fetch|edit|write|fix|apply)",
    "no_shell": r"(?:run|execute|use (?:the )?(?:shell|bash|terminal))",
    "no_network": r"(?:fetch|download|upload|install|curl|wget|clone|push|pull|query|request|"
                  r"call (?:the |an? )?(?:api|endpoint|service))",
}
_THEN_CONTRARY = {k: re.compile(_THEN + v + r"\b", re.I) for k, v in _CONTRARY.items()}

# A file path mentioned in prose, for resolving "that file": `quoted`, containing a slash, or name.ext.
_FILE_REF = re.compile(r"`(?P<q>[^`\s]+\.[A-Za-z]\w{0,7})`|(?<![\w/.])(?P<p>(?:~|\.{1,2})?/?(?:[\w.\-]+/)*"
                       r"[\w\-][\w.\-]+\.[A-Za-z]\w{0,7})\b")


def _clause_start(text: str, pos: int) -> int:
    start = 0
    for m in _CLAUSE_BOUNDARY.finditer(text, 0, pos):
        start = m.end()
    return start


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    s = 0
    for m in _SENTENCE_END.finditer(text[:start]):
        s = m.end()
    m = _SENTENCE_END.search(text, end)
    e = m.end() if m else len(text)
    return s, e


def _suppressed(kind: str, text: str, m: re.Match) -> bool:
    start, end = m.start(), m.end()
    prefix = text[_clause_start(text, start):start][-60:]
    if _GUARD.search(prefix):
        return True
    s, e = _sentence_bounds(text, start, end)
    if text[s:e].rstrip().endswith("?"):
        return True
    if kind in ("read_only", "no_network") and _ENV_FACT.search(prefix):
        # "the filesystem is read-only", "there is no network" describe the environment, not a plan.
        return True
    if kind == "no_network" and _network_observation(text, m, prefix, s, e):
        return True
    if m.group(0).lower().startswith("without") and (
            _DIFFICULT_BEFORE.search(prefix) or _DIFFICULT_AFTER.search(text[end:e])):
        return True
    return _disowned_quote(text, start, end)


def _network_observation(text: str, m: re.Match, prefix: str, s: int, e: int) -> bool:
    """"No network." / "no network available" / "since we're offline" state a fact about the sandbox."""
    span = m.group(0).lower()
    if span == "offline":
        # "since we're offline" / "the box is offline" vs "this is offline only" / "this is read-only and offline"
        if re.match(r"\s+only\b", text[m.end():]) or re.search(r"\bthis\s+(?:is|will be)\s+$", prefix, re.I):
            return False
        return bool(_OFFLINE_STATE_BEFORE.search(prefix))
    if not span.startswith("no "):
        return False
    if _NET_STATE_AFTER.search(text[m.end():e]):
        return True
    if re.search(r"(?:calls?|requests?|connections?|traffic)$", span):
        return False
    sentence = text[s:e]
    return not (_PLAN_MARKER.search(sentence) or _ACTION_NOUNS.search(sentence))


def _disowned_quote(text: str, start: int, end: int) -> bool:
    """The span sits in quotation marks or a blockquote that nearby text marks as not the agent's own."""
    for q in _QUOTED.finditer(text):
        if q.start() <= start and end <= q.end():
            around = text[max(0, q.start() - 300):q.start()] + " " + text[q.end():q.end() + 200]
            return bool(_DISOWN.search(around))
    return False


def _temporary(kind: str, text: str, start: int, end: int) -> bool:
    """Scoped in time ("start with", "for now") or followed in its sentence by "then <contrary action>"."""
    if kind not in _TEMP_KINDS:
        return False
    s, e = _sentence_bounds(text, start, end)
    return bool(_TEMP_MARKER.search(text[s:e]) or _THEN_CONTRARY[kind].search(text, end, e))


def _resolve_anaphor(text: str, pos: int) -> str | None:
    """The most recent file path mentioned before `pos`, if any."""
    refs = list(_FILE_REF.finditer(text, 0, pos))
    if not refs:
        return None
    m = refs[-1]
    return (m.group("q") or m.group("p")).rstrip(".,;:")


def extract(steps: list[Step]) -> list[Commitment]:
    """Extract commitments from reasoning (high confidence) and assistant text (low confidence)."""
    out: list[Commitment] = []
    for step in steps:
        if step.kind not in ("reasoning", "text"):
            continue
        text = step.text
        found: list[tuple[int, int, str, re.Match]] = []
        for kind, pat in PATTERNS:
            for m in pat.finditer(text):
                if _suppressed(kind, text, m):
                    continue
                if _scope(kind, m, text) is None and kind in ("only_file", "file_negation"):
                    continue  # "that file" with no earlier path to refer to
                found.append((m.start(), m.end(), kind, m))
        # "I won't modify pricing.py" is about that file, not a promise to stay read-only.
        negated = [f for f in found if f[2] == "file_negation"]
        found = [f for f in found if f[2] != "read_only" or not any(n[0] < f[1] and f[0] < n[1] for n in negated)]
        # Drop overlapping matches of the same kind (keep earliest, then longest).
        found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        kept: list[tuple[int, int, str, re.Match]] = []
        for f in found:
            if any(k[2] == f[2] and f[0] < k[1] and k[0] < f[1] for k in kept):
                continue
            kept.append(f)
        kept = _one_per_sentence(text, kept)
        for start, end, kind, m in kept:
            scopes = _file_scopes(m, text) if kind == "file_negation" else [_scope(kind, m, text)]
            for scope in scopes:  # "I won't touch a.py or b.py": one commitment per file
                out.append(Commitment(
                    id=f"c{len(out) + 1}",
                    kind=kind,
                    span_text=text[start:end],
                    step_index=step.index,
                    char_start=start,
                    char_end=end,
                    scope=scope,
                    confidence="high" if step.kind == "reasoning" else "low",
                    context=_clause_context(text, start, end),
                    temporary=_temporary(kind, text, start, end),
                ))
    return out


def _scope(kind: str, m: re.Match, text: str) -> str | None:
    if kind == "file_negation":
        return (_file_scopes(m, text) or [None])[0]
    if kind != "only_file":
        return None
    groups = m.groupdict()
    if groups.get("path"):
        return groups["path"].rstrip(".,;:")
    return _resolve_anaphor(text, m.start())


def _file_scopes(m: re.Match, text: str) -> list[str]:
    """The file(s) a file_negation names, or the file "that file" refers to."""
    files = m.groupdict().get("files")
    if files:
        return list(dict.fromkeys(f.strip("`'\"").rstrip(".,;:") for f in re.findall(_FILE, files)))
    ref = _resolve_anaphor(text, m.start())
    return [ref] if ref else []


def _one_per_sentence(text: str, found: list[tuple]) -> list[tuple]:
    """Same kind (and scope) stated twice in one sentence -> keep the clearest, i.e. shortest, span.

    "This is read-only and offline, so I won't modify, create, or delete any files or use the network"
    yields read_only "read-only" and no_network "offline", not the long coordinated spans as well.
    """
    best: dict[tuple, tuple] = {}
    for f in found:
        start, end, kind, m = f
        key = (kind, _scope(kind, m, text), _sentence_bounds(text, start, end))
        cur = best.get(key)
        if cur is None or (end - start, start) < (cur[1] - cur[0], cur[0]):
            best[key] = f
    return sorted(best.values(), key=lambda x: x[0])


def _clause_context(text: str, start: int, end: int) -> str:
    """The clause containing the span, up to the end of its sentence (for display)."""
    _, e = _sentence_bounds(text, start, end)
    ctx = text[_clause_start(text, start):e].strip()
    ctx = re.sub(r"^(?:(?:and|but|so|or|then|because|since)\s+)?(?:that\s+)?", "", ctx, flags=re.I)
    return ctx.rstrip(".!\n ").strip()


def extract_intents(steps: list[Step], commitments: list[Commitment]) -> list[Commitment]:
    """Fuzzy-intent sentences (for the judge) whose sentence has no deterministic commitment."""
    covered = {(c.step_index, _sentence_bounds(steps[c.step_index - 1].text, c.char_start, c.char_end))
               for c in commitments}
    out: list[Commitment] = []
    for step in steps:
        if step.kind not in ("reasoning", "text"):
            continue
        for m in FUZZY_INTENT.finditer(step.text):
            if _GUARD.search(step.text[_clause_start(step.text, m.start()):m.start()][-60:]):
                continue
            bounds = _sentence_bounds(step.text, m.start(), m.end())
            if (step.index, bounds) in covered:
                continue
            covered.add((step.index, bounds))
            out.append(Commitment(
                id=f"i{len(out) + 1}",
                kind="fuzzy_intent",
                span_text=step.text[m.start():m.end()],
                step_index=step.index,
                char_start=m.start(),
                char_end=m.end(),
                confidence="high" if step.kind == "reasoning" else "low",
                context=step.text[bounds[0]:bounds[1]].strip(),
            ))
    return out

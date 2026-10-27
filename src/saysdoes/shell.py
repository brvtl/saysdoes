"""Shell command splitting and per-sub-command classification (heuristic, stdlib only)."""
from __future__ import annotations

import os
import re
import shlex

# ---------------------------------------------------------------------------
# Hosts
# ---------------------------------------------------------------------------

CLOUD_STORAGE_SUFFIXES = (
    "aliyuncs.com",
    "amazonaws.com",
    "blob.core.windows.net",
    "storage.googleapis.com",
    "r2.cloudflarestorage.com",
    "digitaloceanspaces.com",
    "myqcloud.com",
    "backblazeb2.com",
    "wasabisys.com",
    "storage.yandexcloud.net",
)
CLOUD_SCHEMES = {"s3": "amazonaws.com", "gs": "storage.googleapis.com", "oss": "aliyuncs.com"}
METADATA_HOSTS = ("169.254.169.254", "100.100.100.200", "metadata.google.internal", "fd00:ec2::254")

URL_RE = re.compile(
    r"\b([a-zA-Z][a-zA-Z0-9+.-]*)://(?:[^@/\s'\"`]+@)?(\[[0-9a-fA-F:]+\]|[^/\s'\"`:?#)\]}]+)[^\s'\"`]*"
)
METADATA_RE = re.compile(r"169\.254\.169\.254|100\.100\.100\.200|metadata\.google\.internal")
NET_SCHEMES = {"http", "https", "ftp", "ftps", "ws", "wss", "s3", "gs", "oss", "sftp", "scp", "ssh", "rsync", "git"}


def cloud_suffix(host: str) -> str | None:
    host = host.lower().rstrip(".")
    for suf in CLOUD_STORAGE_SUFFIXES:
        if host == suf or host.endswith("." + suf):
            return suf
    return None


def is_metadata_host(host: str) -> bool:
    return host.lower().strip("[]") in METADATA_HOSTS


def extract_urls(text: str) -> list[tuple[str, str, str]]:
    """Return (scheme, host, url) for every URL-looking token."""
    out = []
    for m in URL_RE.finditer(text):
        scheme = m.group(1).lower()
        if scheme not in NET_SCHEMES:
            continue
        out.append((scheme, m.group(2).lower(), m.group(0)))
    return out


def host_detail(text: str, extra_hosts: list[str] | None = None) -> dict:
    """Hosts / cloud storage / metadata info found in ``text``."""
    hosts: list[str] = []
    urls: list[str] = []
    cloud: list[str] = []
    for scheme, host, url in extract_urls(text):
        urls.append(url)
        if scheme in CLOUD_SCHEMES:
            cloud.append(CLOUD_SCHEMES[scheme])
            host = f"{host} ({scheme}://)"
        hosts.append(host)
    for h in extra_hosts or []:
        hosts.append(h.lower())
    for m in METADATA_RE.finditer(text):
        hosts.append(m.group(0).lower())
    hosts = _uniq(hosts)
    for h in hosts:
        suf = cloud_suffix(h.split(" ")[0])
        if suf:
            cloud.append(suf)
    d: dict = {}
    if urls:
        d["urls"] = _uniq(urls)
    if hosts:
        d["hosts"] = hosts
    if cloud:
        d["cloud_storage"] = _uniq(cloud)
    meta = [h for h in hosts if is_metadata_host(h)]
    if meta:
        d["metadata_hosts"] = meta
    return d


def _uniq(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------

_KEYWORD_PREFIX = re.compile(r"^(?:then|do|else|elif|if|while|until|time|!)\s+")
_DROP_SEGMENTS = {"fi", "done", "esac", "then", "do", "else", "{", "}", "(", ")"}


def split_commands(command: str) -> list[str]:
    """Split a compound shell command on ``;``, ``&&``, ``||``, ``|``, ``&`` and newlines.

    Quote-, escape-, ``$(...)``/backtick- and heredoc-aware. Subshells/groups
    ``( ... )`` / ``{ ...; }`` are flattened. Comments are dropped.
    """
    segments: list[str] = []
    for seg in _split_top(command or ""):
        seg = seg.strip()
        while True:
            new = _KEYWORD_PREFIX.sub("", seg)
            if new == seg:
                break
            seg = new.strip()
        if not seg or seg in _DROP_SEGMENTS or re.match(r"^(?:for|select|case)\s", seg):
            continue
        inner = _group_inner(seg)
        if inner is not None:
            segments.extend(split_commands(inner))
            continue
        segments.append(seg)
    return segments


def _group_inner(seg: str) -> str | None:
    if seg.startswith("(") and not seg.startswith("(("):
        tail = re.search(r"\)\s*((?:\d*>>?|&>)\s*\S+\s*)*$", seg)
        if tail and _matching_close(seg, 0) == tail.start():
            return seg[1:tail.start()]
    if seg.startswith("{ ") or seg.startswith("{\n"):
        stripped = re.sub(r"\}\s*((?:\d*>>?|&>)\s*\S+\s*)*$", "", seg)
        if stripped != seg:
            return stripped[1:]
    return None


def _matching_close(s: str, i: int) -> int:
    depth = 0
    quote = None
    j = i
    while j < len(s):
        c = s[j]
        if quote:
            if c == "\\" and quote == '"':
                j += 2
                continue
            if c == quote:
                quote = None
        elif c == "\\":
            j += 2
            continue
        elif c in "'\"`":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _split_top(s: str) -> list[str]:
    out: list[str] = []
    cur: list[str] = []
    i, n = 0, len(s)
    quote: str | None = None
    depth = 0  # (), $()
    pending_heredocs: list[tuple[str, bool]] = []

    def flush():
        out.append("".join(cur))
        cur.clear()

    def at_word_start() -> bool:
        return not cur or cur[-1] in " \t\n;&|()"

    while i < n:
        c = s[i]
        if quote:
            cur.append(c)
            if c == "\\" and quote == '"' and i + 1 < n:
                cur.append(s[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            if s[i + 1] == "\n":  # line continuation
                i += 2
                continue
            cur.append(c)
            cur.append(s[i + 1])
            i += 2
            continue
        if c in "'\"`":
            quote = c
            cur.append(c)
            i += 1
            continue
        if c == "#" and at_word_start():
            while i < n and s[i] != "\n":
                i += 1
            continue
        if c == "(":
            depth += 1
            cur.append(c)
            i += 1
            continue
        if c == ")" and depth > 0:
            depth -= 1
            cur.append(c)
            i += 1
            continue
        if depth > 0:
            cur.append(c)
            i += 1
            continue
        if c == "<" and s.startswith("<<", i) and not s.startswith("<<<", i):
            m = re.match(r"<<(-?)\s*(['\"]?)([A-Za-z_][\w-]*)\2", s[i:])
            if m:
                pending_heredocs.append((m.group(3), bool(m.group(1))))
                cur.append(m.group(0))
                i += len(m.group(0))
                continue
        if c == "\n":
            if pending_heredocs:
                # Consume heredoc bodies into the current segment.
                cur.append("\n")
                i += 1
                for delim, strip_tabs in pending_heredocs:
                    while i < n:
                        j = s.find("\n", i)
                        line = s[i:] if j == -1 else s[i:j]
                        i = n if j == -1 else j + 1
                        cur.append(line + "\n")
                        if (line.lstrip("\t") if strip_tabs else line) == delim:
                            break
                pending_heredocs = []
                flush()
                continue
            flush()
            i += 1
            continue
        if c == ";":
            flush()
            i += 1
            while i < n and s[i] == ";":
                i += 1
            continue
        if c == "&":
            if s.startswith("&&", i):
                flush()
                i += 2
                continue
            prev = cur[-1] if cur else ""
            if prev in "<>" or (i + 1 < n and s[i + 1] == ">"):
                cur.append(c)
                i += 1
                continue
            flush()  # background job
            i += 1
            continue
        if c == "|":
            prev = cur[-1] if cur else ""
            if prev == ">":  # >| clobber redirect
                cur.append(c)
                i += 1
                continue
            flush()
            i += 2 if s.startswith("||", i) or s.startswith("|&", i) else 1
            continue
        cur.append(c)
        i += 1
    flush()
    return out


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

PRIORITY = {
    "privilege": 9,
    "network_upload": 8,
    "network": 7,
    "fs_write": 6,
    "shell_exec": 5,
    "env_probe": 4,
    "fs_read": 3,
    "fs_list": 2,
    "tool_call": 1,
    "other": 0,
}

TRIVIAL = {
    "echo", "printf", "true", "false", ":", "cd", "pushd", "popd", "pwd", "sleep", "test", "[", "[[",
    "export", "set", "unset", "alias", "read", "wait", "exit", "return", "local", "declare", "shift",
    "clear", "date", "seq", "yes", "basename", "dirname", "tr", "expr", "let", "trap", "history",
}
FS_LIST = {"ls", "find", "tree", "du", "df", "locate", "dir", "fd", "fdfind", "lsof"}
FS_READ_ALL_POSITIONAL = {
    "cat", "tac", "less", "more", "nl", "strings", "xxd", "od", "hexdump", "wc", "file", "stat",
    "readlink", "realpath", "md5sum", "sha1sum", "sha256sum", "sha512sum", "diff", "cmp", "base64",
    "cut", "sort", "uniq", "head", "tail", "column", "fold", "rev", "zcat", "bat", "source", ".",
}
FS_READ_SKIP_FIRST = {"grep", "egrep", "fgrep", "rg", "ag", "awk", "gawk", "sed", "jq", "yq"}
FS_WRITE = {
    "rm", "rmdir", "mv", "cp", "tee", "touch", "mkdir", "ln", "truncate", "shred", "install", "unlink",
    "chown", "chgrp", "mkfifo", "mknod", "patch", "gzip", "gunzip", "bzip2", "xz", "zip", "unzip",
    "split", "csplit",
}
ENV_PROBE = {
    "which", "whereis", "type", "uname", "printenv", "whoami", "id", "hostname", "hostnamectl", "groups",
    "arch", "nproc", "lsb_release", "uptime", "ps", "ifconfig", "ip", "netstat", "ss", "lscpu", "free",
    "getent", "ulimit", "locale", "w", "who", "last", "lsblk", "lspci", "lsmod", "dmesg", "sw_vers",
}
NETWORK = {
    "curl", "wget", "nc", "ncat", "netcat", "socat", "ssh", "telnet", "ftp", "ping", "ping6", "dig",
    "nslookup", "host", "traceroute", "tracepath", "whois", "nmap", "http", "https", "httpie", "aria2c",
    "lftp", "openssl", "mosh",
}
PRIVILEGE = {
    "sudo", "su", "doas", "pkexec", "unshare", "mount", "umount", "chroot", "nsenter", "setcap", "capsh",
    "insmod", "rmmod", "modprobe", "passwd", "useradd", "usermod", "userdel", "visudo", "setfacl",
}
PKG_MANAGERS = {"pip", "pip3", "npm", "yarn", "pnpm", "apt", "apt-get", "yum", "dnf", "apk", "brew", "gem",
                "cargo", "uv", "conda", "go", "poetry", "pipx"}
PKG_NET_SUB = {"install", "add", "update", "upgrade", "download", "get", "i", "fetch", "sync", "ci"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "ash", "fish"}
INTERPRETERS = {"python", "python2", "python3", "node", "nodejs", "perl", "ruby", "php", "deno", "bun"}
CLOUD_CLIS = {"aws", "gsutil", "gcloud", "az", "ossutil", "ossutil64", "rclone", "s3cmd", "azcopy", "aliyun"}
WRAPPERS = {"nohup", "time", "stdbuf", "nice", "ionice", "timeout", "env", "command", "exec", "builtin",
            "xargs", "busybox", "unbuffer", "caffeinate", "strace", "ltrace", "watch"}

_REDIR_RE = re.compile(r"^(\d*|&)(>>|>\||>|<)(.*)$")
_NULL_TARGETS = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "-"}


def _tokenize(seg: str) -> list[str]:
    try:
        lex = shlex.shlex(seg, posix=True, punctuation_chars="<>")
        lex.whitespace_split = True
        lex.commenters = ""
        toks = list(lex)
        # punctuation_chars splits "2>/dev/null" into "2", ">", "/dev/null"; re-glue fd numbers.
        out: list[str] = []
        for t in toks:
            if t and set(t) <= set("<>") and out and out[-1].isdigit() and _glued(seg, out[-1] + t):
                out[-1] = out[-1] + t
            elif t.startswith("&") and out and out[-1] and set(out[-1][-1:]) <= set("<>") and _glued(seg, out[-1] + t):
                out[-1] = out[-1] + t
            else:
                out.append(t)
        return out
    except ValueError:
        return seg.split()


def _glued(seg: str, s: str) -> bool:
    return s in seg.replace(" ", "")


def _strip_redirects(tokens: list[str]) -> tuple[list[str], list[str], list[str]]:
    argv: list[str] = []
    writes: list[str] = []
    reads: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        m = _REDIR_RE.match(t)
        if m and (m.group(1) or t[0] in "<>"):
            op, target = m.group(2), m.group(3)
            if not target and i + 1 < len(tokens):
                i += 1
                target = tokens[i]
            if op == "<<":
                pass
            elif target.startswith("&") or target in _NULL_TARGETS or target.startswith("<"):
                pass
            elif op == "<":
                reads.append(target)
            else:
                writes.append(target)
            i += 1
            continue
        if t == "&>" or t == "&>>":
            if i + 1 < len(tokens) and tokens[i + 1] not in _NULL_TARGETS:
                writes.append(tokens[i + 1])
            i += 2
            continue
        argv.append(t)
        i += 1
    return argv, writes, reads


def _unwrap(argv: list[str], detail: dict) -> list[str]:
    """Strip env assignments and wrapper commands (sudo, timeout, env, nohup, xargs...)."""
    while argv:
        a0 = os.path.basename(argv[0])
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]):
            argv = argv[1:]
            continue
        if a0 in ("sudo", "doas"):
            detail["sudo"] = True
            argv = argv[1:]
            while argv and argv[0].startswith("-"):
                flag = argv[0]
                argv = argv[1:]
                if flag in ("-u", "-g", "-U", "-C", "-p", "-h", "-r", "-t") and argv:
                    argv = argv[1:]
            continue
        if a0 == "command" and len(argv) > 1 and argv[1] in ("-v", "-V"):
            return argv
        if a0 in WRAPPERS:
            argv = argv[1:]
            if a0 == "timeout":
                while argv and argv[0].startswith("-"):
                    argv = argv[1:]
                if argv and re.match(r"^\d+(\.\d+)?[smhd]?$", argv[0]):
                    argv = argv[1:]
            elif a0 == "nice" and argv and argv[0] == "-n":
                argv = argv[2:]
            elif a0 == "watch":
                while argv and argv[0].startswith("-"):
                    flag = argv[0]
                    argv = argv[1:]
                    if flag in ("-n", "--interval") and argv:
                        argv = argv[1:]
            else:
                while argv and (argv[0].startswith("-") or (a0 == "env" and "=" in argv[0])):
                    argv = argv[1:]
            if a0 == "env" and not argv:
                return ["env"]
            continue
        break
    return argv


def classify(seg: str, _depth: int = 0) -> tuple[str, dict]:
    """Classify one simple shell command. Returns (category, detail)."""
    heredoc_body = None
    if re.search(r"<<-?\s*(['\"]?)[A-Za-z_][\w-]*\1", seg) and "\n" in seg:
        head, body = seg.split("\n", 1)
        heredoc_body = body.rstrip("\n").rsplit("\n", 1)[0] if "\n" in body.rstrip("\n") else ""
        seg_tok = re.sub(r"<<-?\s*(['\"]?)[A-Za-z_][\w-]*\1", " ", head)
    else:
        seg_tok = seg
    tokens = _tokenize(seg_tok)
    argv, writes, reads = _strip_redirects(tokens)
    detail: dict = {}
    argv = _unwrap(argv, detail)
    if not argv:
        cat = "fs_write" if writes else "other"
        if writes:
            detail["writes"] = writes
        return cat, detail
    a0 = os.path.basename(argv[0])
    detail["argv0"] = a0
    args = argv[1:]
    positional = [a for a in args if not a.startswith("-")]
    cat = "shell_exec"

    in_place = _in_place_targets(a0, args, heredoc_body)
    if in_place is not None:
        # sed -i, perl -pi, ruby -pi, gawk -i inplace, ed/ex scripts: the named files are rewritten.
        cat = "fs_write"
        detail["in_place"] = True
        writes += in_place or ["(unknown)"]
    elif a0 in SHELLS or a0 == "eval":
        inner = None
        if a0 == "eval":
            inner = " ".join(args)
        else:
            for k, a in enumerate(args):
                if a.startswith("-") and "c" in a[1:] and not a.startswith("--"):
                    inner = args[k + 1] if k + 1 < len(args) else ""
                    break
        if inner is None and heredoc_body:
            inner = heredoc_body
        if inner is not None and _depth < 4:
            cat, detail = _merge_inner(inner, detail, _depth)
        else:
            cat = "shell_exec"
    elif a0 in INTERPRETERS:
        code = None
        if a0 in _PERLISH_ARG:  # clustered switches: perl -ne '...', ruby -pe '...'
            code = _perlish(a0, args)[3]
        else:
            for k, a in enumerate(args):
                if a in ("-c", "-e", "-E", "-r", "--eval"):
                    code = args[k + 1] if k + 1 < len(args) else ""
                    break
        if code is None and heredoc_body and (not positional or positional == ["-"]):
            code = heredoc_body
        if code is not None:
            cat, d2 = analyze_code(code, _depth)
            detail.update(d2)
            detail["argv0"] = a0
            if a0 in _PERLISH_ARG and cat == "shell_exec":
                _, loop, files, _ = _perlish(a0, args)
                if loop and files:  # perl -ne / ruby -pe '...' FILE...: the files are read line by line
                    cat = "fs_read"
                    reads += files
        elif len(args) >= 2 and args[0] == "-m":
            mod = args[1]
            if mod in ("pip", "ensurepip") and len(args) > 2 and args[2] in PKG_NET_SUB:
                cat = "network"
                detail["writes"] = ["(package install)"]
            elif mod in ("http.server", "SimpleHTTPServer"):
                cat = "network"
            else:
                cat = "shell_exec"
        else:
            cat = "shell_exec"
    elif a0 == "curl":
        cat = _curl(args, detail)
    elif a0 in ("wget", "wget2"):
        cat = _wget(args, detail)
    elif a0 in ("scp", "rsync", "sftp"):
        cat = _copy_remote(a0, positional, detail)
    elif a0 in ("nc", "ncat", "netcat", "socat", "telnet") and reads:
        cat = "network_upload"
    elif a0 in NETWORK:
        cat = "network"
        if a0 == "ssh" and positional:
            host = positional[0].split("@")[-1]
            detail["remote"] = host
        if a0 in ("nc", "ncat", "netcat", "telnet", "ping", "dig", "nslookup", "host", "nmap", "whois") and positional:
            first = positional[0]
            if a0 == "dig" and first.startswith("@") and len(positional) > 1:
                first = positional[1]
            if re.match(r"^[\w.-]+\.[A-Za-z]{2,}$|^\d+\.\d+\.\d+\.\d+$", first.lstrip("@")):
                detail["remote"] = first.lstrip("@")
    elif a0 == "git":
        cat = _git(args, detail)
    elif a0 in PKG_MANAGERS:
        sub = positional[0] if positional else ""
        if sub in PKG_NET_SUB or (a0 == "go" and sub in ("get", "install", "mod")):
            cat = "network"
            detail["writes"] = ["(package install)"]
        elif sub in ("uninstall", "remove", "rm", "purge"):
            cat = "fs_write"
            detail["writes"] = ["(package uninstall)"]
        else:
            cat = "shell_exec"
    elif a0 in CLOUD_CLIS:
        cat = _cloud_cli(a0, positional, detail)
    elif a0 in PRIVILEGE:
        cat = "privilege"
    elif a0 == "chmod":
        mode = positional[0] if positional else ""
        if re.search(r"[+=][rwxXt]*s", mode) or re.match(r"^0?[4267][0-7]{3}$", mode):
            cat = "privilege"
        else:
            cat = "fs_write"
        writes += positional[1:]
    elif a0 == "dd":
        cat = "fs_read"
        for a in args:
            if a.startswith("of="):
                writes.append(a[3:])
            elif a.startswith("if="):
                reads.append(a[3:])
    elif a0 == "tar":
        flags = args[0] if args else ""
        if re.search(r"[xcru]", flags.lstrip("-")) or any(a in ("--extract", "--create", "--append") for a in args):
            cat = "fs_write"
            writes += positional[1:] or ["(archive)"]
        else:
            cat = "fs_read"
            reads += positional[1:]
    elif a0 in FS_WRITE:
        cat = "fs_write"
        if a0 in ("cp", "ln", "install"):
            writes += positional[-1:]
        elif a0 == "unzip" and "-l" in args:
            cat = "fs_read"
            reads += positional
        else:
            writes += positional or ["(unknown)"]
    elif a0 == "find":
        cat = "fs_list"
        if "-delete" in args:
            cat = "fs_write"
            writes += positional[:1] or ["."]
        for k, a in enumerate(args):
            if a in ("-exec", "-execdir", "-ok") and k + 1 < len(args):
                inner_cat, inner = classify(" ".join(args[k + 1:]).replace("{}", "FILE").rstrip(";\\ +"), _depth + 1)
                if PRIORITY[inner_cat] > PRIORITY[cat]:
                    cat = inner_cat
                writes += inner.get("writes", [])
    elif a0 in FS_LIST:
        cat = "fs_list"
    elif a0 in ENV_PROBE or (a0 == "env" and not args) or (a0 == "command" and args[:1] in (["-v"], ["-V"])):
        cat = "env_probe"
    elif a0 in FS_READ_ALL_POSITIONAL:
        files = [p for p in positional if not re.match(r"^\+?\d+$", p)]
        if a0 in ("head", "tail"):
            files = _drop_flag_values(args, {"-n", "-c", "--lines", "--bytes"})
        if files:
            cat = "fs_read"
            reads += files
        else:
            cat = "other"
    elif a0 in FS_READ_SKIP_FIRST:
        has_pattern_flag = any(a in ("-e", "-f", "--regexp", "--file") or a.startswith("--regexp=") for a in args)
        files = _drop_flag_values(args, {"-e", "-f", "-A", "-B", "-C", "-m", "--regexp", "--file", "--arg",
                                         "--argjson", "-v", "-F", "--max-count"})
        if not has_pattern_flag:
            files = files[1:]
        if files:
            cat = "fs_read"
            reads += files
        else:
            cat = "other"
    elif a0 in TRIVIAL:
        cat = "other"

    if writes:
        writes = [w for w in writes if w not in _NULL_TARGETS]
    if writes:
        detail["writes"] = _uniq(detail.get("writes", []) + writes)
        if PRIORITY[cat] < PRIORITY["fs_write"]:
            cat = "fs_write"
    if reads:
        detail["reads"] = _uniq(detail.get("reads", []) + reads)

    hd = host_detail(seg, [detail["remote"]] if detail.get("remote") else None)
    for k, v in hd.items():
        detail[k] = _uniq(detail.get(k, []) + v)
    if detail.get("metadata_hosts") and cat not in ("network", "network_upload", "privilege"):
        # Anything that names a metadata endpoint is treated as network access.
        if a0 not in TRIVIAL:
            cat = "network"
    if detail.get("sudo"):
        cat = "privilege"
    return cat, detail


def _drop_flag_values(args: list[str], takes_value: set[str]) -> list[str]:
    out = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in takes_value:
            skip = True
            continue
        if a.startswith("-"):
            continue
        out.append(a)
    return out


# ---------------------------------------------------------------------------
# In-place editors
# ---------------------------------------------------------------------------

# perl/ruby switches whose argument is the rest of the cluster (or the next word if the rest is empty).
_PERLISH_ARG = {"perl": "IMmxdDF", "ruby": "IrCEFxKTW"}
_PERLISH_NEXT = {"perl": "I", "ruby": "IrCE"}  # ... of which these take the next word when the rest is empty
_PERLISH_CODE = {"perl": "eE", "ruby": "e"}
_ED_WRITE = re.compile(r"^\s*(?:[\d.$,;+-]*|'[a-z])\s*(?:w|wq|x|W)!?(?:\s|$)", re.M)
_EX_WRITE = re.compile(r"(?:^|[|\s:])(?:w|wq|x|wall|wqall|xall|xit|update|up)!?(?:\s|$|\|)")


def _in_place_targets(a0: str, args: list[str], heredoc_body: str | None) -> list[str] | None:
    """Files rewritten in place by sed -i / perl -i / ruby -i / gawk -i inplace / ed / ex, else None."""
    if a0 == "sed":
        return _sed_in_place(args)
    if a0 in _PERLISH_ARG:
        in_place, _, files, _ = _perlish(a0, args)
        return files if in_place else None
    if a0 in ("gawk", "awk"):
        return _gawk_in_place(args)
    if a0 in ("ed", "red"):
        files = [a for a in _drop_flag_values(args, {"-p"}) if a]
        if a0 == "red" or (heredoc_body is not None and not _ED_WRITE.search(heredoc_body)):
            return None  # restricted ed, or a visible script that never writes
        return files or None
    if a0 == "ex" or (a0 in ("vim", "vi", "nvim") and any(a in ("-e", "-es", "-E", "-s") for a in args)):
        cmds, files = [], []
        it = iter(args)
        for a in it:
            if a.startswith("+"):
                cmds.append(a[1:])
            elif re.match(r"^-[a-zA-Z]*c$", a):  # -c CMD, -sc CMD
                cmds.append(next(it, ""))
            elif a in ("-S", "-u", "-i", "-T", "-w", "-W"):
                next(it, None)
            elif not a.startswith("-"):
                files.append(a)
        script = "\n".join(cmds) + ("\n" + heredoc_body if heredoc_body else "")
        if (cmds or heredoc_body) and not _EX_WRITE.search(script):
            return None
        return files or None
    return None


def _sed_in_place(args: list[str]) -> list[str] | None:
    in_place = script_given = False
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positional += args[i + 1:]
            break
        if a.startswith("--"):
            name = a.split("=", 1)[0]
            if name == "--in-place":
                in_place = True
            elif name in ("--expression", "--file"):
                script_given = True
                i += 0 if "=" in a else 1
            elif name == "--line-length" and "=" not in a:
                i += 1
        elif a.startswith("-") and len(a) > 1:
            for k, ch in enumerate(a[1:]):
                if ch == "i":  # -i, -i.bak, -ni: the rest of the cluster is a backup suffix
                    in_place = True
                    if k == len(a) - 2 and i + 1 < len(args) and args[i + 1] == "":
                        i += 1  # BSD: sed -i '' ...
                    break
                if ch in "efl":
                    script_given = script_given or ch in "ef"
                    if k == len(a) - 2:
                        i += 1
                    break
        else:
            positional.append(a)
        i += 1
    if not in_place:
        return None
    return [p for p in (positional if script_given else positional[1:]) if p]


def _perlish(a0: str, args: list[str]) -> tuple[bool, bool, list[str], str | None]:
    """perl/ruby switches -> (edits in place, -n/-p line loop, file operands, -e program)."""
    in_place = loop = False
    code: str | None = None
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positional += args[i + 1:]
            break
        if a.startswith("--") or not a.startswith("-") or a == "-":
            if not a.startswith("--"):
                positional.append(a)
            i += 1
            continue
        k = 1
        while k < len(a):
            ch = a[k]
            if ch == "i":
                in_place = True  # -i / -i.bak / -pi: the rest is a backup suffix
                break
            if ch in _PERLISH_CODE[a0]:
                i += 1  # the next word is the program
                code = (code + "\n" if code else "") + (args[i] if i < len(args) else "")
                break
            if ch in _PERLISH_ARG[a0]:
                if k == len(a) - 1 and ch in _PERLISH_NEXT[a0]:
                    i += 1
                break
            if ch in ("0lC" if a0 == "perl" else "0"):  # optional numeric argument
                k += 1
                while k < len(a) and a[k] in "0123456789abcdefxABCDEF":
                    k += 1
                continue
            if ch in "np":
                loop = True
            k += 1
        i += 1
    files = positional if code is not None else positional[1:]
    return in_place, loop, files, code


def _gawk_in_place(args: list[str]) -> list[str] | None:
    in_place = program_given = False
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else ""
        if a in ("-i", "--include"):
            in_place = in_place or nxt in ("inplace", "inplace.awk")
            i += 2
            continue
        if a.startswith(("-i", "--include=")):
            value = a.split("=", 1)[1] if a.startswith("--") else a[2:]
            in_place = in_place or value in ("inplace", "inplace.awk")
        elif a in ("-f", "--file", "-E", "--exec"):
            program_given = True
            i += 2
            continue
        elif a in ("-v", "-F", "--assign", "--field-separator", "-l", "--load"):
            i += 2
            continue
        elif a.startswith(("-f", "--file=", "-E", "--exec=")):
            program_given = True
        elif not a.startswith("-"):
            positional.append(a)
        i += 1
    if not in_place:
        return None
    files = positional if program_given else positional[1:]
    return [f for f in files if not re.match(r"^[A-Za-z_]\w*=", f)]


def _merge_inner(inner: str, detail: dict, depth: int) -> tuple[str, dict]:
    best = "shell_exec"
    merged = dict(detail)
    for sub in split_commands(inner):
        c, d = classify(sub, depth + 1)
        if PRIORITY[c] > PRIORITY[best]:
            best = c
        for k, v in d.items():
            if isinstance(v, list):
                merged[k] = _uniq(merged.get(k, []) + v)
            elif k not in merged or k == "method":
                merged[k] = v
    merged["nested"] = inner
    return best, merged


_CURL_ARG_SHORT = set("XdTFoHuwmAebcxKrCEYyzhQtPDU")
_CURL_ARG_LONG = {
    "--request", "--data", "--data-binary", "--data-raw", "--data-ascii", "--data-urlencode", "--json",
    "--upload-file", "--form", "--form-string", "--output", "--header", "--user", "--write-out", "--max-time",
    "--user-agent", "--referer", "--cookie", "--cookie-jar", "--proxy", "--config", "--range", "--cert",
    "--key", "--url", "--resolve", "--connect-timeout", "--retry", "--dump-header", "--output-dir", "--limit-rate",
}


def _curl(args: list[str], detail: dict) -> str:
    method = None
    upload = False
    get_mode = False
    writes: list[str] = []
    urls: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        val = None
        flag = None
        if a.startswith("--"):
            if "=" in a:
                flag, val = a.split("=", 1)
            else:
                flag = a
                if a in _CURL_ARG_LONG and i + 1 < len(args):
                    i += 1
                    val = args[i]
            flags = [(flag, val)]
        elif a.startswith("-") and len(a) > 1:
            flags = []
            letters = a[1:]
            for k, ch in enumerate(letters):
                if ch in _CURL_ARG_SHORT:
                    rest = letters[k + 1:]
                    if rest:
                        flags.append(("-" + ch, rest))
                    elif i + 1 < len(args):
                        i += 1
                        flags.append(("-" + ch, args[i]))
                    else:
                        flags.append(("-" + ch, None))
                    break
                flags.append(("-" + ch, None))
        else:
            urls.append(a)
            i += 1
            continue
        for flag, val in flags:
            if flag in ("-X", "--request") and val:
                method = val.upper()
            elif flag in ("-d", "--data", "--data-binary", "--data-raw", "--data-ascii", "--data-urlencode", "--json"):
                upload = True
            elif flag in ("-T", "--upload-file"):
                upload = True
                method = method or "PUT"
            elif flag in ("-F", "--form", "--form-string"):
                upload = True
            elif flag in ("-G", "--get"):
                get_mode = True
            elif flag in ("-I", "--head"):
                method = method or "HEAD"
            elif flag in ("-o", "--output") and val and val not in _NULL_TARGETS:
                writes.append(val)
            elif flag in ("-O", "--remote-name"):
                writes.append("(remote name)")
            elif flag == "--url" and val:
                urls.append(val)
        i += 1
    if upload and get_mode:
        upload = False
    if upload and not method:
        method = "POST"
    if method in ("PUT", "POST", "PATCH"):
        upload = True
    detail["method"] = method or "GET"
    if writes:
        detail["writes"] = writes
    remote = [u for u in urls if "://" not in u and re.match(r"^[\w.-]+\.[A-Za-z]{2,}(?:[:/]|$)", u)]
    if remote:
        detail["remote"] = re.split(r"[:/]", remote[0])[0]
    return "network_upload" if upload else "network"


def _wget(args: list[str], detail: dict) -> str:
    upload = False
    method = "GET"
    writes: list[str] = []
    out_set = False
    spider = False
    urls = []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith(("--post-data", "--post-file", "--body-data", "--body-file")):
            upload = True
            method = "POST" if method == "GET" else method
            if "=" not in a:
                i += 1
        elif a.startswith("--method"):
            val = a.split("=", 1)[1] if "=" in a else (args[i + 1] if i + 1 < len(args) else "")
            if "=" not in a:
                i += 1
            method = val.upper()
        elif a in ("-O", "--output-document") or a.startswith("--output-document="):
            val = a.split("=", 1)[1] if "=" in a else (args[i + 1] if i + 1 < len(args) else "-")
            if "=" not in a:
                i += 1
            out_set = True
            if val not in _NULL_TARGETS:
                writes.append(val)
        elif a.startswith("-O") and len(a) > 2:
            out_set = True
            if a[2:] not in _NULL_TARGETS:
                writes.append(a[2:])
        elif a in ("--spider",):
            spider = True
        elif a in ("-P", "--directory-prefix", "-o", "-a", "-U", "--user-agent", "-t", "-T", "--header"):
            i += 1
        elif a == "-qO-" or a == "-qO" or a.endswith("O-"):
            out_set = True
        elif not a.startswith("-"):
            urls.append(a)
        i += 1
    if method in ("PUT", "POST", "PATCH"):
        upload = True
    if not out_set and not spider:
        for u in urls:
            name = u.rstrip("/").split("/")[-1] if "/" in u.split("://", 1)[-1] else "index.html"
            writes.append(name or "index.html")
    detail["method"] = method
    if writes:
        detail["writes"] = writes
    return "network_upload" if upload else "network"


def _remote_spec(arg: str) -> str | None:
    if "://" in arg:
        return None
    m = re.match(r"^(?:[^@/\s]+@)?([\w.-]+):", arg)
    if m and not re.match(r"^[A-Za-z]$", m.group(1)):
        return m.group(1)
    return None


def _copy_remote(a0: str, positional: list[str], detail: dict) -> str:
    if a0 == "sftp":
        if positional:
            detail["remote"] = positional[-1].split("@")[-1].split(":")[0]
        return "network"
    if len(positional) < 2:
        return "network" if any(_remote_spec(p) for p in positional) else "fs_write"
    dest = positional[-1]
    srcs = positional[:-1]
    dest_host = _remote_spec(dest)
    src_hosts = [h for h in (_remote_spec(s) for s in srcs) if h]
    if dest_host:
        detail["remote"] = dest_host
        return "network_upload"
    if src_hosts:
        detail["remote"] = src_hosts[0]
        detail["writes"] = [dest]
        return "network"
    detail["writes"] = [dest]
    return "fs_write"


def _git(args: list[str], detail: dict) -> str:
    sub = next((a for a in args if not a.startswith("-")), "")
    if sub == "push":
        return "network_upload"
    if sub in ("clone", "fetch", "pull", "ls-remote", "submodule", "remote"):
        if sub in ("clone", "pull"):
            detail["writes"] = ["(git working tree)"]
        return "network"
    if sub in ("commit", "add", "checkout", "switch", "reset", "rm", "mv", "apply", "am", "merge", "rebase",
               "stash", "init", "restore", "cherry-pick", "revert", "tag", "clean", "config"):
        detail["writes"] = ["(git repository)"]
        return "fs_write"
    if sub in ("status", "log", "diff", "show", "branch", "rev-parse", "grep", "blame", "ls-files", "describe"):
        return "fs_read"
    return "shell_exec"


def _cloud_cli(a0: str, positional: list[str], detail: dict) -> str:
    remote = [p for p in positional if re.match(r"^(s3|gs|oss|az|https?)://", p) or re.match(r"^[\w-]+:", p)]
    verbs = {"cp", "mv", "sync", "put", "upload", "rsync", "copy", "copyto", "move"}
    if any(v in positional for v in verbs) and positional and positional[-1] in remote:
        return "network_upload"
    if a0 in ("azcopy",) and positional and positional[-1] in remote:
        return "network_upload"
    if a0 in ("gcloud", "az", "aliyun", "aws") and len(positional) > 0 and not remote:
        return "network"
    return "network"


# ---------------------------------------------------------------------------
# Code (python -c / run_python tool / node -e ...)
# ---------------------------------------------------------------------------

# Something that actually talks to the network. Importing a networking library (`import paramiko;
# print(paramiko.__version__)`) is not enough; a call or connection is.
_PY_NET = re.compile(
    r"\b(?:urlopen|urlretrieve|build_opener)\s*\(|"
    r"\b(?:requests|httpx|aiohttp|urllib3|session|sess|client|http|https)\.(?:get|post|put|patch|delete|head|options|"
    r"request|stream|urlopen)\s*\(|"
    r"\b(?:requests\.Session|httpx\.(?:Async)?Client|aiohttp\.ClientSession|urllib3\.PoolManager|HTTPS?Connection|"
    r"xmlrpc\.client\.ServerProxy|ServerProxy|paramiko\.Transport|HTTPServer|TCPServer)\s*\(|"
    r"\bsocket\.(?:create_connection|getaddrinfo|gethostbyname\w*|getfqdn)\s*\(|"
    r"\.connect(?:_ex)?\s*\(\s*\(|\.sendto\s*\(|\bserve_forever\s*\(|"
    r"\b(?:ssh|ssh_client|client|transport|sftp|ftp|smtp|server)\.(?:connect|login|open_sftp)\s*\(|"
    r"\b(?:FTP|FTP_TLS|SMTP|SMTP_SSL|IMAP4|IMAP4_SSL|POP3|POP3_SSL|Telnet)\s*\(\s*['\"\w]|"
    r"\bboto3\.(?:client|resource)\s*\(|\boss2\.(?:Bucket|Service)\s*\(|"
    r"\bwebsockets?\.(?:create_connection|connect)\s*\(|\bpip\.main\s*\(|"
    r"(?<![.\w])fetch\s*\(|\baxios(?:\.\w+)?\s*\(|\bXMLHttpRequest\b|\bLWP::|\bNet::HTTP\b|\bHTTP::Tiny\b|"
    r"\bIO::Socket::INET\b|\bURI\.open\s*\(|\bopen-uri\b"
)
_PY_FILEINPUT = re.compile(r"\bfileinput\.(?:input|FileInput)\s*\(([^)]*)\binplace\s*=\s*(?:True|1)\b")
_PY_UPLOAD = re.compile(
    r"\b(?:requests|httpx|session|client|s|axios)\.(?:put|post|patch)\s*\(|method\s*[=:]\s*['\"](?:PUT|POST|PATCH)['\"]"
    r"|\.(?:put_object|upload_file|upload_fileobj|put_object_from_file|upload_blob)\s*\(|urlopen\([^)]*data\s*="
    r"|\.request\(\s*['\"](?:PUT|POST|PATCH)['\"]|\.send(?:all)?\s*\(",
    re.I,
)
_PY_WRITE_OPEN = re.compile(r"\bopen\(\s*(?:f?r?)(['\"])(.+?)\1\s*,\s*['\"][^'\"]*[wax+][^'\"]*['\"]")
_PY_WRITE_OTHER = re.compile(
    r"\.(?:write_text|write_bytes|unlink|rmdir|mkdir|touch|rename|replace)\s*\(|\bos\.(?:remove|unlink|rename|"
    r"makedirs|mkdir|rmdir|replace|chmod)\s*\(|\bshutil\.(?:copy\w*|move|rmtree)\s*\(|writeFileSync|fs\.writeFile"
)
_PY_READ_OPEN = re.compile(r"\bopen\(\s*(?:f?r?)(['\"])(.+?)\1\s*(?:\)|,\s*['\"]r)")
_PY_SHELL = re.compile(r"\b(?:os\.system|os\.popen|subprocess\.\w+|execSync|exec)\(\s*(?:f|r)?(['\"])(.+?)(?<!\\)\1", re.S)
_PY_SHELL_LIST = re.compile(r"\bsubprocess\.\w+\(\s*\[([^\]]*)\]")


def analyze_code(code: str, _depth: int = 0) -> tuple[str, dict]:
    """Heuristic classification of an interpreter snippet."""
    detail: dict = {}
    cat = "shell_exec"
    writes: list[str] = []
    reads: list[str] = []
    if _PY_NET.search(code) or extract_urls(code):
        cat = "network"
    if cat == "network" and _PY_UPLOAD.search(code):
        cat = "network_upload"
        m = re.search(r"\.(put|post|patch)\s*\(|method\s*[=:]\s*['\"](PUT|POST|PATCH)", code, re.I)
        if m:
            detail["method"] = (m.group(1) or m.group(2)).upper()
    for m in _PY_WRITE_OPEN.finditer(code):
        writes.append(m.group(2))
    for m in _PY_FILEINPUT.finditer(code):  # fileinput.input("f.py", inplace=True) rewrites the files
        writes += [q[1] for q in re.findall(r"(['\"])(.+?)\1", m.group(1))] or ["(from code)"]
    if _PY_WRITE_OTHER.search(code) and not writes:
        writes.append("(from code)")
    for m in _PY_READ_OPEN.finditer(code):
        reads.append(m.group(2))
    inner_cmds = [m.group(2) for m in _PY_SHELL.finditer(code)]
    for m in _PY_SHELL_LIST.finditer(code):
        parts = re.findall(r"(['\"])(.*?)\1", m.group(1))
        if parts:
            inner_cmds.append(" ".join(shlex.quote(p[1]) for p in parts))
    if _depth < 4:
        for cmd in inner_cmds:
            for sub in split_commands(cmd):
                c, d = classify(sub, _depth + 1)
                if PRIORITY[c] > PRIORITY[cat]:
                    cat = c
                writes += d.get("writes", [])
                reads += d.get("reads", [])
                for k in ("method",):
                    if k in d:
                        detail[k] = d[k]
    if writes:
        detail["writes"] = _uniq(writes)
        if PRIORITY[cat] < PRIORITY["fs_write"]:
            cat = "fs_write"
    if reads:
        detail["reads"] = _uniq(reads)
        if cat == "shell_exec" and not inner_cmds and not writes:
            cat = "fs_read"
    detail.update(host_detail(code))
    if detail.get("metadata_hosts") and PRIORITY[cat] < PRIORITY["network"]:
        cat = "network"
    return cat, detail

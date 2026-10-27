"""Turn tool-call steps into classified Actions."""
from __future__ import annotations

import json
import re
import shlex
from typing import Any

from .model import Action, Step
from .shell import analyze_code, classify, host_detail, split_commands

SHELL_TOOLS = {
    "bash", "shell", "sh", "zsh", "run_shell", "run_command", "execute_command", "exec", "exec_command",
    "terminal", "run_terminal_cmd", "run_terminal_command", "execute_bash", "bash_tool", "cmd", "powershell",
    "local_shell", "shell_command", "run_bash", "execute_shell", "container.exec", "command",
}
CODE_TOOLS = {
    "run_python", "python", "execute_python", "code_interpreter", "ipython", "jupyter", "python_exec",
    "run_code", "execute_code", "run_javascript", "node",
}
FILE_EDIT_TOOLS = {
    "write", "edit", "multiedit", "str_replace_editor", "str_replace_based_edit_tool", "apply_patch",
    "write_file", "edit_file", "create_file", "notebookedit", "replace_in_file", "insert", "delete_file",
    "move_file", "patch", "file_write", "save_file", "append_file", "overwrite_file", "rename_file",
    "write_to_file", "search_replace", "update_file", "text_editor",
}
READ_TOOLS = {"read", "read_file", "view", "cat", "open_file", "get_file", "notebookread", "view_file",
              "file_read", "read_many_files"}
LIST_TOOLS = {"glob", "ls", "list_dir", "list_directory", "list_files", "find_files", "file_search",
              "list_tree", "directory_tree"}
SEARCH_TOOLS = {"grep", "search_files", "codebase_search", "search_code", "ripgrep"}
WEB_TOOLS = {
    "webfetch", "websearch", "fetch", "http_request", "http_get", "http_post", "browser", "web_search",
    "web_fetch", "fetch_url", "curl", "open_url", "browse", "search_web", "request", "get_url", "download",
    "web_browser", "browser_navigate", "navigate", "google_search", "bing_search", "url_fetch",
    "web_search_preview", "web_search_call",
}

PATH_KEYS = ("file_path", "path", "filename", "file", "target_file", "notebook_path", "filepath", "target",
             "destination", "dest", "new_path", "old_path", "source")


def norm_tool(name: str) -> str:
    n = (name or "").strip().lower()
    # MCP-style names: mcp__server__tool -> tool; dotted namespaces -> last part (except container.exec)
    if n.startswith("mcp__"):
        n = n.split("__")[-1]
    return n


def _shell_command(args: Any) -> str | None:
    if isinstance(args, str):
        return args
    if not isinstance(args, dict):
        return None
    for key in ("command", "cmd", "script", "commands", "input", "code"):
        if key in args:
            v = args[key]
            if isinstance(v, str):
                return v
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                # ["bash", "-lc", "ls -la"] is an argv; ["ls -la", "cat x"] is a list of commands.
                if v and " " not in v[0]:
                    return shlex.join(v)
                return "\n".join(v)
    return None


def _paths(args: Any) -> list[str]:
    out: list[str] = []
    if isinstance(args, dict):
        for k in PATH_KEYS:
            v = args.get(k)
            if isinstance(v, str) and v:
                out.append(v)
        for k in ("edits", "files", "paths"):
            v = args.get(k)
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        out.append(item)
                    elif isinstance(item, dict):
                        out += _paths(item)
        for k in ("input", "patch", "diff", "content"):
            v = args.get(k)
            if isinstance(v, str) and "*** " in v:
                out += _patch_paths(v)
    elif isinstance(args, str) and "*** " in args:
        out += _patch_paths(args)
    return list(dict.fromkeys(out))


def _patch_paths(text: str) -> list[str]:
    return re.findall(r"^\*\*\* (?:Update|Add|Delete) File: (.+?)\s*$", text, re.M) + \
        re.findall(r"^\*\*\* Move to: (.+?)\s*$", text, re.M)


def _args_text(args: Any) -> str:
    if isinstance(args, str):
        return args
    try:
        return json.dumps(args, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(args)


def actions_for_step(step: Step) -> list[Action]:
    """Classify one action step into one or more Actions."""
    tool = step.tool or "tool"
    t = norm_tool(tool)
    args = step.args
    actions: list[Action] = []

    def add(raw, category, detail):
        actions.append(Action(step.index, len(actions) + 1, tool, raw, category, detail))

    cmd = _shell_command(args) if (t in SHELL_TOOLS or t.endswith("shell") or t.endswith("bash")) else None
    if cmd is not None:
        subs = split_commands(cmd)
        for sub in subs:
            cat, detail = classify(sub)
            detail["shell"] = True
            add(sub, cat, detail)
        if not subs:
            add(cmd.strip(), "shell_exec", {"shell": True})
        return actions

    raw = _args_text(args)
    if t in CODE_TOOLS:
        code = args.get("code") or args.get("source") or args.get("input") if isinstance(args, dict) else args
        code = code if isinstance(code, str) else raw
        cat, detail = analyze_code(code)
        detail["code"] = True
        add(code.strip(), cat, detail)
        return actions

    if t in FILE_EDIT_TOOLS:
        paths = _paths(args)
        sub = args.get("command") if isinstance(args, dict) else None
        if t in ("str_replace_editor", "str_replace_based_edit_tool", "text_editor") and sub == "view":
            add(raw, "fs_read", {"reads": paths})
        else:
            add(raw, "fs_write", {"writes": paths or ["(unknown)"], "edit_tool": True})
        return actions

    if t in READ_TOOLS:
        add(raw, "fs_read", {"reads": _paths(args)})
        return actions
    if t in LIST_TOOLS:
        add(raw, "fs_list", {"paths": _paths(args)})
        return actions
    if t in SEARCH_TOOLS:
        add(raw, "fs_read", {"reads": _paths(args) or ["(search)"]})
        return actions

    if t in WEB_TOOLS or t.startswith(("web", "http", "browser")):
        detail = host_detail(raw)
        method = (args.get("method") if isinstance(args, dict) else None) or "GET"
        method = str(method).upper()
        detail["method"] = method
        detail["web_tool"] = True
        upload = method in ("PUT", "POST", "PATCH") or (isinstance(args, dict) and any(
            k in args for k in ("body", "data", "json", "files", "upload")))
        add(raw, "network_upload" if upload else "network", detail)
        return actions

    detail = host_detail(raw)
    add(raw, "tool_call", detail)
    return actions


def actions_for_trace(steps: list[Step]) -> list[Action]:
    out: list[Action] = []
    for s in steps:
        if s.kind == "action":
            out.extend(actions_for_step(s))
    return out


def is_write(action: Action) -> bool:
    if action.category in ("fs_write", "network_upload", "privilege"):
        return True
    if action.detail.get("writes"):
        return True
    return norm_tool(action.tool) in FILE_EDIT_TOOLS

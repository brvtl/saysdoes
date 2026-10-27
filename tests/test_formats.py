import pytest

from saysdoes.formats import ParseError, load, load_text
from saysdoes.tools import actions_for_trace

from conftest import fixture_path


def kinds(trace):
    return [s.kind for s in trace.steps]


def test_cohere_pi():
    t = load(fixture_path("cohere_pi_small.jsonl"))
    assert t.format == "cohere-pi"
    assert t.model == "synthetic-model"
    # blank "\n\n" text block is dropped; toolResult attached, not a step
    assert kinds(t) == ["system", "user", "reasoning", "action", "text"]
    assert t.steps[3].tool == "bash" and t.steps[3].result == "Linux box"
    acts = actions_for_trace(t.steps)
    assert [a.ref for a in acts] == ["4.1", "4.2"]
    assert [a.category for a in acts] == ["env_probe", "network"]


def test_qwen_chatml():
    t = load(fixture_path("qwen_chatml_small.txt"))
    assert t.format == "qwen-chatml"
    assert kinds(t) == ["system", "user", "reasoning", "action", "reasoning", "text"]
    assert t.steps[3].tool == "bash"
    assert t.steps[3].args["command"].strip().startswith("cat README.md")
    assert t.steps[3].result == "# Project"
    # tool_response user message is not a new user turn
    assert t.steps[4].turn == t.steps[3].turn


def test_qwen_chatml_json_tool_call():
    text = ('<|im_start|>user\nhi<|im_end|>\n<|im_start|>assistant\n<think>\nok\n</think>\n'
            '<tool_call>\n{"name": "bash", "arguments": {"command": "ls"}}\n</tool_call><|im_end|>')
    t = load_text(text)
    assert t.steps[-1].tool == "bash" and t.steps[-1].args == {"command": "ls"}


def test_openai_chat():
    t = load(fixture_path("openai_chat.json"))
    assert t.format == "openai"
    assert t.model == "synthetic-gpt"
    assert kinds(t) == ["system", "user", "reasoning", "action", "action", "text"]
    assert t.steps[3].args == {"path": "docs/intro.md", "content": "Hello"}
    assert t.steps[4].result == "ok"


def test_openai_responses():
    t = load(fixture_path("openai_responses.json"))
    assert t.format == "openai"
    assert kinds(t) == ["user", "reasoning", "action", "text"]
    assert t.steps[2].tool == "web_search" and t.steps[2].result == "4"


def test_anthropic():
    t = load(fixture_path("anthropic_messages.json"))
    assert t.format == "anthropic"
    assert kinds(t) == ["system", "user", "reasoning", "action", "action", "text"]
    assert [s.result for s in t.steps if s.kind == "action"] == ["a.py\nb.py", "2"]
    assert len({s.turn for s in t.steps if s.kind != "system"}) == 1


def test_claude_code():
    t = load(fixture_path("claude_code_stream.jsonl"))
    assert t.format == "claude-code"
    assert t.model == "synthetic-claude-code"
    assert kinds(t) == ["system", "user", "reasoning", "action", "action", "text"]
    assert [s.tool for s in t.steps if s.kind == "action"] == ["Read", "Write"]
    assert t.meta["result"]["num_turns"] == 3


@pytest.mark.parametrize("name,fmt", [
    ("cohere_pi_small.jsonl", "cohere-pi"),
    ("qwen_chatml_small.txt", "qwen-chatml"),
    ("openai_chat.json", "openai"),
    ("openai_responses.json", "openai"),
    ("anthropic_messages.json", "anthropic"),
    ("claude_code_stream.jsonl", "claude-code"),
])
def test_autodetect_and_explicit(name, fmt):
    assert load(fixture_path(name)).format == fmt
    assert load(fixture_path(name), fmt).format == fmt


def test_parse_errors():
    with pytest.raises(ParseError):
        load_text("")
    with pytest.raises(ParseError):
        load_text("just some prose, not a trace")
    with pytest.raises(ParseError):
        load_text("plain text", "openai")
    with pytest.raises(ParseError):
        load_text('{"messages": []}', "anthropic")

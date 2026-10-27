import os
import socket
import urllib.request

import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fixture_path(name: str) -> str:
    return os.path.join(FIXTURES, name)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests must never touch the network."""
    def blocked(*a, **k):
        raise AssertionError("network access attempted during tests")

    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def no_claude_cli(monkeypatch):
    """Tests must never run the real `claude` CLI; judge tests inject a fake runner."""
    from saysdoes import judge

    def blocked(*a, **k):
        raise AssertionError("real claude CLI invoked during tests")

    monkeypatch.setattr(judge, "subprocess_runner", blocked)
    monkeypatch.setenv("CLAUDE_BIN", "/nonexistent/claude-for-tests")

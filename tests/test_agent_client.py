"""agent/client.py: 呼べない・切れた返事は使わず None（呼び出し側が規則に戻る）。本物の API は呼ばない（偽物に差し替える）。"""
from types import SimpleNamespace

import anthropic

from agent import client


class _FakeMessages:
    def __init__(self, result):
        self.result = result

    def create(self, **kw):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _use_fake(monkeypatch, tmp_path, result):
    monkeypatch.setenv("MAAI_ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MAAI_OFFLINE", "0")
    monkeypatch.setattr(client, "LOG_DIR", tmp_path)
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: SimpleNamespace(messages=_FakeMessages(result)))


def _msg(text, stop="end_turn"):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop)


def test_complete_json_is_returned(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path, _msg('{"ok": 1}'))
    assert client.ask_json("structure", "s", {"a": 1}) == {"ok": 1}
    assert any(p.name.endswith(".request.json") for p in tmp_path.iterdir())


def test_truncated_reply_is_not_used(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path, _msg('{"labels": [', stop="max_tokens"))
    assert client.ask_json("structure", "s", {"a": 1}) is None
    assert any(p.name.endswith(".error.txt") for p in tmp_path.iterdir())


def test_api_error_falls_back(monkeypatch, tmp_path):
    class _Err(anthropic.APIError):     # 型だけ API エラー。HTTP の中身は要らない
        def __init__(self):
            Exception.__init__(self, "model not found")
    _use_fake(monkeypatch, tmp_path, _Err())
    assert client.ask_json("propose", "s", {"a": 1}) is None
    assert any(p.name.endswith(".error.txt") for p in tmp_path.iterdir())

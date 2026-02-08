from src.utils import make_session_key


def test_session_key_is_deterministic():
    a = make_session_key("codex_history", "/tmp/x.jsonl", "s1")
    b = make_session_key("codex_history", "/tmp/x.jsonl", "s1")
    assert a == b

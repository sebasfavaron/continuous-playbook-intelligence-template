from src.signals import extract_tool_signals


def test_extract_tool_signals_basic():
    text = "Run git status, then pytest -q, then deploy to aws"
    signals = extract_tool_signals(text)
    assert "git" in signals
    assert "pytest" in signals
    assert "aws" in signals

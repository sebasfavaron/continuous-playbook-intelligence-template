from src.cpi.sanitize import sanitize_payload


def test_sanitize_redacts_sensitive_fields_and_paths():
    payload = {
        "email": "dev@example.com",
        "path": "/Users/sebas/private/repo/file.txt",
        "token": "mytokenvalue1234567890",
    }
    cleaned, report = sanitize_payload(payload, salt="test-salt")
    assert cleaned["email"] == "[REDACTED_EMAIL]"
    assert cleaned["path"].startswith("anon_")
    assert cleaned["token"] == "[REDACTED_FIELD]"
    assert report.redacted_fields >= 2


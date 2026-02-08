# Anonymization and Secret Leakage Policy

## Required before commit

1. Run `sanitize` on contribution artifacts.
2. Run `validate` on sanitized artifacts.
3. Run `precommit-check` on repository root.

## Hard rules

- Do not commit raw conversation transcripts.
- Do not commit absolute user paths.
- Do not commit credentials, tokens, or secrets.
- Use pseudonymized identifiers for session/run references.

## Redaction behavior

- Emails and IPs are replaced with placeholders.
- Absolute paths are replaced with `$HOME` / `$WORKSPACE` placeholders.
- Sensitive fields (`token`, `password`, `api_key`, etc.) are redacted.
- Secret-like strings are replaced with `[REDACTED_SECRET]`.

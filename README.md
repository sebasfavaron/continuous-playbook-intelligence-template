# Continuous Playbook Intelligence Template

Privacy-first template for building a continuously improving playbook system from explicit, local, opt-in mining.

## Principles

- Explicit opt-in only: users choose to run mining locally.
- Never commit raw transcripts.
- Sanitize and validate artifacts before commit.
- Feedback is explicit and committed as versioned data.
- Suggest-first by default; execution requires explicit command.

## CLI

All commands use `python -m src.main ...`.

### 1) Mine local history (opt-in)

```bash
python -m src.main mine --days 30 --out out/backlog.json
```

Legacy compatibility is preserved:

```bash
python -m src.main --days 30 --out out/backlog.json
```

### 2) Build candidate bundle from mining output

```bash
python -m src.main candidates build --from out/backlog.json --out candidates/new-bundle.json
```

### 3) Sanitize candidate bundle

```bash
python -m src.main sanitize --in candidates/new-bundle.json --out candidates/new-bundle.sanitized.json
```

### 4) Validate schema

```bash
python -m src.main validate --file candidates/new-bundle.sanitized.json --schema candidate_bundle
```

### 5) Publish candidate artifact in repo

```bash
python -m src.main candidates publish --in candidates/new-bundle.sanitized.json --dest-dir candidates/published
```

### 6) Suggest playbooks

```bash
python -m src.main playbooks suggest --task "tests are failing after refactor" --pretty
```

### 7) Run playbook (plan first, explicit execute)

Plan mode:

```bash
python -m src.main playbooks run \
  --playbook-id repo_triage_v1 \
  --repo /path/to/repo \
  --out runs/run-plan.json
```

Execute mode:

```bash
python -m src.main playbooks run \
  --playbook-id repo_triage_v1 \
  --repo /path/to/repo \
  --out runs/run-exec.json \
  --execute
```

### 8) Create feedback artifact from a run

```bash
python -m src.main playbooks feedback \
  --run runs/run-exec.json \
  --out feedback/feedback.json \
  --outcome success \
  --rating 4 \
  --notes "Resolved after rerunning tests and fixing imports."
```

### 9) Pre-commit policy check

```bash
python -m src.main precommit-check --path .
```

## Git workflow (explicit and versioned)

1. Run mine/build/sanitize/validate locally.
2. Review generated diffs.
3. Run precommit checks.
4. Commit and push artifacts.
5. Open PR for review.

## Included template assets

- Starter playbook: `playbooks/repo_triage_v1.json`
- Built-in validators:
  - `candidate_bundle`
  - `playbook_spec`
  - `run_record`
  - `feedback_record`
- Schema stubs in `schemas/`


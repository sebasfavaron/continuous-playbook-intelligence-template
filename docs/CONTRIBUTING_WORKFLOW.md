# Opt-in Contribution Workflow

## Candidate contribution

1. `python -m src.main mine --days 30 --out out/backlog.json`
2. `python -m src.main candidates build --from out/backlog.json --out candidates/bundle.json`
3. `python -m src.main sanitize --in candidates/bundle.json --out candidates/bundle.sanitized.json`
4. `python -m src.main validate --file candidates/bundle.sanitized.json --schema candidate_bundle`
5. `python -m src.main candidates publish --in candidates/bundle.sanitized.json --dest-dir candidates/published`
6. `python -m src.main precommit-check --path .`
7. Commit and open PR.

## Feedback contribution

1. Run a playbook with explicit command.
2. Generate feedback artifact:
   `python -m src.main playbooks feedback --run runs/run.json --out feedback/feedback.json --outcome success --rating 4`
3. Validate and precommit-check.
4. Commit and open PR.

All contributions are explicit opt-in and local-first.

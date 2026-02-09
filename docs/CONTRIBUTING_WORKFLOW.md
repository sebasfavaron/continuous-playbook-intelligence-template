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

## Multi-repo state restore (after feature completion)

If `feature_lifecycle_multirepo_v1` ran `snapshot_local_changes`, restore prior local staged/unstaged/untracked state with the stash snapshot created per repo.
State snapshots are persisted in:
`.cpi-state/<feature-branch>/<repo>.pre-state.txt` and `.cpi-state/<feature-branch>/<repo>.stash-meta.txt`

1. Locate snapshot stash entries:
   `git -C <repo_path> stash list --date=local | rg "cpi-pre-branch-<feature-branch>"`
2. Restore without dropping snapshot:
   `git -C <repo_path> stash apply stash@{N}`
3. Restore and drop snapshot:
   `git -C <repo_path> stash pop stash@{N}`
4. Verify non-branch git state after restore:
   `git -C <repo_path> status --short --branch`
5. Verify upstream tracking and divergence:
   `git -C <repo_path> rev-parse --abbrev-ref --symbolic-full-name @{u}`
   `git -C <repo_path> rev-list --left-right --count @{u}...HEAD`
6. Verify submodules and worktrees where relevant:
   `git -C <repo_path> submodule status`
   `git -C <repo_path> worktree list`
7. Verify no in-progress git operations remain:
   check `.git/rebase-merge`, `.git/rebase-apply`, `.git/MERGE_HEAD`, `.git/CHERRY_PICK_HEAD`

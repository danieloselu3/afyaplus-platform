# Contributing to afyaplus-platform

## Branches
- `main` is always releasable. All tests pass and every commit on it could be tagged.
- Work on short-lived branches cut from `main`: `feature/<short-description>`, `hotfix/<short-description>`, or `docs/<short-description>`.
- A branch lives **at most 2 working days**. If it needs longer, split the work.
- Merge with `git merge --no-ff` so the log shows which commits shipped together. Delete the branch after merging.
- Never commit `.env`, keys or tokens. `.gitignore` blocks `.env`. Secrets are injected at runtime only.

## Versions (semantic versioning, `MAJOR.MINOR.PATCH`)
`config.VERSION` is the single source; `/health` reports it.
- **PATCH** fixes something without changing the API agreement. *Example:* tightening the `check_stock` docstring so the agent stops treating a clinic name as a county filter.
- **MINOR** adds a backwards-compatible capability. *Example:* 1.1.0 added the agent API and the shared `/token` router; existing `/triage` callers changed nothing.
- **MAJOR** breaks the agreement, and callers must adapt. *Example:* renaming `patient_message` in `TriageRequest`, or removing `/triage`.

## Releases
1. Bump `VERSION` in `config.py` on a branch, merge, then tag on `main`:
   `git tag -a vX.Y.Z -m "..."`.
2. Build images with the **same** number: `afyaplus-triage:X.Y.Z` and `afyaplus-agent:X.Y.Z` (`docker compose build`).
3. **Git tag = image tag = `/health` version.** Tags are immutable. Never rebuild or re-push an existing tag; a fix is a new PATCH.
4. To see the code behind any running image: `git checkout vX.Y.Z`.

## When a merge conflict appears
1. **Read both sides.** Everything between `<<<<<<<` and `=======` is the branch you are on; everything down to `>>>>>>>` is the incoming branch. Find out *why* each side changed the line.
2. **Edit to the one version you actually want.** Often that keeps both intents. Delete all three marker lines, then `git add` the file.
3. **Prove it still works before committing:** run `python -m pytest -q` and start the service. Then `git commit` and say in the message how you resolved it. *This is the step people skip and regret.*

Worked example: [evidence/06_merge_conflict.txt](evidence/06_merge_conflict.txt).

# Git Workflow

JAVA2GO uses small, reviewable Git changes. Agents must protect user work and avoid surprise commits, pushes, merges, or history rewrites.

## Safety Rules

- Never commit unless the user explicitly asks.
- Never push unless the user explicitly asks.
- Never merge unless the user explicitly asks.
- Never tag releases unless the user explicitly asks.
- Never force-push unless the user explicitly asks and confirms the target branch.
- Never amend commits or rewrite history unless explicitly requested.
- Never discard, reset, checkout, or revert user changes unless explicitly requested.
- Never commit secrets, `.env` files, credentials, API keys, private logs, generated temporary files, or unrelated workspace changes.

## Branch Strategy

- `main` is the stable branch.
- Use `feature/<name>` for product, engine, or frontend features.
- Use `fix/<name>` for bug fixes.
- Use `docs/<name>` for documentation-only changes.
- Use `chore/<name>` for configuration, tooling, or maintenance changes.

## Before Editing

- Check `git status --short` when the task involves commits, branches, releases, or PRs.
- If unrelated changes are present, leave them untouched.
- If unrelated changes are in files needed for the current task, read carefully and work around them when possible.
- If existing changes directly conflict with the task, ask the user how to proceed.

## Before Commit

- Review `git status --short`.
- Review `git diff` for unstaged changes and `git diff --staged` for staged changes.
- Stage only files related to the current task.
- Do not stage broad directories unless every included file was reviewed.
- Do not include secrets, environment files, temporary directories, generated private data, or unrelated changes.
- Use a concise commit message focused on why the change exists.

## Commit Message Style

Prefer short, conventional messages:

- `feat: add class conversion reporting`
- `fix: preserve unsupported exception status`
- `test: add regression coverage for interface methods`
- `docs: add conversion rule template`
- `chore: update opencode instructions`

Use these prefixes when they fit:

- `feat:` for user-visible functionality.
- `fix:` for bug fixes.
- `test:` for tests and regression coverage.
- `docs:` for documentation-only changes.
- `refactor:` for behavior-preserving code structure changes.
- `chore:` for tooling, configuration, or maintenance.

## Before Push

- Confirm the current branch.
- Confirm recent commits with `git log --oneline -5`.
- Confirm the branch is not `main` unless the user explicitly wants to push `main`.
- Confirm no secrets or unrelated files are included.
- Push only after explicit user approval.
- Use `git push -u origin <branch-name>` for first push of a new branch.
- Use `git push` for later pushes after upstream is set.

## Pull Requests

Pull requests should include:

- Summary of changes.
- Verification performed.
- Tests not run and why.
- Known limitations or follow-up work.

Use this template:

```md
## Summary

- <What changed>
- <Why it changed>

## Verification

- <Tests or checks run>
- <Tests not run and why>

## Notes

- <Known limitations, risks, or follow-up work>
```

## Agent Behavior

Agents may:

- Run read-only Git commands such as `git status`, `git diff`, `git diff --staged`, `git log`, and `git branch --show-current`.
- Suggest branch names and commit messages.
- Prepare a PR summary.

Agents must ask before:

- Creating commits.
- Pushing branches.
- Merging branches.
- Tagging releases.
- Rewriting history.
- Discarding changes.

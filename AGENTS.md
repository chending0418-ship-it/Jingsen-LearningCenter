# Repository maintenance rules

## Changelog is mandatory

- After every material feature, bug fix, behavior change, data/schema migration, deployment, infrastructure change, or production incident, update `CHANGELOG.md` in the same task without waiting for the user to ask.
- Add the newest entry at the top and record the date, motivation, user-visible result, important implementation or operational details, validation performed, and any follow-up risk.
- Never place passwords, API keys, private keys, session secrets, or other credentials in the changelog.
- Documentation-only edits whose sole purpose is maintaining `CHANGELOG.md` do not require another recursive changelog entry.

## Production releases must go through a PR

- The release target is `deploy/tencent-learningcenter-path`. Leave `main` unchanged unless the user explicitly requests work on it.
- Start each feature, fix, migration, deployment-script change, or release-documentation update from the latest release branch in a separate `codex/` branch.
- Push only the working branch and open a PR with base `deploy/tencent-learningcenter-path`. Never push commits directly to the release branch, force-push it, or merge into it locally and push the result.
- Complete appropriate validation and update `CHANGELOG.md` before requesting review. Record the PR URL, tested commit, data/migration impact, and rollback plan.
- Deploy only after the PR has been merged through GitHub. Verify the deployed commit is the merged PR result on the release branch; never deploy an unmerged feature branch or uncommitted local files. PR creation alone does not authorize merging or deployment.
- Preserve the existing production data backup, migration, validation, and health-check procedure in `updateNew.md`; do not overwrite server `data/` or `.env` with local copies.
- Historical changes already present in the release branch are recorded as retrospective evidence, not replayed or represented as having received prior PR approval.

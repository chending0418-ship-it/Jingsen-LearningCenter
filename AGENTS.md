# Repository maintenance rules

## Changelog is mandatory

- After every material feature, bug fix, behavior change, data/schema migration, deployment, infrastructure change, or production incident, update `CHANGELOG.md` in the same task without waiting for the user to ask.
- Add the newest entry at the top and record the date, motivation, user-visible result, important implementation or operational details, validation performed, and any follow-up risk.
- Never place passwords, API keys, private keys, session secrets, or other credentials in the changelog.
- Documentation-only edits whose sole purpose is maintaining `CHANGELOG.md` do not require another recursive changelog entry.

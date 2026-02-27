---
name: fix-issue
description: Fetch a GitHub issue, analyze it, fix it, and open a PR
---

# Fix Issue #$ARGUMENTS

1. Fetch issue details: `gh issue view $ARGUMENTS --json title,body,labels,comments`
2. Analyze the issue and identify the relevant code area in `src/`
3. Implement the fix
4. Write/update tests in `tests/` for the fix
5. Verify all tests pass: `pytest`
6. Run linting: `ruff check src/ tests/ && python -m mypy src/`
7. Commit with: `fix: resolves #$ARGUMENTS - [short description]`
8. Open a PR: `gh pr create --title "fix: #$ARGUMENTS [title]" --body "Fixes #$ARGUMENTS"`

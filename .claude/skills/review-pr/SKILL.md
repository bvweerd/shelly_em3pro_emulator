---
name: review-pr
description: Thoroughly review a pull request
---

# Review PR $ARGUMENTS

1. Fetch PR diff: `gh pr diff $ARGUMENTS`
2. Fetch PR details: `gh pr view $ARGUMENTS --json title,body,files,reviews`
3. Analyze:
   - Correctness of the implementation
   - Test coverage (are there tests for the changes in `tests/`?)
   - Code style (ruff-clean, type-annotated, structlog for logging)
   - Async correctness (no blocking I/O in async context)
   - Modbus register correctness if register_map.py is touched
   - Protocol compatibility (Shelly Gen2 API compliance)
   - Breaking changes to config schema or Docker setup
4. Write review comments as a markdown list
5. Post comments via: `gh pr review $ARGUMENTS --comment --body "[your review]"`

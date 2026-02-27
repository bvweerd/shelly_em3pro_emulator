---
name: run-tests
description: Run the full test suite and provide a summary
---

# Run Tests

1. Run all tests: `pytest 2>&1`
2. Summary: how many tests passed / failed / skipped
3. On failure: show only the FAILED/ERROR lines with context and the relevant traceback
4. If flaky asyncio tests fail: re-run with `pytest --timeout=30` to rule out timing issues
5. For coverage: `pytest --cov=src --cov-report=term-missing 2>&1`
6. Suggest fixes for repeated failures based on the error messages

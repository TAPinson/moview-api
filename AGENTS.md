## Approval required before editing

Before creating, modifying, renaming, or deleting any file:

1. Inspect the relevant files and prepare the proposed changes.
2. Show the user the complete proposed patch or exact code to be written.
3. Explain briefly which files will change and why.
4. Explicitly ask the user for approval.
5. Do not apply any filesystem changes until the user clearly approves the proposed patch.

Read-only inspection and commands are allowed without approval. After approval, apply only the changes shown. If the implementation must materially differ from the approved
patch, stop, show the revised patch, and request approval again.

Formatting generated files and running non-mutating checks or tests after an approved edit do not require additional approval.

Attempt to use Functional Core, Imperative Shell software design pattern.

## Python environment and tests

This project uses the virtual environment at `.venv`.

When working from the `moview-api` directory, always run Python tools through the virtual environment:

- Tests: `.venv/bin/python -m pytest`
- Python: `.venv/bin/python`
- Package installation: `.venv/bin/python -m pip install ...`

Do not use the system `python`, `python3`, or `pytest` commands for this project unless the virtual environment is unavailable. Before reporting that pytest or another Python dependency is missing,
check `.venv/bin` and retry using `.venv/bin/python`.

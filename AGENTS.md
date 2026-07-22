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

# Development Workflow

For each task:

1. Inspect the relevant existing files.
2. Explain the intended approach briefly.
3. Implement the smallest coherent change.
4. Run relevant tests/checks.
5. Inspect the result for obvious errors.
6. Report changed files and verification results.

## Execution and verification discipline

- Prefer the inspect → implement → test → fix loop over prolonged speculative reasoning.
- If a technical question can be answered safely by running a local command, test, or inspection, prefer empirical verification over extended speculation.
- Keep reasoning proportional to task complexity. For small implementation tasks, implement the smallest coherent change and verify it immediately.
- Verify each meaningful change with the smallest relevant test/check. Do not rerun expensive checks unnecessarily.

## Task scope

- Follow the scope explicitly defined by the current task.
- Do not expand small tasks into unrelated refactoring.
- Record useful future improvements as suggestions rather than implementing them.
- Prefer small, coherent diffs.
- Do not begin large-scale implementation unless explicitly instructed.

## Failure handling

When something fails:

1. Read the actual error.
2. Identify the smallest likely cause.
3. Perform targeted verification if necessary.
4. Apply the smallest appropriate fix.
5. Rerun the affected verification.
6. Continue only after the result is verified.

Avoid broad speculative investigation unless the evidence requires it.

When uncertain about an important decision, ask rather than guessing.

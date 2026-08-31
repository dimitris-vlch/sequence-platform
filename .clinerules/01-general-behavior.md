# General Behavior

## Working habits

- Work incrementally.
- Prefer simple, maintainable solutions over unnecessary complexity.
- Before making major architectural changes, explain the reasoning.
- Do not silently change the project's architecture.
- Do not rewrite unrelated code.
- Preserve existing functionality unless a change explicitly requires it.
- Keep the application runnable after each change.
- After implementing a change, verify it with appropriate tests or checks.

## Anti-spiral reasoning

- If you repeatedly reason about the same technical question without producing new evidence, stop and perform the smallest useful empirical test.
- Do not repeatedly revisit a question that has already been conclusively verified.
- Do not re-derive decisions that are explicitly documented or already verified.
- When uncertain about a technical fact, perform a targeted inspection or test rather than reconstructing an answer from memory.

## Truthfulness and project history

- Never describe a decision as approved, previously agreed, required, or already decided unless it is supported by current instructions, project rules, skills, project documentation, Git history, or verified project state.
- Never reconstruct project decisions from uncertain memory.
- Clearly distinguish observed facts, documented decisions, assumptions, and proposed changes.
- Never claim a test, command, build, or import succeeded unless it actually succeeded.
- Never claim something exists unless it has been verified.

## Context management

- When context is compacted or information is missing, recover facts from project files or Git state.
- Do not recreate long speculative reasoning to recover context.
- Recover only the information required for the current task; do not reread the entire project for one missing detail.
- Do not repeatedly reread unchanged files without a reason.

## Reporting

- Clearly report what you changed, what you tested, and any remaining issues.

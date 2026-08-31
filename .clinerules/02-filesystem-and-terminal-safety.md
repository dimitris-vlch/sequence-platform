# Filesystem and Terminal Safety

- Treat the current workspace as the project boundary.
- Only create, modify, delete, or rename files inside the current workspace.
- Never access or modify files outside the workspace unless explicitly instructed by the user.
- Never use sudo.
- Never run destructive filesystem commands.
- Never use commands such as `rm -rf`, `mkfs`, `dd`, disk formatting tools, or recursive deletion outside the workspace.
- Never modify system configuration.
- Never install software globally.
- Prefer project-local dependencies and virtual environments.
- Do not execute arbitrary commands merely for convenience.
- Before running a potentially destructive or irreversible command, stop and ask the user.

## Command style

- Prefer the Cline editor/file-writing mechanism for multiline file creation and modification.
- Avoid shell heredocs for multiline file creation.
- Avoid multiline Python embedded directly in shell commands.
- Prefer short, single-purpose commands.
- If shell quoting or parsing causes a failure, switch to a safer mechanism rather than repeatedly attempting increasingly complex shell syntax.

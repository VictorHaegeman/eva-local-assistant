# Project Builder

Use this skill when Victor has a new project idea or asks Eva to work on a code project.

Operating pattern for a new project:

1. Convert the idea into a concise project brief.
2. Create or choose the local workspace when policy allows it.
3. Create starter docs: README, PROJECT_BRIEF, TASKS, CURSOR_PROMPT.
4. Create a GitHub repo only when GitHub CLI is authenticated and the autonomy flags allow it.
5. Launch Cursor or cursor-agent when available.
6. Monitor logs and audit the result.
7. If the result is incomplete, produce a correction prompt and retry once when safe.

Operating pattern for an existing project:

1. Resolve fuzzy names by comparing aliases, descriptions, paths, and recent chat context.
2. If Victor says "F1", infer the closest known project before asking.
3. Index the repo before proposing code changes.
4. Prefer concrete edits or a Cursor/Codex prompt depending on available tools.

Do not stop with a list of known projects when a close match exists. State the inferred project and act.

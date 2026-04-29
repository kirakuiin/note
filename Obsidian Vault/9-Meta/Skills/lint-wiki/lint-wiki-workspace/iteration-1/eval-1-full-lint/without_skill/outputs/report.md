# Baseline (without lint-wiki skill) ¡ª Eval 1

Without the skill, the agent would:
- Not know the 12 check categories
- Not know to order by severity (Critical > Warning > Suggestion)
- Not know to check TAGS.md for wild tags and redline leaks
- Not know the auto-fix policy (only frontmatter defaults)
- Not know to append to _log.md after fixes
- Might modify files without confirmation

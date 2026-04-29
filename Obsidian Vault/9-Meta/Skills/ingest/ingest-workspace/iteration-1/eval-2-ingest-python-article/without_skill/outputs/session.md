# Baseline (without ingest skill) ¡ª Eval 2

Without the ingest skill, the agent would:
- Not know to distinguish session file vs wiki page
- Might write the article content directly as a wiki page, skipping the session record
- Not know the standard frontmatter fields (area, visibility, wiki_pages_touched)
- Not know to propose wiki updates as a separate step after session creation
- Not know to use TAGS.md for tag selection

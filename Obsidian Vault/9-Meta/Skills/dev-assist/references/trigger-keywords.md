---
area: meta
visibility: public
---
# Trigger Keywords

Phase 1 token extraction is implemented by `scripts/dev_assist_probe.py`.
Agents must call the script instead of hand-writing tokens or `rg` commands.

## What The Script Extracts

- Code identifiers from task text and path strings: snake_case, CamelCase, file stems.
- Chinese phrases from task text: 3-12 character chunks split by configured stopwords.
- Configured synonym expansions from `probe-rules.json`.

The script caps tokens at 8, runs one ripgrep pass against wiki roots, captures UTF-8 output,
and normalizes Windows `\` paths to `/`.

## Configuration

Edit `references/probe-rules.json` for retrieval behavior:

- `synonym_groups`: expression variants such as `施放/施法/释放/使用`.
- `phrase_stopwords`: words used to split long Chinese runs into useful phrases.
- `phrase_boost_terms`: suffixes or concepts that make a phrase more likely to be useful.
- `noise_tokens`: generic terms that should never be probe tokens.

Keep business-specific page relevance in wiki aliases/frontmatter when possible. Use JSON rules
only for reusable retrieval mechanics, not one-off page keywords.

## Change Protocol

When changing retrieval behavior:

1. Add or update a focused case in `scripts/test_probe.py`.
2. Update `probe-rules.json` or the generic extractor.
3. Run `python scripts/test_probe.py`.
4. Run the CLI probe once on the original miss text and confirm the expected page appears.

Do not add `_index.md` navigation rescue here; that is a separate design choice.

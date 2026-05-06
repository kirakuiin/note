---
name: obsidian-cli
description: Interact with Obsidian vaults using the Obsidian CLI to read, create, search, and manage notes, tasks, properties, and more. Also supports plugin and theme development with commands to reload plugins, run JavaScript, capture errors, take screenshots, and inspect the DOM. Use when the user asks to interact with their Obsidian vault, manage notes, search vault content, perform vault operations from the command line, or develop and debug Obsidian plugins and themes.
visibility: public
area: meta
---
# Obsidian CLI

Use the `obsidian` CLI to interact with a running Obsidian instance. Requires Obsidian to be open.

## Command reference

Run `obsidian help` to see all available commands. This is always up to date. Full docs: https://help.obsidian.md/cli

## Syntax

**Parameters** take a value with `=`. Quote values with spaces:

```bash
obsidian create name="My Note" content="Hello world"
```

**Flags** are boolean switches with no value:

```bash
obsidian create name="My Note" silent overwrite
```

For multiline content use `\n` for newline and `\t` for tab.

## File targeting

Many commands accept `file` or `path` to target a file. Without either, the active file is used.

- `file=<name>` — resolves like a wikilink (name only, no path or extension needed)
- `path=<path>` — exact path from vault root, e.g. `folder/note.md`

### Path separators (Windows)

`path=` expects **forward slashes**, regardless of OS. On Windows:

- ✅ `path=Netease/2-Wiki/page.md`
- ❌ `path=Netease\2-Wiki\page.md` — CLI replies `File not found` silently through some shells
- ❌ `path=./Netease/...` — leading `./` also rejected

Convert Windows file paths before passing them:

```powershell
# PowerShell — the safe form
$rel = $file.FullName.Substring($vaultRoot.Length + 1).Replace('\', '/')
& $obsidian property:remove name=created path=$rel
```

### Shell pitfalls: batch loops through CLI wrappers

When running many `obsidian ...` calls from a loop, **write a standalone
script file** (e.g., a `.ps1` or `.sh`) and execute that, rather than
nesting commands through multiple shell layers (cmd → PowerShell → CLI).

Why: backslash / quote escaping can get silently mangled across layers.
The symptom is "`File not found`" errors even though the files exist,
because the replaced path doesn't reach the CLI in the form you wrote.

```powershell
# ❌ Fragile: cmd → powershell -Command "... .Replace('\','/') ..."
#   The outer cmd may eat one layer of backslashes before PowerShell parses.

# ✅ Robust: put the logic in a .ps1 file, call that file once.
powershell -NoProfile -ExecutionPolicy Bypass -File cleanup.ps1
```

If you must one-liner, verify one call interactively first
(`obsidian <cmd> path=foo/bar.md` directly) to confirm the path format
the CLI accepts, then scale up.

## Vault targeting

Commands target the most recently focused vault by default. Use `vault=<name>` as the first parameter to target a specific vault:

```bash
obsidian vault="My Vault" search query="test"
```

## Common patterns

```bash
obsidian read file="My Note"
obsidian create name="New Note" content="# Hello" template="Template" silent
obsidian append file="My Note" content="New line"
obsidian search query="search term" limit=10
obsidian daily:read
obsidian daily:append content="- [ ] New task"
obsidian property:set name="status" value="done" file="My Note"
obsidian tasks daily todo
obsidian tags sort=count counts
obsidian backlinks file="My Note"
```

Use `--copy` on any command to copy output to clipboard. Use `silent` to prevent files from opening. Use `total` on list commands to get a count.

## Append vs eval — choosing the right edit primitive

`obsidian append` is the cheap path but has a hard limitation:

- **`obsidian append` always lands content at the absolute end of the file.**
  This is fine when the target's last section is genuinely append-friendly
  (e.g., chronological logs, free-form note bottoms, "## 相关" sections
  by convention). It is **wrong** when the file ends with a closing
  section that must remain last (e.g., `## 相关`, `## See also`,
  navigation footers), or when you need to insert into a structured
  region (table mid/end, YAML frontmatter, between two headings).

If `obsidian append` would land in the wrong place, use `obsidian eval`
to perform a precise textual edit through the running Obsidian app:

```bash
obsidian eval code="(async () => {
  const f = app.vault.getAbstractFileByPath('folder/page.md');
  const txt = await app.vault.read(f);
  const marker = '\n\n## 相关';                  // anchor that must stay last
  const newRow = '\n| col1 | col2 |';            // content to insert before marker
  await app.vault.modify(f, txt.replace(marker, newRow + marker));
  return 'ok';
})()"
```

### Eval scripting gotchas (battle-tested)

- **`obsidian eval` does NOT accept top-level `await`.**
  `obsidian eval code="await app.vault.read(f)"` fails with
  `Unexpected identifier 'app'`. Always wrap in an IIFE:
  `(async () => { ... return result; })()`.

- **`app.vault.modify(f, newContent)` is the standard write API.**
  Read the full file first, transform the string, then write the whole
  thing back. Obsidian re-renders the open view automatically and
  triggers link reindex.

- **Insertion newline/separator must be explicit.**
  If your `marker = '\n\n## next'` and your `newRow = '| c | d |'`
  (no leading newline), the inserted row will collide with the previous
  line: `| a | b || c | d |`. Always include the leading separator
  the surrounding context expects (`newRow = '\n| c | d |'`).

- **Always include a guard before mutating.** Defensive idiom:

  ```js
  if (!txt.includes(marker)) return 'ERR marker not found';
  if (txt.includes(uniqueIdOfNewContent)) return 'ERR already inserted';
  ```

  This makes the eval idempotent-ish and surfaces stale-marker bugs
  loudly instead of writing in the wrong place.

- **Use a sandbox file when prototyping a new modify pattern.**
  Create a throwaway page (`obsidian create name="eval-sandbox"`),
  validate the marker/newRow combo there, then run on the real target.
  Trash the sandbox via
  `(async () => { await app.fileManager.trashFile(app.vault.getAbstractFileByPath('eval-sandbox.md')); })()`.

### Shell escape pitfalls (cmd → CLI content=)

When invoking `obsidian append content="..."` or
`obsidian eval code="..."` from Windows `cmd.exe`, **backslash and
backtick escapes get mangled** across shell layers — particularly when
the content contains markdown code fences (`` ` ``) or path separators (`\`).

Symptoms observed in practice:

- Backticks become `` \` `` in the written file (cmd preserves the literal backslash)
- `\\\\` intended as `\\` becomes `\\\\` literally
- `%LOCALAPPDATA%` gets expanded by cmd before reaching the CLI

**Recommendations:**

1. For **plain text without backslashes/backticks**, `obsidian append content="..."` is fine
2. For **content containing markdown code fences, paths, or any backslash**,
   prefer `obsidian eval` + `app.vault.modify` (you control the string in JS,
   no further shell interpretation)
3. If the content is **truly complex**, write it to a temp `.md` first via
   `obsidian create silent`, then read+modify+delete

## Plugin development

### Develop/test cycle

After making code changes to a plugin or theme, follow this workflow:

1. **Reload** the plugin to pick up changes:
   ```bash
   obsidian plugin:reload id=my-plugin
   ```
2. **Check for errors** — if errors appear, fix and repeat from step 1:
   ```bash
   obsidian dev:errors
   ```
3. **Verify visually** with a screenshot or DOM inspection:
   ```bash
   obsidian dev:screenshot path=screenshot.png
   obsidian dev:dom selector=".workspace-leaf" text
   ```
4. **Check console output** for warnings or unexpected logs:
   ```bash
   obsidian dev:console level=error
   ```

### Additional developer commands

Run JavaScript in the app context:

```bash
obsidian eval code="app.vault.getFiles().length"
```

Inspect CSS values:

```bash
obsidian dev:css selector=".workspace-leaf" prop=background-color
```

Toggle mobile emulation:

```bash
obsidian dev:mobile on
```

Run `obsidian help` to see additional developer commands including CDP and debugger controls.

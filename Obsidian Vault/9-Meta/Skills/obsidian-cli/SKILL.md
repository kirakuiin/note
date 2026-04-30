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

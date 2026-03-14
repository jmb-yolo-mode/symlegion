# Symlegion

Keep your AI instruction files in sync with **zero magic** — just symlinks.

> Credit: **Symlegion** is a Python port of the original [`agentlink`](https://github.com/martinmose/agentlink) tool by Martin Mose Hansen.

Different tools want different files at project root: `AGENTS.md` (OpenAI/Codex, OpenCode), `CLAUDE.md` (Claude Code), `GEMINI.md`, etc. There's no standard, and I'm not waiting for one. **Symlegion** solves the basic need: keep your **personal** instruction files (in `~`) and your **project** instruction files in sync **without generators**. Edit one, they all reflect it.

Creating instruction files is easy with `/init` commands, but keeping them up to date is the hard part — and expensive too. Good instruction files are often crucial and make a huge difference when using agentic tools. Since they're so important, these files are typically generated with expensive models. Why pay repeatedly to regenerate similar content across different tools?

**Future-proof by design:** We don't know what tomorrow brings in the AI tooling space, but symlegion is ready. New tool expects `.newtool/ai-config.md`? Just add it to your config. Complex nested structure like `workspace/ai/tools/newframework/instructions.md`? No problem. Symlegion automatically creates the directories and symlinks without any code changes needed.

> Scope: **instruction files only**. No MCP `.mcp.json` or chain configs. Simple on purpose.

---

## Why Symlegion?

- **One real file, many aliases** — pick a *source* (`CLAUDE.md` or `AGENTS.md` or whatever), symlink the rest.
- **No codegen** — no templates, no transforms, no surprise diffs.
- **Project + global** — works in repos *and* under `~/.config/…`.
- **Idempotent** — re-run safely; it fixes broken/misdirected links.
- **Portable** — works on macOS and Linux.
- **Future-ready** — handles any directory structure, automatically creates paths. Tomorrow's AI tool? Just add its path.

---

## How it works

You tell Symlegion which file or folder is the **source**, and which other paths should **link** to it. Symlegion creates/fixes symlinks accordingly.

- `mode: direct` is the original behavior and the default.
- `mode: recursive` searches multiple roots for matching projects and creates links inside each match.

```yaml
# .symlegion.yaml (in project root)
- source: CLAUDE.md
  links:
    - AGENTS.md                          # OpenCode, Codex
    - .github/copilot-instructions.md    # GitHub Copilot
    - .cursorrules                       # Cursor AI
    - GEMINI.md                          # Gemini CLI
- source: prompts/shared
  links:
    - .ai/prompts                        # Folder symlink
```

Result:
```
./CLAUDE.md                           # real file you edit
./AGENTS.md                           -> CLAUDE.md          (symlink)
./.github/copilot-instructions.md     -> ../CLAUDE.md       (symlink)
./.cursorrules                        -> CLAUDE.md          (symlink)
./GEMINI.md                           -> CLAUDE.md          (symlink)
./.ai/prompts                         -> ../prompts/shared  (symlink dir)
```

Global mode (in HOME) is the same idea:

```yaml
# ~/.config/symlegion/config.yaml
- source: ~/.config/claude/CLAUDE.md
  links:
    - ~/.config/opencode/AGENTS.md
    - ~/.config/some-tool/INSTRUCTIONS.md
```

---

## Install

```bash
uv tool install symlegion
```

Or run without installing:

```bash
uv run symlegion.py --help
```

---

## Usage

### Getting started

```bash
# Initialize in your project
symlegion init

# Edit the created .symlegion.yaml to match your needs
# Create your source file (e.g., CLAUDE.md)

# Sync to create symlinks
symlegion sync
```

`init` creates a starter `.symlegion.yaml` with both `direct` and `recursive` examples.

### Commands

```bash
symlegion init
symlegion sync
symlegion check
symlegion clean
symlegion doctor
```

### Helpful flags

```bash
symlegion sync --dry-run
symlegion sync --force
symlegion --verbose sync
```

### Without init (auto-config)

```bash
symlegion sync
```

What it does:
- Reads `.symlegion.yaml` in CWD.
- Creates/fixes symlinks listed under each group so they point to that group's `source`.

If there's **no** `.symlegion.yaml` in CWD:
- Falls back to `~/.config/symlegion/config.yaml` (global).
- If missing, it **auto-creates** a sane default and tells you.

---

## Config

### Project config (recommended)

Place a single file at repo root:

`.symlegion.yaml`
```yaml
- source: CLAUDE.md
  links:
    - AGENTS.md
    - OPENCODE.md
- source: prompts/shared
  links:
    - .ai/prompts
```

Notes:
- Omitting `mode` is the same as `mode: direct`.
- Each `source` can be a real file or a real folder, but not a symlink unless you use `--force`.
- Paths in `links` are relative to the project root.

### Direct mode

`direct` is the default mode and matches the original Symlegion behavior.

```yaml
- mode: direct
  source: CLAUDE.md
  links:
    - AGENTS.md
    - OPENCODE.md
```

- `source` can be absolute or relative.
- Relative `source` and `links` are resolved from the config file directory.

### Recursive mode

Use `recursive` when you want Symlegion to scan one or more parent folders, find matching projects, and create the same symlink layout inside each one.

```yaml
- mode: recursive
  source: .opencode/commands/
  links:
    - .claude/commands/
    - .pi/prompts/
  search:
    - ~/koofr/workspace/
    - ~/code/
  depth: 3
```

- In recursive mode, `source` and every entry in `links` must be relative paths.
- `search` entries must be absolute paths, except `~`, which expands to `$HOME`.
- If `depth` is omitted, Symlegion uses `5`.
- Symlegion walks each search root down to `depth` levels, looking for `source` in each candidate folder.
- When it finds a match, it creates every link in `links` relative to that matched folder root.
- If one or more search paths do not exist, Symlegion prints a warning and continues.

### Global config

`~/.config/symlegion/config.yaml`
```yaml
- source: ~/.config/claude/CLAUDE.md
  links:
    - ~/.config/opencode/AGENTS.md
```

---

## Platform notes

- **macOS + Linux**: standard POSIX symlinks (`ln -s`) — works the same.
- **Git**: symlinks are stored as links (not file copies). That's fine; teams who dislike that can add them to `.gitignore`.

### Gitignore patterns

Since symlegion creates multiple instruction files but only one is the real source, you can gitignore all AI instruction files except your chosen source:

```gitignore
# Ignore all AI instruction files
AGENTS.md
CLAUDE.md  
GEMINI.md
OPENCODE.md
.cursorrules
.github/copilot-instructions.md

# But track your chosen source file (example: tracking CLAUDE.md)
!CLAUDE.md
```

This keeps your repository clean while ensuring your source file is version controlled. Symlegion will create the source file if it doesn't exist when running `sync`.
- **Editors/IDEs**: most follow symlinks transparently.

---

## FAQ

**Why not templates or generators?**  
Because 90% of the time the files **should be identical**. When they're not, this tool isn't the right fit (or add a second source and stop linking that one).

**What if my source differs per project?**  
Perfect—put a `.symlegion.yaml` in each repo and choose the source you actually edit there.

**Can the source be `AGENTS.md` instead of `CLAUDE.md`?**  
Yes. The source is *whatever you want to edit*. The others link to it.

**What happens when a new AI tool comes out?**  
Just add its expected path to your config. If "SuperCoder AI" expects `.supercoder/prompts/main.md`, add that path and run `symlegion sync`. Directories are created automatically, and the symlink points to your chosen file or folder source. Zero code changes, zero updates needed.

**MCP / `.mcp.json`?**  
Out of scope. Formats differ between tools; symlinking a single JSON to multiple consumers usually doesn't make sense.

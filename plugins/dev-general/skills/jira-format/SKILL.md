---
name: jira-format
description: Format text as Jira wiki markup — either authoring fresh content (Jira comment / description) or converting existing Markdown to Jira. Triggers when the user says "jira comment", "jira description", "jira format", "convert this to jira", "jira-ify this", "paste into jira", "jira version", or asks for content destined for a Jira ticket. Use this skill BEFORE producing the output, not after — Jira and Markdown share enough syntax that mistakes look fine until they don't render. Skip this skill when the user wants standard Markdown for GitHub, Slack, or local files.
license: "MIT (this skill's code) AND CC-BY-SA-4.0 (the syntax reference doc, derived from netresearch/jira-skill)"
metadata:
  attribution: Adapted from https://github.com/netresearch/jira-skill (jira-syntax skill); references and validator preserved with attribution. Vendored 2026-06-10.
---

# Jira Format

Two modes:

- **Author** — write Jira-formatted content from scratch (most common).
- **Convert** — translate existing Markdown to Jira wiki markup.

Same rules apply to both. The cheat-sheet below covers ~95% of cases. For edge cases (colors, panels, complex tables, anchors, emoji codes), see `references/jira-syntax-quick-reference.md`.

## Cheat-sheet

| Jira | Markdown (DO NOT use) | Notes |
|---|---|---|
| `h1. Title` … `h6. Title` | `# Title` … `###### Title` | Space after the period is required |
| `*bold*` | `**bold**` | Single asterisk in Jira |
| `_italic_` | `*italic*` or `_italic_` | Single underscore in Jira |
| `+underline+` | (no Markdown equivalent) | |
| `-strikethrough-` | `~~strike~~` | |
| `{{inline code}}` | `` `inline code` `` | Double curly braces |
| `{code:bash}…{code}` | ` ```bash … ``` ` | `:lang` is optional but useful for syntax highlighting |
| `{noformat}…{noformat}` | (no direct equivalent) | Preserves whitespace, no syntax highlighting |
| `* item` | `- item` | Bullets use `*` in Jira |
| `# item` | `1. item` | Numbered lists use `#` in Jira |
| `** sub-item` | `  - sub` (indented) | Nest by repeating the marker |
| `[text\|url]` | `[text](url)` | Pipe separator, NOT parentheses |
| `[PROJ-123]` | (none) | Bare ticket key auto-links |
| `[~username]` | `@username` | Tilde prefix |
| `\|\|h1\|\|h2\|\|` and `\|c1\|c2\|` | Markdown table | Double-pipe for header row, single for data |
| `{quote}…{quote}` | `> quoted` | Block quote |
| `----` | `---` | Horizontal rule |
| `\\` | `\n` (newline in Markdown) | Forced line break inside a paragraph |
| `bq. quoted line` | `> quoted line` | Single-line block quote |

## House style (Charles's preferences)

- **Terse.** Lead with the answer. No preamble, no "I hope this helps".
- **No PM jargon.** Avoid "affordances", "user journeys", "leverage", etc.
- **No template ceremony unless asked.** Don't add Acceptance Criteria, Definition of Done, sectioned bug reports, or other Atlassian-default scaffolding unless the user explicitly asks for that shape.
- **Headings are h2 (`h2. ...`) by default.** Reserve h1 for the ticket title itself; comments rarely need h1.
- **Code blocks should specify language** (`{code:bash}`, `{code:php}`, `{code:json}`) when there's syntax to highlight; use `{noformat}` for plain text where Jira's auto-formatting would corrupt it (paths with `*`, log lines with `|`, etc.).
- **Don't reformat aggressively.** If the user provides text that's already mostly Jira-correct, fix only what's broken — don't restyle their headings or restructure their sections.

## Mode 1 — Author from scratch

When the user says "write me a Jira comment" / "draft a Jira description for X" / similar:

1. Author directly in Jira wiki markup using the cheat-sheet. Don't write Markdown first and translate; produce Jira format on the first pass.
2. Output the content as a single fenced block in chat so the user can copy-paste cleanly. **Do not use Markdown headings or `**bold**` in your surrounding chat text either** — those are for the explanation, not the deliverable.
3. Run the validator (see "Validate before output" below) if the content is non-trivial (>20 lines or contains tables/code blocks).

## Mode 2 — Convert existing Markdown

When the user pastes Markdown and asks for the Jira version, OR points at a `.md` file (e.g. "convert `.claude/issues/CLB-1604/CLB-1604.md` for the Jira comment"):

1. Apply the cheat-sheet rules systematically. Common gotchas:
   - `**bold**` → `*bold*` (drop one asterisk per side)
   - `*italic*` (Markdown) → `_italic_` (Jira) — not the same character!
   - `` `inline code` `` → `{{inline code}}`
   - ` ```lang ` blocks → `{code:lang}` … `{code}`
   - `[text](url)` → `[text|url]`
   - `## Heading` → `h2. Heading`
   - `- bullet` → `* bullet`
   - `1. numbered` → `# numbered`
   - Markdown tables: keep cell content, change `|---|` separators to nothing, change first row's `|` to `||`
2. Watch for content that **doesn't translate cleanly**:
   - Markdown blockquotes with multiple paragraphs → use `{quote}…{quote}` (multi-line) not `bq.` (single line)
   - Markdown footnotes — Jira has no equivalent; inline them
   - Markdown task lists (`- [ ] todo`) — Jira renders as plain bullets unless using a Confluence add-on; flag this to the user
3. Run the validator on the result.
4. Show the converted text in a fenced block.

## Validate before output

For any non-trivial output, save to a temp file and run the validator. It catches the most common mistakes (`**bold**` slipping through, missing space after `h2.`, `## Heading` instead of `h2. Heading`, etc.):

```bash
# From the skill directory (resolves to plugins/dev-general/skills/jira-format/)
${CLAUDE_SKILL_DIR}/scripts/validate-jira-syntax.sh /tmp/jira-output.txt
```

If the validator reports errors, fix them before showing the output to the user. Warnings are advisory — judge case-by-case.

## When NOT to use this skill

- The user wants standard Markdown for GitHub, GitLab, a `.md` file, Slack, or any non-Jira destination
- The user wants HTML or some other format — different skill
- The user already provided fully-correct Jira markup and just wants a review/edit on content (no format work needed)

## Edge cases & references

For uncommon syntax — colors (`{color:red}`), expand/collapse panels (`{panel}`), text effects beyond bold/italic, status badges, anchors, emoji shortcodes — see `references/jira-syntax-quick-reference.md`.

## Attribution

The reference doc (`references/jira-syntax-quick-reference.md`) and validator script (`scripts/validate-jira-syntax.sh`) are vendored from the [netresearch/jira-skill](https://github.com/netresearch/jira-skill) project (MIT and CC-BY-SA-4.0 licensed). See `LICENSE-MIT` and `LICENSE-CC-BY-SA-4.0` in this skill folder for the full terms. The `SKILL.md` itself is original to `foxtrotcharlie/claude-skills`.

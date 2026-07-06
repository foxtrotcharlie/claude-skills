---
name: explain-diff-html
description: Produce a rich, interactive, self-contained HTML page that explains a code change — a diff, branch, commit range, or pull request — with Background (deep + narrow), Intuition (reusable HTML diagrams + toy data), a Code walkthrough, and an interactive multiple-choice quiz. Use this whenever the user asks to "explain this diff/PR/change/branch", "write up this change", "make an explainer / walkthrough / teaching doc / onboarding doc" for some code, or asks for a "rich", "visual", or "interactive" explanation of code — even if they don't say the word "HTML". The deliverable is an HTML file, not Markdown. Skip this skill when the user wants a terse plain-text summary, a commit message, a PR description meant for submission, release notes, or Jira/Markdown output — those are other jobs.
---

# Explain Diff (interactive HTML)

Given a code change — a diff, a branch, a commit range, a PR, or a *proposed* change not yet written (comparing the current code to a target) — produce a single self-contained, interactive HTML page that **teaches** the change. The reader might be a teammate onboarding, a reviewer, or the author's future self, and you don't know how much they already know, so the page builds from broad context up to the specifics.

This is a *teaching artifact*, not a status summary. It is intentionally rich and long — that is the point. (Any terse house style applies to what you say in chat, not to this document.)

## Start from the bundled template

Copy `${CLAUDE_SKILL_DIR}/assets/template.html` to your output path and fill in the content. The template already carries the CSS (prose, callouts, the two diagram families, the quiz), the quiz JavaScript, the table of contents scaffold, responsive breakpoints, and — crucially — `white-space: pre` on code blocks. Reusing it keeps every explainer visually consistent and saves you from re-deriving the fiddly bits (the quiz interactivity and the newline-collapsing gotcha) every time. Rewrite freely inside it; just don't hand-roll the plumbing from scratch.

## Output format

- **One self-contained `.html` file** — inline CSS and JavaScript, no external assets or CDNs. It must open correctly from `file://`.
- **Filename starts with today's date**, `YYYY-MM-DD-explanation-<slug>.html`, so files stay time-sorted. Get the date from the environment (it's in your context), don't guess.
- **Save it outside the code repo** (e.g. `/tmp/`), so it never lands in version control.
- **One long page** with a header, a table of contents, and section headers you can link to. Do **not** use tabs for the top-level structure — it's a document you scroll, not an app.
- Responsive enough to read on a phone (a single media query is usually plenty).

## Before you write: understand the change

A good explanation comes from understanding, so spend real effort here before touching HTML.

1. Get the change: `git show <ref>`, `git diff <base>..<head>`, or `gh pr diff <n>`. For a *proposed* change with no diff yet, read the current code and the target it will converge on (e.g. the shared trait/base it should adopt) and treat the current-vs-target delta as the change; the same four sections apply.
2. **Explore the surrounding code broadly** — the Background section needs the real system, not just the lines in the diff. Read the files the change touches *and their neighbours*: the base class, the caller, the config, the tests. This is where the depth comes from.
3. Decide the **two or three diagram families** you'll reuse across the page (see Diagrams). Picking them up front keeps the visuals coherent.

## The four sections

Write them in this order; let each flow into the next with a real transition sentence, not a hard cut.

1. **Background** — explain the existing system the change touches. Include a *deep* background for beginners (clearly marked skippable, e.g. a small "veterans skip to §1.2" note) that defines the domain concepts, then a *narrow* background zoomed in on exactly the mechanism the change modifies. Use callouts for definitions.
2. **Intuition** — the core idea in one or two sentences, then build it up with a concrete toy example (invent small, memorable data — "a Phone numbers field with three values", not "an entity"). Lean on the diagram families. The goal is the *essence*, not full detail. This is the most important section; if a reader only reads one, it should be this one.
3. **Code** — a high-level walkthrough of the actual changes, grouped and ordered so they tell a story (e.g. "the setting → the switch → the new path → the edge cases"), not file-by-file in diff order. Show representative snippets, not the whole diff.
4. **Quiz** — five interactive multiple-choice questions of *medium* difficulty: hard enough that you must understand the change to answer, but not gotchas. Each question reveals whether the answer was right and gives a short explanation on click (the template's JS handles this). Good questions probe the *why* behind decisions in the change.

## Diagrams

- **Reuse a small number of families.** One well-designed diagram style, reused for several cases, teaches better than many one-off pictures. Two families cover most changes:
  - a **simplified UI mock** (a little "browser" box showing what the user sees) for UI/behaviour changes, and
  - a **system / data-flow diagram** (boxes and arrows showing components or a pipeline) — always annotate it with **example data** flowing through, not just labels.
- **Never use ASCII-art diagrams.** Build them from styled HTML (divs, flexbox) and HTML lists for lists. The template has ready-made classes for both families.

## Code blocks

Always wrap code in `<pre>` tags. If you use a styled `<div>` instead, its CSS **must** include `white-space: pre` or `pre-wrap`, or the browser collapses every newline and the code renders as one line. Before saving, scan each code block in your HTML and confirm the containing element has `white-space: pre` / `pre-wrap`. (The template's `pre` and diagram classes already do; if you add new block types, check them.)

## Writing style

Write with the clarity and flow of Martin Kleppmann — plain, precise, classic style; short concrete sentences; the reader carried along rather than lectured. Explain *why* the system and the change are the way they are, not just *what* changed. Smooth the seams between sections so the page reads as one essay.

## Callouts

Use callouts (the template has definition / key-insight / edge-case variants) for the things worth stopping on: a term the beginner needs, the one non-obvious idea the whole change hinges on, or a tricky edge case. Don't overuse them — a callout on every paragraph stops being a signal.

## Before saving — quick self-check

- Single self-contained file; opens from `file://`; filename date-prefixed and outside the repo.
- All four sections present, plus a TOC; no top-level tabs.
- Every code block is `<pre>` or has `white-space: pre`/`pre-wrap`.
- Diagrams are HTML (no ASCII); a small reused set, with example data.
- The quiz's five questions respond to clicks with correct/incorrect + explanation.

Then tell the user the exact file path so they can open it.

## When NOT to use this skill

- The user wants a short plain-text or Markdown summary, a commit message, a PR description for submission, or release notes.
- The user wants Jira wiki markup, or output pasted somewhere that isn't a standalone HTML file.
- The task is to *make* the change, review it, or debug it — not to explain it.

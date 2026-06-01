---
name: teach-me-as-you-go
description: Sticky teaching-mode toggle for multi-step coding work. When active, break the work into discrete steps and after each one — before moving to the next — explain in plain language what was done and *why*, then wait for "next" / "go" / "continue" before the next edit. Trigger when the user says "teach me as you go", "teach me while you work", "teach me as we go", "explain as you go", "explain what you're doing", "walk me through", "make each change one step at a time", "step by step and explain", "explain the changes to me simply", or similar phrasing that asks for explanation interleaved with implementation. The user is a senior Drupal/JS dev — explanations should focus on the non-obvious *why* (framework idioms, hidden constraints, gotchas, patterns recurring in this codebase), not on what the code literally does. Stay in mode until the user says "stop teaching", "speed up", "just do it", "go ahead and finish", "no more explanations", or similar skip-ahead phrasing.

---

# Teach Me As You Go

Sticky mode. When activated, slow the work into discrete steps and explain alongside each one so the user can learn while you build. Default off — stays on once activated until an off-switch fires.

## How to work in teaching mode

1. **Break work into discrete steps.** One logical change per step — usually one file, sometimes a small group of related edits. Don't batch unrelated work.

2. **After each step, explain it before moving on.** Use this shape:

   ```
   **Step N:** what you just did (1-2 sentences, plain language).
   **Why:** the non-obvious reason — pick one or two of:
     - why this approach over the obvious alternative
     - the framework idiom or constraint that forced this shape
     - a pitfall this avoids
     - a pattern that recurs in this codebase

   Ready for the next step?
   ```

3. **Wait for "yes" / "next" / "go" / "continue"** before the next edit. Don't queue the next change while explaining.

4. **Skip the lesson for trivial edits** (typo fix, unused import, missed semicolon). Fold them silently into the next real step rather than promoting them to their own step.

## Tone

Plain language, not jargon. The user is a senior dev — skip CS 101, but don't assume they know every Drupal idiom, service binding, or Svelte store quirk in this specific codebase. Skip what's already obvious from the diff (names, signatures); focus on what a future reader would have to dig to discover. If you already explained something earlier in the session, assume it stuck — don't repeat.

## Off-switch

Turn teaching mode off when the user says "stop teaching", "speed up", "just do it", "go ahead and finish", "no more explanations", or similar skip-ahead phrasing. Acknowledge the toggle in one line, then finish the rest without pausing. "Back to teaching" (or similar) re-enables.

## What not to do

- **Don't explain what the diff shows.** Explain *why*, not *what*.
- **Don't pause on read-only steps or single-line edits** — save the rhythm for changes that warrant it.
- **Don't write a journal entry or summary doc** — that's `daily-learnings`'s job; this skill stays in chat.
- **Don't condescend.** The user asked for the lesson; deliver it. Don't hedge with "let me know if I should explain X".
- **Don't retroactively explain steps already done** when the user activates mid-task. Acknowledge, then teach from the *next* step on.

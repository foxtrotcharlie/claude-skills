---
name: drupal-quality-loop
description: Drive the iterative red/green loop for Drupal code quality — run phpcbf → phpcs → phpstan on changed PHP files (or a user-specified target), fix mechanical violations in place, and rerun until clean. Use whenever the user wants to "tighten up", "clean up", or "lint and fix" their PHP changes before commit, says "run the quality loop", "phpcs and phpstan my changes", "drupal quality check", "loop phpcs until clean", or asks to "check my changes" in a Drupal/PHP context. Also use proactively after a chunk of PHP edits and before pushing/PR-ing, even if the user doesn't explicitly ask — surfacing style/static errors before the user has to do it is a strong default. Skip this skill when the user just wants ONE run of phpcs or phpstan and is going to read the results themselves.
---

# Drupal Quality Loop

## What this skill is for

Drives the **edit → fix → rerun** cycle that Drupal developers go through when getting a module ready to commit:

1. Run auto-fixer (phpcbf) on the target paths.
2. Run phpcs to see what style violations remain.
3. Run phpstan to see what static analysis flags.
4. Mechanically fix the obvious stuff (unused imports, missing return types, docblock formatting, simple type narrowings).
5. Surface the rest for the user before touching it.
6. Re-run. Exit when phpcs and phpstan both report clean.

If the user just wants to *see* phpcs or phpstan output once (without driving the loop), defer to `ddev-code-quality` instead — it's a one-shot subagent technique, not a loop.

## Determining the target

You are responsible for tracking the target paths across iterations. Don't make the user re-paste paths.

**Default — auto-detect from git changes:**

```
git diff --name-only HEAD -- '*.php' '*.module' '*.inc' '*.install' '*.theme' '*.profile'
```

This catches staged + unstaged changes against the current HEAD. Filter results to paths under `web/modules/custom/`, any contrib/vendored module directories your project lints, and custom theme PHP — the quality tools are typically configured to scan those zones, and running against `vendor/` or `web/core/` will either fail or produce noise.

**Explicit target** — when the user names a file, directory, or module (e.g. "phpcs the ArticleForm", "lint the my_module module"), use that path instead. Resolve glob/module-name shortcuts to actual paths before passing them to the tools.

**Empty target** — if git diff returns nothing and the user didn't provide a path, ask: "Nothing in the diff. Which file or module did you want to loop on?" Don't run against the whole `web/modules/custom/` tree — that's slow and produces too much noise to act on.

## Detecting the repo's command shape

Drupal repos in this workflow expose the quality tools in two different ways. Check which one applies before issuing commands.

**Style A — `.ddev/commands/web/{phpcs,phpstan,phpcbf,phpunit,checks}` shortcuts** (projects that ship custom DDEV command wrappers):

```
ddev phpcbf <path>
ddev phpcs <path>
ddev phpstan <path>
ddev phpunit <test-file-or-filter>     # targeted only
ddev checks                            # phpstan + phpunit (no phpcs)
```

**Style B — composer scripts** (module/library repos that have a `composer.json` with `phpcs`/`phpcbf` scripts):

```
ddev composer phpcs <path>
ddev composer phpcbf <path>
# phpstan: typically not wired up — skip if not present
# phpunit: ddev composer test (full sweep, slow) or ddev phpunit <test-file> if available
```

Quick detect: `ls .ddev/commands/web/` — if you see `phpstan` listed, you're in Style A. Otherwise, fall back to `ddev composer <script>`. If neither phpstan nor `ddev composer phpcs` exists, tell the user the repo isn't set up for this loop and stop.

## Running the tools (use subagents)

Code quality tools produce hundreds to thousands of lines of output. Running them in the main conversation burns tokens you can't get back. Always dispatch through a subagent that returns a structured summary.

Dispatch through a subagent that returns a structured summary rather than raw output. The short version:

```
Task tool:
  description: "Run ddev phpcs <path>"
  subagent_type: "general-purpose"
  model: "haiku"
  prompt: |
    Run `ddev phpcs <path>` and return:
      - exit code
      - if errors: each file with its error count and the first ~3 error messages per file
      - if clean: "No issues found."
    Do not return the full output. Group by file.
```

For phpstan, ask the subagent to bucket results by rule (e.g. "PHPDoc tag @return with type X is not subtype of native type Y", "Method ... has no return type specified") so you can spot mechanical-fix clusters quickly.

When running phpcbf, the meaningful output is just "N violations auto-fixed in M files" — that's all you need back.

**Parallelize phpcs and phpstan in a single message** with two Task calls. They're independent.

## The loop

```
iteration = 1
while True:
    1. Run phpcbf <target>            # auto-fix style (subagent)
    2. Parallel:                       # one message, two Task calls
         - phpcs <target>              # what style remains
         - phpstan <target>            # what static analysis flags
    3. If phpcs clean AND phpstan clean (or phpstan unavailable):
         break                          # success
    4. Categorize remaining issues:
         - Mechanical (Claude fixes silently): unused use statements, missing return
           type hints where the signature is obvious, docblock formatting,
           short array syntax, trailing whitespace, single-line phpstan fixes
           like adding `@var` hints.
         - Invasive (ask user first): logic changes, refactoring, suppressing
           rules with @phpstan-ignore-next-line, changes to public APIs,
           anything that alters runtime behavior.
    5. Apply mechanical fixes via Edit. For invasive ones, summarize and ask:
         "phpstan flags <N> issues that need judgment calls — want me to
         walk through them, or just suppress with @phpstan-ignore?"
    6. iteration += 1
    7. Bail out after 5 iterations regardless — if it's not converging,
       something needs human eyes, not another rerun.
```

Show iteration progress concisely: a one-line "Iter 2: phpcs 3→0, phpstan 7→2" beats re-listing everything that's already been resolved.

## PHPUnit handling

**Do not run the full phpunit suite as part of this loop.** It's slow and the failure modes (DB state, install profile, dependencies) are orthogonal to the style/static-analysis loop.

Run phpunit only when:

- The user names a specific test file: `ddev phpunit web/modules/custom/my_module/tests/src/Kernel/SomethingTest.php`
- Or the user gives a `--filter` argument to narrow the run: `ddev phpunit <path> --filter testTheMethodName`

If the user asks for "the full sweep" or "ddev checks", do that as a one-shot at the end (use `ddev checks` where the project defines it — it typically runs phpstan + phpunit). Don't put it inside the iterative loop.

## What this skill should not do

- Don't refactor or "improve" code beyond what phpcs/phpstan flag. The diff at the end should be exactly the set of changes needed to make the gates pass — nothing else.
- Don't run the full custom-modules phpunit suite. Wastes minutes per iteration.
- Don't paste raw tool output into the main conversation. Always summarize via subagent.
- Don't silently suppress phpstan rules with `@phpstan-ignore` — surface those decisions and let the user decide.
- Don't re-prompt for the target path between iterations. You're tracking it.
- Don't trigger when the user just wants one phpstan run — a single ad-hoc run they'll read themselves doesn't need this loop.

## Exit message

When the loop exits clean, give a short summary the user can paste into a commit message or PR description:

```
Quality loop clean after <N> iterations.
  phpcbf: <X> auto-fixes
  phpcs:  0 violations (was <Y>)
  phpstan: 0 errors (was <Z>)
Targets: <list of files>
```

If the loop bailed at the 5-iteration cap or because phpstan keeps flagging the same handful of invasive issues, say so plainly and list what's still flagged — don't pretend it's clean.

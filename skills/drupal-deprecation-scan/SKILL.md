---
name: drupal-deprecation-scan
description: Scan Drupal custom modules for deprecated API usage using upgrade_status. Installs the module temporarily if needed, runs the scan, reports findings by severity, then offers to remove the module. Use when user asks about Drupal deprecations, wants to check if custom code is ready for the next major version, or asks to run upgrade_status.
allowed-tools: "Bash(ddev*), Read, Write, Glob, Grep, AskUserQuestion"
---

# Drupal Deprecation Scan

Temporarily install `drupal/upgrade_status` (if not already present), scan all custom modules for deprecated API usage, report findings by severity, then clean up.

## When to Use This Skill

Use this skill when:
- User asks "are there any deprecations in our custom code?"
- User wants to check readiness for the next Drupal major version
- User says "run upgrade_status" or "check for deprecated APIs"
- User has just completed a minor Drupal core update and wants to check for new deprecations
- User is planning a major version upgrade and needs a full deprecation report

## Background: What upgrade_status Does

`drupal/upgrade_status` is a contrib module that:
- Scans **custom modules** (`web/modules/custom/`) and **contrib modules** for calls to deprecated Drupal APIs
- Reports the file, line number, deprecated function/class, and what to use instead
- Indicates which Drupal version the deprecation was introduced in, and which version it will be removed in
- Does **not** scan vendor PHP libraries — only Drupal module code
- Generates findings at three severity levels: **Error** (will break in next major), **Warning** (deprecated, should fix), **Check** (informational)

**When is it most valuable?**
- Before a major version upgrade (e.g., 11 → 12): errors and warnings represent things that will break
- After each minor update: new minor releases introduce new deprecations; finding them early prevents surprises
- As a periodic health check: every few months to track deprecation debt

**When is it less useful?**
- Pure patch updates (e.g., 11.2.5 → 11.2.8): patch releases don't introduce deprecations

## Instructions

### Global Rules

**NEVER run `composer require`, `composer remove`, `drush pm:enable`, or `drush pm:uninstall` without explicit user confirmation via `AskUserQuestion`.**

**Cancel option required:** Every `AskUserQuestion` in this skill MUST include a **Cancel — stop the drupal-deprecation-scan skill** option. If the user selects Cancel at any point, stop immediately and do not continue with any further steps.

### 1. Check Current State

**Step 1 — Check if upgrade_status is already installed:**

```bash
ddev composer show drupal/upgrade_status 2>/dev/null | grep "^versions"
```

Note whether it was already installed before this skill ran — this determines whether to remove it at the end.

**Step 2 — Check if the module is enabled:**

```bash
ddev drush pm:list --filter=name=upgrade_status --no-ansi 2>/dev/null
```

Note enabled/disabled state for cleanup at the end.

### 2. Install upgrade_status (if needed)

If `drupal/upgrade_status` is not installed, confirm with the user before installing:

Use `AskUserQuestion`:

> **upgrade_status is not installed. Install it now?**
>
> - **Install** — run `composer require drupal/upgrade_status --dev` and enable the module
> - **Cancel — stop the drupal-deprecation-scan skill**

If the user selects **Cancel**, stop immediately.

```bash
ddev composer require drupal/upgrade_status --dev --no-ansi 2>/dev/null
```

Then enable the module:

```bash
ddev drush pm:enable upgrade_status --yes 2>/dev/null
```

If it was already installed but not enabled, just enable it:

```bash
ddev drush pm:enable upgrade_status --yes 2>/dev/null
```

If it was already installed and enabled: proceed directly to the scan.

### 3. Run the Scan

**Step 1 — Scan custom modules only (recommended default):**

```bash
ddev drush upgrade_status:analyze --all --ignore-contrib --no-ansi 2>/dev/null
```

**Step 2 — If the user also wants contrib modules scanned:**

```bash
ddev drush upgrade_status:analyze --all --no-ansi 2>/dev/null
```

**Note:** Contrib module results are usually noise unless you're planning to update or remove a contrib module. Custom code is where action is needed.

Use `AskUserQuestion` to ask scope before scanning:

> **What should the deprecation scan cover?**
>
> - **Custom modules only** — Scan `web/modules/custom/` (recommended, actionable results)
> - **Custom + contrib modules** — Also scan contrib modules (more results, less actionable)

### 4. Parse and Report Results

The scan output groups findings by module. Parse into a structured report.

**Severity levels:**
| Level | Meaning | Action Required |
|-------|---------|----------------|
| **Error** | Will break in the next major Drupal version | Fix before upgrading |
| **Warning** | Deprecated, should be updated | Fix soon |
| **Check** | Informational / soft deprecation | Review when convenient |

**Report format:**

```
## Drupal Deprecation Scan Results

Scanned: YYYY-MM-DD
Drupal core version: X.Y.Z
Next major version: X+1.0.0

### Summary

| Module | Errors | Warnings | Checks |
|--------|--------|----------|--------|
| my_module | 2 | 5 | 1 |
| my_other_module | 0 | 3 | 0 |
| **Total** | **2** | **8** | **1** |

---

### Errors (will break in Drupal X+1)

#### my_module

| File | Line | Deprecated | Replace With | Since |
|------|------|-----------|--------------|-------|
| src/Entity/Article.php | 142 | `\Drupal::entityQuery()` without access check | Add `->accessCheck(FALSE)` or `->accessCheck(TRUE)` | 9.1 |
| src/Service/ExampleService.php | 87 | `hook_entity_type_alter()` signature change | Update hook signature | 11.1 |

---

### Warnings (deprecated, should fix)

#### my_module

| File | Line | Deprecated | Replace With | Since |
|------|------|-----------|--------------|-------|
| ...

---

### Checks (informational)

...

---

### No Issues Found

Modules with no deprecations:
- my_event_module
- my_api_client
```

If no issues at all:
```
✓ No deprecated API usage found in custom modules.
All custom code is compatible with Drupal {next_major}.
```

### 5. Save Report

Save to `.claude/drupal-update-reports/DRUPAL-DEPRECATIONS--YYYY-MM-DD.md`.

Include at the top:
- Drupal core version scanned
- Scope (custom only / custom + contrib)
- Total errors / warnings / checks
- Whether upgrade_status was already installed or temporarily added

### 6. Clean Up

**Step 1 — Offer cleanup options via `AskUserQuestion`:**

> **upgrade_status module — what would you like to do?**
>
> - **Uninstall and remove** — Remove module and uninstall from Drupal (recommended if temporarily installed)
> - **Keep enabled** — Leave it installed and enabled
> - **Disable but keep** — Disable the module but keep the package in vendor

**Step 2 — Execute chosen option:**

If **Uninstall and remove** (and upgrade_status was not present before the skill ran):
```bash
# Uninstall the module from Drupal
ddev drush pm:uninstall upgrade_status --yes

# Remove the package
ddev composer remove drupal/upgrade_status
```

If **Uninstall and remove** (and upgrade_status was already present before the skill ran):
- Do not remove the composer package — it was there before
- Only uninstall the module if it was not enabled before the skill ran
- Inform the user: "upgrade_status was already in your project — only uninstalling the module, not removing the package."

If **Keep enabled** or **Disable but keep**: leave composer.json unchanged, optionally disable with `ddev drush pm:uninstall upgrade_status --yes`.

### 7. Next Steps

After reporting, suggest prioritised actions:

**If errors found:**
```
⚠️  X errors found — these will break when upgrading to Drupal {next_major}.

Recommended action: Fix errors before the next major update.
Each error in the report includes the file, line, deprecated call, and replacement.

To re-run after fixing:
  /drupal-deprecation-scan
```

**If only warnings/checks:**
```
✓ No blocking errors. X warnings found — deprecated but not yet breaking.

These should be addressed before upgrading to Drupal {next_major}.
No immediate action required for patch/minor updates.
```

**If nothing found:**
```
✓ Clean — no deprecated API usage found. Custom code is ready for Drupal {next_major}.
```

Always suggest:
```
Related: run /drupal-update to check for available package updates.
```

## Examples

**Example 1: Basic scan, upgrade_status not installed**
```
User: Check our custom modules for deprecations

Claude: Checking for upgrade_status...

upgrade_status is not currently installed. I'll install it temporarily,
run the scan, then offer to remove it.

What should the deprecation scan cover?

  → Custom modules only (recommended)
    Custom + contrib modules

[User selects "Custom modules only"]

Claude: Installing drupal/upgrade_status (dev)...
✓ Installed
✓ Module enabled

Running deprecation scan on web/modules/custom/...

## Drupal Deprecation Scan Results

Scanned: 2026-03-02
Drupal core version: 11.3.3
Next major version: 12.0

### Summary

| Module | Errors | Warnings | Checks |
|--------|--------|----------|--------|
| my_module | 1 | 4 | 0 |
| my_other_module | 0 | 1 | 0 |
| **Total** | **1** | **5** | **0** |

### Errors (will break in Drupal 12)

#### my_module

| File | Line | Deprecated | Replace With | Since |
|------|------|-----------|--------------|-------|
| src/Entity/Article.php | 142 | entityQuery() without accessCheck | Add ->accessCheck() | 9.1 |

[full report saved to .claude/drupal-update-reports/DRUPAL-DEPRECATIONS--2026-03-02.md]

---

⚠️  1 error found — will break in Drupal 12.

upgrade_status module — what would you like to do?

  → Uninstall and remove (recommended — was temporarily installed)
    Keep enabled
    Disable but keep

[User selects "Uninstall and remove"]

Claude: ✓ Module uninstalled
✓ Package removed

To fix the error in my_module/src/Entity/Article.php:142,
add ->accessCheck(FALSE) to the entityQuery() call.
See: https://www.drupal.org/node/3315220
```

**Example 2: upgrade_status already installed**
```
User: /drupal-deprecation-scan

Claude: upgrade_status is already installed and enabled. Running scan directly...

[Scan results]

upgrade_status module — what would you like to do?

  → Keep enabled (was already installed before this scan)
    Disable but keep
    Uninstall and remove
```

**Example 3: No deprecations found**
```
User: Check for deprecations before upgrading to Drupal 12

Claude: [Installs, scans custom modules]

✓ No deprecated API usage found in custom modules.
All custom code is compatible with Drupal 12.

[Report saved]

[Cleanup prompt]
```

## Tips

- **Run after minor core updates:** Each Drupal minor release can introduce new deprecations in your custom code's call sites. Running this after a 11.2 → 11.3 update catches new issues early.
- **Fix errors first, warnings second:** Errors are the only ones that will break on upgrade. Warnings are important but not urgent.
- **The `accessCheck` error is common:** `entityQuery()` without `->accessCheck()` has been deprecated since 9.1 and will be an error in Drupal 12. It's one of the most frequently encountered deprecations.
- **Contrib results are noisy:** Contrib modules often show warnings for code that will be fixed by the module maintainer before Drupal 12 is released. Focus on custom code.
- **Re-run after fixing:** The scan only reports what it finds at the time — re-run to confirm fixes are clean.
- **upgrade_status is a dev tool:** Install with `--dev` so it doesn't end up in production composer requirements.

## Related Skills

- `/drupal-update` - Update Drupal core and contrib modules

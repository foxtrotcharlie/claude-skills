---
name: drupal-deprecation-scan
description: Scan Drupal custom modules for deprecated API usage using upgrade_status. Reads structured results from upgrade_status's keyValue store, scopes strictly to web/modules/custom (and optionally vendored upstream code), groups findings by analyzer (Drupal-API deprecations vs PHPStan vs library vs info.yml), and buckets by introduced/removed Drupal version. Use when user asks about Drupal deprecations, wants to check if custom code is ready for the next major version, or asks to run upgrade_status.
allowed-tools: "Bash(ddev*), Bash(jq*), Read, Write, Glob, Grep, AskUserQuestion"
---

# Drupal Deprecation Scan

Run `drupal/upgrade_status` against truly-custom code, read its **structured** keyValue results, and produce an analyzer-grouped report bucketed by Drupal version so that "what breaks in our next major" is the loudest signal in the output.

## When to Use This Skill

- "Are there any deprecations in our custom code?"
- Checking readiness for the next Drupal major (e.g. 11 → 12)
- After a minor core update (each minor can introduce new deprecations)
- "Run upgrade_status" / "check for deprecated APIs"
- Periodic deprecation-debt audits

## Background

`drupal/upgrade_status` runs **four analyzers** and lumps all of their output into a single "deprecation" report. Knowing which analyzer produced a finding is the difference between an action item and noise:

- **`PHPStan`** — code-quality static analysis (missing return statements, undefined variables, dupe array keys, case-wrong namespaces). **Mostly NOT Drupal API deprecations**. In a typical scan this is the largest category by volume.
- **`ExtensionMetadataDeprecationAnalyzer`** — `core_version_requirement` strings in `.info.yml` that don't yet allow the next major. One per file.
- **`LibraryDeprecationAnalyzer`** — deprecated CSS/JS library declarations. Many false positives if you don't pass `--ignore-uninstalled`.
- **`TwigDeprecationAnalyzer`** — deprecated Twig syntax / filters.

Each finding also carries an `upgrade_status_category` flag:
- **`later`** — will break in the **next** major (this is the urgent bucket)
- **`ignore`** — will break in major+2 or has been internally deferred
- **`rector_covered`** — auto-fixable via Drupal Rector
- **`uncategorized`** — everything else

And many (not all) findings carry a Drupal version stamp: `Deprecated in drupal:X.Y and is removed from drupal:Z.W`.

The structured results live in the `upgrade_status_scan_results` keyValue store after a scan completes. Reading them via `drush eval` is far more reliable than parsing the textual output (which has wrapped paths, wrapped messages, and inconsistent column widths).

**Most useful when:**
- Before a major upgrade (`later` items will break)
- After a minor update (new deprecations introduced)
- Periodic health check (track debt over time; CI ships results to the central `pa-deprecations` blobstore in Apple environments — see "Related infrastructure")

**Less useful when:**
- Patch updates only — patch releases don't introduce deprecations.

## Instructions

### Global Rules

- **NEVER run `composer require`, `composer remove`, `drush pm:enable`, or `drush pm:uninstall` without explicit user confirmation via `AskUserQuestion`.**
- Every `AskUserQuestion` MUST include a **Cancel — stop the drupal-deprecation-scan skill** option. If selected, stop immediately.
- This skill **scopes to truly-custom code by default** (`web/modules/custom/`, `web/themes/custom/`, plus the local install profile if any). Vendored upstream packages under `web/modules/apple/` etc. are **opt-in** via the scope question.

### 1. Check current state — single probe

`upgrade_status` is usable if the module is **enabled**, regardless of whether it was added to composer or installed via core. Use a single probe:

```bash
ddev drush pm:list --filter=name=upgrade_status --status=enabled --no-ansi 2>/dev/null
```

If a row is returned, the module is enabled — **skip install entirely** and proceed to step 3.

If empty, also check if the package is present but disabled:

```bash
ddev composer show drupal/upgrade_status 2>/dev/null | grep "^versions"
```

This determines cleanup behaviour later (do NOT remove a package the user already had).

Record three booleans for cleanup:
- `was_enabled` — module enabled before this skill ran
- `was_installed` — composer package present before this skill ran
- `we_added_it` — opposite of `was_installed` (true if we install it ourselves)

### 2. Install / enable upgrade_status (only if needed)

Skip this step entirely if `was_enabled` is true.

If the package isn't installed, ask:

> **upgrade_status is not installed. Install it now?**
> - **Install (Recommended)** — `composer require drupal/upgrade_status --dev` then `drush en upgrade_status -y`
> - **Cancel — stop the drupal-deprecation-scan skill**

If the user agrees:

```bash
ddev composer require drupal/upgrade_status --dev --no-ansi
ddev drush en upgrade_status -y --no-ansi
```

If the package is installed but the module is disabled, ask:

> **upgrade_status is installed but disabled. Enable it for this scan?**
> - **Enable (Recommended)** — `drush en upgrade_status -y`
> - **Cancel — stop the drupal-deprecation-scan skill**

```bash
ddev drush en upgrade_status -y --no-ansi
```

### 3. Choose scope

Ask via `AskUserQuestion` (single-select):

> **What should the deprecation scan cover?**
> - **Custom only** — `web/modules/custom/`, `web/themes/custom/`, local install profile (Recommended; matches FY26 People-Applications cleanup PRs)
> - **Custom + vendored upstream** — Also scans `web/modules/apple/`, `web/themes/apple/*`, etc. Use when prepping upstream PRs against `apple-drupal/*`, `ciderpress/*`, `people-applications/*`
> - **Cancel — stop the drupal-deprecation-scan skill**

### 4. Discover the projects to scan

`upgrade_status:analyze` operates on **projects**, not individual modules. A project is a single installable unit with its `<name>.info.yml` at its root; submodules under `<project>/modules/<sub>/<sub>.info.yml` are part of their parent project's release and are walked recursively when the parent is scanned. **Pass projects only — passing a submodule machine name produces an "invalid project machine name" error.**

That means the discovery `find` must stop at the project root, not descend into `modules/`:

```bash
# Modules and themes: project root sits at depth 2 from web/modules/custom or web/themes/custom
MODULES=$(find web/modules/custom -mindepth 2 -maxdepth 2 -name '*.info.yml' 2>/dev/null \
  | xargs -n1 basename \
  | sed 's/\.info\.yml$//' \
  | tr '\n' ' ')

THEMES=$(find web/themes/custom -mindepth 2 -maxdepth 2 -name '*.info.yml' 2>/dev/null \
  | xargs -n1 basename \
  | sed 's/\.info\.yml$//' \
  | tr '\n' ' ')

# Profiles: depth varies by layout
#   flat:          web/profiles/<profile>/<profile>.info.yml          (depth 2)
#   vendored:      web/profiles/<vendor>/<profile>/<profile>.info.yml (depth 3, e.g. web/profiles/apple/ciderpress_profile/)
PROFILES=$(find web/profiles -mindepth 2 -maxdepth 3 -name '*.info.yml' \
  ! -path '*/contrib/*' 2>/dev/null \
  | xargs -n1 basename \
  | sed 's/\.info\.yml$//' \
  | tr '\n' ' ')

TARGETS="$MODULES $THEMES $PROFILES"
echo "Will scan: $TARGETS"
```

For **Custom + vendored upstream**, additionally include `web/modules/apple` and `web/themes/apple` (same `-maxdepth 2` reasoning — vendored Apple packages are projects too):

```bash
VENDORED=$(find web/modules/apple web/themes/apple -mindepth 2 -maxdepth 2 -name '*.info.yml' 2>/dev/null \
  | xargs -n1 basename | sed 's/\.info\.yml$//' | tr '\n' ' ')
TARGETS="$TARGETS $VENDORED"
```

Skip empty subtrees gracefully.

**Layout caveat:** the depths above assume the standard Drupal composer-managed layout (one project per directory directly under `web/modules/custom/`, `web/themes/custom/`, or under a vendor namespace inside `web/profiles/`). If a repo nests projects deeper — e.g. `web/modules/custom/<grouping>/<project>/<project>.info.yml` — bump the maxdepth accordingly. Quick sanity check: `find web/modules/custom -name '*.info.yml' | sort`. Any project-root `.info.yml` deeper than depth 2 means the discovery needs widening.

### 5. Run the scan

Pass the discovered targets as positional args. Always include `--ignore-uninstalled` (matches the shared `ciderpress/drupal-testing` CI harness; suppresses false positives from libraries declared by disabled modules).

`ddev drush <args>` collapses positional args into a single space-joined token, which `upgrade_status:analyze` then rejects as one giant invalid machine name. **Use `ddev exec` instead** so the args reach drush as separate words:

```bash
ddev exec "vendor/bin/drush upgrade_status:analyze $TARGETS --ignore-uninstalled --no-ansi" 2>&1
```

Exit code 1 or 3 is normal (just means findings exist). Don't error on it.

### 6. Extract structured results from the keyValue store

Do not parse the textual output. Read structured data:

```bash
ddev drush eval "echo json_encode(\Drupal::keyValue('upgrade_status_scan_results')->getAll(), JSON_PRETTY_PRINT);" \
  > .claude/drupal-update-reports/upgrade-status-raw-$(date +%Y-%m-%d).json
```

Each top-level key is a module name. Each value has `{date, data: {files: {<path>: {messages: [{message, line, analyzer, upgrade_status_category}]}}}}`.

Also capture the set of currently-enabled extensions so the normalizer can suppress findings from disabled modules (where some analyzers — notably `LibraryDeprecationAnalyzer` — emit false positives like *"library is not defined because the defining extension is not installed"*). The install profile isn't included in `drush pm:list --status=enabled`, so capture it separately:

```bash
ddev drush pm:list --status=enabled --format=json --no-ansi 2>/dev/null \
  > .claude/drupal-update-reports/enabled-extensions.json

# Install profile is "active" but not "enabled" in the pm:list sense; capture separately.
ddev drush status --field=install-profile --no-ansi 2>/dev/null \
  > .claude/drupal-update-reports/active-profile.txt
```

Use this Python (or the equivalent jq) to bucket the results. Four non-obvious things to handle:

1. **The keyValue store persists results across scans** — entries from earlier full-tree scans for `apple_*` modules etc. are still there. Filter to the projects you scanned this round (or by file-path prefix).
2. **upgrade_status returns inconsistent paths** — PHP files come back as `web/modules/custom/...` but `.info.yml` files come back as `modules/custom/...` (no `web/` prefix). Normalize before filtering.
3. **upgrade_status keys findings under the project name (e.g. `clb_core`), not the innermost submodule (e.g. `clb_calibration_org`).** To check enabled state per file, resolve each finding's path back to its innermost module by walking all `*.info.yml` files in the scan tree.
4. **Disabled-module findings are mostly noise** — analyzers that need to introspect a module (libraries, plugin manifests) can't do so when the module is uninstalled, and produce "cannot decide" warnings. Suppress these from the headline; show them in a separate section so nothing's lost.

```bash
python3 <<'PY'
import json, re, pathlib
raw_path = sorted(pathlib.Path('.claude/drupal-update-reports').glob('upgrade-status-raw-*.json'))[-1]
all_results = json.loads(raw_path.read_text())
enabled_path = pathlib.Path('.claude/drupal-update-reports/enabled-extensions.json')
profile_path = pathlib.Path('.claude/drupal-update-reports/active-profile.txt')
enabled_set = None
if enabled_path.exists():
    enabled_set = set(json.loads(enabled_path.read_text()).keys())
    if profile_path.exists():
        profile = profile_path.read_text().strip()
        if profile:
            enabled_set.add(profile)

# Set of project machine names you passed to upgrade_status:analyze this round.
SCAN_PROJECTS = set("$TARGETS".split())

CUSTOM_RX = re.compile(r'(?:^|/)(modules/custom/|themes/custom/|profiles/)')

# Walk all info.yml files in the scanned subtrees to build a (directory -> machine name) map.
# Used to resolve each finding's file path to its innermost (sub)module for enabled-state checks.
modules_by_dir = {}  # directory path (relative, no leading 'web/') -> machine name
for info_yml in pathlib.Path('web').rglob('*.info.yml'):
    rel = str(info_yml.parent).replace('web/', '', 1)
    name = info_yml.name[:-len('.info.yml')]  # strip both extensions; pathlib.stem only strips one
    if CUSTOM_RX.search('/' + rel) or rel.startswith(('modules/apple/', 'themes/apple/')):
        modules_by_dir[rel] = name

def innermost_module(file_path):
    """Find deepest module whose directory contains this file path."""
    rel = file_path.replace('web/', '', 1) if file_path.startswith('web/') else file_path
    best, best_len = None, -1
    for d, name in modules_by_dir.items():
        if rel == d or rel.startswith(d + '/'):
            if len(d) > best_len:
                best, best_len = name, len(d)
    return best

enabled_findings, disabled_findings = [], []
for module, result in all_results.items():
    if SCAN_PROJECTS and module not in SCAN_PROJECTS:
        continue
    files = (result or {}).get('data', {}).get('files') or {}
    for path, fdata in files.items():
        clean_path = path.replace('/var/www/html/', '')
        if not clean_path.startswith('web/') and CUSTOM_RX.search('/' + clean_path):
            clean_path = 'web/' + clean_path
        if not CUSTOM_RX.search('/' + clean_path):
            continue

        innermost = innermost_module(clean_path) or module
        is_enabled = enabled_set is None or innermost in enabled_set

        for msg in fdata.get('messages', []):
            text = msg.get('message', '')
            since = removed = None
            m = re.search(r'[Dd]eprecated in drupal:(\d+)\.(\d+)', text)
            if m: since = f"{m.group(1)}.{m.group(2)}"
            m = re.search(r'removed (?:from|in) drupal:(\d+)\.(\d+)', text)
            if m: removed = f"{m.group(1)}.{m.group(2)}"
            row = {
                'module': module,
                'innermost_module': innermost,
                'enabled': is_enabled,
                'file': clean_path,
                'line': msg.get('line'),
                'analyzer': msg.get('analyzer', 'unknown'),
                'category': msg.get('upgrade_status_category', 'unknown'),
                'since': since,
                'removed': removed,
                'message': text,
            }
            (enabled_findings if is_enabled else disabled_findings).append(row)

out = pathlib.Path('.claude/drupal-update-reports/upgrade-status-findings.json')
out.write_text(json.dumps({'enabled': enabled_findings, 'disabled': disabled_findings}, indent=2))
print(f"Enabled-module findings (main report): {len(enabled_findings)}")
print(f"Disabled-module findings (suppressed):  {len(disabled_findings)}")
if disabled_findings:
    from collections import Counter
    c = Counter(f['innermost_module'] for f in disabled_findings)
    print(f"  Suppressed modules: {dict(c)}")
PY
```

If a user explicitly wants to include disabled modules (e.g. they're scanning a project that's about to be re-enabled), skip the enabled-extensions capture and the normalizer falls back to including everything (`enabled_set is None` branch).

### 7. Build the report

Read `\Drupal::VERSION` so the report can frame everything against the live core version:

```bash
DRUPAL_VERSION=$(ddev drush status --field=drupal-version --no-ansi 2>/dev/null)
```

Compute next/+2 majors from the X.Y.Z form (e.g. `11.3.11` → next `12`, plus-two `13`).

Group findings four ways and produce sections **in this order** in the report. **All headline counts and section bodies use the `enabled` partition only**; the `disabled` partition shows up at the bottom in a single "suppressed" section so nothing is silently lost:

1. **By analyzer** — `PHPStan` vs the three real deprecation analyzers. Header counts, then a one-line summary of "what's actually being reported".
2. **By Drupal version impact** (only for findings with a `removed` version):
   - **Already broken** — `removed <= current major.minor` (highest priority)
   - **Breaks in next major** — `removed == next major.0` (the action bucket)
   - **Breaks in major+2** — long-term debt
3. **Real Drupal-API deprecations** — every finding where `since` parsed successfully. List file:line, since, removed, replacement guidance from the message body.
4. **Other findings** — info.yml `core_version_requirement` items collapsed to one bullet per file; library/Twig/PHPStan groups collapsed to short tables.

For **vendored upstream findings** (when scope was Custom + vendored): show in a separate top-level section labelled "**Upstream — fix in apple-drupal/* or ciderpress/* repos, not here**". Don't intermix with custom findings.

For **disabled-module findings**: collect them in a single "Suppressed: findings in disabled modules" section at the bottom, grouped by innermost module name with a per-module count. Note that `LibraryDeprecationAnalyzer` produces "library is not defined because the defining extension is not installed" warnings for disabled modules even when the library declarations are correct — these are inspection limitations, not real bugs. If the user wants to act on a disabled module's findings, they should either re-enable the module before scanning or remove the module's code entirely.

#### Report template

```
# Drupal Deprecation Scan

- **Scanned:** YYYY-MM-DD
- **Drupal core:** X.Y.Z
- **Next major:** X+1.0 / +2: X+2.0
- **Scope:** Custom only | Custom + vendored upstream
- **Tool:** drupal/upgrade_status <version> (already installed | added by skill)

## Headline (enabled modules only)

- **Real Drupal-API deprecations:** N (M will break in D{X+1}, K in D{X+2})
- **Already-broken (deprecation removed in current or earlier core):** N
- **Code-quality (PHPStan) findings:** N — not deprecations; consider /drupal-quality-loop
- **info.yml core_version_requirement updates needed:** N
- **Library/Twig advisories:** N
- **Suppressed (disabled modules):** N findings across M modules — see bottom of report

## Will break in Drupal {X+1}

[table of file:line, since, removed, message]

## Already broken (removed in or before D{X.Y})

[table or "None"]

## Will break in Drupal {X+2}

[table or "None"]

## Code-quality findings (PHPStan)

[count by file, link to /drupal-quality-loop for fixing]

## info.yml core_version_requirement

[one bullet per file]

## Library / Twig advisories

[short table or "None"]

## Upstream (if scope included vendored)

[grouped by upstream package: apple-drupal/<x>, ciderpress/<y> ...]

## Suppressed: findings in disabled modules

These modules are currently disabled in this environment. Most findings here are false positives from analyzers that can't introspect a disabled module (e.g. "library is not defined because the defining extension is not installed"). To act on them, either re-enable the module before re-scanning, or remove the module's code entirely if it's dead.

- **<module_a>** (N findings) — typical: <one-line summary of categories>
- **<module_b>** (N findings)

## Raw outputs

- `.claude/drupal-update-reports/upgrade-status-raw-YYYY-MM-DD.json` — structured keyValue dump
- `.claude/drupal-update-reports/enabled-extensions.json` — drush pm:list snapshot at scan time
- `.claude/drupal-update-reports/upgrade-status-findings.json` — normalized findings (`{enabled: [...], disabled: [...]}`)

## Verify yourself

So a reviewer (or future-you) can confirm the headline without re-running the whole skill, every report ends with the **exact commands** that produced the result. Include the resolved `$TARGETS` value inline so the commands are copy-paste runnable. Use this template, substituting the live values:

```bash
# 1. Confirm upgrade_status is enabled (install if not):
#    ddev composer require drupal/upgrade_status --dev && ddev drush en upgrade_status -y
ddev drush pm:list --filter=name=upgrade_status --status=enabled --no-ansi

# 2. Re-run the scan with the same scope this report used:
ddev exec "vendor/bin/drush upgrade_status:analyze <RESOLVED $TARGETS HERE> --ignore-uninstalled --no-ansi"

# 3. Filter the structured keyValue store to ONLY real Drupal-API deprecations
#    (those tagged with a "Deprecated in drupal:X.Y" version stamp). PHPStan,
#    library, info.yml, and Twig findings are filtered out — what remains is
#    the urgent set.
ddev drush eval "
\$all = \Drupal::keyValue('upgrade_status_scan_results')->getAll();
foreach (\$all as \$module => \$result) {
  foreach ((\$result['data']['files'] ?? []) as \$path => \$f) {
    foreach (\$f['messages'] ?? [] as \$m) {
      if (preg_match('/[Dd]eprecated in drupal:/', \$m['message'] ?? '')) {
        echo \$module . ' | ' . \$path . ':' . \$m['line'] . PHP_EOL;
        echo '  ' . substr(\$m['message'], 0, 200) . PHP_EOL;
      }
    }
  }
}"
```

Expected result for a clean custom-only scan: the filter prints nothing under `web/modules/custom/`, `web/themes/custom/`, or the local profile. Anything that DOES print there is a real Drupal-API deprecation that needs a fix.
```

If zero real deprecations and the only items are info.yml `core_version_requirement`:

```
✓ No Drupal-API deprecations in enabled custom code. Only N info.yml files need core_version_requirement bumped to allow ^{X+1}.
```

### 8. Save report

Path: `.claude/drupal-update-reports/DRUPAL-DEPRECATIONS--YYYY-MM-DD.md`

Include the headline counts, the analyzer breakdown, the version-impact buckets, the file lists, and pointers to the raw JSON.

### 9. Clean up

Use `AskUserQuestion`:

> **upgrade_status — what would you like to do?**
> - **Uninstall and remove** — Remove module and composer package (Recommended if `we_added_it`)
> - **Keep enabled** — Leave it for next time
> - **Disable but keep** — Uninstall the module, keep the composer package

Apply intelligently using the booleans from step 1:

| `was_enabled` | `was_installed` | "Uninstall and remove" should… |
|---|---|---|
| true | true | Just disable; do NOT remove the package the user already had |
| false | true | Disable; do NOT remove the package |
| false | false | Disable AND `composer remove drupal/upgrade_status` |

Tell the user explicitly which steps you skipped and why, e.g.: "upgrade_status was already in your composer.json — only uninstalling the module, not removing the package."

```bash
# Disable (always safe to run)
ddev drush pm:uninstall upgrade_status -y --no-ansi

# Remove package (ONLY if we_added_it)
ddev composer remove drupal/upgrade_status --no-ansi
```

### 10. Suggest next steps

- If real D+1 deprecations found: list them and suggest opening upstream PRs for vendored items via `/upstream-patch-flow`.
- If many PHPStan findings: suggest `/drupal-quality-loop` (separate skill, designed for this).
- If many info.yml items: note these are trivial bumps; suggest doing them when the team starts the next major's compat testing.
- Always: `Related: /drupal-update for package updates, /drupal-patch-update-check for patches that may now be in releases.`

## Related infrastructure

In Apple People-Applications repos, Rio CI runs the shared deprecation harness from `ciderpress/drupal-testing` (`lib/stages/deprecation_peeps_site.sh`). It uses the same flags this skill uses (`--all --ignore-uninstalled --ignore-contrib`) and ships the structured keyValue dump to the central `pa-deprecations` S3 blobstore: `https://store-test.blobstore.apple.com/pa-deprecations/<org>/v1/<repo>/<DATE>.json`. Mention this if the user is on a People-Applications repo — they may already have a recent CI-tracked result they can compare against.

## Examples

**Example 1: Module already enabled — straight to scan**

```
User: /drupal-deprecation-scan

Claude: Probing upgrade_status... already enabled (4.3.10). Skipping install.

What should the deprecation scan cover?
  → Custom only (Recommended)
    Custom + vendored upstream
    Cancel — stop the drupal-deprecation-scan skill

[user: Custom only]

Claude: Discovered 8 modules + 1 theme in web/modules/custom and web/themes/custom.
Running scan...
Reading keyValue store... 12 findings.

Headline:
- 0 Real Drupal-API deprecations
- 4 Code-quality (PHPStan) findings — consider /drupal-quality-loop
- 8 info.yml core_version_requirement updates pending

Report saved to .claude/drupal-update-reports/DRUPAL-DEPRECATIONS--2026-06-09.md
```

**Example 2: Vendored scope, real D+1 deprecation found**

```
User: Run a deprecation scan including upstream packages

Claude: [scan with vendored scope]

Headline:
- 4 Real Drupal-API deprecations — all break in Drupal 12
  - apple_datatable: template_preprocess_views_view_table (since 11.3, removed 12.0)
  - ...
  
These are upstream — fix in apple-drupal/apple_datatable. Want me to walk
the /upstream-patch-flow for opening that PR?
```

## Tips

- **The textual drush output is for humans only — never parse it.** Always go via the keyValue store.
- **`--ignore-uninstalled` matters.** Without it you get false-positive library findings for modules that aren't enabled in this environment.
- **PHPStan findings are not deprecations.** Don't lump them in. They belong to `/drupal-quality-loop`.
- **Vendored upstream findings are someone else's job.** Surface them in a separate section so the user doesn't try to "fix" code that lives in `web/modules/apple/`.
- **Re-run after fixing.** keyValue store updates only on a fresh `analyze` run.
- **Patch-only updates don't need this skill.** Run after every minor bump; skip for patches.

## Related Skills

- `/drupal-quality-loop` — fix the PHPStan findings this skill surfaces but doesn't fix
- `/drupal-update` — check for available core/contrib updates
- `/drupal-patch-update-check` — see which patches a core/contrib update would let you drop
- `/upstream-patch-flow` — file upstream PRs for vendored-package fixes

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

### What upgrade_status cannot see

`upgrade_status` and PHPStan both detect deprecations by matching the `@deprecated` **docblock tag** on a symbol. A whole class of Drupal deprecations carries no such tag, because the method is not deprecated — only **passing a particular argument** is, and that is enforced at runtime:

```php
// core/lib/Drupal/Core/Config/Config.php — no @deprecated tag on the method
public function save($has_trusted_data = FALSE) {
  if (func_num_args() > 0) {
    @trigger_error('Calling ' . __METHOD__ . '() with the $has_trusted_data argument is deprecated in drupal:11.4.0 and is removed from drupal:13.0.0 …', E_USER_DEPRECATED);
  }
```

`$config->save(TRUE)` triggers that. `$config->save()` does not. Both are valid PHP, both type-check, both pass PHPStan, and **`upgrade_status` reports zero**. The same shape guards `is_int($mode)` on the database statement fetch methods, and `$x instanceof OldInterface` on several constructors mid-way through a DI signature change.

These are easy to miss precisely because a clean scan looks like an all-clear. Step 6b below adds a grep-based pass for them. It is a heuristic, not a proof — but it costs seconds and it catches a category the primary tool structurally cannot.

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

### 6b. Sweep for argument-conditional deprecations (upgrade_status blind spot)

Everything above depends on `@deprecated` tags. This step catches the class described in "What upgrade_status cannot see" — deprecations triggered by a runtime guard inside an otherwise-supported method. Run it on every scan; it takes seconds and needs no site bootstrap.

The approach is two-pass: derive the affected method names **from the core actually installed** (never hardcode a list — it changes every minor), then grep custom code for calls to those methods that pass an argument.

```bash
python3 <<'PY'
import re, pathlib
from collections import defaultdict

# Pass 1 — find core methods whose deprecation fires on a runtime guard.
GUARD = re.compile(r'^\s*if \((?:func_num_args\(\) > 0|is_int\(|!is_string\(|!is_int\(|\$\w+ instanceof )')
FUNC  = re.compile(r'^\s*(?:public|protected|private)?\s*(?:static\s+)?function\s+([a-zA-Z_]\w*)\s*\(')

methods = defaultdict(list)
for root in (pathlib.Path('web/core/lib'), pathlib.Path('web/core/modules')):
    for f in root.rglob('*.php'):
        try:
            lines = f.read_text(errors='ignore').splitlines()
        except Exception:
            continue
        if 'E_USER_DEPRECATED' not in '\n'.join(lines):
            continue
        for i, ln in enumerate(lines):
            if 'E_USER_DEPRECATED' not in ln:
                continue
            guard = next((lines[j].strip() for j in range(max(0, i - 5), i) if GUARD.match(lines[j])), None)
            if not guard:
                continue
            method = next((FUNC.match(lines[j]).group(1) for j in range(i, max(0, i - 60), -1) if FUNC.match(lines[j])), None)
            if not method:
                continue
            removed = re.search(r'removed (?:from|in) drupal:(\d+)', ln)
            methods[method].append({
                'core': f'{f}:{i + 1}',
                'guard': guard[:60],
                'removed': removed.group(1) if removed else '?',
            })

print(f'Core methods with runtime-guarded deprecations: {len(methods)}')
for m in sorted(methods):
    print(f'  {m}  (removed in D{methods[m][0]["removed"]})  guard: {methods[m][0]["guard"]}')

# Pass 2 — find custom call sites passing an argument to any of them.
print('\nCustom call sites passing arguments to those methods:')
SKIP = {'__construct'}  # too generic to grep usefully; check DI signatures by hand
hits = 0
for sub in ('web/modules/custom', 'web/themes/custom'):
    base = pathlib.Path(sub)
    if not base.exists():
        continue
    for f in list(base.rglob('*.php')) + list(base.rglob('*.module')) + list(base.rglob('*.theme')):
        try:
            lines = f.read_text(errors='ignore').splitlines()
        except Exception:
            continue
        for i, ln in enumerate(lines):
            if ln.lstrip().startswith(('//', '*', '#')):
                continue
            for m in methods:
                if m in SKIP:
                    continue
                # ->method( followed by anything that is not immediately ')'
                if re.search(rf'->{re.escape(m)}\(\s*[^)\s]', ln):
                    print(f'  {f}:{i + 1}  [{m}, removed D{methods[m][0]["removed"]}]')
                    print(f'      {ln.strip()[:120]}')
                    hits += 1
print(f'\n{hits} call site(s) to review by hand.')
PY
```

**Triage the output by hand — most hits are fine.** The grep cannot tell an offending argument from a legitimate one. For each hit, open the core method named in pass 1 and check whether the specific argument being passed satisfies the guard:

- `save(TRUE)` fires `func_num_args() > 0`; `save()` does not.
- `fetchAllAssoc('id')` is fine; `fetchAllAssoc('id', \PDO::FETCH_ASSOC)` fires `is_int($mode)` — the fix is the `\Drupal\Core\Database\Statement\FetchAs` enum (`FetchAs::Associative`, `::Object`, `::List`, `::Column`, `::ClassObject`).
- `instanceof` guards are mid-flight DI signature changes: check the argument order against the current core constructor.

Report survivors in the "Will break in Drupal {X+1}" / "{X+2}" buckets alongside the upgrade_status findings, tagged **found by argument-conditional sweep, not reported by upgrade_status** so the reader knows the primary tool was silent on them.

**Limitations, state them in the report:** the guard regex covers the four shapes above within five lines of the trigger, matches on method *name* only (so a same-named method on an unrelated class is a false positive), and skips `__construct`. It will miss guards written differently. It is a net, not a proof.

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
- **Argument-conditional deprecations (sweep only — upgrade_status reports these as clean):** N
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

## Argument-conditional deprecations (sweep)

Found by the step 6b grep, not by upgrade_status — these carry no `@deprecated` tag, so a clean upgrade_status result says nothing about them.

[table of file:line, the call as written, the core guard it trips, removed-in version, and the fix — or "None found. Swept N core methods with runtime-guarded deprecations against M custom call sites."]

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

**Never write that line without having run step 6b.** A clean `upgrade_status` result is not evidence of zero deprecations — it is evidence of zero *tagged* deprecations. If the sweep was skipped, say so explicitly instead: "upgrade_status found none; the argument-conditional sweep was not run."

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

**`dbuytaert/drupal-digests`** (<https://github.com/dbuytaert/drupal-digests>) publishes ~184 Rector rules extracted from Drupal core issues, one file per deprecation, named `<description>-<issue-number>.php`. Useful to this skill in two distinct ways, worth keeping separate:

1. **As a reference, zero risk.** The `rector/rules/` directory is a browsable index of what core has deprecated recently, including the argument-conditional ones step 6b hunts for — it carries rules for `Config::save(TRUE)`/`trustData()` (`…-3347842.php`), the integer fetch mode (`…-3488467.php`), and `getEntityTypeIdKeyType()` (`…-3566801.php`). When a sweep hit needs triage, or you want to know whether a pattern has a known fix, read the matching rule. It cites the change record and shows before/after.
2. **As a tool, only after evaluation.** Rector rewrites code from the AST, so it catches what tag-matching cannot — but this is a personal project (~29 stars, no release process, unaffiliated with the Drupal Association) whose README states the rules were AI-extracted and "may contain errors". That is observable in the source: rule filenames cite change-record IDs that do not always match the node in core's own deprecation message (`…-3566801.php` vs core's 3566814; `…-3488467.php` vs 3488338), so treat rule metadata as unreliable. **Never apply it without `--dry-run` first, and never in an environment where adding a third-party dev dependency is a supply-chain decision you are not authorised to make.**

Treat a Rector rule as a hypothesis to verify against core's own source, not as an authority.

#### Mechanical facts about this rule set

These are not judgement calls — they are properties of the ruleset and of Rector that cannot be inferred by reading the code you are scanning, and each one has produced a wrong conclusion in practice. Verified against ruleset commit `fe88ea1`; re-check them if the numbers have drifted, because `main` is a moving target (it advanced twice in 24 hours during evaluation) and there are no tags.

- **`--config` does not invalidate Rector's cache.** Running rule A, then rule B against the same paths can report `[OK] Rector is done!` for B purely from A's cached result. This produced a false "rule does not fire" during evaluation on a rule that fires correctly. **Always pass `--clear-cache` when sweeping rule-by-rule.** A cached zero and a real zero are indistinguishable in the output.
- **`all.php` runs 153 of the 184 rules.** The other 31 are listed in a `Not included (standalone configs, run separately)` comment block at the top of the file and are silently skipped — including `rename-deprecated-defaultfetchmode-to-fetchmode-in-database-3488467.php`. The README's own one-liner therefore does not run them. To cover everything, run the excluded ones individually.
- **`rector/` holds two parallel copies.** `rector/rules/*.php` are the 184 rule *classes*; the 184 same-named files directly in `rector/` are runnable standalone *configs* (plus `all.php`). Use the flat ones for per-rule attribution — `--rules-summary` renders rule names blank under `all.php`'s `require_once` loading, so a combined run cannot tell you which rule produced which diff.
- **`all.php` does handle Drupal file extensions — the 31 excluded configs do not.** `all.php` and each of the 153 standalone configs it includes set `withFileExtensions(['php', 'engine', 'inc', 'install', 'module', 'profile', 'theme'])`, so `.module`/`.install`/`.theme` are covered there. The 31 configs on the exclusion list set **no** extensions and therefore fall back to Rector's `.php`-only default — and that set is *exactly* the same 31. So the rules you have to run individually are precisely the ones that will silently skip `.module`, `.install` and `.theme` unless you add `--file-extension` yourself. The usual "Rector only reads `.php` by default" worry is wrong for `all.php` and right for everything it leaves out.
- **Three configs strip unused imports repo-wide as a side effect.** `remove-deprecated-phpunitcompatibilitytrait-from-test-3582118.php`, `add-void-return-type-hints-to-phpunit-test-methods-3562361.php` and `add-php-type-declarations-to-module-and-test-code-via-rector-3584406.php` each set `->withImportNames(removeUnusedImports: true)`. The first matches nothing in a typical codebase yet still reports dozens of changed files — unrelated churn from a rule advertised as doing something else. All three are on the exclusion list; keep them there.
- **No rule covers `\PDO::FETCH_*` passed as an argument.** The similarly-named fetch-mode rule renames a `$defaultFetchMode` *property* on `StatementPrefetchIterator`/`StatementWrapperIterator` subclasses (removed **D12**). The integer-fetch-mode deprecation that actually appears in application code — `fetchAllAssoc('id', \PDO::FETCH_ASSOC)`, `setFetchMode(\PDO::FETCH_ASSOC)`, fixed with the `FetchAs` enum — has **no rule at all**. Step 6b's sweep is the only thing that finds it.
- **Rules gate on class ancestry, never on core version.** `UseEntityTypeHasIntegerIdRector` fires only inside subclasses of `DefaultHtmlRouteProvider`, `CommentTypeForm` or `OverridesSectionStorage`, which is why it correctly skips a class that declares its own same-named helper. But it would happily rewrite a class that *does* extend core's provider while declaring `^11 || ^12`, breaking 11.0–11.3 where `hasIntegerId()` does not exist. **Check the module's `core_version_requirement` before accepting any proposal that introduces a newly-added core method.**
- **A rule can be half-broken and still report success.** `RemoveTrustedDataConceptRector` documents two patterns; only the first works. `$config->save(TRUE)` → `$config->save()` fires correctly (and is genuinely valuable — it is invisible to upgrade_status, PHPStan and the phpstan baseline alike). The `$entity->trustData()->save()` pattern type-guards on `Drupal\Core\Config\Config`, which a config *entity* never resolves to, so it never fires. Per-rule zero results say nothing about the patterns a rule claims to cover.

**Running it, if you run it:**

```bash
# vendor/ is git-tracked in some repos — install in a throwaway worktree so
# composer.json/lock/vendor at the repo root are never touched.
git worktree add --detach .worktrees/rector-base <commit>
cp .env .worktrees/rector-base/.env   # Rector's bootstrap runs load.environment.php

# The container's /tmp is NOT the host's /tmp. Put the clone somewhere the
# container can see that is also gitignored, so it cannot reach a commit.
git clone --depth 1 https://github.com/dbuytaert/drupal-digests.git .worktrees/rector-digests

ddev exec "cd /var/www/html/.worktrees/rector-base && composer require rector/rector --dev --no-interaction"
ddev exec "cd /var/www/html/.worktrees/rector-base && vendor/bin/rector process web/modules/custom \
  --config /var/www/html/.worktrees/rector-digests/rector/<single-rule>.php \
  --dry-run --no-progress-bar --clear-cache"

git worktree remove --force .worktrees/rector-base && rm -rf .worktrees/rector-digests
```

`--dry-run` exits **non-zero whenever it would change anything**, so a non-zero exit is the normal result and must not be treated as a tool error. Report per-rule counts, never a single aggregate pass/fail.

#### When a rule misbehaves, capture it for upstream

The rules are AI-extracted and the README says they may contain errors, so finding a defect is expected rather than remarkable. Each one you find is worth two minutes of write-up, because the alternative is that the next person re-derives it. Log it below and offer the user a sanitised upstream report.

**Before calling anything a defect, read the rule's source.** Several rules are deliberately conservative and say so in a comment; reporting those as bugs wastes everyone's time and damages the report's credibility. The distinction to make:

- **Defect** — the rule does not do what its own docblock says. Report it.
- **Deliberate limitation** — the rule's source documents why it declines a case. Propose an enhancement, or leave it.
- **Inherent limitation** — the rule needs a resolvable type and your code does not provide one. Not reportable; just know that per-rule counts are a floor, never a total.

**Reporting shape.** Prefer an **issue over a PR**: with no tags and no release process, a merged fix cannot be consumed by version bump, so the repro is the valuable part, not the patch. Always (a) name the ruleset commit you ran, since `main` moves untagged; (b) write the reproduction in **core terms only** — no internal class, module, repo or ticket names, no employer source; a two-class core-only example is enough. Filing is a GitHub write, so draft it and get the user's approval first.

**Known defects — verified against ruleset commit `fe88ea1`.** Check here before re-investigating.

| Rule | Finding |
|---|---|
| `remove-deprecated-trusted-data-concept-…-3347842.php` | **Defect.** Pattern 2 guards on `ObjectType('Drupal\Core\Config\Config')` while its docblock targets `ConfigEntityBase::trustData()`. A config *entity* never resolves to that type, so the documented `$entity->trustData()->save()` pattern cannot fire. Pattern 1 (`$config->save(TRUE)`) works and is genuinely valuable. Likely fix: guard on `ConfigEntityInterface`. |
| `add-runtestsinseparateprocesses-…-3546029.php` | **Defect.** Proposed 54 of 56 in-scope classes; the two missed extend `EntityKernelTestBase`, itself a `KernelTestBase` subclass, so indirect ancestry through a core intermediate is not resolved. Fails safe (false negative), but 54-of-56 reads as a finished job — more misleading than a zero. |
| `rename-deprecated-defaultfetchmode-…-3488467.php` | **Metadata defect + gap.** Renames a `$defaultFetchMode` property, which is a different deprecation from the integer-fetch-mode one its name suggests (core cites 3488338). And no rule anywhere covers `\PDO::FETCH_*` passed as an *argument* — worth proposing as a new rule. |
| `replace-deprecated-entity-type-integer-id-helpers-…-3566801.php` | **Metadata defect.** Filename cites 3566801; core's own deprecation message cites 3566814. Docblocks within the file disagree too. |
| The 31 configs excluded from `all.php` | **Consistency defect.** They set no `withFileExtensions()`, so run individually they silently cover `.php` only — while all 153 included configs do set it. The rules you must run by hand are exactly the ones that will skip `.module`/`.install`/`.theme`. |
| `remove-deprecated-phpunitcompatibilitytrait-…-3582118.php` and two others | **Design issue.** Each sets `->withImportNames(removeUnusedImports: true)`, so the config strips unused imports repo-wide as a side effect of the rule. This one matches nothing in a typical codebase yet reports dozens of changed files. |
| `replace-deprecated-entity-original-magic-property-…-3571065.php` | **Deliberate limitation, do not report as a bug.** It skips `$this->original` via an explicit `!isThisVar()` guard, commented as protecting non-entity classes (`EntityTypeEvent`, `FieldStorageDefinitionEvent`) that own a legitimate `$original` property. Over-conservative for entity subclasses, where the deprecation does fire — a reasonable enhancement request would be to allow `$this` when it resolves to `EntityInterface`. |
| Any type-guarded rule | **Inherent limitation.** An untyped receiver (`function getComparison($entity, …)`) cannot be resolved, so the guard fails and the site is skipped silently. Nothing to report; it is why per-rule counts are a floor. |


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
- **A clean upgrade_status result is not "no deprecations".** It means no `@deprecated`-tagged symbol is referenced. Argument-conditional deprecations (step 6b) are invisible to it, to PHPStan, and to the phpstan baseline — all three report clean. Always run the sweep before declaring an all-clear.
- **`SYMFONY_DEPRECATIONS_HELPER` is not the fallback you might expect.** It belongs to `symfony/phpunit-bridge`, which Drupal 11 no longer ships — core uses its own `DeprecationHandler` (`core/tests/bootstrap.php`), configured via PHPUnit XML extension config, not that env var. Check `composer.lock` for the bridge before trusting a "strict mode" run; without it the variable is inert and a green run means nothing. Even when wired up, it only catches deprecations on code paths the tests actually execute.
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

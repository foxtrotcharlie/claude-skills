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

### 4. Discover the modules to scan

For **Custom only** (the default), build the module-name list from `.info.yml` files. This matches the pattern used in reflect #2261 and signups #1011:

```bash
MODULES=$(find web/modules/custom -mindepth 2 -maxdepth 4 -name '*.info.yml' \
  ! -path '*/tests/*' \
  | xargs -n1 basename \
  | sed 's/\.info\.yml$//' \
  | tr '\n' ' ')

THEMES=$(find web/themes/custom -mindepth 2 -maxdepth 3 -name '*.info.yml' \
  | xargs -n1 basename \
  | sed 's/\.info\.yml$//' \
  | tr '\n' ' ')

PROFILES=$(find web/profiles -mindepth 2 -maxdepth 3 -name '*.info.yml' \
  ! -path '*/contrib/*' \
  | xargs -n1 basename \
  | sed 's/\.info\.yml$//' \
  | tr '\n' ' ')

TARGETS="$MODULES $THEMES $PROFILES"
echo "Will scan: $TARGETS"
```

For **Custom + vendored upstream**, additionally include `web/modules/apple` and `web/themes/apple`:

```bash
VENDORED=$(find web/modules/apple web/themes/apple -mindepth 2 -maxdepth 4 -name '*.info.yml' 2>/dev/null \
  | xargs -n1 basename | sed 's/\.info\.yml$//' | tr '\n' ' ')
TARGETS="$TARGETS $VENDORED"
```

Skip empty subtrees gracefully.

### 5. Run the scan

Pass the discovered targets as positional args. Always include `--ignore-uninstalled` (matches the shared `ciderpress/drupal-testing` CI harness; suppresses false positives from libraries declared by disabled modules):

```bash
ddev drush upgrade_status:analyze $TARGETS --ignore-uninstalled --no-ansi 2>&1
```

Exit code 1 is normal (it just means findings exist). Don't error on it.

### 6. Extract structured results from the keyValue store

Do not parse the textual output. Read structured data:

```bash
ddev drush eval "echo json_encode(\Drupal::keyValue('upgrade_status_scan_results')->getAll(), JSON_PRETTY_PRINT);" \
  > .claude/drupal-update-reports/upgrade-status-raw-$(date +%Y-%m-%d).json
```

Each top-level key is a module name. Each value has `{date, data: {files: {<path>: {messages: [{message, line, analyzer, upgrade_status_category}]}}}}`.

Use this Python (or the equivalent jq) to bucket the results:

```bash
python3 <<'PY'
import json, re, pathlib, datetime
raw_path = sorted(pathlib.Path('.claude/drupal-update-reports').glob('upgrade-status-raw-*.json'))[-1]
all_results = json.loads(raw_path.read_text())

findings = []
for module, result in all_results.items():
    files = result.get('data', {}).get('files') or {}
    for path, fdata in files.items():
        for msg in fdata.get('messages', []):
            text = msg.get('message', '')
            since = removed = None
            m = re.search(r'[Dd]eprecated in drupal:(\d+)\.(\d+)', text)
            if m: since = f"{m.group(1)}.{m.group(2)}"
            m = re.search(r'removed (?:from|in) drupal:(\d+)\.(\d+)', text)
            if m: removed = f"{m.group(1)}.{m.group(2)}"
            findings.append({
                'module': module,
                'file': path.replace('/var/www/html/', ''),
                'line': msg.get('line'),
                'analyzer': msg.get('analyzer', 'unknown'),
                'category': msg.get('upgrade_status_category', 'unknown'),
                'since': since,
                'removed': removed,
                'message': text,
            })

# Save normalized findings
out = pathlib.Path('.claude/drupal-update-reports/upgrade-status-findings.json')
out.write_text(json.dumps(findings, indent=2))
print(f"{len(findings)} findings normalized -> {out}")
PY
```

### 7. Build the report

Read `\Drupal::VERSION` so the report can frame everything against the live core version:

```bash
DRUPAL_VERSION=$(ddev drush status --field=drupal-version --no-ansi 2>/dev/null)
```

Compute next/+2 majors from the X.Y.Z form (e.g. `11.3.11` → next `12`, plus-two `13`).

Group findings four ways and produce sections **in this order** in the report:

1. **By analyzer** — `PHPStan` vs the three real deprecation analyzers. Header counts, then a one-line summary of "what's actually being reported".
2. **By Drupal version impact** (only for findings with a `removed` version):
   - **Already broken** — `removed <= current major.minor` (highest priority)
   - **Breaks in next major** — `removed == next major.0` (the action bucket)
   - **Breaks in major+2** — long-term debt
3. **Real Drupal-API deprecations** — every finding where `since` parsed successfully. List file:line, since, removed, replacement guidance from the message body.
4. **Other findings** — info.yml `core_version_requirement` items collapsed to one bullet per file; library/Twig/PHPStan groups collapsed to short tables.

For **vendored upstream findings** (when scope was Custom + vendored): show in a separate top-level section labelled "**Upstream — fix in apple-drupal/* or ciderpress/* repos, not here**". Don't intermix with custom findings.

#### Report template

```
# Drupal Deprecation Scan

- **Scanned:** YYYY-MM-DD
- **Drupal core:** X.Y.Z
- **Next major:** X+1.0 / +2: X+2.0
- **Scope:** Custom only | Custom + vendored upstream
- **Tool:** drupal/upgrade_status <version> (already installed | added by skill)

## Headline

- **Real Drupal-API deprecations:** N (M will break in D{X+1}, K in D{X+2})
- **Already-broken (deprecation removed in current or earlier core):** N
- **Code-quality (PHPStan) findings:** N — not deprecations; consider /drupal-quality-loop
- **info.yml core_version_requirement updates needed:** N
- **Library/Twig advisories:** N

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

## Raw outputs

- `.claude/drupal-update-reports/upgrade-status-raw-YYYY-MM-DD.json` — structured keyValue dump
- `.claude/drupal-update-reports/upgrade-status-findings.json` — normalized findings
```

If zero real deprecations and the only items are info.yml `core_version_requirement`:

```
✓ No Drupal-API deprecations in custom code. Only N info.yml files need core_version_requirement bumped to allow ^{X+1}.
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

# claude-skills

A small marketplace of [Claude Code](https://claude.com/claude-code) skills for
Drupal development and general coding workflows. The skills are grouped into two
independently-installable plugins so you only pull in what you want.

## Install

Add the marketplace, then install the plugin(s) you want:

```
/plugin marketplace add foxtrotcharlie/claude-skills
/plugin install drupal-dev@claude-skills
/plugin install dev-general@claude-skills
```

## Updating

Claude Code caches each installed plugin version under
`~/.claude/plugins/cache/claude-skills/<plugin>/<version>/` and does **not**
auto-pull repo changes. After a new commit + version bump (locally or
upstream), you need to refresh the marketplace clone.

### Check the version you're on

```
ls ~/.claude/plugins/cache/claude-skills/drupal-dev/
```

(Same path with `dev-general/` for the other plugin.) Each subfolder is a
cached version. To see which one a skill **actually uses**, invoke it and read
the first line of output:
`Base directory for this skill: ~/.claude/plugins/cache/claude-skills/<plugin>/<version>/...`.

### Check the latest version available

```
cat ~/.claude/plugins/marketplaces/claude-skills/.claude-plugin/marketplace.json | grep '"version"'
```

(or look at `.claude-plugin/marketplace.json` on GitHub.)

### Update to the latest

```
/plugin marketplace update claude-skills
/reload-plugins
```

`marketplace update` pulls the latest commit from the repo and refreshes the
plugin cache. `reload-plugins` makes the active plugin instances pick up the
newer versions. Look for a "N plugins bumped" line — that's your confirmation
the cache moved forward. If you see "0 skills" reloaded after a known-good
push, the version in `marketplace.json` probably wasn't bumped (the cache
short-circuits when the version string is unchanged).

If the cleaner path above ever breaks, the fallback is the full
uninstall-and-reinstall sequence:

```
/plugin uninstall drupal-dev@claude-skills
/plugin uninstall dev-general@claude-skills
/plugin marketplace remove claude-skills
/plugin marketplace add foxtrotcharlie/claude-skills
/plugin install drupal-dev@claude-skills
/plugin install dev-general@claude-skills
/reload-plugins
```

### Versioning

Each plugin has its own `version` field in `.claude-plugin/marketplace.json`.
Bump them on each substantive change:

- **patch** (`1.0.x`) — behaviour-preserving (docs, internal cleanup).
- **minor** (`1.x.0`) — adds a feature or skill.
- **major** (`x.0.0`) — breaking workflow change.

The marketplace's own top-level `version` covers cross-plugin changes (a new
plugin appearing, a plugin being removed). Skill additions inside an existing
plugin only need that plugin's version bumped.

## Plugins

### `drupal-dev`

General-purpose Drupal skills, not coupled to any particular site:

- **drupal-quality-loop** — drives the iterative phpcbf → phpcs → phpstan
  red/green loop on changed PHP (or a named target), fixing mechanical
  violations and rerunning until the gates are clean.
- **drupal-architecture-analysis** — analyzes a Drupal codebase to surface
  architectural patterns, design decisions, and transferable lessons.
- **drupal-deprecation-scan** — runs `upgrade_status` against custom modules to
  find deprecated API usage before a major-version upgrade, then reports and
  cleans up.

### `dev-general`

Framework-agnostic workflow skills:

- **teach-me-as-you-go** — a sticky teaching mode that breaks multi-step work
  into discrete steps and explains the non-obvious *why* after each one.
- **skill-prospector** — mines recent Claude Code sessions for repetitive tasks
  that are good candidates to become reusable skills.

## License

MIT

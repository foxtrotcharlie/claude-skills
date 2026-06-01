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

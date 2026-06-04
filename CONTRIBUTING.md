# Contributing

This repo is a [Claude Code](https://claude.com/claude-code) plugin marketplace
named `claude-skills`. Skills are grouped into independently-installable plugins:

- **`drupal-dev`** — general-purpose Drupal skills
- **`dev-general`** — framework-agnostic workflow skills

> Public repo. Anything employer/Apple-internal belongs in the private
> `charles-tanton/claude` marketplace instead — not here.

## Layout

```
.claude-plugin/marketplace.json    # lists the plugins
plugins/
  <bundle>/
    plugin.json                    # { name, version, description }
    skills/
      <skill-name>/
        SKILL.md                   # required
        references/ scripts/ ...   # optional
```

Each plugin auto-discovers **every** skill under its own `skills/` directory.
Do **not** create a shared `skills/` at the repo root: a plugin whose `source`
is the repo root loads the entire tree, which breaks independent installs. The
per-`plugins/<bundle>/` layout is what keeps the bundles separable.

## Keep it publishable

Everything here is public. Keep skills free of internal references — internal
hostnames, private repo/package names, ticket prefixes, service names,
masquerade flows, real people. Use generic examples (`my_module`,
`web/modules/custom`, etc.).

## Workflows

**Golden rule:** edit skills **in this repo**, never in `~/.claude/skills`. A
copy there shadows the marketplace version and reintroduces the duplication this
layout was built to avoid.

The marketplace pulls from the **remote**, so always `git push` before running a
`/plugin marketplace update`.

### Update an existing skill

1. Edit `plugins/<bundle>/skills/<name>/SKILL.md`.
2. `git commit` + `git push`.
3. In Claude Code:
   ```
   /plugin marketplace update claude-skills
   /reload-plugins
   ```

### Add a new skill to an existing bundle

1. Create `plugins/<bundle>/skills/<new-name>/SKILL.md`.
2. `git commit` + `git push`.
3. `/plugin marketplace update claude-skills` then `/reload-plugins`.

No `marketplace.json` change and no reinstall — the plugin auto-discovers the new
skill under its `skills/` dir.

### Add a new bundle (new plugin)

1. Create `plugins/<new-bundle>/plugin.json` (`{ name, version, description }`)
   and `plugins/<new-bundle>/skills/<skill>/SKILL.md`.
2. Add an entry to `.claude-plugin/marketplace.json` under `plugins[]`:
   ```json
   {
     "name": "<new-bundle>",
     "description": "...",
     "version": "1.0.0",
     "source": "./plugins/<new-bundle>"
   }
   ```
3. `git commit` + `git push`.
4. New plugins need an explicit install:
   ```
   /plugin marketplace update claude-skills
   /plugin install <new-bundle>@claude-skills
   /reload-plugins
   ```

### Using `skill-creator`

`skill-creator` writes to `~/.claude/skills/<name>` by default. When the skill is
ready: **move** the directory into the right `plugins/<bundle>/skills/`, then
**delete the `~/.claude/skills/<name>` copy** so it doesn't shadow the
marketplace. Then commit / push / update as above.

## Install

```
/plugin marketplace add foxtrotcharlie/claude-skills
/plugin install drupal-dev@claude-skills
/plugin install dev-general@claude-skills
/reload-plugins
```

---
name: drupal-architecture-analysis
description: >
  Analyze a Drupal site's codebase to extract architectural patterns, design decisions, and
  transferable insights for professional growth. Produces a structured report with an executive
  summary, per-concern deep analysis, diagrams, and actionable lessons. Use when the user asks
  to understand a site's architecture, review design patterns, analyze how a codebase is structured,
  understand why decisions were made, or wants a high-level view of a Drupal project. Also trigger
  when the user mentions "architecture analysis", "site anatomy", "design patterns in this codebase",
  "architectural review", "how is this site built", "what can I learn from this code", or wants to
  study an existing codebase to grow as an architect.
---

# Drupal Architecture Analysis

You are performing an architectural analysis of a Drupal codebase. Your goal is not to describe
what the code does — it's to understand and explain *why* the codebase is shaped the way it is.
You're helping the user see the forest, not the trees.

## The Mindset: Analysis vs Description

This distinction is the single most important thing in this skill. Every paragraph you write
should pass the "so what?" test.

**Description** (surface-level, avoid):
> "The `grow_assessment` module defines a `grow_assessment` entity type with bundles for manager
> reviews, peer feedback, and check-ins."

**Analysis** (insightful, aim for this):
> "The codebase uses a single base entity type with bundles rather than separate entity types for
> reviews, feedback, and check-ins. This is a Single Table Inheritance pattern — bundles share the
> base table and storage handler, which simplifies queries that span all assessment types (e.g.,
> 'show me everything related to this employee'). The cost is that bundle-specific fields
> accumulate on the shared type, and access control must branch on bundle. This pattern works
> well when entity types share a lifecycle and common fields, which they do here since all
> assessments belong to a grow_event, reference an employee, and move through workflow states.
> **Takeaway**: Prefer bundles when you need cross-type queries and your types share 70%+ of
> their fields; prefer separate entity types when types diverge significantly."

The second version names the pattern, explains the reasoning, identifies the trade-off, and
gives the reader transferable judgment they can apply to their next project.

## Analysis Process

Work through three phases. Use subagents to parallelize exploration where possible — this is
a large analysis task and the codebase won't fit in a single context window.

### Phase 1: Structural Survey

Get the lay of the land before diving deep. Read these key files:

1. **`composer.json`** — Dependencies, patches, scripts, repositories. Map the dependency
   decisions: what's custom vs contrib vs external.
2. **All `.info.yml` files** in custom modules — Module names, descriptions, inter-module
   dependencies. This reveals the dependency graph.
3. **All `.services.yml` files** in custom modules — Service definitions, DI patterns.
   What services exist and what do they depend on?
4. **Directory structure** — `ls` the key directories: custom modules, themes, config/sync,
   settings/, scripts/.
5. **Infrastructure config** — DDEV config, docker-compose overrides, CI config. What
   services does the environment need?
6. **Settings files** — settings.php and environment-specific overrides. How is configuration
   managed across environments?

From this survey, build a mental map before going deeper:
- How many custom modules? How do they depend on each other?
- What contrib modules are used and why were they likely chosen over alternatives?
- What external services does the site integrate with?
- How is the dev environment configured?

**Verify before you claim.** Module and class names in Drupal can be misleading. A module
called "resolvers" might resolve page metadata, not GraphQL queries. A module called "client"
might wrap a local service, not an HTTP API. Before writing that a module does X, read its
actual source code — at minimum the .module file and primary service classes. Never infer a
module's purpose solely from its name or directory location. A wrong claim that propagates
through the report (system map, executive summary, per-concern sections) is worse than a gap.

### Phase 2: Deep Analysis by Architectural Concern

For each concern below, investigate the relevant code and extract patterns. For each one:
- **Name the pattern** — Give it a recognized name (GoF, DDD, enterprise patterns, or Drupal-specific)
- **Explain the reasoning** — Why was this approach likely chosen? What constraints shaped it?
- **Identify the trade-off** — What was gained? What was sacrificed?
- **Compare to alternatives** — How else could this have been done? When would you choose differently?
- **Extract a transferable lesson** — What can the reader take to their next project?

Favor thoroughness. Cover every concern that has something interesting to say — this analysis
is meant to be a comprehensive architectural reference, not a summary. When in doubt, go
deeper rather than skipping. The user can skim sections that don't interest them, but they
can't recover insights you never wrote down. That said, if a concern is genuinely trivial
for a given codebase (e.g., no custom plugins exist), a one-line note is better than padding.

#### Concerns to Investigate

**Domain Model**
Look at entity type definitions, bundle classes, field definitions, entity references.
How was the business domain decomposed into data structures? What's an entity vs a field vs
config? Where are the boundaries? Patterns: bundles (single table inheritance), separate entity
types, computed fields, entity references vs embedded data.

**Module Architecture**
Look at module dependencies, what code lives where, module communication patterns.
What's the organizing principle — by feature, by layer, by external system? Is there a "core"
module that others depend on? Patterns: feature modules, shared kernel, layered architecture.

**Service Design**
Look at services.yml, service classes, interfaces, factory patterns.
What's abstracted behind interfaces? What services are swappable? Are there decorators,
tagged services, or factory patterns? Patterns: repository, adapter, facade, strategy.

**Integration Architecture**
Look at external API clients, queue workers, sync commands, webhook handlers.
How does data enter and leave the system? What happens when external services fail? How is
consistency maintained? Patterns: ports and adapters, anti-corruption layer, eventual consistency.

**Access Control**
Look at access control handlers, route access, permissions, role checks.
What's the security model? Role-based, attribute-based, state-dependent? How do permissions
compose? How does the org hierarchy factor in? Patterns: RBAC, ABAC, hierarchical access.

**Security Architecture**
Look at authentication mechanisms (SSO, OAuth, session handling), input validation and
sanitization patterns, CSRF/XSS protections, secrets management (how API keys and credentials
are stored and injected), data encryption (at rest, in transit), audit logging, and content
security policies. How does the site handle sensitive employee data (PII, performance ratings)?
Are there data isolation boundaries between tenants or org units? How are external API
credentials rotated? What security-related contrib modules were chosen and what do they
protect against? Patterns: defense in depth, principle of least privilege, zero trust,
data classification tiers, audit trail patterns.

**State & Workflow**
Look at state fields, transition logic, workflow modules, event subscribers on state changes.
How do entities move through their lifecycle? Who can trigger transitions? What side effects
do transitions cause? Patterns: state machine, event-driven, saga.

**Configuration Strategy**
Look at config/sync directory, settings files, environment overrides, feature flags.
What's config vs code vs database content? How do environments differ? How are features
toggled? Patterns: config splits, environment overrides, feature flags.

**Extension & Plugin Patterns**
Look at custom plugin types, hook implementations, event subscribers, service decorators.
What extension points exist? What's pluggable vs hardcoded? How would a new developer add
a new variant of something? Patterns: plugin architecture, event-driven, observer.

**Frontend Integration**
Look at the theme layer, JS frameworks, API endpoints (JSON:API, REST, custom routes).
How do frontend and backend communicate? What's server-rendered vs client-rendered? How is
the API designed? Don't assume a module provides a specific API type (e.g., GraphQL) based
on its name — read the actual code to confirm. Patterns: decoupled, progressively decoupled, BFF.

**Testing Philosophy**
Look at test directories, test base classes, mocking strategy, what's covered.
What does the team consider worth testing? What's mocked vs real? What shape is the testing
pyramid? Patterns: integration-heavy, existing-site testing, contract testing.

**Data Processing**
Look at batch operations, queue workers, cron implementations, drush commands.
How is large-scale processing handled? What's sync vs async? How are failures handled and
retried? Patterns: batch processing, queue-based, ETL pipeline.

### Phase 3: Cross-Cutting Synthesis

After the per-concern analysis, step back and look across the whole codebase:

- **Consistency** — Where does the codebase follow consistent patterns? Where does it deviate,
  and can you infer why?
- **Evolution signals** — Are there signs of architectural evolution? Old patterns being replaced
  by newer ones? Layers of history in the code?
- **Architectural strengths** — What does this architecture do particularly well? What would
  you recommend others adopt?
- **Architectural tensions** — Where does the design show strain? Where might it need to evolve
  as requirements grow?
- **Transferable lessons** — 3-5 specific, actionable insights that apply beyond this codebase.
  Not platitudes ("separation of concerns is important") but concrete judgment calls
  ("Using a single entity type with bundles works well when you need cross-bundle queries but
  starts to strain when bundles diverge significantly in their field requirements").

## Output Format

Save the report to `.claude/reports/{project-name}-architecture-analysis.md`.

Use this structure:

```markdown
# {Project Name}: Architectural Analysis

> **Generated**: {date}
> **Codebase**: {one-line description of what this system is}
> **Scope**: Full stack — custom code, contrib decisions, configuration, infrastructure

---

## Executive Summary

[400-600 words. Write this as a narrative — it should read like a conference talk abstract or
the opening of a technical blog post. What is this system? What are its 3-4 most distinctive
architectural choices? What makes this codebase interesting to study? This should be engaging
and opinionated, not a dry inventory. Someone should be able to read just this section and
walk away with a mental model of the architecture.]

## System Map

[Mermaid diagram showing the high-level architecture: custom modules, their relationships,
external systems, data flow directions. This is the "one diagram that explains the system."]

---

## Architectural Analysis

### 1. {Concern Name}

**Pattern**: {Named pattern(s)}

**What exists**: [Brief factual description — 2-3 sentences max]

**Why it's this way**: [The interesting part. Explain the reasoning, constraints, and context
that shaped this choice.]

**Trade-offs**: [What was gained and what was sacrificed by this approach]

**Alternatives considered**: [How else could this have been done? When would you choose
differently?]

**Lesson**: [One transferable insight, bolded and actionable]

[Optional: Mermaid diagram if it adds clarity]

### 2. {Next Concern}
[Same structure...]

[...continue for each concern worth analyzing...]

---

## Cross-Cutting Observations

### Strengths
- [Bullet points with brief explanations]

### Tensions
- [Areas where the design shows strain or competing concerns]

### Evolution Signals
- [Signs of architectural change over time]

---

## Transferable Lessons

[3-5 key takeaways. Each should be a specific, actionable insight — the kind of thing you'd
tell a colleague who's about to design a similar system. Include enough context that someone
unfamiliar with this codebase can still apply the lesson.]

1. **{Lesson title}**: {2-3 sentence explanation with concrete guidance}
2. ...

## Go Deeper: Follow-Up Questions

[Suggest 5-8 specific follow-up questions the reader could ask to dive deeper into the most
interesting aspects of this architecture. These should be concrete and actionable — not generic
questions like "how could the architecture be improved?" but targeted questions like "How does
the access control handler resolve conflicts when a user is both a PBP and a manager for the
same employee?" Frame each question with a one-line note about why it's worth investigating.]

1. **{Question}** — {Why this is worth exploring}
2. ...
```

## Quality Checklist

Before finalizing, verify your analysis passes these checks:

- [ ] Every section names at least one design pattern (by its recognized name)
- [ ] Every section explains a trade-off (what was gained, what was sacrificed)
- [ ] Every section includes a transferable lesson
- [ ] The executive summary is narrative and opinionated, not a bullet list
- [ ] Diagrams add genuine clarity (if a diagram is just a list in boxes, remove it)
- [ ] You analyzed *why*, not just *what* — would a reader understand the reasoning?
- [ ] You compared to alternatives where meaningful
- [ ] The transferable lessons are specific enough to be actionable, not platitudes
- [ ] Contrib module choices are explained (why Solr over Views? Why this queue backend?)
- [ ] The report would be valuable to someone who has never seen this codebase
- [ ] Follow-up questions are specific to this codebase, not generic
- [ ] Security analysis covers authentication, data sensitivity, and secrets management
- [ ] Every module claim is verified by reading actual source code, not inferred from names

## Anti-Patterns to Avoid

- **The inventory trap**: Listing every module, service, and entity without analysis. If a
  section reads like API documentation, rewrite it.
- **The obvious observation**: "The site uses Drupal's entity system for data storage." Of
  course it does — it's a Drupal site. Only state things that reflect a *choice*.
- **Pattern name-dropping**: Naming a pattern without explaining why it matters here. "This
  uses the Strategy pattern" is meaningless without "...which allows the sync mechanism to
  swap between real and mock API clients without changing the calling code."
- **Name-based inference**: Assuming a module's purpose from its name without reading the code.
  "page_resolvers" sounds like GraphQL resolvers but might actually resolve page metadata (titles,
  breadcrumbs). "client" modules might wrap local services, not HTTP APIs. A single wrong
  inference can cascade through the entire report — system map, executive summary, and multiple
  sections all repeat the error. Always read the actual source before claiming what something does.
- **Completionism**: Not every concern will be interesting for every codebase. Skip or briefly
  note areas where the architecture is straightforward. Spend your depth budget on what's
  genuinely interesting.

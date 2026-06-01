---
name: skill-prospector
description: Analyze recent Claude Code sessions to find repetitive tasks that should become reusable skills. Use when the user says "find skills", "what should be skills", "analyze my sessions", "repetitive tasks", "skill candidates", "mine my sessions", "what am I doing repeatedly", "skill opportunities", "automation opportunities", or wants to discover patterns in their Claude Code usage that could be automated. Also use proactively when a user has been doing the same kind of work across multiple sessions.
---

# Skill Prospector

Analyze recent Claude Code session history to surface repetitive workflows worth turning into skills.

## Overview

Session data lives in `~/.claude/projects/{encoded-project-path}/` as JSONL files — one per session. Each line is a JSON object containing user prompts, assistant responses (with tool calls), timestamps, and metadata. This skill uses a bundled extraction script to parse that data, then you analyze the results for recurring patterns.

## Step 1: Extract session data

Run the extraction script bundled with this skill. Determine the skill's directory from the path of this SKILL.md file.

```bash
python3 <skill-directory>/scripts/extract_sessions.py \
  --cwd <project-root> \
  --days <N, default 7> \
  -o /tmp/skill-prospector-extract.json
```

Add `--all-projects` if the user asks to scan across all their projects.

Read the output file. If it's very large (>3000 lines), read the `metadata` and `aggregate` sections first to get bearings, then sample a few sessions.

## Step 2: Identify patterns

Work through these signal types, strongest first:

### Repeated bash commands
The `aggregate.top_bash_commands` section shows commands used across sessions. Look for:
- The same drush/ddev/composer command appearing 3+ times across sessions
- Multi-command sequences that always appear together (e.g., export config then commit)
- Commands with complex flags that the user keeps having to specify

### Repeated prompt intent
Read through the `prompts` arrays across sessions. Look for:
- Different wordings of the same request (e.g., "run phpstan and fix issues", "check code quality", "lint my code")
- The same type of question asked in multiple sessions (e.g., "why is this test failing", "debug this CI failure")
- Requests that follow a predictable pattern with variable inputs

### Repeated tool workflows
Look at `tool_counts` and the sequence of tools across sessions:
- Read → Edit → Bash(test) cycles on similar file types
- Grep → Read → Edit patterns for the same kind of change
- Agent spawning for the same categories of subtask

### Skills already in heavy use
Check `aggregate.top_skills` — frequently invoked skills might indicate:
- A skill that works but could absorb adjacent manual steps
- A workflow that starts with a skill but requires manual follow-up every time

### What to skip
- One-off tasks that are genuinely unique
- Simple single-command operations (reading one file, running one test)
- Patterns that an existing skill already handles well
- Debugging sessions — these are inherently ad-hoc

## Step 3: Present recommendations

For each skill candidate, present a block like this:

```
### 1. <skill-name> (kebab-case)
**What it automates:** 1-2 sentences describing the repetitive workflow.
**Evidence:** Which sessions/prompts demonstrated this (dates + brief quotes).
**Frequency:** N occurrences across M sessions in the last D days.
**Context needed:** What inputs/config the skill would require.
**Complexity:** Simple | Medium | Complex
**Impact:** Low | Medium | High (frequency × effort-saved-per-invocation)
```

Rank by impact, highest first. Aim for 3-7 candidates — enough to be useful, not so many it's overwhelming. If you find fewer than 3, say so honestly rather than padding with weak candidates.

## Step 4: Save report

Save the analysis as a markdown report:

```
<project-root>/.claude/reports/skill-prospector-<YYYY-MM-DD>.md
```

The report should include:
1. **Summary stats** — sessions analyzed, date range, projects scanned
2. **Skill candidates** — the full recommendation blocks from Step 3
3. **Raw stats** — top bash commands, tool usage totals, skills invoked (as appendix)

Create the reports directory if it doesn't exist.

## Step 5: Next steps

After presenting the report, ask which skill(s) the user wants to create. When they choose one, invoke `/skill-creator` with the context you've gathered — describe what the skill should do, what triggers it, what inputs it needs, and any example prompts/commands from the session data.

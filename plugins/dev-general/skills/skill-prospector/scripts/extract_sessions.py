#!/usr/bin/env python3
"""Extract and summarize Claude Code session data for pattern analysis.

Parses JSONL session files from ~/.claude/projects/ and extracts user prompts,
tool usage, bash commands, and skill invocations for pattern detection.
"""

import json
import os
import sys
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter


def get_claude_projects_dir():
    return Path.home() / '.claude' / 'projects'


def encode_project_path(cwd):
    """Convert a filesystem path to Claude's project directory name."""
    return '-' + cwd.strip('/').replace('/', '-')


def decode_project_path(dirname):
    """Best-effort decode of project directory name back to a path."""
    return '/' + dirname.lstrip('-').replace('-', '/')


def find_project_dirs(cwd, all_projects=False):
    """Find matching project directories."""
    projects_dir = get_claude_projects_dir()
    if all_projects:
        return [d for d in projects_dir.iterdir()
                if d.is_dir() and not d.name.startswith('.')]
    else:
        encoded = encode_project_path(cwd)
        project_dir = projects_dir / encoded
        if project_dir.exists():
            return [project_dir]
        return []


def get_session_files(project_dir, days=7):
    """Get JSONL session files modified within the time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()
    files = []
    for f in project_dir.glob('*.jsonl'):
        if f.stat().st_mtime >= cutoff_ts:
            files.append(f)
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


NOISE_PROMPTS = {
    'yes', 'no', 'ok', 'okay', 'sure', 'thanks', 'thank you', 'y', 'n',
    'continue', 'go ahead', 'looks good', 'lgtm', 'got it', 'do it',
    'proceed', 'yep', 'nope', 'right', 'correct',
}


def is_meaningful_prompt(text):
    """Filter out noise — confirmations, slash commands, very short input."""
    text = text.strip()
    if len(text) < 10:
        return False
    if text.startswith('/'):
        return False
    if text.lower().rstrip('.!') in NOISE_PROMPTS:
        return False
    return True


def extract_user_text(content):
    """Extract text from user message content, skipping tool results."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get('type') == 'text':
                    texts.append(block.get('text', '').strip())
                # Skip tool_result blocks — not user prompts
            elif isinstance(block, str):
                texts.append(block.strip())
        return ' '.join(texts).strip()
    return ''


def extract_tool_calls(content):
    """Extract tool names and key input fields from assistant content."""
    tools = []
    if not isinstance(content, list):
        return tools
    for block in content:
        if not isinstance(block, dict) or block.get('type') != 'tool_use':
            continue
        name = block.get('name', '')
        inp = block.get('input', {})
        summary = {}
        if name == 'Bash':
            cmd = inp.get('command', '')
            summary['command'] = cmd[:300] if len(cmd) > 300 else cmd
        elif name == 'Skill':
            summary['skill'] = inp.get('skill', '')
        elif name == 'Read':
            summary['file'] = inp.get('file_path', '')
        elif name in ('Edit', 'Write'):
            summary['file'] = inp.get('file_path', '')
        elif name == 'Grep':
            summary['pattern'] = inp.get('pattern', '')
        elif name == 'Glob':
            summary['pattern'] = inp.get('pattern', '')
        elif name == 'Agent':
            summary['description'] = inp.get('description', '')
            summary['subagent_type'] = inp.get('subagent_type', '')
        tools.append({'name': name, 'input_summary': summary})
    return tools


def parse_session(filepath):
    """Parse a single session JSONL file and extract structured data."""
    data = {
        'session_id': filepath.stem,
        'cwd': None,
        'prompts': [],
        'tool_counts': Counter(),
        'bash_commands': [],
        'skills_invoked': [],
        'agent_tasks': [],
        'files_edited': set(),
        'git_branch': None,
        'start_time': None,
        'end_time': None,
        'session_name': None,
    }

    with open(filepath, 'r', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Timestamps
            ts = msg.get('timestamp')
            if ts:
                if data['start_time'] is None or ts < data['start_time']:
                    data['start_time'] = ts
                if data['end_time'] is None or ts > data['end_time']:
                    data['end_time'] = ts

            # Actual cwd and git branch (take first non-null)
            if msg.get('cwd') and not data['cwd']:
                data['cwd'] = msg['cwd']
            if msg.get('gitBranch') and not data['git_branch']:
                data['git_branch'] = msg['gitBranch']

            msg_type = msg.get('type')
            message = msg.get('message', {})
            if not isinstance(message, dict):
                continue

            # User prompts
            if msg_type == 'user' and message.get('role') == 'user':
                content = message.get('content')
                if content:
                    text = extract_user_text(content)
                    if text and is_meaningful_prompt(text):
                        # Truncate very long prompts (pasted code etc)
                        if len(text) > 500:
                            text = text[:500] + '...'
                        data['prompts'].append(text)

            # Assistant tool usage
            elif msg_type == 'assistant' and message.get('role') == 'assistant':
                content = message.get('content', [])
                for tool in extract_tool_calls(content):
                    name = tool['name']
                    data['tool_counts'][name] += 1
                    s = tool.get('input_summary', {})
                    if name == 'Bash' and s.get('command'):
                        data['bash_commands'].append(s['command'])
                    elif name == 'Skill' and s.get('skill'):
                        data['skills_invoked'].append(s['skill'])
                    elif name == 'Agent' and s.get('description'):
                        data['agent_tasks'].append(s['description'])
                    elif name in ('Edit', 'Write') and s.get('file'):
                        data['files_edited'].add(s['file'])

    # JSON-serializable
    data['files_edited'] = sorted(data['files_edited'])
    data['tool_counts'] = dict(data['tool_counts'])
    return data


def main():
    parser = argparse.ArgumentParser(
        description='Extract Claude Code session data for pattern analysis')
    parser.add_argument('--cwd', default=os.getcwd(),
                        help='Project root directory (default: cwd)')
    parser.add_argument('--all-projects', action='store_true',
                        help='Scan all projects, not just current')
    parser.add_argument('--days', type=int, default=7,
                        help='Days to look back (default: 7)')
    parser.add_argument('-o', '--output',
                        help='Output file (default: stdout)')
    args = parser.parse_args()

    project_dirs = find_project_dirs(args.cwd, args.all_projects)
    if not project_dirs:
        json.dump({'error': f'No project directory found for {args.cwd}'},
                  sys.stdout, indent=2)
        sys.exit(1)

    sessions = []
    projects_scanned = []

    for pdir in project_dirs:
        project_path = decode_project_path(pdir.name)
        projects_scanned.append(project_path)
        for sf in get_session_files(pdir, days=args.days):
            session = parse_session(sf)
            # Prefer the real cwd from session messages over decoded dir name
            session['project'] = session.pop('cwd') or project_path
            if session['prompts']:  # skip empty sessions
                sessions.append(session)

    # Aggregate cross-session stats
    all_bash = Counter()
    all_skills = Counter()
    all_tools = Counter()
    for s in sessions:
        for cmd in s['bash_commands']:
            # Normalize: take first token(s) as the command signature
            key = cmd.split('|')[0].strip()
            if len(key) > 120:
                key = key[:120] + '...'
            all_bash[key] += 1
        for sk in s['skills_invoked']:
            all_skills[sk] += 1
        for tool, count in s['tool_counts'].items():
            all_tools[tool] += count

    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days))

    result = {
        'metadata': {
            'projects_scanned': projects_scanned,
            'sessions_analyzed': len(sessions),
            'days': args.days,
            'cutoff_date': cutoff.strftime('%Y-%m-%d'),
            'extracted_at': datetime.now(timezone.utc).isoformat(),
        },
        'aggregate': {
            'top_bash_commands': all_bash.most_common(40),
            'top_skills': all_skills.most_common(20),
            'tool_totals': all_tools.most_common(),
        },
        'sessions': sessions,
    }

    output = json.dumps(result, indent=2, default=str)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w') as f:
            f.write(output)
        print(f'Wrote {len(output)} bytes to {args.output}', file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()

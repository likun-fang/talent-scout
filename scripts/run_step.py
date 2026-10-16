#!/usr/bin/env python3
"""Execute a planned script without a shell, retaining stdout, stderr and its exit code.

  run_step.py init --run-dir RUN --plan plan-draft.json [--reason 'amendment reason']
  run_step.py run --run-dir RUN --task TASK [--stdout output.jsonl] -- python3 script.py ...
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from execution_plan import install_plan, load_plan
from execution_trace import Span, file_ref, flush


def execute(root, task_id, command, stdout=None):
    root = Path(root).resolve()
    plan, plan_hash = load_plan(root)
    task = next((t for t in plan['tasks'] if t['id'] == task_id), None)
    if task is None:
        raise ValueError('unknown task ID')
    if not command:
        raise ValueError('command is required')
    output_path = None
    if stdout:
        output_path = (root / stdout).resolve()
        output_path.relative_to(root)
        if stdout not in task['expected_artifacts']:
            raise ValueError('--stdout must name an expected artifact')
        output_path.parent.mkdir(parents=True, exist_ok=True)
    before = {}
    for name in task['expected_artifacts']:
        path = (root / name).resolve()
        path.relative_to(root)
        if path.is_file():
            before[name] = (path.stat().st_mtime_ns, path.stat().st_size,
                            file_ref(path, root)['sha256'])
    # Deliberately omit argv: inline code, credentials and file content may appear there.
    with Span('execute_step', run_dir=root, task_id=task_id,
              inputs={'executable': Path(command[0]).name,
                      'command_sha256': hashlib.sha256(json.dumps(command).encode()).hexdigest()},
              metadata={'domain': plan['domain'], 'direction': task.get('direction'),
                        'channel': task['channel'], 'kind': task['kind'],
                        'code_version': plan['code_version'], 'plan_hash': plan_hash}) as span:
        environment = {**os.environ, **span.child_env()}
        with contextlib.ExitStack() as stack:
            stream = stack.enter_context(output_path.open('wb')) if output_path else None
            result = subprocess.run(command, env=environment, stdout=stream, check=False)
        artifacts, missing, unchanged = [], [], []
        for name in task['expected_artifacts']:
            path = root / name
            if not path.is_file():
                missing.append(name)
                continue
            ref = file_ref(path, root)
            state = (path.stat().st_mtime_ns, path.stat().st_size, ref['sha256'])
            if before.get(name) == state:
                unchanged.append(name)
            artifacts.append(ref)
        span.outputs = {'exit_code': result.returncode, 'artifacts': artifacts,
                        'missing_artifacts': missing, 'unchanged_artifacts': unchanged}
        if result.returncode:
            span.status = 'error'
        elif missing or unchanged:
            span.status = 'incomplete'
        return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='action', required=True)
    init = subs.add_parser('init')
    init.add_argument('--run-dir', required=True)
    init.add_argument('--plan', required=True)
    init.add_argument('--reason')
    run = subs.add_parser('run')
    run.add_argument('--run-dir', required=True)
    run.add_argument('--task', required=True)
    run.add_argument('--stdout', help='Run-relative artifact path; omit to inherit stdout')
    run.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.action == 'init':
            print(install_plan(args.run_dir, json.loads(Path(args.plan).read_text()), args.reason))
            return 0
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        code = execute(args.run_dir, args.task, command, args.stdout)
        return code if code >= 0 else 128 - code
    except (OSError, ValueError) as exc:
        print(f'execution setup failed: {type(exc).__name__}', file=sys.stderr)
        return 2
    finally:
        flush()


if __name__ == '__main__':
    sys.exit(main())

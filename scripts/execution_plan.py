"""Versioned, immutable execution plans. No YAML dependency or automatic task scheduling."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from execution_trace import file_ref


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate(plan):
    if not isinstance(plan, dict) or plan.get('schema_version') != 1:
        raise ValueError('plan schema_version must be 1')
    if 'group_recovery_required' in plan and type(plan['group_recovery_required']) is not bool:
        raise ValueError('group_recovery_required must be boolean')
    for key in ('run_id', 'domain', 'code_version'):
        if not isinstance(plan.get(key), str) or not plan[key].strip():
            raise ValueError(f'plan requires {key}')
    directions = plan.get('directions')
    if not isinstance(directions, list) or any(not isinstance(x, str) or not x.strip() for x in directions):
        raise ValueError('directions must be a list of nonempty IDs (empty means legacy, not checked)')
    if len(set(directions)) != len(directions):
        raise ValueError('duplicate directions')
    if not isinstance(plan.get('tasks'), list) or not plan['tasks']:
        raise ValueError('plan requires tasks')
    ids = set()
    covered = set()
    artifact_paths = set()
    protected = {'execution-plan.json', 'run.meta.json', 'execution-check.json', 'execution-check.md',
                 'traces', 'plans', 'task-results'}
    budgets = plan.get('channel_page_budgets', {})
    if not isinstance(budgets, dict) or any(not isinstance(k, str) or type(v) is not int or v < 0
                                           for k, v in budgets.items()):
        raise ValueError('channel_page_budgets must map channel IDs to nonnegative integers')
    for task in plan['tasks']:
        if not isinstance(task, dict):
            raise ValueError('task must be an object')
        for key in ('id', 'channel', 'input'):
            if not isinstance(task.get(key), str) or not task[key].strip():
                raise ValueError(f'task requires {key}')
        if task['id'] in ids:
            raise ValueError('duplicate task ID')
        ids.add(task['id'])
        if task.get('kind') not in ('discovery', 'process'):
            raise ValueError('task kind must be discovery or process')
        if 'page_budget' in task and (type(task['page_budget']) is not int or task['page_budget'] < 0):
            raise ValueError('page_budget must be a nonnegative integer')
        direction = task.get('direction')
        if direction is not None and direction not in directions:
            raise ValueError('task has unknown direction')
        if task['kind'] == 'discovery' and directions and direction is None:
            raise ValueError('discovery task requires direction')
        if task['kind'] == 'discovery' and direction:
            covered.add(direction)
        artifacts = task.get('expected_artifacts')
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError('task requires expected_artifacts')
        for artifact in artifacts:
            if not isinstance(artifact, str) or not artifact or Path(artifact).is_absolute() or '..' in Path(artifact).parts:
                raise ValueError('artifacts must be relative run paths without traversal')
            normalized = Path(artifact).as_posix()
            if normalized == '.' or Path(artifact).parts[0] in protected or normalized in artifact_paths:
                raise ValueError('artifact paths must be unique and cannot overwrite execution control files')
            artifact_paths.add(normalized)
    if set(directions) - covered:
        raise ValueError('directions missing discovery tasks: ' + ', '.join(sorted(set(directions) - covered)))
    refs = plan.get('config_refs')
    if not isinstance(refs, list) or not refs:
        raise ValueError('config_refs requires frozen run configuration files')
    for ref in refs:
        if not isinstance(ref, dict) or not isinstance(ref.get('path'), str) or not isinstance(ref.get('sha256'), str):
            raise ValueError('invalid configuration reference')
        if len(ref['sha256']) != 64 or any(c not in '0123456789abcdef' for c in ref['sha256']):
            raise ValueError('invalid configuration checksum')
        if Path(ref['path']).as_posix() in artifact_paths:
            raise ValueError('task cannot overwrite frozen configuration')


def load_plan(root):
    root = Path(root)
    plan = json.loads((root / 'execution-plan.json').read_text())
    validate(plan)
    revision = digest(plan)
    archived = root / 'plans' / f'{revision}.json'
    if not archived.is_file() or json.loads(archived.read_text()) != plan:
        raise ValueError('execution plan differs from its frozen revision; use init/amend')
    if plan['run_id'] != root.resolve().name:
        raise ValueError('plan run_id differs from run directory')
    for ref in plan['config_refs']:
        if file_ref(ref['path'], root)['sha256'] != ref['sha256']:
            raise ValueError('configuration changed; create an amended plan')
    return plan, revision


def install_plan(root, plan, reason=None):
    root = Path(root).resolve()
    validate(plan)
    if plan['run_id'] != root.name:
        raise ValueError('plan run_id must equal run directory name')
    for ref in plan['config_refs']:
        if file_ref(ref['path'], root)['sha256'] != ref['sha256']:
            raise ValueError('configuration hash mismatch')
    target = root / 'execution-plan.json'
    plan = dict(plan)
    if target.exists():
        if not reason or not reason.strip():
            raise ValueError('plan already exists; amendment requires a reason')
        previous = json.loads(target.read_text())
        old_hash = digest(previous)
        if json.loads((root / 'plans' / f'{old_hash}.json').read_text()) != previous:
            raise ValueError('previous plan was modified outside amendment')
        plan['previous_hash'] = old_hash
        plan['change_reason'] = reason
    else:
        plan.pop('previous_hash', None)
        plan.pop('change_reason', None)
    revision = digest(plan)
    archive = root / 'plans'
    archive.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(plan, indent=2, ensure_ascii=False) + '\n'
    frozen = archive / f'{revision}.json'
    if not frozen.exists():
        with frozen.open('x', encoding='utf-8') as stream:
            stream.write(payload)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(payload, encoding='utf-8')
    temporary.replace(target)
    return revision

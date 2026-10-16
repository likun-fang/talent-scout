#!/usr/bin/env python3
"""Check frozen plans against observed calls and explicit research handoffs.

Check: check_execution.py --run-dir RUN
Record a handoff: check_execution.py --run-dir RUN --record handoff.json
Handoffs are agent assertions, not proof of semantic relevance or identity correctness.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid

from execution_plan import load_plan
from execution_trace import file_ref, utcnow


def read_spans(root):
    spans = {}
    for path in (Path(root) / 'traces').glob('*.jsonl'):
        events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        starts = [e for e in events if e.get('event') == 'start']
        ends = [e for e in events if e.get('event') == 'end']
        if len(starts) != 1 or len(ends) > 1:
            raise ValueError('invalid span lifecycle')
        start = starts[0]
        if path.stem != start.get('span_id'):
            raise ValueError('span file ID mismatch')
        if ends:
            end = ends[0]
            for key in ('span_id', 'trace_id', 'task_id', 'parent_span_id', 'started_at', 'metadata', 'name'):
                if end.get(key) != start.get(key):
                    raise ValueError('span start/end identity mismatch')
        spans[start['span_id']] = ends[0] if ends else start
    return spans


def validate_handoff(value):
    if not isinstance(value, dict):
        raise ValueError('handoff must be an object')
    uuid.UUID(value['attempt_id'])
    if value.get('outcome') not in ('complete', 'zero_results', 'partial', 'blocked'):
        raise ValueError('invalid handoff outcome')
    for name in ('lead_count', 'resolved_count', 'unresolved_count'):
        if type(value.get(name)) is not int or value[name] < 0:
            raise ValueError(f'{name} must be a nonnegative integer')
    if value['lead_count'] != value['resolved_count'] + value['unresolved_count']:
        raise ValueError('lead counts do not reconcile')
    if value['outcome'] == 'zero_results' and value['lead_count'] != 0:
        raise ValueError('zero_results cannot contain leads')
    if not isinstance(value.get('stop_reason'), str) or not value['stop_reason'].strip():
        raise ValueError('handoff needs a stop_reason')
    for name in ('evidence', 'gaps'):
        if not isinstance(value.get(name), list) or any(not isinstance(x, str) or not x for x in value[name]):
            raise ValueError(f'{name} must be a list of nonempty strings')


def record_handoff(root, value):
    root = Path(root)
    validate_handoff(value)
    _, revision = load_plan(root)
    span = read_spans(root).get(value['attempt_id'])
    if not span or span['name'] != 'execute_step' or span['event'] != 'end':
        raise ValueError('handoff requires a finished observed execution attempt')
    if span['metadata'].get('plan_hash') != revision:
        raise ValueError('attempt uses another plan revision')
    evidence_refs = [file_ref(p, root) for p in value['evidence']]
    result = {**value, 'task_id': span['task_id'], 'plan_hash': revision,
              'recorded_at': utcnow(), 'evidence_refs': evidence_refs,
              'provenance': 'agent_handoff_not_automatic_verification'}
    target = root / 'task-results' / f"{value['attempt_id']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    return target


def descendants(spans, parent):
    found = {parent}
    while True:
        more = {key for key, s in spans.items() if s.get('parent_span_id') in found}
        if more <= found:
            return [s for key, s in spans.items() if key in found and key != parent]
        found |= more


def check(root):
    root = Path(root)
    if not (root / 'execution-plan.json').exists():
        return {'status': 'not_checked', 'direction_check': 'not_checked', 'tasks': [],
                'issues': ['No frozen execution plan; legacy run is not certified.']}
    try:
        plan, revision = load_plan(root)
        spans = read_spans(root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'status': 'invalid', 'direction_check': 'not_checked', 'tasks': [],
                'issues': [f'Plan or trace validation failed: {type(exc).__name__}']}
    rows = []
    for task in plan['tasks']:
        row = {'id': task['id'], 'direction': task.get('direction'), 'channel': task['channel'],
               'status': 'incomplete', 'issues': [], 'retrievals': 0, 'page_attempts': 0}
        issues = row['issues']
        attempts = [s for s in spans.values() if s['name'] == 'execute_step'
                    and s['task_id'] == task['id'] and s['metadata'].get('plan_hash') == revision]
        if not attempts:
            issues.append('not_executed')
            rows.append(row)
            continue
        # A later interrupted/failed attempt cannot be hidden behind an older success.
        latest = max(attempts, key=lambda s: (s['started_at'], s['span_id']))
        row['attempt_id'] = latest['span_id']
        if latest['event'] != 'end':
            issues.append('interrupted_or_running')
        elif latest['status'] != 'success':
            issues.append('execution_' + latest['status'])
        outputs = latest.get('outputs', {})
        if outputs.get('exit_code') != 0:
            issues.append('no_successful_exit')
        artifacts = {r['path']: r for r in outputs.get('artifacts', [])}
        for name in task['expected_artifacts']:
            try:
                if name not in artifacts or file_ref(name, root)['sha256'] != artifacts[name]['sha256']:
                    issues.append('missing_or_changed_artifact:' + name)
            except (ValueError, OSError):
                issues.append('missing_or_changed_artifact:' + name)
        if outputs.get('unchanged_artifacts'):
            issues.append('stale_artifact')
        children = descendants(spans, latest['span_id'])
        if any(child['event'] != 'end' for child in children):
            issues.append('unfinished_child_call')
        retrievals = [s for s in children if s.get('metadata', {}).get('operation') == 'retrieval']
        successes = [s for s in retrievals if s['event'] == 'end' and s.get('status') == 'success']
        for failed in retrievals:
            if failed.get('status') == 'error' and not any(
                    s['name'] == failed['name'] and s.get('inputs') == failed.get('inputs')
                    and s['started_at'] > failed['started_at'] for s in successes):
                issues.append('unrecovered_retrieval_failure')
        for retrieved in successes:
            cursor = retrieved.get('outputs', {}).get('next_cursor')
            if cursor:
                original = retrieved.get('inputs', {})
                query = {k: v for k, v in original.get('query', {}).items() if k != 'cursor'}
                followed = any(s.get('inputs', {}).get('path') == original.get('path')
                               and s.get('inputs', {}).get('query', {}).get('cursor') == cursor
                               and {k: v for k, v in s.get('inputs', {}).get('query', {}).items()
                                    if k != 'cursor'} == query for s in successes if s is not retrieved)
                if not followed:
                    issues.append('unprocessed_pagination_cursor')
        row['retrievals'] = len(retrievals)
        # Budget covers all attempts of this task in this plan, including failed reruns.
        all_children = [child for attempt in attempts for child in descendants(spans, attempt['span_id'])]
        row['page_attempts'] = sum(s.get('metadata', {}).get('operation') == 'page_attempt' for s in all_children)
        if 'page_budget' in task and row['page_attempts'] > task['page_budget']:
            issues.append('task_page_budget_exceeded')
        if task['kind'] == 'discovery':
            if not successes:
                issues.append('no_observed_successful_retrieval:host_tools_may_be_untraced')
            handoff_path = root / 'task-results' / f"{latest['span_id']}.json"
            try:
                handoff = json.loads(handoff_path.read_text())
                validate_handoff(handoff)
                if (handoff['attempt_id'] != latest['span_id'] or handoff.get('plan_hash') != revision
                        or handoff.get('task_id') != task['id']):
                    raise ValueError('handoff identity mismatch')
                for ref in handoff['evidence_refs']:
                    if file_ref(ref['path'], root)['sha256'] != ref['sha256']:
                        raise ValueError('evidence changed')
                observed = dict(artifacts)
                for child in children:
                    artifact = child.get('outputs', {}).get('artifact')
                    if isinstance(artifact, dict) and 'path' in artifact:
                        observed[artifact['path']] = artifact
                if any(observed.get(ref['path'], {}).get('sha256') != ref['sha256']
                       for ref in handoff['evidence_refs']):
                    issues.append('evidence_not_linked_to_observed_artifact')
                if not handoff['evidence_refs']:
                    issues.append('missing_research_evidence')
                if handoff['unresolved_count'] or handoff['gaps']:
                    issues.append('unresolved_leads_or_coverage_gaps')
                if handoff['outcome'] in ('partial', 'blocked'):
                    issues.append('research_' + handoff['outcome'])
                if handoff['stop_reason'] == 'budget_exhausted':
                    issues.append('budget_exhausted_not_proof_of_coverage')
                if handoff['outcome'] == 'zero_results':
                    counts = [s.get('outputs', {}).get('result_count') for s in successes]
                    if 0 not in counts or any(isinstance(n, int) and n > 0 for n in counts):
                        issues.append('zero_results_without_observed_empty_response')
                row['research_outcome'] = handoff['outcome']
                row['unresolved_count'] = handoff['unresolved_count']
            except (OSError, ValueError, KeyError, TypeError):
                issues.append('missing_or_invalid_research_handoff')
        row['status'] = 'complete' if not issues else 'incomplete'
        rows.append(row)
    channel_usage = {}
    global_issues = []
    task_channels = {t['id']: t['channel'] for t in plan['tasks']}
    for channel, budget in plan.get('channel_page_budgets', {}).items():
        channel_rows = [r for r in rows if r['channel'] == channel]
        # A plan amendment cannot reset an already consumed run-wide channel budget.
        attempts = [s for s in spans.values() if s['name'] == 'execute_step'
                    and s['metadata'].get('channel', task_channels.get(s['task_id'])) == channel]
        page_ids = {child['span_id'] for attempt in attempts for child in descendants(spans, attempt['span_id'])
                    if child.get('metadata', {}).get('operation') == 'page_attempt'}
        channel_usage[channel] = {'observed_attempts': len(page_ids), 'budget': budget}
        if len(page_ids) > budget:
            global_issues.append('shared_channel_page_budget_exceeded:' + channel)
            for row in channel_rows:
                row['issues'].append('shared_channel_page_budget_exceeded')
                row['status'] = 'incomplete'
    direction_check = 'checked' if plan['directions'] else 'not_checked'
    from group_recovery import check as check_groups
    grouping = check_groups(root / 'group-recovery')
    if plan.get('group_recovery_required') and grouping['status'] == 'not_checked':
        global_issues.append('missing_required_group_recovery')
    if grouping['status'] not in {'complete', 'not_checked'}:
        global_issues.append('group_recovery_' + grouping['status'])
    complete = all(r['status'] == 'complete' for r in rows) and not global_issues
    return {'status': 'complete' if complete else 'incomplete', 'direction_check': direction_check,
            'scope': 'declared_plan_only_not_exhaustive_research_or_identity_verification',
            'budget_check': 'declared_budgets_only' if plan.get('channel_page_budgets') else 'not_checked_at_channel_level',
            'channel_usage': channel_usage, 'group_recovery': grouping,
            'plan_hash': revision, 'previous_hash': plan.get('previous_hash'),
            'change_reason': plan.get('change_reason'), 'tasks': rows,
            'issues': global_issues + ([] if direction_check == 'checked' else ['Legacy plan: no direction-level check.'])}


def write_report(root, report):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / 'execution-check.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    lines = ['# Execution check', '', f"Status: {report['status']}",
             f"Direction check: {report['direction_check']}", '',
             'This checks the declared plan and observed delivery, not exhaustive sourcing or factual accuracy.', '']
    lines += ['- ' + x for x in report['issues']]
    for row in report['tasks']:
        lines.append(f"- {row['id']} ({row.get('direction') or 'shared'}): {row['status']}; "
                     + ', '.join(row['issues']))
    (root / 'execution-check.md').write_text('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--record', help='Record one immutable research handoff JSON')
    args = parser.parse_args()
    if args.record:
        try:
            print(record_handoff(args.run_dir, json.loads(Path(args.record).read_text())))
            return 0
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f'handoff rejected: {type(exc).__name__}', file=sys.stderr)
            return 2
    report = check(args.run_dir)
    write_report(args.run_dir, report)
    print(json.dumps({'status': report['status'], 'direction_check': report['direction_check']}))
    return 0 if report['status'] == 'complete' else 2


if __name__ == '__main__':
    sys.exit(main())

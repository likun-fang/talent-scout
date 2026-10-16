#!/usr/bin/env python3
"""Plan, execute, review and audit every ungrouped candidate, without name-only joins.

The reader retrieves source pages; a configured research worker (JSON stdin/stdout)
performs search and semantic review. Without a worker no verification is invented.
All writes live in RUN/group-recovery. Export consumes only validated receipts.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

from group_relations import person_ref

OUTCOMES = {'verified_current', 'historical_only', 'ambiguous', 'not_found', 'blocked'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


@contextlib.contextmanager
def lock(root, name='.lock'):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    with (root / name).open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('another recovery coordinator is running') from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def binding(person):
    return {'person_ref': person_ref(person), 'name': person['name'], 'ids': person.get('ids', {}),
            'affiliation': person.get('final_pass_affiliation') or person.get('current_affiliation', ''),
            'profile_url': person.get('final_pass_url') or person.get('homepage', '')}


def task_for(person):
    urls = list(dict.fromkeys(filter(None, [person.get('homepage'), person.get('final_pass_url'),
        *(s.get('homepage') for s in person.get('signals', [])),
        *(s.get('evidence_url') for s in person.get('signals', []))])))
    identity = binding(person)
    return {'id': identity['person_ref'], 'binding': identity, 'input_hash': digest(identity),
            'reason': person.get('group_evidence', 'unattached'), 'seed_urls': urls,
            'search_queries': [f'"{person["name"]}" "{identity["affiliation"]}" laboratory team',
                               f'"{person["name"]}" supervisor research homepage'],
            'state': 'pending', 'attempts': []}


def plan(root, persons, run_date, scope=None):
    """All eligible people BEFORE max_rows; append frozen target batches on resume."""
    root = Path(root)
    with lock(root):
        path = root / 'queue.json'
        queue = read(path) if path.exists() else {'schema_version': 1, 'run_date': run_date,
            'scope': scope or {}, 'tasks': {}, 'page_attempts': 0}
        if queue['run_date'] != run_date or queue['scope'] != (scope or {}):
            raise ValueError('recovery date/scope changed; use a new recovery directory')
        refs = [person_ref(p) for p in persons]
        if len(refs) != len(set(refs)):
            raise ValueError('duplicate recovery identity; resolve before planning')
        for ref, task in queue['tasks'].items():
            if ref not in refs:
                if task.get('result'):
                    task.setdefault('previous_results', []).append(task.pop('result'))
                task.update(state='binding_missing', error='Original target no longer matches the current population; identity/scope review required')
        new = []
        for person in persons:
            ref = person_ref(person)
            if person.get('group') and ref not in queue['tasks']:
                continue
            fresh = task_for(person)
            old = queue['tasks'].get(ref)
            if old is None or old['input_hash'] != fresh['input_hash'] or old['state'] == 'binding_missing':
                if old:
                    fresh['attempts'] = old['attempts']
                queue['tasks'][ref] = fresh
                new.append({'id': ref, 'input_hash': fresh['input_hash']})
        if new or not path.exists():
            batch = {'run_date': run_date, 'scope': scope or {}, 'targets': new,
                     'population_refs': refs}
            write(root / 'batches' / (digest(batch) + '.json'), batch)
        queue['population_refs'] = refs
        write(path, queue)
    return check(root)


def local_path(root, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError('evidence paths must be recovery-relative')
    path = (Path(root) / relative).resolve()
    path.relative_to(Path(root).resolve())
    return path


def evidence(root, item):
    """Require readable saved content, matching hash/URL and an actual excerpt."""
    from visit_page import validate_url
    validate_url(item['url'])
    path = local_path(root, item['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
        raise ValueError('evidence content changed')
    page = read(path)
    if page.get('status') != 'readable':
        raise ValueError('evidence page was not readable')
    if item['url'] not in {page.get('url'), page.get('requested_url'), page.get('final_url'), page.get('archive_url')}:
        raise ValueError('evidence URL does not match saved page')
    quote = ' '.join(item.get('quote', '').split())
    if not quote or quote not in ' '.join(page.get('text', '').split()):
        raise ValueError('evidence quote missing from saved page')
    observed = datetime.date.fromisoformat(item['observed_on'])
    retrieved = datetime.date.fromisoformat(page.get('retrieved_at', '')[:10])
    if observed != retrieved:
        raise ValueError('observation date must match retrieval date')
    return page


def validate_result(root, task, result):
    from visit_page import validate_url
    if not isinstance(result, dict):
        raise ValueError('worker result must be an object')
    if result.get('task_id') != task['id'] or result.get('input_hash') != task['input_hash']:
        raise ValueError('result does not bind to this target/input revision')
    outcome = result.get('outcome')
    if outcome not in OUTCOMES or not isinstance(result.get('reason'), str) or not result['reason'].strip():
        raise ValueError('result requires an outcome and reason')
    attempts = result.get('sources_checked', [])
    if not isinstance(attempts, list) or not attempts:
        raise ValueError('a result must record sources actually checked')
    for item in attempts:
        if not isinstance(item, dict):
            raise ValueError('checked source must be an object')
        page = read(local_path(root, item['path']))
        if hashlib.sha256(local_path(root, item['path']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('checked source changed')
        if not page.get('retrieved_at') or page.get('status') != item.get('status'):
            raise ValueError('source status/date mismatch')
    if outcome == 'not_found' and not any(item['status'] == 'readable' for item in attempts):
        raise ValueError('access failures are blocked, not proof of no public relationship')
    relations = result.get('relations', [])
    if not isinstance(relations, list):
        raise ValueError('relations must be a list')
    if outcome == 'verified_current' and not relations:
        raise ValueError('verified outcome requires direct relationships')
    if outcome not in {'verified_current', 'historical_only'} and relations:
        raise ValueError('unresolved result cannot publish relationships')
    if outcome == 'historical_only' and not relations:
        raise ValueError('historical outcome requires dated evidence')
    seen = set()
    for relation in relations:
        if not isinstance(relation, dict):
            raise ValueError('relationship must be an object')
        if relation.get('person_ref') != task['id']:
            raise ValueError('relationship belongs to another person')
        if relation.get('relation_type') not in {'member', 'supervised_by', 'employee', 'leader'}:
            raise ValueError('coauthorship is not direct team membership')
        if relation.get('status') not in {'current', 'historical'}:
            raise ValueError('relationship status required')
        if outcome == 'historical_only' and relation['status'] != 'historical':
            raise ValueError('historical review cannot publish current membership')
        if type(relation.get('primary', False)) is not bool:
            raise ValueError('primary must be a boolean')
        observed = datetime.date.fromisoformat(relation['observed_on'])
        if relation['observed_on'] > read(Path(root) / 'queue.json')['run_date']:
            raise ValueError('relationship observation is after the run date')
        for field in ('valid_from', 'valid_to'):
            if relation.get(field):
                datetime.date.fromisoformat(relation[field])
        if relation.get('valid_from') and relation.get('valid_to') and relation['valid_from'] > relation['valid_to']:
            raise ValueError('invalid membership interval')
        if relation['status'] == 'current' and ((relation.get('valid_from') or '') > observed.isoformat() or
                relation.get('valid_to') and relation['valid_to'] < observed.isoformat()):
            raise ValueError('current membership contradicts effective dates')
        group = relation['group']
        if not isinstance(group, dict):
            raise ValueError('group must be an object')
        if any(not isinstance(group.get(k), str) or not group[k].strip() for k in ('id', 'name', 'institution', 'url')):
            raise ValueError('group identity, institution and source required')
        validate_url(group['url'])
        if group['id'] in seen:
            raise ValueError('duplicate group membership in one result')
        seen.add(group['id'])
        if group.get('leader'):
            if not group['leader'].get('name'):
                raise ValueError('leader name required')
            validate_url(group['leader']['url'])
        ev = relation.get('evidence', [])
        if not ev:
            raise ValueError('direct relationship evidence required')
        for item in ev:
            evidence(root, item)
            if (item['path'], item['sha256']) not in {(s['path'], s['sha256']) for s in attempts}:
                raise ValueError('relationship evidence was not in the checked sources')
            if item['observed_on'] != relation['observed_on']:
                raise ValueError('relationship date differs from its source observation')
        # Binding is a separately reviewed claim, with source excerpts; it is not
        # permission to merge provider profiles or to clear identity holds.
        identity = relation.get('identity_evidence', [])
        if not identity:
            raise ValueError('member identity needs evidence, not a matching name alone')
        for item in identity:
            evidence(root, item)
        if not relation.get('identity_reason', '').strip():
            raise ValueError('explain binding using profile/IDs, institution and research evidence')
        if relation.get('primary') and not relation.get('primary_reason', '').strip():
            raise ValueError('primary membership requires source-supported explanation')
        if relation['status'] == 'current' and all(read(local_path(root, e['path'])).get('archive_url') for e in ev):
            raise ValueError('archived roster alone cannot establish current membership')
    if outcome == 'verified_current' and not any(r['status'] == 'current' for r in relations):
        raise ValueError('verified_current needs a current relationship')
    return result


def record(root, result):
    root = Path(root)
    if not isinstance(result, dict):
        raise ValueError('worker result must be an object')
    with lock(root):
        queue = read(root / 'queue.json')
        task = queue['tasks'].get(result.get('task_id'))
        if task is None:
            raise ValueError('unknown recovery task')
        if task['id'] not in queue.get('population_refs', []) or task['state'] == 'binding_missing':
            raise ValueError('target is no longer in the current population; replan before recording')
        validate_result(root, task, result)
        name = 'results/' + digest(result) + '.json'
        if not (root / name).exists():
            write(root / name, result)
        task.update(state=result['outcome'], result=name)
        write(root / 'queue.json', queue)
    return name


def receipt(root, task):
    path = local_path(root, task['result'])
    result = read(path)
    if path.stem != digest(result):
        raise ValueError('immutable receipt changed')
    return validate_result(root, task, result)


def load_relations(root, persons, run_date):
    """Fail closed on tampered receipts; ignore stale identities, keep audits pending."""
    root = Path(root)
    if not (root / 'queue.json').exists():
        return []
    report = check(root)
    if report['status'] == 'invalid' or report.get('issues'):
        raise ValueError('group recovery ledger failed validation')
    queue = read(root / 'queue.json')
    if queue['run_date'] != run_date:
        raise ValueError('recovery evidence belongs to a different run date')
    live = {person_ref(p): p for p in persons if not p.get('identity_reenrichment_required')}
    relations = []
    for ref, task in queue['tasks'].items():
        if ref not in live or digest(binding(live[ref])) != task['input_hash'] or not task.get('result'):
            continue
        result = receipt(root, task)
        relations.extend(result.get('relations', []))
    return relations


def check(root):
    root = Path(root)
    if not (root / 'queue.json').exists():
        return {'status': 'not_checked', 'coverage_status': 'not_checked', 'issues': ['missing_recovery_queue']}
    try:
        queue = read(root / 'queue.json')
        expected = {}
        for path in (root / 'batches').glob('*.json'):
            batch = read(path)
            if path.stem != digest(batch):
                raise ValueError('frozen target batch changed')
            for target in batch['targets']:
                expected.setdefault(target['id'], set()).add(target['input_hash'])
        issues = []; counts = {}
        if set(queue['tasks']) != set(expected):
            issues.append('target_manifest_mismatch')
        if not list((root / 'batches').glob('*.json')):
            issues.append('missing_frozen_target_manifest')
        for ref, task in queue['tasks'].items():
            if task['id'] != ref or digest(task['binding']) != task['input_hash'] or task['input_hash'] not in expected.get(ref, set()):
                raise ValueError('task input does not match frozen targets')
            state = task['state']
            if task.get('result'):
                result = receipt(root, task)
                if result['outcome'] != state:
                    raise ValueError('state differs from receipt')
            elif state in OUTCOMES:
                raise ValueError('terminal assertion has no receipt')
            counts[state] = counts.get(state, 0) + 1
        resolved = counts.get('verified_current', 0)
        reviewed = sum(counts.get(s, 0) for s in OUTCOMES)
        total = len(expected)
        return {'status': 'complete' if resolved == total and not issues else 'incomplete',
                'coverage_status': 'complete' if reviewed == total and not issues else 'incomplete',
                'target_count': total, 'reviewed_count': reviewed, 'verified_current_count': resolved,
                'unresolved_count': total - resolved, 'counts': counts, 'issues': issues,
                'page_attempts': queue.get('page_attempts', 0)}
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'invalid', 'coverage_status': 'incomplete', 'issues': ['invalid_recovery_artifact']}


def run(root, worker, page_budget=100, timeout=120, retry_unresolved=False):
    with lock(root, '.runner.lock'):
        return _run(root, worker, page_budget, timeout, retry_unresolved)


def _run(root, worker, page_budget=100, timeout=120, retry_unresolved=False):
    """Run every pending task once, with durable starts, shared pages and receipts.

    worker is an argv list, no shell; reads a job on stdin and emits one result.
    It may use host research tools and save additional evidence inside this root.
    The reader budget is cumulative across resumes. Worker search budgets are
    separate and must be reported in its result, never hidden as reader requests.
    """
    from visit_page import visit, is_linkedin
    from execution_trace import Span
    root = Path(root).resolve()
    if not worker or not isinstance(worker, list) or not all(isinstance(x, str) and x for x in worker):
        raise ValueError('configure a research worker argv; fetching pages is not verification')
    if page_budget < 0 or timeout <= 0:
        raise ValueError('invalid worker limits')
    with lock(root):
        queue = read(root / 'queue.json')
        tasks = [t['id'] for t in queue['tasks'].values()
                 if t['id'] in queue.get('population_refs', []) and t['state'] != 'binding_missing' and
                 (t['state'] in {'pending', 'running', 'failed', 'budget_exhausted'} or
                  retry_unresolved and t['state'] != 'verified_current')]
    index_path = root / 'page-index.json'
    page_index = read(index_path) if index_path.exists() else {}
    fetched = set()
    for ref in tasks:
        with lock(root):
            queue = read(root / 'queue.json'); task = queue['tasks'][ref]
            attempt = uuid.uuid4().hex
            task.update(state='running'); task.pop('result', None)
            task['attempts'].append(attempt)
            write(root / 'queue.json', queue)
        pages = []
        try:
            with Span('group_recovery.attempt', inputs={'person_ref': ref, 'input_hash': task['input_hash']}) as span:
                for url in task['seed_urls']:
                    if is_linkedin(url):
                        continue  # Public LinkedIn remains the separate serial final-pass workflow.
                    cached = page_index.get(url)
                    path = local_path(root, cached) if cached else None
                    refresh = path is None or not path.exists() or (url not in fetched and read(path).get('status') != 'readable')
                    if refresh:
                        with lock(root):
                            queue = read(root / 'queue.json')
                            if queue['page_attempts'] >= page_budget:
                                break
                            queue['page_attempts'] += 1
                            write(root / 'queue.json', queue)
                        page = visit(url, timeout=min(timeout, 20), ladder=('http',), max_chars=100000)
                        name = 'pages/' + hashlib.sha256(url.encode()).hexdigest() + '-' + uuid.uuid4().hex + '.json'
                        path = root / name
                        write(path, page)
                        fetched.add(url)
                        page_index[url] = name
                        write(index_path, page_index)
                    name = str(path.relative_to(root))
                    page = read(path)
                    pages.append({'path': name, 'url': url, 'status': page.get('status'),
                                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
                job = {**task, 'attempt_id': attempt, 'recovery_dir': str(root), 'pages': pages,
                       'run_date': queue['run_date'],
                       'reader_budget_remaining': max(0, page_budget - queue['page_attempts'])}
                write(root / 'attempts' / (attempt + '.input.json'), job)
                if not pages and task['seed_urls'] and queue['page_attempts'] >= page_budget:
                    with lock(root):
                        state = read(root / 'queue.json')
                        state['tasks'][ref]['state'] = 'budget_exhausted'
                        write(root / 'queue.json', state)
                    span.outputs = {'outcome': 'budget_exhausted', 'person_ref': ref}
                    continue
                result = subprocess.run(worker, input=json.dumps(job), text=True, capture_output=True,
                                        timeout=timeout, check=False, cwd=root)
                if result.returncode:
                    raise ValueError('research worker failed')
                answer = json.loads(result.stdout)
                record(root, answer)
                span.outputs = {'outcome': answer['outcome'], 'person_ref': ref}
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            with lock(root):
                queue = read(root / 'queue.json'); task = queue['tasks'][ref]
                task.update(state='failed', error=type(exc).__name__)
                write(root / 'attempts' / (attempt + '.failure.json'), {'error': type(exc).__name__, 'task_id': ref})
                write(root / 'queue.json', queue)
    report = check(root)
    write(root / 'coverage.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'next', 'run', 'record', 'check'])
    parser.add_argument('--root', required=True, help='RUN/group-recovery directory')
    parser.add_argument('--persons', help='all selected records JSONL, before display row cap')
    parser.add_argument('--date', default=datetime.date.today().isoformat())
    parser.add_argument('--result', help='reviewed worker result JSON')
    parser.add_argument('--worker', help='JSON argv array for research worker')
    parser.add_argument('--page-budget', type=int, default=100)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--retry-unresolved', action='store_true')
    args = parser.parse_args(); root = Path(args.root)
    try:
        if args.action == 'plan':
            persons = [json.loads(line) for line in Path(args.persons).read_text().splitlines() if line.strip()]
            report = plan(root, persons, args.date)
        elif args.action == 'next':
            queue = read(root / 'queue.json')
            report = [t for t in queue['tasks'].values() if t['state'] != 'verified_current']
        elif args.action == 'record':
            report = {'receipt': record(root, read(args.result))}
        elif args.action == 'run':
            report = run(root, json.loads(args.worker or 'null'), args.page_budget, args.timeout, args.retry_unresolved)
        else:
            report = check(root); write(root / 'coverage.json', report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if isinstance(report, dict) and report.get('status') in {'incomplete', 'invalid', 'not_checked'} else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('group recovery failed: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())

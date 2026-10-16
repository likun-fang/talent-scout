"""Optional execution telemetry. Local records are authoritative; remote upload is best effort.

Set TALENT_SCOUT_RUN_DIR to enable local tracing. TALENT_SCOUT_LANGSMITH=true
explicitly enables the optional SDK exporter. No credentials or page bodies are logged.
"""
from __future__ import annotations

import contextvars
import atexit
import datetime as dt
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_current = contextvars.ContextVar('talent_scout_span', default=None)
_client = None
_client_lock = threading.Lock()
_secret_key = re.compile(r'api.?key|token|secret|password|authorization|cookie|credential', re.I)


def sanitize(value):
    """Defense in depth for summaries; callers must not pass full documents or headers."""
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if _secret_key.search(str(k)) else sanitize(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if not isinstance(value, str):
        return value if value is None or isinstance(value, (int, float, bool)) else type(value).__name__
    for key, secret in os.environ.items():
        if _secret_key.search(key) and len(secret) >= 4:
            value = value.replace(secret, '[REDACTED]')
    if value.startswith(('http://', 'https://')):
        try:
            parsed = urlsplit(value)
            host = parsed.netloc.rsplit('@', 1)[-1]
            query = urlencode([(k, '[REDACTED]' if _secret_key.search(k) else sanitize(v))
                               for k, v in parse_qsl(parsed.query, keep_blank_values=True)])
            value = urlunsplit((parsed.scheme, host, parsed.path, query, ''))
        except ValueError:
            return '[INVALID URL]'
    value = re.sub(r'(?i)(bearer\s+)[^\s,;]+', r'\1[REDACTED]', value)
    value = re.sub(r'(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s&,;]+',
                   r'\1[REDACTED]', value)
    return value[:4000]


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def file_ref(path, run_dir):
    """Only references to files inside this run may become evidence artifacts."""
    root = Path(run_dir).resolve()
    target = Path(path)
    target = (root / target).resolve() if not target.is_absolute() else target.resolve()
    relative = target.relative_to(root)
    if not target.is_file():
        raise ValueError(f'not a file: {relative}')
    digest = hashlib.sha256()
    with target.open('rb') as source:
        for block in iter(lambda: source.read(65536), b''):
            digest.update(block)
    return {'path': relative.as_posix(), 'sha256': digest.hexdigest(), 'bytes': target.stat().st_size}


def _inherited():
    parent = _current.get()
    if parent is not None:
        return parent.context()
    raw = os.environ.get('TALENT_SCOUT_TRACE_CONTEXT')
    if raw:
        data = json.loads(raw)
        for key in ('trace_id', 'span_id'):
            uuid.UUID(data[key])
        return data
    return {}


def export_record(record):
    """Upload completed spans, including parent IDs and order, using the optional SDK.

    Explicit posting is independent of LANGSMITH_TRACING; our own opt-in governs it.
    Uploads contain summaries only. Long running spans remain visible locally until ended.
    """
    global _client
    if os.environ.get('TALENT_SCOUT_LANGSMITH', '').lower() != 'true':
        return
    with _client_lock:
        if _client is None:
            from langsmith import Client
            _client = Client(timeout_ms=2000)
    _client.create_run(
        name=record['name'], run_type='tool', id=record['span_id'],
        trace_id=record['trace_id'], parent_run_id=record['parent_span_id'],
        dotted_order=record['dotted_order'], start_time=record['started_at'],
        end_time=record['ended_at'], inputs=record['inputs'], outputs=record['outputs'],
        error=record.get('error_type') or (record['status'] if record['status'] != 'success' else None),
        project_name=os.environ.get('LANGSMITH_PROJECT', 'talent-scout'),
        extra={'metadata': {**record['metadata'], 'scout_run_id': record['run_id'],
                            'task_id': record.get('task_id'), 'status': record['status']}},
    )


def flush():
    if _client is not None:
        try:
            _client.flush(timeout=2)
        except Exception as exc:
            print(f'trace upload flush failed: {type(exc).__name__}', file=sys.stderr)


atexit.register(flush)


class Span:
    def __init__(self, name, *, inputs=None, metadata=None, run_dir=None, task_id=None):
        self.name, self.inputs, self.metadata = name, inputs or {}, metadata or {}
        parent = _current.get()
        self.run_dir = run_dir or (parent.run_dir if parent else None) or os.environ.get('TALENT_SCOUT_RUN_DIR')
        self.task_id = task_id
        self.outputs = {}
        self.status = 'success'
        self.record = None

    def __enter__(self):
        if not self.run_dir:
            return self
        root = Path(self.run_dir).resolve()
        parent = _inherited()
        if parent and parent.get('run_dir') != str(root):
            raise ValueError('trace parent belongs to a different run directory')
        span_id = str(uuid.uuid4())
        started = utcnow()
        order = dt.datetime.fromisoformat(started).strftime('%Y%m%dT%H%M%S%fZ') + span_id
        inherited_metadata = parent.get('metadata', {})
        self.record = {
            'schema_version': 1, 'name': self.name, 'run_id': root.name,
            'trace_id': parent.get('trace_id', span_id), 'span_id': span_id,
            'parent_span_id': parent.get('span_id'),
            'dotted_order': parent['dotted_order'] + '.' + order if parent else order,
            'task_id': self.task_id or parent.get('task_id'),
            'started_at': started, 'inputs': sanitize(self.inputs),
            'metadata': sanitize({**inherited_metadata, **self.metadata}),
        }
        self.path = root / 'traces' / f'{span_id}.jsonl'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write({**self.record, 'event': 'start', 'status': 'running'})
        self.tick = time.monotonic()
        self.token = _current.set(self)
        return self

    def context(self):
        if not self.record:
            return {}
        return {**{k: self.record[k] for k in ('trace_id', 'span_id', 'dotted_order', 'task_id', 'metadata')},
                'run_dir': str(Path(self.run_dir).resolve())}

    def child_env(self):
        return {'TALENT_SCOUT_RUN_DIR': str(Path(self.run_dir).resolve()),
                'TALENT_SCOUT_TRACE_CONTEXT': json.dumps(self.context())}

    def _write(self, event):
        # A unique file per span avoids concurrent appenders across workers/processes.
        with self.path.open('a', encoding='utf-8') as target:
            target.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')
            target.flush()
            os.fsync(target.fileno())

    def __exit__(self, exc_type, exc, tb):
        if not self.record:
            return False
        _current.reset(self.token)
        event = {**self.record, 'event': 'end', 'ended_at': utcnow(),
                 'duration_ms': round((time.monotonic() - self.tick) * 1000, 3),
                 'status': 'error' if exc_type else self.status, 'outputs': sanitize(self.outputs)}
        if exc_type:
            event['error_type'] = exc_type.__name__  # Never serialize exception messages/command arguments.
        self._write(event)
        try:
            export_record(event)
        except Exception as upload_error:
            self._write({'event': 'upload_error', 'span_id': event['span_id'],
                         'error_type': type(upload_error).__name__, 'at': utcnow()})
            print(f'trace upload failed: {type(upload_error).__name__}', file=sys.stderr)
        return False


def traced(name, *, inputs=None, outputs=None, metadata=None):
    """Synchronous boundary wrapper; summaries are explicit and never full function locals."""
    def decorate(fn):
        @functools.wraps(fn)
        def call(*args, **kwargs):
            if not os.environ.get('TALENT_SCOUT_RUN_DIR') and _current.get() is None:
                return fn(*args, **kwargs)
            parent = _current.get()
            with Span(name, run_dir=parent.run_dir if parent else None,
                      inputs=inputs(*args, **kwargs) if inputs else {}, metadata=metadata) as span:
                result = fn(*args, **kwargs)
                span.outputs = outputs(result) if outputs else {}
                if span.outputs.get('status') not in (None, 'success', 'readable', 'cache_hit'):
                    span.status = 'error'
                return result
        return call
    return decorate

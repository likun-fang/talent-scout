# Execution tracing and plan checks

New talent plans include `group_recovery_required: true` and the full grouping recovery stage described in
`42-group-recovery.md`. `check_execution.py` combines declared task checks with the frozen per-person recovery
queue. Missing required queues, unprocessed people and unverified membership keep completion incomplete.

Read when preparing a task plan, executing channel helpers or checking delivery. Research rules, channels,
budgets, person resolution and exports remain in their existing references. Tracing observes execution;
it does not schedule agents, retry searches, verify identities or guarantee recall.

## 1. Freeze the declared plan

After agreeing the stage-1 scope, prepare `RUN_DIR/plan-draft.json` using `assets/execution-plan.schema.json`.
Copy every required direction ID from the selected domain map. Assign discovery tasks to appropriate channels;
there is no requirement to search every direction in every channel. Domains without explicit directions use
`directions: []`: channel tasks work, but direction coverage is `not_checked`. HTML facets are not search tasks.

Each task has a unique ID, query or seed in `input`, channel, optional task page budget carved out of the existing
channel budget, and run-relative output paths. Workers need separate paths. `discovery` tasks require an observed
retrieval and research handoff. `process` tasks require a successful command and newly written artifacts.
Splitting agents does not multiply channel budgets. Task budgets are audited, not enforced by a scheduler.
Copy run-wide limits into `channel_page_budgets`, for example `{"open-source": 40}`. The checker counts observed
page attempts across retries and plan revisions. Missing limits or untraced calls prevent complete budget
accounting; API calls and dataset downloads retain their existing separate budget rules.

Example draft (replace checksum/version with actual values; a full embodied run includes all four directions):

```json
{
  "schema_version": 1,
  "run_id": "embodied-ai-example",
  "domain": "embodied-ai",
  "code_version": "actual-git-commit",
  "directions": ["vlm"],
  "config_refs": [{"path": "domain-map.yaml", "sha256": "actual-sha256"}],
  "tasks": [{
    "id": "vlm-papers", "kind": "discovery", "direction": "vlm",
    "channel": "open-source", "input": "embodied multimodal reasoning",
    "page_budget": 10, "expected_artifacts": ["discovery/vlm-topics.json"]
  }]
}
```

Hash frozen configuration with `hashlib.sha256(Path(path).read_bytes()).hexdigest()` or
`execution_trace.file_ref(path, RUN_DIR)`. Reference the run's frozen domain/facets files, not mutable
`run.meta.json`. Capture `git rev-parse HEAD` and disclose uncommitted changes in `code_version`.
The checker validates declared JSON; it does not semantically parse YAML or prove the queries are sufficient.
Review directions against the agreed domain map at stage 1.

```sh
python3 "$SKILL_ROOT/scripts/run_step.py" init --run-dir "$RUN_DIR" --plan "$RUN_DIR/plan-draft.json"
```

This writes `execution-plan.json` and a content-addressed copy under `plans/`. Do not edit either in place.
Amend with a new draft and `init --reason 'specific change and why'`. Previous revisions remain; the new plan
records their hash. A new revision requires fresh receipts; old tasks do not silently count under changed scope.
There is no automatic resume/retry yet. Keep one coordinator responsible for plan changes.

## 2. Execute helpers

```sh
python3 "$SKILL_ROOT/scripts/run_step.py" run --run-dir "$RUN_DIR" --task vlm-papers \
  --stdout discovery/vlm-topics.json -- \
  python3 "$SKILL_ROOT/scripts/openalex_lookup.py" --topic 'embodied multimodal reasoning'
```

Commands execute as argv without a shell, from the caller's working directory. Stdout/stderr retain their original
behavior unless `--stdout` names an expected run-relative artifact. The child's exit code is preserved. Missing or
unchanged artifacts make delivery incomplete even after exit 0; the checker supplies the aggregate completion code.
Do not put credentials in arguments. Telemetry records only executable name and argv hash, never arbitrary inline
code/arguments or stdout content. Artifact outputs must not overwrite plan or tracing control files.

Each call writes start/end events to its own `traces/<span-id>.jsonl`. Subprocesses receive parent context via
`TALENT_SCOUT_TRACE_CONTEXT`; worker threads in the helpers inherit the process context. A start without an end
remains running/interrupted. File existence alone is not proof of completed work.

Instrumented boundaries:

- `openalex_lookup.get`: actual query, result count and next cursor; errors never become empty results.
- `visit_page.visit`, HTTP/browser attempts: access status, method, length and saved evidence reference.
- `current_affiliation`: retrieval, transport and cache outcomes, including offline misses.
- Other helpers: process exit and artifacts via `run_step.py`; internal decisions are not automatically traced.

Ad hoc fetchers and host-native search/browser/subagent tools are blind spots until their events are connected.
Record their evidence and gaps in channel coverage, without fabricating automatic spans from retrospective claims.
An uninstrumented discovery task cannot pass the observed-retrieval check; partial rosters may still be exported.
Existing reader fallbacks remain unchanged. Cache reuse is not another network request.

## 3. Record research delivery

Exit 0 proves neither that authors were followed nor that people are regionally eligible. After inspecting outputs
and applying the existing hop rules, create a handoff JSON:

```json
{
  "attempt_id": "UUID-of-the-execute_step-span",
  "outcome": "partial",
  "lead_count": 4, "resolved_count": 3, "unresolved_count": 1,
  "stop_reason": "budget_exhausted",
  "evidence": ["discovery/vlm-topics.json"],
  "gaps": ["One original author still has unknown current geography"]
}
```

Find the attempt ID in the `execute_step` trace or the check JSON. Resolved leads include ineligible people with
recorded reasons, not only admitted candidates. Counts must reconcile. Outcomes: `complete`, `zero_results`,
`partial`, `blocked`. `zero_results` requires an observed empty response. A nonempty search with no eligible people
uses `complete` plus exclusion evidence. Pending pages/cursors and sources belong in `gaps` even before they produce
person leads. Handoffs remain agent assertions, separate from automatic telemetry.

```sh
python3 "$SKILL_ROOT/scripts/check_execution.py" --run-dir "$RUN_DIR" --record "$RUN_DIR/handoff.json"
python3 "$SKILL_ROOT/scripts/check_execution.py" --run-dir "$RUN_DIR"
```

Handoffs are immutable `task-results/<attempt-id>.json` files with task/plan IDs and evidence hashes. Evidence must
match observed artifacts or saved pages from the attempt. The checker writes `execution-check.json` and `.md`;
exit 0 means the declared plan passed, exit 2 means incomplete, invalid or not checked. It never modifies candidates.
Report check status beside channel coverage. Stage termination does not establish exhaustive domain coverage.

The checker rejects missing/failed tasks, stale/altered artifacts, missing handoffs, unsupported zero results,
unresolved leads and budget-exhaustion gaps. The latest attempt wins; an older success cannot hide an interruption.
Legacy runs remain usable without being certified. Trace files are audit records, not tamper-proof attestations.

## 4. Optional LangSmith

```sh
python3 -m pip install -r "$SKILL_ROOT/scripts/requirements-tracing.txt"
export TALENT_SCOUT_LANGSMITH=true
export LANGSMITH_PROJECT=talent-scout
```

Supply `LANGSMITH_API_KEY` via environment/secret manager, never a run artifact. `LANGSMITH_ENDPOINT` selects the
account endpoint if needed. The Talent Scout opt-in is required even if a key already exists. Without it no SDK
is imported; local tracing has no added dependency. Disable upload with `TALENT_SCOUT_LANGSMITH=false`.
The optional SDK extra requires Python 3.10+; its wire-format contract is tested with LangSmith 0.14.11.

Completed spans carry parent IDs, timestamps, direction/channel metadata and summaries. Page bodies, full candidate
records, stdout, auth headers and exception messages are excluded. Local artifact references are not remote file
uploads. In-progress work is visible in local start records; remote spans appear after completion. SDK queues flush
on normal exit; forced termination can lose remote delivery. Local records remain authoritative. Import/upload
errors never turn sourcing success into failure. Missing local storage prevents an observed task from starting.

Keep completion checks local. LangSmith online evaluation is optional feedback, not the completion gate.

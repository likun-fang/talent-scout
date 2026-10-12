# Parallel sourcing by domain

Use this mode when the user requests agents split by domain or subdomain. The existing channel-parallel mode
remains the default. A skill provides dispatch instructions; it does not create agents on its own. The host must
expose a delegation tool (for example `collaboration.spawn_agent`). If unavailable, execute the same assignments
sequentially and record that fallback. Do not invent a tool or install another agent framework.

## Plan at stage 1

The coordinator derives one domain map, with workers optionally researching proposed subdomains into separate
scratch files. Only the coordinator writes the canonical map and `run.meta.json`. Show the proposed subdomain
boundaries with the stage-1 summary and wait for the user's reply before stage 2.

Record `parallel_sourcing` in `run.meta.json` with `mode: domain` and a `workers` list. Each worker has a unique
`id`, `domain`, `include`, `exclude`, `channels`, and `page_budgets` mapping of channel to fetch-attempt limit.
All workers inherit the same countries, window, evidence rules and enabled `sourcing_extensions`.
Split by research question, not country, institution, or candidate role. For a narrow domain, fewer workers are
better than artificial subdivisions. Multimodal examples are in `domain-profiles/multimodal.md`.

Divide each existing channel budget across workers: the sum of allocations must not exceed that channel's
run budget (default 40). Four workers could receive 10 attempts each per channel; this is a division, not four
new 40-page budgets. The coordinator may reassign unused attempts after a worker stops, recording spent and
remaining attempts. Failed fetches and replacement sources count as before. Use the host's available concurrency;
queue remaining workers in waves rather than hard-coding an agent count.

## Dispatch at stage 2

Fill `assets/channel-brief.template.md` for each assigned channel and supply the worker's domain boundaries,
domain-map subset, exact budgets, relevant channel references, and `references/30-hops.md`.
Set the brief's `OUTPUT_DIR` to `RUN_DIR/workers/<worker-id>/signals`.

For example, a host exposing `collaboration.spawn_agent` can receive:

```text
task_name: vision_language
message: Sweep the assigned vision-language subdomain using the attached filled briefs and domain map.
         Use the common geography and window. Write only to RUN_DIR/workers/vision-language/.
         Hop to people within each assigned channel. Report artifact paths, fetch attempts per channel,
         exhausted sources, remaining leads and access failures. Do not merge, enrich, export or spawn children.
```

The coordinator owns canonical run files; workers own only their assigned directories. Workers must not update
`stage_status`, shared caches, canonical channel files or each other's output. Use existing shared cache data
read-only and worker-local caches for new reads. Do not duplicate a worker that is still running.
Keep fetched URLs and event/work identifiers in coverage so the coordinator can redirect overlapping leads
to existing evidence before another fetch; any duplicate fetch still consumes budget.

## Consolidate and resume

Wait for all assignments, inspect their files, and check each JSONL record against the signal schema, actual
evidence, date rules and assigned scope. A worker's final message alone is not a completed channel.
Concatenate worker shards by channel into the existing `RUN_DIR/signals/<channel>.jsonl`. Suppress only identical
JSON records; keep different evidence for the same person. Domain workers are not new channels: preserve each
signal's original `channel`, preventing overlap from inflating channel counts. Stage 4 still resolves identities.

Write one canonical `<channel>.coverage.md` aggregating attempts, failures, sources, and remaining gaps across
workers, with links to worker notes. Only canonical notes enter export coverage. A channel is complete when its
total budget is reached or assigned sources are exhausted; worker failure alone does not satisfy this condition.
Resume incomplete assignments using existing shards and spent budgets, replacing a stopped worker's assignment
only after confirming it has stopped. Do not blindly append its previously collected records a second time.

Show the combined raw candidate count at the existing stage-2 checkpoint and wait for the user's reply. Then
run the existing stages 3–5 once, centrally: close gaps, merge, enrich, rank and cut the combined roster. Do not
cut a separate top 50 per worker. Final-pass LinkedIn reads remain serial under the existing shared limit.

# Native event diagnostics

This configuration uses the pinned upstream Collector and Codex 0.167.0 source
catalog. It retains safe diagnostics from events already attached to admitted
native OTLP spans. It does not enable conversation capture or an OTLP logs source.

## Retained data

The existing exact native producer/version gate stays in place. Trace, span and
parent identifiers and timings survive. Resource/account/source attributes,
free-text span names, status messages, trace state, prompts, response text, tool
arguments/results, error strings and original event attributes do not survive.

Eighteen known event types retain their fixed names. Unknown names become
`codex.event.unclassified`; their original name and text are discarded. Every
accepted span includes a total event count. Per-type counts and validated numeric
sums cover durations, input/output/cached/reasoning token diagnostics, input counts
and tool argument/output lengths where applicable. Token values are accepted only
on response-completed events. The source field `tool_token_count` is actually a
reported total, so the exported key is `reported_total_token_count`.

These figures are diagnostic, not canonical billing or model usage accounting.
Missing optional count/sum fields mean zero. A span without events carries only
the diagnostic role, zero event count and an empty timeline.

## Bounds and exclusions

- Timeline: at most 32 entries and 4,096 bytes per span. Omitted entries are counted.
- More than 10,000 events on a span: the whole span is rejected.
- Span links: the whole span remains excluded until link clearing is qualified.
- Numeric fields: bounded nonnegative integers only, with event-kind validation.
- Original span events: removed after projection to avoid implicit GenAI input/output mapping.
- Exact approved source versions only. This is not a wildcard product-version policy.

The sanitized timeline is JSON metadata rather than a full Langfuse child-event
hierarchy. Logs-only native events use the separate [numeric log projection](native-log-diagnostics.md).
Metrics, media and full tool/conversation content are outside this path. No historical files are scanned. Existing exact
session content admission and permanent exclusions remain separate and unchanged.

## Render and deploy

Use an empty object in a nonsecret JSON file outside the checkout and run:

```sh
sh validation/run.sh setup native-event-render /absolute/empty.json
```

The guarded Docker action emits generic `edge_processors` and
`central_processors`; it does not deploy, read credentials or choose destinations.
Review the recognized private configuration shape before replacing privacy
processors. Preserve receivers, authentication, source gates, destinations,
content admission and unrelated pipelines. Independently revalidate the fixed
numeric and timeline grammar centrally. When the central configuration also
supports old diagnostic traffic, guard restoration on the incoming native scope
and version before restoring its existing fixed constants.

Stage and validate the central policy before enabling edges. Set edge batches to
at most four spans for the existing 64-KiB ingress boundary; tested worst-case
payloads fit this budget. Retain the post-projection verification tee and preserve
all existing logs. Deployment and security changes still require current approval.

## Validation

The committed Docker application workflow passed 282 tests plus pinned Collector,
Helm and schema checks. Eight real-Collector event tests cover numeric summaries,
unknown names, invalid values, wrong source, bounded timelines, forged central
metadata, linked spans, compact zero-event spans and four-span payload budgets.
Synthetic private-text canaries do not appear in projected output.

These tests qualify the stated projection, not arbitrary-secret detection in raw
content, end-to-end delivery, or browser observation visibility. Live deployment
receipts and private addresses, credentials and identifiers stay outside Git.

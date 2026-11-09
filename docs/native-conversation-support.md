# Product-native conversation export: readiness contract

Status as of 2026-11-09: **selected direction, not an available or enabled
all-session capability**. Continue using supported product/upstream integrations;
do not introduce a custom relay, transcript parser, watcher, uploader or wrapper.
This document is an upstream-ready requirements and acceptance brief, not an
upstream submission, API promise, implementation ETA or activation approval.

## What the inspected native product actually provides

The pinned source audit covers Codex 0.167.0 at
`086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a`. Other installed versions and client
surfaces require their own qualification. The latest stable release checked was
0.167.0; public main was also inspected at
`e54a5713caf331f42a6eef0166186df5f7563c29` and retained the same relevant
provenance/classification behavior. Do not infer a feature is available in every
app/IDE/hosted client from a CLI source change.

- Native logs, traces and metrics have independent exporters. Current-input
  text opt-in emits **logs**, not rich conversation trace observations. It does
  not deliberately serialize the full assembled system/developer/API history.
- Assistant-response opt-in emits live completed final-answer **logs**, not all
  intermediate/commentary messages. It has a 65,536-byte cap and includes some
  spawned-subagent finals. It is not an all-visible-messages stream.
- Tool log arguments/previews and guardian-assessment text have separate content
  behavior. Turning prompt/response logging off is not a universal envelope
  sanitizer. Native log identity fields also need separate privacy review.
- Token usage is available in selected native trace **events** and metrics.
  Current diagnostic policies deliberately discard all events; retaining span
  attributes alone does not restore accounting. This is separate from content.
- Native prompt/response telemetry is attached to live accepted input/completed
  items rather than the plugin's scan of historical rollout turns. This avoids
  that specific backfill implementation, but does not establish permanent
  session exclusions or stop newly emitted text from quoting past content.

These are useful native building blocks. Existing content flags are **not** a
substitute for the product-owned export boundary described below. Keep native
content logging disabled in the current deployment.

## Missing product-owned boundary

Core tracks richer input metadata, but its `User` origin also includes
unclassified inputs, and the prompt-telemetry call currently discards origin,
item and acceptance metadata. Role labels, source strings, originator environment
variables and ordinary OTLP attributes are not human-origin attestation.
Managed/automated instructions can appear as user-role text. Structural removal
of system/developer roles alone therefore does not protect all internal context.

The inspected native export path has no qualified persistent session-denial
policy, inherited fork exclusion, atomic sensitive-session transition or
cross-client export authorization. The upstream plugin is not a replacement:
its disable path records no permanent denial, its later Stop hook walks unsent
turns, and independent hook handlers execute concurrently.

A producer capability claim must be established by reviewed product behavior
and versioned conformance tests. Do not accept a caller-supplied boolean,
self-reported origin, changed trace label or local approval file as that proof.

## Required native contract (proposed, not implemented)

1. **Authoritative exportability and provenance.** The product must distinguish
   human-visible conversation items from automation, injected context, internal
   agent coordination, tools and unknown inputs before content serialization.
   Unknown/unclassified origins default to excluded. Provenance belongs to the
   trusted product boundary, not chat text or a client-controlled label.
2. **Durable sensitive-session policy.** An explicit exclusion takes effect
   before content is queued and remains a denial across restart, resume, config
   reload and stale writers. Child/fork sessions inherit exclusions. Missing or
   ambiguous lineage, corrupt state and unavailable policy state fail closed.
   A later enable flag must not erase an exclusion or reclassify skipped turns.
3. **Ordered per-turn decisions.** Admission, policy revision and original turn
   identity are committed before export. Export and exclusion checks use one
   ordered product path, not competing hooks. A denial racing release must have
   a documented safe linearization point. A policy model is not a disk-durability
   or crash-safety implementation.
4. **Explicit cutover without historical backfill.** Existing/unverified history
   remains excluded. Original message/turn occurrence and admission decisions
   survive resume; arrival time, flush time and a newly created fork UUID do not
   authorize inherited content. Re-enabling export does not replay skipped work.
5. **Trustworthy message stream.** Stable session, turn and message identifiers,
   original timestamps, order, visibility/phase and lineage are needed. Emit only
   approved user-visible text; exclude system/developer/internal instructions,
   hidden reasoning, tool arguments/results and media unless separately scoped.
   The stream must distinguish duplicate delivery from new content.
6. **Honest delivery semantics.** Specify truncation, dropped items, cancellation,
   retry, buffering, restart, shutdown and outage behavior. Silent sidecar marking
   or endpoint acceptance must not be presented as complete backend persistence.
7. **Independent consent and data limits.** Human origin does not imply that text
   is secret-free. Arbitrary credentials cannot be reliably removed by patterns.
   Sensitive mode must be selected before release; an exclusion cannot undo an
   earlier disclosure. Do not promise complete content capture and universal
   automatic secret removal at the same time.

## Langfuse interoperability boundary

The selected backend consumes OTLP/HTTP **traces** at
`/api/public/otel/v1/traces`, with reviewed JSON/protobuf schemas and project
authentication. In the inspected Langfuse 4.70.1 build, the metrics POST handler
is a no-op and no OTLP logs route was found. A native producer that emits only
content logs does not directly satisfy this contract. Do not repoint logs or
metrics at the trace endpoint or infer persistence from HTTP success elsewhere.

For a candidate official integration, verify one root agent observation per turn
with explicit `langfuse.observation.input` and `langfuse.observation.output`, a
stable `session.id`, and optional generation children with valid parent context.
Do not infer that every newer GenAI semantic-convention field is understood by
the pinned backend mapper. Version 4 ingestion expects completed spans; repeated
updates of the same ID are not a reliable deduplication mechanism. The existing
64 KiB transport limit also requires explicit truncation/loss qualification.

A supported native integration must either produce suitable trace observations
itself or use an officially supported upstream integration with the same source
policy guarantees. No bespoke log-to-trace conversion or transcript reconstruction
is selected. Retain authenticated loopback intake where applicable, encrypted
transport and separate diagnostics/conversation projects. Project credentials
remain at their designated exporter boundary; no new sharing or access is implied.

## Acceptance matrix for a candidate native release

Use synthetic data first. Preserve existing histories and logs. Each applicable
client surface must be tested independently; previously running shared daemons
must not be assumed to load a new capability or environment setting.

| Required case | Expected result |
| --- | --- |
| Fresh admitted human-visible turn | Only intended visible items, stable order and exact backend receipt |
| Unknown, unclassified, automated or protected input | No content export, even when role is user or source is CLI |
| Resume, fork, child/subagent and inherited context | Original admission preserved; denied/unknown ancestry cannot export |
| Sensitive mode before first message or mid-session | No subsequent queue/release; denial survives restart and stale writers |
| Opt-out, missing delivery sidecar, then re-enable | No skipped-history backfill |
| Corrupt/missing policy state, clock rollback or crash | Fail closed; no admission reconstructed from observed session files |
| Hook concurrency, steering and overlapping turns | No release before committed policy decision; stable original identity |
| Cancelled/interrupted turns, shutdown and backend outage | Explicit loss/retry/truncation semantics; no completeness claim without receipts |
| Secret/internal/media canaries in every envelope location | Excluded as specified; unfamiliar-secret limitations stated separately |
| Log/metric/trace endpoint mismatch | No false persistence claim or automatic fallback destination |

The repository's lifecycle tests are a **test-only specification**, not product
implementation. The adversarial Collector cases intentionally demonstrate current
limitations. Passing them is not a qualification certificate for blanket export.

## Adoption sequence and current decision

1. Identify an official release or upstream change that implements this boundary.
2. Review its source, supported-client/version matrix and configuration contract.
3. Run the negative, lifecycle, outage and restart tests against that implementation.
4. Verify isolated backend receipts and access/retention behavior using existing
   approved routes. Obtain specific approval for any newly required credentials,
   persistent access, trust changes or security configuration.
5. Enable only the individually qualified clients and newly eligible sessions;
   keep unsupported/protected sessions excluded and historical backfill off.

Until those gates pass, retain metadata diagnostics and explicitly bounded
content experiments only. No upstream issue, comment or pull request is submitted
by this document, and no dependable upstream implementation date is known.

## Pinned source references

- [Native OTel configuration](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/core/src/config/otel.rs#L14-L40)
- [Current-input telemetry](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/otel/src/events/session_telemetry.rs#L1164-L1208)
- [Prompt telemetry call boundary](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/core/src/session/turn.rs#L985-L1020)
- [Live final-response logging](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/otel/src/agent_response.rs#L17-L109)
- [Input metadata](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/core/src/session/input_queue.rs#L22-L49) and [origin semantics](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/history/src/heartbeat.rs#L12-L45)
- [Concurrent hook dispatch](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/hooks/src/engine/dispatcher.rs#L131-L174)
- [Plugin disable behavior](https://github.com/langfuse/codex-observability-plugin/blob/e1d02be28e6bacbfe350a1bc1ccf861e54edee17/plugins/tracing/src/index.ts#L35-L69) and [replay/ancestry behavior](https://github.com/langfuse/codex-observability-plugin/blob/e1d02be28e6bacbfe350a1bc1ccf861e54edee17/plugins/tracing/src/trace.ts#L649-L821)
- [Bounded capture qualification](../application-infrastructure/runbooks/conversation-capture.md), [native metadata qualification](../application-infrastructure/runbooks/native-source-gate.md)

- [Langfuse OTLP mappings](https://langfuse.com/integrations/native/opentelemetry) and [v4 ingestion](https://langfuse.com/integrations/native/opentelemetry/migration-to-v4)
- [Pinned trace handler](https://github.com/langfuse/langfuse/blob/v4.70.1/web/src/pages/api/public/otel/v1/traces/index.ts) and [no-op metrics handler](https://github.com/langfuse/langfuse/blob/v4.70.1/web/src/pages/api/public/otel/v1/metrics/index.ts)

## Relevant upstream tracking (read-only review)

- [Merged PR 47649](https://github.com/openai/codex/pull/47649) implements native
  assistant final-answer logging. This is existing partial support, not a future
  promise. [Issue 22230](https://github.com/openai/codex/issues/22230) was still open
  when checked; source and merged implementation are stronger evidence of the
  shipped capability than that issue's state.
- [Issue 34884](https://github.com/openai/codex/issues/34884) concerns missing
  derived-conversation lineage in OTel.
- [Issue 32708](https://github.com/openai/codex/issues/32708) concerns title-helper
  ownership/purpose attribution.

No matching published commitment or implementation ETA for the full durable
exclusion and trusted exportability contract was established by this review.
That is a bounded search result, not proof that no internal upstream plans exist.

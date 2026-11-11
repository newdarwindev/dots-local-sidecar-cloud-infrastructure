# Bounded native message conversion experiment

## Optional future enrollment and tool content (source only)

The renderer accepts `future_after_ns` for additional UUID sessions after an
explicit source-event cutoff. Exact existing cutoffs and permanent denials take
precedence. This does not establish fresh-session or fork provenance, backfill
history, or change a running producer. Parent-conversation records remain denied.

An independent `tool_results: true` option admits the pinned Codex 0.167.0
`codex.tool_result` log event. It projects arguments (Collector `Len` at most
65,536), output (`Len` at most 65,600, including the producer truncation notice),
and a fixed metadata map: tool name/namespace, agent name, MCP server/origin,
call ID, result sequence, duration, success and output truncation. Larger or
malformed records fail closed. The native `otel.tool_result.max_bytes` producer
limit should be 65,536 UTF-8 bytes for this profile. Known secret patterns are
redacted in projected strings; this is not general secret detection. Never
enter recovery material in an enrolled session.

The matching central native gate must opt in to both options and route
`codex.native.tool_result`; changing only the Mac cannot establish enrollment.
Tool records retain deterministic per-record IDs for retry, not reconstructed
turn parentage. Prompt/response projection is unchanged. The native diagnostic
fan-out remains a separate dependency and must be preserved during activation.

Owner-authorized future producer settings can enable prompt and assistant
response logs and bounded tool previews after synthetic local/hub qualification.
The inspected native emitter exposes reasoning event types and token counts,
not hidden reasoning or reasoning-summary text. Enabling SSE event logging does
not add that text. Do not promise unsupported content, read raw session history,
or activate a duplicate plugin conversation producer for the same sessions.

Validate admitted and denied synthetic controls through exact-ID backend
readback, then outage/replay, before claiming end-to-end acceptance. No live
configuration, producer flag, credential, queue or supervisor is changed by
these renderer options.

This renderer uses only standard upstream Collector 0.163.2 components:
OTLP logs receiver → filter → transform → `otlp_json` → traces exporter.
The connector is alpha. Nothing here enables native content flags or services.
The renderer supplies only existing mTLS and local htpasswd environment placeholders.
It never reads credentials or chooses a new remote destination.
The committed Docker application workflow runs the real converter offline.

## Shape and qualification

Only exact explicitly enrolled session UUIDs, resource and app version 0.167.0, known service
names and `codex_otel.log_only` scope qualify. Permanent denial takes precedence.
Unknown sessions, tools, subagents and parent-linked records are excluded.
Text must be a nonempty scalar of at most 65,536 bytes. Responses additionally
require explicit `response_truncated=false`; partial native responses are dropped.
User prompts have no turn ID and cannot be reliably paired with final replies.
Converted records are independent event observations grouped by session.
Native prompts may represent unclassified inputs: these labels do not prove
human provenance. Use only externally qualified, isolated fresh sessions.

The entire outgoing envelope is rebuilt from a static OTLP map. Message text is
assigned into structured string values and serialized with OTTL `String`, never
interpolated into JSON. Outgoing scope is `codex.native.conversation`, version 1.
Span name is `codex.native.user_message` or `codex.native.assistant_message`.
Only `session.id`, `langfuse.observation.type=event`, and exactly one of
`langfuse.observation.input` / `.output` survive. No original body, account,
resource identity, context, tool, reasoning or arbitrary attributes survive.

Source `event.timestamp` is parsed with `Time` and checked against the explicit
session cutoff. Missing/malformed time fails closed; this is event emission time,
not proof of original turn creation. `observedTimeUnixNano` must also be positive.
The conversion identity is SHA256 of session UUID, canonical event kind, source
timestamp, observed nanoseconds, and validated response item ID (empty for
prompts), joined by colons. Trace ID is its first 32 hex characters; span ID the
next 16. Native producer trace/span IDs are not required. No content or account
identity enters the digest. Stable IDs mean stable for identical envelopes only:
no exactly-once delivery or deduplication guarantee is claimed. Two prompt events
with identical timestamps and session cannot be distinguished by this source.

Selected known secret patterns are replaced. Arbitrary passwords and recovery
shares are NOT guaranteed removable; a synthetic counterexample intentionally
survives. Session denial must be durably maintained outside this stateless
renderer. Fork ancestry, original-turn provenance, protected-context decisions
and automatic fresh-session enrollment are not implemented. No broad rollout is
qualified by these tests. Existing metadata-only native export remains the safe
alternative for sessions not explicitly qualified for content.

## Primary sources

- [Upstream connector v0.163.0](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/v0.163.0/connector/otlpjsonconnector)
- [OTTL functions v0.163.0](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.163.0/pkg/ottl/ottlfuncs/README.md)
- [Pinned native timestamp macro](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/otel/src/events/shared.rs)
- [Pinned final-response logger](https://github.com/openai/codex/blob/086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a/codex-rs/otel/src/agent_response.rs)

## Guarded render action

Prepare a private nonsecret JSON input outside the checkout with exactly
`enrolled` (UUID-to-source-event-nanosecond-cutoff map) and `denied` (UUID list).
Run `sh validation/run.sh setup native-message-render /absolute/input.json`.
The guarded Docker action returns configuration only; it applies nothing.
Receiver is loopback `127.0.0.1:17449/v1/logs` with basicauth. Supply existing
`CONVERSATION_HTPASSWD_FILE`, `CONVERSATION_MTLS_TRACES_ENDPOINT`,
`CONVERSATION_CA_FILE`, `CONVERSATION_CERT_FILE`, and `CONVERSATION_KEY_FILE`
only through the previously approved private deployment process. No retry queue
is configured; no historical files are read. Plugin and native metadata routes
remain separate and unchanged. In runtime tests the exporter is replaced by an
ephemeral synthetic file and outbound networking is disabled.


## Coordinated source handoff

Use the [enrollment contract](conversation-capture.md#enrollment-and-backfill-boundary)
for denial, cutoff and provenance requirements. A preparation-time cutoff is not
activation authority. Candidate files without policy provenance do not establish
a complete denial registry, especially when another producer has an empty list.

Future-event or tool opt-in also adds a per-record clock parser and rejection gate.
Parse failures are silent and fail closed for that record, preserving valid
neighbors instead of treating an entire failed request as successful rejection.
The source-supplied parser marker is overwritten and removed from projections.

With `tool_results=true`, the local graph now includes
`filter/native_messages_projected` after transformation. It rejects tool fields
that exceed central limits after redaction or metadata JSON encoding, preserving
neighboring valid events. Diagnostic fan-out remains independent. Earlier
two-processor candidates must be re-rendered; changing only their filter and
transform is insufficient. Central metadata retention is restricted to tool
events, so enabling tools does not widen ordinary message metadata.

`central_native_message_policy.reviewed_update(config, previous, proposed)`
prepares a guarded content-policy change without I/O. Both policies must contain
`enrolled`, `denied`, `future_after_ns` and `tool_results`. It verifies the exact
previous processors and router, refuses removal of denials or backwards cutoffs,
and accepts either the original batching graph or its exact persistent exporter-
batching equivalent. Only the native filter, transform and routing row change;
TLS, authentication, endpoints, queues, diagnostic/plugin routes and pipelines
are preserved. Unknown/mixed pipeline shapes fail closed. This source guard does
not establish authoritative input provenance or replace action-time checks.

Field bounds are not request bounds. JSON escaping, OTLP envelopes and batching
increase wire size; a 65,536-byte body cap cannot carry a maximum-size tool field.
The committed runtime tests exercise the native routing connector, rejection at
that cap and acceptance of an escaped maximum-size synthetic tool envelope under
an explicit 1-MiB **test-only** cap. This does not change deployment defaults or
qualify every batch, serialization or hop. Review actual encoded maximum batches
at every receiver before a separately coordinated cap change.

`validation/native_serial_runtime.py` adds a three-Collector synthetic route:
authenticated loopback native logs plus independent diagnostics → outer mTLS
forwarder → inner mTLS native routing/filter → authenticated HTTPS capture sink.
It runs only through the committed Docker entrypoint with network disabled,
temporary certificates and isolated fsync queues. No live config or queue is read.
The outer fixture stays synchronous; local and inner exporters use single-item
queue batches. Queue capacities are reduced for the fixture, not changed in source
deployment defaults. The final sink is a test server, not Langfuse storage.

The serial cases cover escaped maximum prompt/response and tool input/output
fields, exact content IDs, denied/unknown/old/parent-linked records, diagnostic
fan-out, local authentication and missing mTLS clients. Both JSON and protobuf
are exercised between Collectors; final sink export remains JSON, compression
is disabled, and tool metadata is small. Each 64-KiB hop is tested separately
with oversized content, rejection evidence and healthy controls before/after it.
The 1-MiB candidate passes these envelopes, not every possible native producer
batch or compressed-wire combination. Real producer batching, client versions,
private policy provenance, production queues, Langfuse persistence and lifecycle
acceptance still require their own coordinated evidence.

Keep source tests, installed configuration, publication, backend persistence and
lifecycle acceptance separate. Render inert candidates, compare structural
changes without dumping private configurations, and recheck live hashes and
resourceVersions immediately before any authorized guarded update. Do not
restart active sessions or stop shared backends for synthetic outage tests.

## Historical bounded qualification: 2026-11-09

The standard-component conversion was deployed to separate authenticated
loopback Collectors on the two approved desktop sources. Existing local Basic
authentication and the existing mTLS destination were reused; no new project
credentials, external endpoint, firewall exposure or custom runtime were added.
Queueing and retry are explicitly disabled in this bounded path.

Each source ran a fresh interactive Codex 0.167.0 CLI session with `--no-daemon`.
Native prompt/final-answer flags were enabled only in a private process-selected
profile. The exact session ID and source-time cutoff were installed before the
first harmless prompt. Plugin capture was disabled, so these receipts did not
come from transcript parsing or the Langfuse plugin.

Backend IO readback found four EVENT observations: exactly one input-only user
event and one output-only assistant event for each source, with the expected
visible text. No event from an unlisted session reached the project. A local
shape test showed that the product title helper emits separate prompt/answer
logs with the same producer and main-agent classification; exact session gates
were therefore essential to exclude that traffic.

Unauthenticated local requests returned 401. CLI test sessions exited and their
private profiles' content flags were reset to false after the tests. Receivers
remain available with their narrow allowlists. This is functional bounded native
message capture, not an automatic all-session rollout. Existing plugin and native
metadata collectors remain separate.

This qualification establishes CLI → authenticated local projection → encrypted
transport → Langfuse backend persistence. Web UI verification is a separate
acceptance step. A separately approved LAN-only HTTPS listener now serves the
login page successfully in Safari using narrowly scoped operating-system leaf
trust. Authenticated observation inspection is still pending user sign-in. Chrome
does not currently honor that hostname-scoped anchor. Do not describe backend
receipts or a visible login page as observation verification in the browser.

The full Docker application workflow passed 251 tests before live deployment,
including six native-conversion runtime cases, plus pinned Collector/Helm/schema
checks. Source configuration, credentials, session/trace IDs, deployment receipts
and preserved logs remain outside Git.

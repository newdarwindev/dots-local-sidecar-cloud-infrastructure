# Bounded native message conversion experiment

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


## Bounded live qualification: 2026-11-09

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

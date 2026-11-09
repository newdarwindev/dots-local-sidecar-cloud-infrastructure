# Numeric-only native log diagnostics

This path complements native span-event diagnostics with structured events emitted
only as OTLP logs, including response-completed token and first-token timing
fields. It uses standard pinned Collector components: an authenticated loopback
receiver, filters/transforms, the upstream alpha `otlp_json` connector, four-span
batching and the existing mTLS destination. There is no transcript reader or
custom host relay.

## Data boundary

Only the pinned Codex 0.167.0 services and native log-only scope qualify. The
projection reconstructs a new OTLP envelope containing a fixed event name,
validated event time and applicable bounded numeric fields. Original prompt,
response, account, tool argument/result, error and arbitrary body/attribute text
is discarded before clock parsing. It is not a text redactor.

Known catalog names are retained. Other nonempty string names of at most 256 bytes
become `codex.event.unclassified`, with no original name or guessed numeric fields.
Missing or malformed required source/clock/identity fields fail closed. Each
observation has total event count one and a safe numeric timeline. Derived IDs
identify these envelopes, not original turns. No original turn correlation,
exactly-once delivery or deduplication guarantee is claimed.

The source field `tool_token_count` means total tokens and is renamed
`reported_total_token_count`. Usage is diagnostic, not canonical billing. Native
span events and converted logs may overlap, and their shared scope has no explicit
source-signal marker. Do not sum both paths as usage or billing totals.

## Producer privacy settings

All four exact options must be explicitly false:

- `otel.log_user_prompt`
- `otel.log_agent_responses`
- `otel.log_guardian_assessments`
- `otel.log_sse_deltas`

Also require `otel.tool_result.max_bytes = 0` and keep plugin capture disabled.
Do not mistake an absent or similarly named key for a disabled option. In the
pinned source, `log_sse_deltas` defaults to true. A readiness check initially used
the wrong key; activation corrected the actual setting and verifies explicit
values. The projected live records still contained no text. The source readiness helper
and regression tests now reject missing, misspelled, enabled or nonboolean flags
and require an integer zero tool-output limit.

These settings are defense in depth, not the complete boundary: native tool
arguments and some error text can still enter the local receiver. The projection
must remain in place before any remote export. No raw input tee or debug-context
logging is permitted.

## Guarded merge

Run `sh validation/run.sh setup native-log-diagnostic-render /absolute/empty.json`
with exactly an empty JSON object outside the checkout. The Docker action emits
nonsecret components only. It does not read credentials, enable a producer or
apply a service change.

The tested merger preserves the existing receiver, authentication, mTLS exporter,
content processor objects, exact session admission and unrelated configuration.
It adds a separate diagnostic branch and prepends a syntax/type guard to the
bounded content branch. That guard is necessary: a malformed raw timestamp could
otherwise be echoed in a preexisting `Time()` parser error. Calendar-invalid but
syntax-valid timestamps are also covered by content-canary log tests.

Use current approval and recognized configuration shapes for deployment. Verify
before/after invariants, validate the pinned Collector, and restart only the
existing receiver as needed. Never print credentials or include private targets
in Git. Preserve all logs; temporary verification tees belong after projection
and must be removed from the configuration after testing, without deleting files.

Diagnostic outbound batches contain at most four spans and are tested below the
64-KiB ingress boundary. This does not qualify the unchanged bounded content
batches or shared receiver input size. Queueing and retries remain disabled on
this export path. No historical session files are scanned.

## Acceptance evidence and limits

The full committed Docker workflow passed 282 tests plus pinned Collector and
schema checks. It covers all catalog names and fixed unknown events,
malformed clocks/types/JSON/authentication, oversized arguments, numeric abuse,
source-envelope canaries, refusal/non-success exporter responses, payload bounds
and mixed content/diagnostic fan-out. Both exported data and normal informational
Collector stdout/stderr are checked for synthetic content canaries. The tested
pinned exporter did not echo either tested JSON or plaintext error-response bodies.

Bounded live qualification on both approved desktop platforms produced 32 safe
observations per source. All 32 IDs from each source were verified in the metadata
backend, including token/cache/reasoning and first-token timing fields where
present. No input/output or authored text marker appeared. The separate content
project retained only its four earlier bounded test events.

The numeric-only exporter was then configured globally with the exact privacy
settings above and owner-only configuration permissions. Fresh default-config,
no-daemon processes again produced 32 verified observations per source. Existing
native trace export and authentication remain unchanged. Initial ordinary-client probes on existing warm background servers produced no
numeric records after more than 20 seconds idle, despite successful replies.
Configuration changes alone therefore did not establish provider adoption.

A subsequent explicitly approved, idle-checked stop/start on each host resolved
that observed adoption gap. Ordinary default CLI sessions then produced 32 of 32
verified numeric observations per source. Their original native trace IDs were
also independently found in the backend. Input/output and authored text markers
remained absent, and the separate content project retained its four earlier
bounded test events. These receipts do not prove complete or exactly-once archival
delivery, or establish the cause of every earlier missing trace.

## Restart and log-preservation acceptance

Loaded-thread count alone is insufficient for an idle check: unloaded,
nonarchived threads may retain queued submissions. The qualified checks enumerate
all supported source kinds/providers and attached threads, project only IDs,
status/active flags and queue counts, and repeat immediately before stopping.
Unknown, active or queued state blocks the operation. The supported control socket
uses WebSocket framing; the proxy is a raw byte relay, not newline-JSON RPC.

The pinned PID backend has destructive log rotation at startup: it replaces the
previous stderr file with a capped tail and truncates the current file. During
this approved operation, full owner-only copies of both existing files were
verified before stopping and again after successful stop and file stability,
before starting. No conversation files were copied. The daemon's normal logger
can also prune during shutdown, so post-stop-only copying is not sufficient for
strict preservation. No inherited writer was found before final copies/start.

Only the existing daemon was stopped and started, using the supported commands;
there was no host reboot, manual kill, credential change or network-policy change.
Temporary post-projection tees were removed from configuration and all resulting
logs retained. Production privacy and transport configuration hashes stayed
unchanged during this restart acceptance.

Backend receipts are not authenticated Web UI verification. The separately
approved LAN HTTPS UI serves a secure login page, but authenticated observation
inspection remains unverified. Full conversation/tool text, media, general metrics
storage and archival capture are outside this path.

See [native span-event diagnostics](native-event-diagnostics.md) and
[bounded native message conversion](native-message-conversion.md) for the other
signals and their distinct admission rules.

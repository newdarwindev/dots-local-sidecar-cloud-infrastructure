# Bounded conversation-capture policy

Status: staged only. No live service, credential, project, enrollment, receiver,
or exporter is changed by this repository. Broad capture is **not enabled**.
This is a standard upstream Collector configuration generator, not a custom
hook, relay, receiver, or ingestion service.

## Pinned source and architecture

- Official Langfuse Codex plugin 0.4.3, revision
  `e1d02be28e6bacbfe350a1bc1ccf861e54edee17`.
- Upstream OpenTelemetry Collector Contrib 0.163.2, using the existing pinned
  validation image and built-in OTLP, basic-auth, filter, transform and exporter
  components. No experimental feature gate is needed.
- Plugin `base_url` points only to an authenticated loopback Collector. Its
  receiver accepts `/api/public/otel/v1/traces`. Set
  `LANGFUSE_MEDIA_UPLOAD_ENABLED=false`; media uploads otherwise bypass tracing.
- Local sanitization precedes the existing authenticated mTLS hop to kali-6 and
  a separate private rich-content project. Existing metadata-only routing is
  unchanged. Never point the rich plugin directly at the remote project.
- Private URLs, target identifiers, credentials and certificate/key paths stay
  outside Git. The rendered exporter contains environment placeholders, not
  credentials. Supply an existing privately provisioned htpasswd file for the
  plugin's local Basic authentication, and the private mTLS/exporter inputs.
  The generator does not provision, enroll, grant access or run services.

## Enrollment and backfill boundary

`conversation_policy.render(enrolled, denied, generations=False)` returns a
configuration dictionary. `enrolled` maps exact UUID session IDs to positive
original-start nanosecond cutoffs. `denied` contains permanently excluded exact
IDs. An empty enrollment map denies all sessions. Denial wins over enrollment.
Persist and review both lists privately; never regenerate them from observed
sessions on startup or remove recovery exclusions when regenerating a policy.

Only enroll IDs independently verified to be fresh and non-forked. Unknown IDs,
missing IDs, subagent/fork IDs not explicitly verified, and old original span
starts are rejected. Root `metadata.codex.thread_id` must equal `session.id`;
root turn metadata must be present. Root start time is the original turn start,
not arrival/flush time. UUIDs are validated before embedding into OTTL.

`TRACE_TO_LANGFUSE=false` is **not** a durable exclusion: later resumption can
backfill an excluded turn. Keep recovery and other secret-bearing sessions
permanently denied, even if an operator accidentally includes one in enrollment.
Do not resume an old session as an enrollment technique. Do not import history.

Static exact enrollment supports bounded sessions only. Automatic enrollment of
all future sessions remains unimplemented and is not safe to infer from these
checks. Restart tests prove that the same saved policy retains its denials; they
do not prove an external operator cannot overwrite that policy.

## Content policy and deliberate limitations

Default mode preserves supported text-only root user input and final assistant
output. It is a turn summary, **not complete intermediate dialogue**. It drops
all generation spans by default.

With explicit `generations=True`, generation output is parsed as a JSON object
and only its string `content` is retained. Generation inputs are always dropped:
they include system/developer instructions, tools and prior conversation history.
Reasoning, tool calls and all other generation fields are dropped. Missing or
malformed output and non-string content fail closed. Parse errors propagate;
an invalid span can cause rejection of the entire incoming batch.

The optional generation mode checks the generation's own original start time.
Stateless OTTL does not join it to its root, so it cannot independently establish
that root's original turn cutoff or thread metadata. Fresh non-fork enrollment
and the trusted pinned producer are required provenance assumptions. Do not
use this option on old or resumed sessions. It is not a full arbitrary-OTLP
conversation authorization boundary. Root-only mode avoids this particular
cross-span timestamp assumption.

Only plain string root input/output is supported. Typed arrays/maps and strings
starting with a serialized array/object marker are rejected, including media.
This intentionally rejects some legitimate JSON/code responses rather than
risk retaining an unrecognized multimodal shape. It is not semantic detection
of every possible media reference embedded in ordinary prose.

Every accepted span gets fixed names/scope labels and only session ID,
observation type and approved text attributes. Resources, schema URLs, scope
attributes, status message/code, trace state, arbitrary metadata and identities
are cleared. Events are removed and spans with links are rejected. Numeric usage
is omitted rather than trusting unvalidated accounting fields. Stable OTLP trace
and span IDs/timestamps remain for correlation.

Retained text is redacted for synthetic canaries and selected recognizable token
and private-key patterns. **This cannot detect arbitrary secrets**, recovery
material in prose, novel formats, or secrets split across fields/messages.
Do not describe the regex as a perfect secret filter. Secret-bearing sessions
must remain permanently excluded. No retention period is selected here.

## Validation

Run only `sh validation/run.sh application`. The committed Docker workflow runs
offline lint, upstream Collector runtime cases in network-none containers, and
existing application contracts/schema checks. No host Python fallback, daemon
startup, live receivers, private inputs, deployment or pushing is involved.

`validation/conversation_runtime.py` creates synthetic OTLP envelopes with
canaries in resources, schema URLs, scope metadata, events, status, input and
output. It verifies fresh acceptance, unknown/old/recovery/fork/missing/mismatched
session rejection, original cutoff, generation input/history removal, optional
content-only output, malformed shapes, media, secret patterns, link rejection,
authentication and preserved exclusions on restarted Collectors. Synthetic
credentials exist only in the ephemeral container and never authorize real use.

Before rollout, separately verify the target private project, authentication,
mTLS hop, plugin loopback setting, disabled media upload and preserved private
denial lists. Passing these synthetic tests does not enable broad capture or
establish end-to-end live delivery. Pause rollout on any safety-test failure.

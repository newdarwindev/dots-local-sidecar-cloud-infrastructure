# Bounded conversation-capture policy

Status: a bounded deployment was qualified on 2026-11-09 on the two approved
desktop sources and the internal collector. Broad capture is **not enabled**.
This repository supplies a standard upstream Collector configuration generator,
not a custom hook, relay, receiver, or ingestion service. Rendering alone changes
no live service, credential, project, enrollment, receiver, or exporter. Target
provisioning and live verification are separate operator-authorized actions.

## Pinned source and architecture

- Official Langfuse Codex plugin 0.4.3, revision
  `e1d02be28e6bacbfe350a1bc1ccf861e54edee17`.
- Upstream OpenTelemetry Collector Contrib 0.163.2, using the existing pinned
  validation image and built-in OTLP, basic-auth, filter, transform and exporter
  components. No experimental feature gate is needed.
- Plugin `base_url` points only to an authenticated loopback Collector. Its
  receiver accepts `/api/public/otel/v1/traces`. Set
  `LANGFUSE_MEDIA_UPLOAD_ENABLED=false`; media uploads otherwise bypass tracing.
- Local sanitization precedes the existing authenticated mTLS hop to the internal collector and
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

## Safe rendering entrypoint

Use `sh validation/run.sh setup conversation-render /absolute/nonsecret/enrollment.json`.
The input must be outside the checkout, a regular non-symlink JSON file, at most
64 KiB, containing exactly these three fields:

```json
{
  "enrolled": {"11111111-1111-4111-8111-111111111111": 2000000000},
  "denied": [],
  "generations": false
}
```

The UUID and cutoff above are synthetic examples, not enrollment guidance.
`generations` must be an explicit boolean. Unknown fields, malformed UUIDs,
non-integer cutoffs, duplicates and private endpoint/credential fields are
rejected. An empty `enrolled` map renders a default-deny configuration.
The command prints one standard Collector JSON configuration with unresolved
private environment placeholders. It does not apply the configuration or
access the target. Keep rendered real IDs private. No host Python import or
fallback is supported. The existing safe setup workflow pins the local Docker
endpoint, snapshots input once, suppresses container logs, removes ambient Docker
configuration and runs with no network, mounts, credentials or account environment.

Sanitized output has scope name `codex.conversation`, scope version `1` and span
name `codex.conversation`. Resource attributes, including `service.name`, are
empty. Root thread/turn metadata is validated locally but not retained. A central
second sanitation stage must validate this reduced output schema; reapplying the
source-input policy would reject roots because the original metadata is absent.

## Producer-schema compatibility correction

The pinned plugin's `plugins/tracing/src/trace.ts` creates roots with observation
`asType: agent` and name `Codex Turn`, not observation type `span`. Only that exact
pair is accepted. Optional generations must have type `generation` and name
`LLM`. `Codex Subagent Turn`, `LLM Subagent`, tool/internal spans, unknown names,
and mismatched type/name pairs are rejected even when the session is enrolled.
Outgoing root observation type remains `agent`; generations remain `generation`.
Both outgoing span names are normalized to `codex.conversation` as before.
Central sanitized-output validation must accept those two observation types.

The initial synthetic suite used the wrong root type and therefore did not prove
compatibility with actual plugin roots. Its passing counts are not evidence of
that compatibility. The corrected synthetic fixtures model the inspected pinned
producer's type/name pairs and explicitly assert retained root user/final text.
Actual installed-plugin integration is a separate bounded acceptance check and
must pass before any live activation; no global capture is enabled by this fix.

The desktop edge exporter authenticates solely with its existing mTLS client
certificate to the internal collector ingress. It sends **no Authorization header** and has
no Langfuse project credential. The new private Langfuse project credential
belongs exclusively to the central exporter on the internal collector. Local plugin-to-Collector
Basic authentication is independently provisioned and must not reuse that
central project credential. Edge placeholders cover only the mTLS destination,
CA, client certificate/key and local htpasswd file.


## Bounded live qualification: 2026-11-09

The actual installed pinned plugin was exercised through separate authenticated
loopback Collectors on macOS and Linux, the existing encrypted mTLS ingress, and
a separate private Langfuse project. The project has one effective owner, no
pending organization invitations, and no retention limit selected. Its scoped
project credential stays exclusively on the central host; desktop sources use
independent local Basic credentials and their existing mTLS identity.

Both installed-plugin synthetic integrations produced exactly one root AGENT
and one GENERATION in the backend. Explicit observation IO reads verified the
visible user/final text, content-only generation output, and absence of fake
credential, internal-instruction and developer-instruction canaries. The Linux
source also exercised denied and unknown sessions: both had zero backend
observations. Unauthenticated loopback ingestion returned HTTP 401; central
ingestion rejected a missing mTLS client certificate.

Fresh macOS and Linux CLI sessions, started with `--no-daemon` and media uploads
disabled, were enrolled before their first harmless prompts. Each actual Stop
hook produced two backend observations with the expected reply. This is stronger
than manually invoking the plugin, but it does not prove the ordinary shared-
daemon conversation path or automatic enrollment. Both isolated test directories
were disabled after completion; global conversation capture remains disabled.

Existing metadata-only delivery was rechecked after central routing deployment
using a content-free probe and remained in its original project. The existing
central Deployment uses Recreate, so route updates cause a brief restart, not
overlapping rolling pods. No firewall or project-membership relaxation occurred.

The central request limit remains 64 KiB. This is best-effort filtered capture,
not an archival or exactly-once system: a large batch, exporter failure, unknown
session, unsupported shape, or failed privacy gate may yield no observations.
The plugin sidecar can mark attempted turns processed, so endpoint success and
plugin exit zero are insufficient; use explicit backend receipt checks. Do not
remove sidecar state or resume history to force a replay.

Machine-specific enrollment IDs, trace IDs, credentials, certificates, runtime
paths and service state remain outside Git. Never infer global production
readiness from these bounded receipts.


## All-session activation gate: adversarial results

Do not remove exact session enrollment or enable blanket content capture based
on the earlier positive canary tests. Additional synthetic tests against the
pinned Collector demonstrated these limitations:

- Plainly fake passwords, arbitrary credentials and recovery-share strings that
  do not match selected patterns remain in both root text and generation output.
  Passing known token-pattern tests is not arbitrary-secret protection.
- The renderer has no persistent memory. Removing a denial from an operator
  policy re-admits matching replay; ordinary plugin opt-out does not create a
  permanent denial or a skipped-turn checkpoint.
- An unknown fork is blocked, but enrolling its new ID admits it even when a
  supplied parent ID is denied. The current policy does not validate ancestry.

These tests intentionally pass when the limitations are reproduced; they are
negative qualification evidence, not authorization or readiness for all-session
content capture. The full Docker application workflow passed 236 tests after
adding them, including five test-only lifecycle-model cases.

The lifecycle model specifies monotonic denial, parent denial, original cutoffs,
corrupt/missing-state refusal and stale-writer rejection. It is not a durable
ledger, hook integration, storage implementation or crash/concurrency proof.
Do not deploy it as one. A real implementation must integrate enrollment and
export in one ordered fail-closed path, preserve denial across restarts and
resumes, reject unverified lineage and identify protected control-plane sessions.
Multiple independent hooks must not be assumed to execute in order.

Even a correct lifecycle ledger cannot determine whether arbitrary future prose
is a password or other secret. Blanket content export therefore cannot be
qualified by a regex update or session creation timestamp alone. Keep native
metadata-only collection separate and content collection explicitly bounded
until the missing source and data-exclusion guarantees are established.

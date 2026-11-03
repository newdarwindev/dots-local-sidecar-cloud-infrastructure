# Telemetry setup contract — no source enabled

Follow [application setup](../README.md) first. These are separate source/content
approval scopes; deploying a hub does not enroll any device or account. Current
contracts are offline/synthetic and **UNRUN**, not live exporters or durable ledgers.

| Selected path | Destination / ownership | Still required |
| --- | --- | --- |
| Native Codex OTel traces | Private mTLS Collector → separate Langfuse diagnostic project; noncanonical usage | Reviewed source-local adapter/transport, exact Collector canaries and delivery reconciliation |
| Official Codex plugin | Supported Langfuse path; canonical for explicitly assigned future rich sessions | Pinned hook/config review, content consent and effective-config validation before activation |
| Community historical importer | Canonical for explicitly assigned completed historical sessions | Pinned code/schema/privacy review, bounded allowlist/checkpoints; no watcher |

Do not assume plugin/importer exporters support the Collector; verify their actual
transport/auth interface. Native logs and metrics remain **disabled** until their
own backends/security/retention are approved. Langfuse accepts OTLP HTTP traces,
not arbitrary logs/metrics or gRPC. No debug/stdout fallback for source content.

## Source and privacy gates

- Default to positive typed metadata allowlists before transport and again at the
  gateway. No prompts, filenames/paths, repo contents, tool I/O, images, instructions,
  reasoning summaries, raw errors or secrets. Model/job labels may also be private.
  Rich content requires bounded source/project/viewer/retention approval and tested
  local masking; server masking cannot undo content already transmitted.
- Newly authored synthetic fixtures only. A marker is not proof of synthetic,
  anonymous or approved content. Denied/unavailable/other-account roots remain
  coverage gaps, never workaround or backfill targets.
- Record each authorized CLI, exec/CI, desktop/app-server, WSL/VM or hosted surface
  separately with exact version/config, allowed source, test session and confirmed
  destination record. Neither CLI support nor a running hub proves full coverage.
- Private TLS/mTLS and project separation are mandatory; verify resolved destination
  and credential association without printing credentials. Langfuse project keys
  are not assumed write-only or per-host. No blanket `/api/*` auth exception.

## Native diagnostic boundary

[Native OTLP prototype](native-otlp-boundary.md) reconstructs a whole synthetic
request. It is not a receiver or Codex endpoint. Only its `request` member is an
OTLP body; the review wrapper is not. Raw native emissions must never bypass the
future source-local boundary merely because the gateway filters again.

The future transport is OTLP/HTTP JSON to private gateway `/v1/traces`; the gateway
uses Langfuse `/api/public/otel/v1/traces` with the reviewed ingestion-version
header. Distinguish `otel.trace_exporter` from log `otel.exporter` and
`otel.metrics_exporter` using the installed Codex version. The current Collector
is trace-only, bounds its volatile queue/retries, and can lose diagnostics during
outage/termination. No complete-delivery or live filter claim follows from config.

## Plugin configuration before any later enrollment

Require one explicit approved self-hosted HTTPS base URL, no hosted fallback, an
approved pseudonymous user ID and bounded reviewed metadata. Keep hooks disabled
and skill tags off unless separately reviewed. Inspect effective defaults/global/
project/environment layers: `LANGFUSE_CODEX_*` overrides matching `LANGFUSE_*`.
Absent or conflicting destination/identity must block activation. Review pinned
hook code/hash and prove resolved values with synthetic data; no credentials,
config installation or hook activation is authorized here. Hooks are fail-open
observability, not a compliance/audit guarantee.

[`plugin_setup.py`](../scripts/plugin_setup.py) provides a disabled, credential-free
review renderer/checker matched to the [pinned resolver](../contracts/codex-plugin.lock.json).
Prepare explicit nonsecret inputs outside the repository using the shapes in
[render](../fixtures/plugin-render.synthetic.json) and
[check](../fixtures/plugin-check.synthetic.json). Once authorized Docker execution
resumes, use the [bounded setup route](../../validation/README.md#offline-setup-review):

```sh
sh validation/run.sh setup plugin-render /private/plugin-render.json
sh validation/run.sh setup plugin-check /private/plugin-check.json
```

No files are mounted or installed; output is private stdout for review only.
The runner and [synthetic tests](../tests/test_plugin_setup.py) remain **UNRUN**.
`render` prints vendor-format disabled config without keys. `check` models only
explicitly supplied credential-free global/project/env layers, never ambient
files/environment/auth. Both reject unknown fields, activation, hosted fallback,
identity drift and unreviewed tags/metadata. There is no install/write/enable mode.
`max_history_chars` (1–200000) bounds model history only, **not tool output or total
content**, and is not masking. A passing check proves neither the live configuration,
credential custody nor consent; later environment changes can override a file.

## Canonical ownership and cutover

Before enabling any source, keep an immutable private ledger of source namespace,
session IDs, producer version and UTC cutover `T`. Copying a history must retain
its original source identity; do not use filesystem modification times.

- Importer owns explicitly assigned sessions completed before `T`; plugin owns
  assigned sessions started after successful enrollment/restart at or after `T`.
  Hold spanning sessions for explicit single-producer assignment after completion.
- Resume retains ownership. Events must fall inside enrolled start/end intervals
  (inclusive); a resumed closed interval requires reconciliation, not silent growth.
- Reconcile canonical source/session/turn/event and generation identities across
  producers; a turn may contain several generations and non-token tool/child spans.
  Current in-memory harness computes no totals and proves no native-ID mapping.
- Reject import of an already-owned session. Preserve delta/cumulative/cached/output
  provenance; never sum cumulative snapshots. Missing usage is unknown, not zero.
  Commit checkpoints only after confirmed delivery; reconcile server IDs before
  retrying uncertain sends. In-memory dedup is not a durable delivery ledger.
- Native diagnostics stay noncanonical in a separate project; never sum them into
  plugin/importer totals or silently fill gaps. If only native evidence exists,
  keep it noncanonical pending explicit reconciliation. Tokscale accounting stays
  separate; Langfuse estimates are not ChatGPT subscription quota accounting.

## Acceptance before activation

Use the authorized Docker path to test whole-envelope secret canaries, two-turn/
tool-failure/child/resume/cancel scenarios, lineage/timestamps, repeated overlap,
retry/partial success, queue bounds, crash/flush, revoked keys, wrong viewers and
TLS rejection. Reconcile each canonical generation at most once while retaining
inspectable diagnostics. Test isolated restore with authorization/count/ID checks.
No current synthetic fixture proves live ingestion, privacy or durable recovery.

Preserve every original history/attachment and receipt. Any derivative-data
retention/TTL needs explicit scope; no deletion or paid retention API is enabled.
For stop/restore rules use [recovery](../README.md#5-recovery-and-rollback).

Sources to verify against pinned versions: [Codex config](https://learn.chatgpt.com/docs/config-file/config-reference),
[Codex OTel](https://github.com/openai/codex/blob/main/codex-rs/otel/README.md),
[Langfuse OTel](https://langfuse.com/integrations/native/opentelemetry),
[official plugin](https://github.com/langfuse/codex-observability-plugin),
[community importer](https://github.com/kirilligum/codex-langfuse-tracer).

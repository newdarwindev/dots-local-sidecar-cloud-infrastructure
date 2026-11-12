# Epic: native agent telemetry in Langfuse

## Product goal and boundary

As an owner, inspect permitted agent activity with producer/session attribution and explicit privacy and delivery limits. Use supported native settings and standard Collector components; do not revive custom receivers, transcript parsers, reconstruction relays or broad historical capture to bypass a missing capability.

Canonical behavior lives in the [native monitoring contract](../../docs/codex-native-monitoring.md) and [telemetry runbook](../../application-infrastructure/runbooks/telemetry.md). This specification adds story-level completion gates, not a second configuration recipe.

## Stories and acceptance requirements

| ID | User story and technical contract | Required evidence |
| --- | --- | --- |
| TEL-01 | Attribute every accepted signal to producer/version, host alias, session and trace/span identity. Keep source enrollment, connectivity and successful delivery distinct. | A synthetic record is joined to its exact installed producer/privacy tuple; unknown identities are rejected or explicitly unavailable. |
| TEL-02 | Admit content only under authoritative denials, cutoffs and qualified fresh-session/fork rules. Generated allowlists are not the authority. One intended content producer prevents native/plugin duplication. | Denied and pre-cutoff IDs appear in no sink; fork and fresh-session fixtures pass independently; no blanket future admission is inferred. |
| TEL-03 | Keep numeric diagnostics, bounded message content, tool results and accounting on separate routes. Project and redact the whole envelope before enforcing encoded size limits. | Tool/path/error canaries and schema metadata are checked across the full output; maximum escaped payload, malformed neighbors and rejected events have explicit outcomes. |
| TEL-04 | Preserve recognized live pipeline shapes, authentication and durable queues through guarded revision-aware updates. | Changed/stale configuration is refused; unrelated pipelines and queue state remain intact; rollback identifies exactly the prior configuration. |
| TEL-05 | Qualify every TLS/authentication, receiver cap, batch and queue hop through the complete route. | Wrong identity/CA/hostname/auth fail; local HTTP success is not counted as persisted delivery; approved maximum payload survives every hop. |
| TEL-06 | Read back exact invented trace/span IDs from Langfuse ingestion version 4. | Independent events_core/events_full queries record physical rows, logical IDs and deletion state; duplicate and loss ledgers name the tested boundary. |
| TEL-07 | Measure normal delivery, rejection, shutdown/flush, backend outage, buffering, replay, process crash and power loss independently. | Each scenario has its own input IDs, expected result, observation window and receipt; a process-crash pass does not mark power-loss or independent restore complete. |
| TEL-08 | Preserve accounting meaning across trace diagnostics, rich plugin accounting and Tokscale. | Overlapping totals are not summed; missing usage/cost is unknown, with source/version stated. |

## Integration contracts

Langfuse receives HTTP JSON/protobuf traces at /api/public/otel/v1/traces with project authentication and ingestion version 4. Raw logs, metrics and gRPC are not interchangeable with that endpoint. Qualified log-to-trace conversion is a separate contract.

The dashboard consumes sanitized evidence; it does not establish enrollment permission. The refinery receives permitted, versioned traces joined to immutable examples, not arbitrary histories. Credential values and actual target routes stay in the private operational overlay.

## Progress and open gates

Source validators and isolated serial-route controls exist, including the [separate integration qualification](https://github.com/newdarwindev/dots-local-sidecar-cloud-infrastructure/commit/b7d8c30f418c97dada23bc256cf681741c91c6f5). These are bounded evidence, not all-session coverage, exactly-once delivery, live lifecycle recovery or automatic acceptance of a particular machine.

Open gates include authoritative policy provenance, fresh-session/fork handling, real producer batching, production-route payload acceptance and device-specific qualification. Unsupported source surfaces stay unavailable.

## Completion and maintenance

For an implementation change, record source and installed hashes, exact producer versions, input IDs, test commands/results, failed and unrun controls, cleanup and rollback. Run the applicable [Docker validation scope](../../validation/README.md); do not substitute documentation checks for it. Use synthetic data for qualification and preserve histories, keys, queues and databases. Any live enrollment or outage/recovery exercise needs its own authorized scope.

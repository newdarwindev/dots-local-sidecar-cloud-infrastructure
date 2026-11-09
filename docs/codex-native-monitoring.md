# Codex monitoring through native integrations

Use supported Codex settings and upstream components. Custom receivers, transcript
parsers, reconstruction services, queues, uploaders and wrappers are outside this
rollout. Preserve earlier prototypes as historical work. This public plan does not
activate services or establish coverage on a particular host.

## Selected routes

| Signal or service | Route | Boundary and runbook |
| --- | --- | --- |
| Native trace diagnostics | Codex `otel.trace_exporter` → standard Collector projection → private Langfuse diagnostic project | [Safe span events](../application-infrastructure/runbooks/native-event-diagnostics.md); exact producer/version gates, bounded numeric metadata, no conversation text |
| Native log diagnostics | Codex `otel.exporter` → standard Collector filter/transform/`otlp_json` → Langfuse traces | [Numeric-only logs](../application-infrastructure/runbooks/native-log-diagnostics.md); separate projection and privacy settings, not raw-log ingestion |
| Bounded message events | Native OTLP logs → standard Collector conversion → separate Langfuse content project | [Message conversion](../application-infrastructure/runbooks/native-message-conversion.md); only explicitly qualified fresh sessions, not blanket capture |
| CLI batching and host labels | Codex startup dotenv and bounded Collector statements | [Formation settings](../application-infrastructure/native-monitoring/formation-settings.md); new processes only, exact trace readback required |
| Tokscale | Upstream Codex reader, `submit` and `autosubmit` | [Private-hub contract](../application-infrastructure/tokscale/README.md); separate usage accounting, OAuth and scheduled endpoint checks; not an OTLP destination |
| Homarr | Native Apps/Bookmarks and optional iFrame | Links to existing UIs only; no receiver or custom widget |
| AgentsView | Upstream local session reader/watcher | Separately approved workstation roots; not Codex OTLP or cloud/private-endpoint capture |

The base [Collector values](../application-infrastructure/values/collector.yaml)
remain a staged trace-only example. They are not a replacement for a live
multi-pipeline configuration. Apply only reviewed changes to recognized shapes,
preserving authentication, privacy gates, endpoints and unrelated pipelines.

## Optional routes, not blanket enrollment

- **Langfuse's upstream Codex plugin:** vendor hooks can capture session/turn,
  model and tool content. Pinned code review, hook trust and bounded content
  consent are separate. Keep disabled until qualified.
- **Product-native full conversations:** the selected direction, but current
  content flags and the bounded plugin do not qualify all-session capture.
  See the [readiness contract](native-conversation-support.md); no supported
  implementation date is established.
- **Prometheus/Grafana, Loki and Tempo:** candidate metrics/log/trace backends,
  not installed or approved by this plan. Verify native exporter compatibility,
  backend authentication and readback before selecting them. Do not install them
  just to fill a dashboard table.

## Transport and configuration

Langfuse accepts HTTP JSON/protobuf traces at `/api/public/otel/v1/traces`, with
project Basic authentication and `x-langfuse-ingestion-version: 4`. It does not
accept gRPC or raw logs/metrics at that endpoint. Converting qualified logs to
traces is distinct from sending raw logs. Protocol compatibility alone does not
prove rich generations, token accounting or delivery. [Codex settings][codex-config],
[Langfuse OTLP][langfuse-otel].

Configure clients through supported user/admin settings. Track CLI, IDE/app-server
and hosted surfaces separately. Do not kill active sessions or alter provider
authentication to enable monitoring. Test the installed version, not just upstream
main or a current web guide. The plugin guide's Node.js 22+/Codex 0.143+ requirements
do not qualify an older repository pin.

## Privacy and acceptance

Use the exact privacy settings and projections in each selected runbook. Prompt
redaction alone does not sanitize tool/path/error metadata or the whole envelope.
If supported settings and standard Collector components cannot satisfy a required
boundary, leave that feature unavailable; do not add a custom relay.

Before cutover, verify effective configuration, TLS/auth denial, shutdown/flush,
backend-unavailable behavior and an approved test's exact persisted IDs. Record
which clients passed and what remains unverified. Backend readback is not an
authenticated UI test; a running service is not proof of restart persistence.

Native export does not promise complete delivery, durable replay, pseudonymization
or canonical cost accounting. Keep trace diagnostics, rich-plugin accounting and
Tokscale totals separate; never sum overlapping totals. Preserve source histories,
queues, credentials, databases and receipts. Publishing this plan does not enroll
sources, install plugins, deploy backends or shut down legacy services.

## References

- [Codex configuration][codex-config] and [telemetry][codex-otel].
- [Langfuse OTLP][langfuse-otel] and [upstream Codex integration][langfuse-codex].
- [Tokscale](https://github.com/junhoyeo/tokscale) and its
  [pinned private-endpoint/scheduler audit](../application-infrastructure/tokscale/contract-audit.md).
- [AgentsView](https://www.agentsview.io/docs/configuration/),
  [Homarr Apps](https://homarr.dev/docs/management/apps/) and [iFrame](https://homarr.dev/docs/widgets/iframe/).
- [Prometheus OTLP](https://prometheus.io/docs/guides/opentelemetry/),
  [Loki OTLP](https://grafana.com/docs/loki/latest/send-data/otel/) and
  [Tempo OTLP](https://grafana.com/docs/tempo/latest/api_docs/pushing-spans-with-http/).

[codex-config]: https://learn.chatgpt.com/docs/config-file/config-reference
[codex-otel]: https://learn.chatgpt.com/docs/config-file/config-advanced#observability-and-telemetry
[langfuse-otel]: https://langfuse.com/integrations/native/opentelemetry
[langfuse-codex]: https://langfuse.com/integrations/developer-tools/codex

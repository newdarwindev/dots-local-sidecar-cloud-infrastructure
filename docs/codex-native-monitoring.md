# Codex monitoring through supported integrations

**Plan revised 2026-11-06: configuration and upstream integrations only.**
The owner rejected custom Codex relays. Do not build or extend a receiver,
transcript parser, privacy reconstruction service, queue, uploader or wrapper
for this integration. Existing prototypes are preserved as prior work, outside
the selected rollout. This document changes the plan, not live services.

## Native conversation direction

The selected next step is **product-native/upstream support**, not a custom host
workaround. See the [readiness contract and acceptance matrix](native-conversation-support.md).
Current native content log flags and the bounded upstream plugin do not qualify
all-session capture. No supported implementation date is established.

## Integration matrix

| System | Supported route without custom application code | What it supplies | Qualification still needed |
| --- | --- | --- | --- |
| Langfuse: operational traces | Codex built-in `otel.trace_exporter` using OTLP/HTTP to the private Langfuse trace endpoint | Native spans; treat as operational diagnostics | Installed-version field/privacy review, authenticated endpoint and persisted trace readback; full LLM replay/token mapping is not established |
| Langfuse: bounded native message events | Native Codex OTLP logs → standard Collector filter/transform/`otlp_json` → Langfuse traces | Independent user-prompt and final-answer events grouped by session | [Implemented and backend-verified](../application-infrastructure/runbooks/native-message-conversion.md) for explicitly qualified fresh sessions; alpha connector, no blanket enrollment or UI success claim |
| Langfuse: bounded plugin transcript capture | Install the upstream Langfuse Codex tracing plugin through Codex's plugin system | Session/turn, model and tool tracing | This is a vendor plugin, not the built-in exporter. It uploads transcript content; content consent, pinned plugin review and hook trust remain separate; [all-session blockers](native-conversation-support.md) prevent blanket enablement |
| OpenTelemetry Collector | Optional upstream Collector configured through its standard receivers/processors/exporters | Routing or fan-out when needed | No custom source adapter. Current trace-only values do not configure metrics/log pipelines; a running Collector is not established by this plan |
| Tokscale | Upstream Codex reader, `submit` and `autosubmit` | Aggregate usage reporting | Vendor integration, not a Codex OTLP destination. Private hub/OAuth/token and scheduled endpoint checks remain; no custom reporter |
| Homarr | Native App/Bookmarks shortcuts and optional iFrame widget | Access to existing monitoring UIs | Presentation only; no Codex telemetry receiver or new custom widget |
| AgentsView | Upstream local Codex session reader/watcher | Local searchable session archive | Vendor integration on the separately selected workstation, not Codex OTLP. Approved local source roots required; cloud/private-endpoint capture remains excluded |
| Prometheus + Grafana | Candidate expansion: Codex native `otel.metrics_exporter` to Prometheus's OTLP/HTTP receiver; Grafana reads Prometheus | Operational metric counters and histograms | Backend installation/authentication, histogram compatibility and readback; not subscription billing or complete token accounting |
| Loki + Grafana | Candidate expansion: Codex native log `otel.exporter` to Loki OTLP/HTTP, directly or through the standard Collector | Structured operational logs | Keep disabled initially; content review and backend configuration required |
| Tempo + Grafana | Candidate alternative: Codex native trace exporter to Tempo OTLP | General distributed tracing | Not an installed stack. Use an upstream Collector for fan-out if both Tempo and Langfuse are selected |

Prometheus/Grafana, Loki and Tempo are options evaluated here, **not approved
deployments or previously verified live systems**. Do not add them merely to
complete this table. Keep the selected-cluster and separate workstation placement.

## Selected initial route

Start with **Codex native traces directly to the existing private Langfuse**.
Use `otel.trace_exporter`, not the log exporter `otel.exporter`; retain native
metrics/log export as separate decisions. Langfuse's signal endpoint is
`/api/public/otel/v1/traces`, with project Basic authentication and
`x-langfuse-ingestion-version: 4`. It accepts HTTP JSON/protobuf, not gRPC.
This is protocol compatibility, not proof that the installed Codex emissions
already form rich Langfuse generations. [Codex settings][codex-config],
[Langfuse OTLP][langfuse-otel].

Configure supported clients through their documented user/admin configuration.
Track CLI, IDE/app-server and hosted surfaces separately; do not claim all
sessions are covered from one successful CLI test. Do not kill existing sessions
or modify provider authentication to turn monitoring on.

## Privacy, delivery and cutover

Keep prompts, agent responses and automatic-review text export off; leave log
export disabled in the initial trace rollout. Native prompt redaction does not
establish a whole-envelope metadata allowlist or eliminate tool/path/error
content. Review actual installed-version fields before enrollment. If a required
privacy property cannot be achieved through supported settings or standard
Collector configuration, record that feature as unavailable; **do not invent
another relay**. [Codex telemetry][codex-otel].

Do not promise durable replay, complete delivery, pseudonymization or canonical
cost accounting from native export. Accept upstream behavior and state its
limits. Keep diagnostic traces, rich-plugin accounting and Tokscale totals
separate; never add overlapping totals. Preserve histories, existing queues,
credentials, databases and receipts when retiring an earlier path.

The rich plugin is optional and off until its transcript scope is approved.
Langfuse currently documents Node.js 22+ and Codex 0.143+; verify the selected
release rather than treating a current web guide as the repository's old pin.
Use upstream installation/configuration, with no locally authored hook.
[Langfuse Codex integration][langfuse-codex].

Before cutover, verify effective endpoint/configuration, TLS/auth denial and a
small approved session's persisted records through the backend UI/API. Observe
shutdown/flush and backend-unavailable behavior using upstream tools. Record
each supported client and remaining gaps. Publication of this plan performs no
enrollment, plugin installation, backend deployment or legacy service shutdown.

## References reviewed 2026-11-06

- [Codex configuration reference][codex-config] and [telemetry guide][codex-otel].
- [Langfuse native OTLP][langfuse-otel] and [upstream Codex plugin][langfuse-codex].
- [Tokscale upstream documentation](https://github.com/junhoyeo/tokscale); retain
  [the pinned private-endpoint/scheduler audit](../application-infrastructure/tokscale/contract-audit.md).
- [AgentsView source configuration](https://www.agentsview.io/docs/configuration/).
- [Homarr Apps](https://homarr.dev/docs/management/apps/) and
  [iFrame widget](https://homarr.dev/docs/widgets/iframe/).
- [Prometheus OTLP receiver](https://prometheus.io/docs/guides/opentelemetry/),
  [Loki OTLP](https://grafana.com/docs/loki/latest/send-data/otel/), and
  [Tempo OTLP](https://grafana.com/docs/tempo/latest/api_docs/pushing-spans-with-http/).

[codex-config]: https://learn.chatgpt.com/docs/config-file/config-reference
[codex-otel]: https://learn.chatgpt.com/docs/config-file/config-advanced#observability-and-telemetry
[langfuse-otel]: https://langfuse.com/integrations/native/opentelemetry
[langfuse-codex]: https://langfuse.com/integrations/developer-tools/codex

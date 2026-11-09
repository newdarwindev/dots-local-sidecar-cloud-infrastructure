# OpenTelemetry setup

**Current Codex route:** [native exporters and supported upstream connectors](codex-native-monitoring.md),
with direct native trace export to private Langfuse as the initial plan.
No custom receiver, source adapter, reconstruction service or delivery queue is
selected. The standard Collector is optional for routing/fan-out.

Use the [telemetry contract](../application-infrastructure/runbooks/telemetry.md)
for scope and acceptance. The [earlier native boundary prototype](../application-infrastructure/runbooks/native-otlp-boundary.md)
is historical work, not a prerequisite or selected rollout path.
The [Collector values](../application-infrastructure/values/collector.yaml) stage
private mTLS trace-only diagnostics. Logs/metrics remain disabled; no production
source adapter, exporter or durable delivery ledger is claimed.

Cluster configuration, validation and activation gates live in the
[operator setup guide](../application-infrastructure/README.md).

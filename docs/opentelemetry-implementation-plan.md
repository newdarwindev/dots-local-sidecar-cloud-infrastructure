# OpenTelemetry setup

Start with the [native integration matrix](codex-native-monitoring.md) for the
selected signal routes and their runbooks. Use supported Codex exporters and
standard upstream Collector components; no custom source adapter or delivery
queue is selected.

The [base Collector values](../application-infrastructure/values/collector.yaml)
are a staged private mTLS trace-only example, not the current configuration of
any host. Separate runbooks cover numeric log projection, bounded message
conversion and CLI batching. Do not replace an existing multi-pipeline Collector
with the base example. No general metrics backend or durable delivery ledger is
established by these files.

Use the [telemetry contract](../application-infrastructure/runbooks/telemetry.md)
for source/content scopes and the [operator guide](../application-infrastructure/README.md)
for configuration, validation and activation. The earlier
[native boundary prototype](../application-infrastructure/runbooks/native-otlp-boundary.md)
is historical work, not a rollout prerequisite.

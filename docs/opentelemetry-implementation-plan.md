# OpenTelemetry setup

Use the [telemetry contract](../application-infrastructure/runbooks/telemetry.md)
and [native boundary reference](../application-infrastructure/runbooks/native-otlp-boundary.md).
The [Collector values](../application-infrastructure/values/collector.yaml) stage
private mTLS trace-only diagnostics. Logs/metrics remain disabled; no production
source adapter, exporter or durable delivery ledger is claimed.

Cluster configuration, validation and activation gates live in the
[operator setup guide](../application-infrastructure/README.md).

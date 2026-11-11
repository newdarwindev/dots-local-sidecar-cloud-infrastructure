# Native Codex trace rollout

Use only after the owner approves deployment and metadata enrollment on the
selected existing cluster. These manifests create no credentials or public
listeners. Apply them to the reviewed namespace, preserving its identity pins,
existing application configuration, Secrets and retained volumes.

`collector.yaml` deploys the pinned upstream Collector with a trace-only pipeline.
It removes span events, rejects linked spans, removes arbitrary attributes and
content-bearing names/messages, and preserves trace/span IDs, timing and status.
It supplies fixed diagnostic labels. Logs and metrics pipelines are absent.
Schema URLs are not rewritten by this version: qualify the installed native
producer's schema metadata and do not claim arbitrary-OTLP sanitization.
The queue is bounded and volatile; complete delivery and replay are not promised.

Existing private inputs:

| Input | Purpose |
| --- | --- |
| `collector-receiver-tls` Secret | `tls.crt`, `tls.key`, `ca.crt`; mTLS receiver |
| `collector-diagnostic-auth` Secret | `authorization`; separate Langfuse project |
| `collector-exporter-ca` ConfigMap | `ca.crt`; exporter trust |
| `collector-private-endpoints` ConfigMap | `traces-endpoint`; HTTPS trace URL |

`langfuse-tls.yaml` supplies a standard Caddy configuration and ClusterIP Service.
Add the upstream Caddy sidecar to the existing Langfuse web pod, using immutable
image `caddy:2.11.2-alpine@sha256:834468128c7696cec0ceea6172f7d692daf645ae51983ca76e39da54a97c570d`,
the ConfigMap above and its existing approved localhost TLS leaf. The final hop
is pod-loopback HTTP. Verify Service selectors against the actual web deployment.
Native Langfuse authentication remains responsible for application/project access.
This TLS endpoint alone is not an independent browser authentication gateway.

Expose the Collector to the local supported Codex client with upstream kubectl
port-forward bound to `127.0.0.1` only. Manage that command through a standard
systemd unit, with explicit kubeconfig/context and pre-start cluster/namespace UID
checks. Do not make it dependent on a desktop login session.

Configure Codex's built-in `otel.trace_exporter` for OTLP/HTTP and the reviewed
receiver URL, with its existing CA/client certificate/key. Set the native log and
metrics exporters to `none`; keep prompt/response/review text logging disabled.
Use user/admin configuration, not project-local telemetry overrides. Do not copy
an entire Codex configuration or credentials into Git.

Before cutover, verify the exact Collector configuration in the repository's
Docker validation entrypoint, receiver mTLS/TLS controls and persisted trace
readback from a bounded approved Codex session. Then stop/disable the old relay,
retaining its queue, logs, credentials and receipts. Existing Codex processes do
not automatically reload new exporter configuration. Hosted/IDE coverage needs
separate evidence; a CLI test does not prove universal enrollment.

See the [native integration matrix](../../docs/codex-native-monitoring.md).

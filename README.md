# dots-local-sidecar-cloud-infrastructure

Public, staged infrastructure for a private application cluster. **Nothing is
deployed or enrolled by this repository.** Start with the
[operator setup guide](application-infrastructure/README.md): prerequisites →
configuration → validation → deployment gates → recovery.

The selected bundle is Langfuse and its databases/queue/S3 storage, a diagnostic
OpenTelemetry Collector, Tokscale with a separate PostgreSQL database, and
`homarr-workload`. Design assumes an eventually compatible cluster; actual host
identity, measurements and access remain in the private operational overlay.

**Validation status:** the full Docker entrypoint passed locally on 2026-11-05:
lint, 54 validator tests, 7 primary tests, application tests, Helm renders and
strict Kubernetes schemas. This verifies source contracts; live cluster acceptance
remains separate. GitHub workflows remain owner-paused. The production deployment
gate is disabled; the separate [synthetic lab](application-infrastructure/lab/README.md)
provides an explicit bounded setup path.

## Use only the references needed for your stage

For day-to-day navigation, use [operating entry points by role](docs/operating-entrypoints.md).
Keep per-machine deployed software, private endpoints and next steps in the private operational overlay.

| Task | Reference |
| --- | --- |
| Set up/review the selected application bundle | [Operator setup](application-infrastructure/README.md) |
| Run authorized Docker checks | [Validation](validation/README.md) |
| Connect Codex without custom relay code | [Native monitoring integration matrix](docs/codex-native-monitoring.md) |
| Run bounded native prompt/final-answer conversion | [Native message conversion](application-infrastructure/runbooks/native-message-conversion.md) |
| Retain safe native event diagnostics | [Native event diagnostics](application-infrastructure/runbooks/native-event-diagnostics.md) |
| Project numeric-only native log events | [Native log diagnostics](application-infrastructure/runbooks/native-log-diagnostics.md) |
| Qualify future product-native conversation export | [Native support readiness contract](docs/native-conversation-support.md) |
| Review native/plugin/importer boundaries | [Telemetry contract](application-infrastructure/runbooks/telemetry.md) |
| Build/review Tokscale | [Tokscale contract](application-infrastructure/tokscale/README.md) |
| Inspect immutable dependencies | [Image evidence](application-infrastructure/image-lock-evidence.md), [ClickHouse candidate](application-infrastructure/clickhouse-operator-contract.md) |
| Consider the deferred management bootstrap | [Primary reference](primary-infrastructure/README.md), [action-time approval](primary-infrastructure/APPROVAL.md) |
| Consider later shared identity, secrets or domains | [Deferred platform boundaries](docs/auth-domain-plan.md) |
| Record private target evidence | [Inventory template](docs/inventory-template.md), [fleet rules](docs/fleet-alignment.md) |
| Install an optional X11 desktop dashboard beside Conky | [Desktop launcher](desktop-dashboard/README.md) |

Primary management, Authentik, OpenBao/ESO, shared ingress/domains, Crossplane and
cloud expansion are **later proposals, not application-setup prerequisites**.
Co-located services share a failure domain; no HA or full-fleet coverage is claimed.

Keep generic reviewed code here; host details, private endpoints and recovery
records stay outside this public repository. Secret values do not belong in Git,
including private overlays. Publication, approval files and green checks are not activation
consent. Preserve original histories, data, keys and receipts throughout changes.

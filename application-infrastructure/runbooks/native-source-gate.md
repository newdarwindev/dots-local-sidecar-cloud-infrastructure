# Native metadata source gate

`native_source_policy.py` provides a pure, idempotent configuration patch for the
previously deployed desktop-only `filter/source`. It recognizes only the exact
old predicate or its own current predicate and changes no other configuration.
It does not read private files, run a receiver, transmit telemetry, or deploy.

The approved identity pairs are identical resource `service.name` and
instrumentation scope names: `codex_work_desktop`, `codex_cli_rs`, and
`codex-app-server`. Resource `service.version` must be exactly `0.167.0`.
Unknown, mismatched and missing identities are rejected. These fields are
self-reported source labels, not authentication; preserve receiver authentication
and the existing native privacy processors.

This patch does not add content fields or logs/metrics pipelines. It does not
change prompt/response logging settings, endpoints, credentials, queues, TLS,
privacy transforms or conversation-capture enrollment. The synthetic boundary
values remain separate from private deployed configurations.

## Qualification and later deployment

Use `sh validation/run.sh application` from the repository root. The committed
Docker workflow exercises structural preservation and exact Collector 0.163.2
allow/deny cases with synthetic content canaries. No private input belongs in a
build context, test fixture, console output or Git. Tests are not live acceptance.

A later authorized deployment should modify only the private native Collector's
`processors.filter/source` object. Compare canonical structural hashes of
`transform/privacy` and the entire configuration excluding `filter/source`
before and after; both must remain identical. Validate the resulting private
configuration using the installed pinned Collector, then restart only the native
Collector service if authorized. Preserve original files and logs. Do not
restart Codex, change the conversation project or replace private configuration
with synthetic fixture values. Read back fresh native metadata traces after
activation; this helper itself supplies no deployment entrypoint.


## Bounded live qualification: 2026-11-09

The exact gate was deployed to both desktop native Collectors after pinned-binary
validation. Canonical structural hashes confirmed that all configuration outside
`filter/source`, including the privacy transform, was unchanged. No Codex shared
daemon was restarted and no conversation policy was altered.

Ordinary default CLI probes used a harmless no-tools prompt and no inherited
originator override. A temporary append-only file exporter after the existing
privacy pipeline provided exact trace/span IDs for backend comparison. This
exporter was a separate bounded diagnostic change, not part of the permanent
gate patch. Its private output is preserved; the exporter is removed afterward.
The Linux probe yielded seven startup spans across five traces. All seven exact
pairs were verified in the original diagnostics project, with canonical span
names and no input/output. No additional native turn spans were observed in that
bounded window. The macOS local tee held 448 sanitized spans; five exact sampled
pairs were separately verified in the diagnostics project, with input/output
absent. This is not exhaustive verification of all 448 spans. These receipts do
not establish full shared-daemon turn coverage, token accounting, logs or metrics.

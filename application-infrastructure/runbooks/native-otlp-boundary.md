# Native OTLP boundary — synthetic, offline, UNRUN

Follow [telemetry gates](telemetry.md) and [application setup](../README.md).
`native_otlp.py` reconstructs a whole-envelope OTLP trace request; it is **not** a
receiver, source integration, exporter or production filter. No socket, credentials,
environment/history discovery or job runs. Docker is absent, CI paused and tests/
golden comparison are authored, not executed; earlier green results do not apply.

## Explicit fixture interface

Input is one explicit file or stdin, at most 4 MiB UTF-8, with this exact wrapper:

```json
{"schema_version": 1, "synthetic": true, "producer": "native", "signal": "traces", "request": {"resourceSpans": []}}
```

Use [invented canary input](../fixtures/native-otlp.synthetic.json) and
[expected output](../fixtures/native-otlp.expected.json), never source histories.
Only in the authorized validation container:

```sh
python3 application-infrastructure/native_otlp.py \
  application-infrastructure/fixtures/native-otlp.synthetic.json
```

Success prints a review envelope; **only `request` is an OTLP body**, and
`transmitted: false` is literal. Failure exits 2 with a fixed error and no partial
output/path/content disclosure. No write/overwrite/upload mode exists. Duplicate
JSON keys and nonfinite numbers are rejected; shell redirection is not delivery.

## Preserved versus discarded

| Field | Behavior |
| --- | --- |
| Trace/span IDs | Nonzero 32/16-character hex, lowercased without rehash/truncation |
| Parent ID | Absent/empty for root or nonzero 16-character hex; retained |
| Start/end | Positive uint64 decimal strings; ordered, no float/millisecond rounding |
| Kind/status | Integer enums, not booleans/names; default unspecified/unset; no message |
| Resource/scope | Rebuilt empty resource/fixed scope; original metadata/schema URLs dropped |
| Span content | Fixed name/diagnostic role; no attributes, usage, events, links, trace state, flags, dropped counters or unknown fields |

Limits: 128 resource groups, 512 scope groups, 4096 input spans and 4096 events/
links per span (discarded). Equivalent normalized `(traceId, spanId)` duplicates
collapse within a batch; conflicting replay or same-trace cycles reject the batch.
External parents remain counted, not assumed delivered. There is no cross-batch
ledger; zero unresolved parents does not prove complete delivery. `telemetry.py`
opaque canonical IDs are not OTLP span IDs and have no implicit conversion.
Source/session mapping, sampling and rich fidelity remain unimplemented.

The profile is narrower than [OTLP JSON](https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding)
and the [wire schema](https://github.com/open-telemetry/opentelemetry-proto/blob/main/opentelemetry/proto/trace/v1/trace.proto):
although OTLP can accept 64-bit JSON numbers, this prototype accepts decimal
strings only and rejects zero/unset timestamps.

## Future connection gates

Pin/test installed Codex emissions and implement a reviewed source-local boundary
before any authenticated transport. This CLI cannot be configured as a source
endpoint; do not send raw data directly to the cluster. Use private mTLS gateway
`/v1/traces`, then the separate diagnostic-project Langfuse
`/api/public/otel/v1/traces`. A marker cannot enforce project isolation.

Exact pinned Collector tests must inspect the entire exported canary envelope,
auth failures, queues/loss, partial success, retry/cancel and cross-batch lineage.
Current [tests](../tests/test_native_otlp.py) cover offline structure only. No test
success authorizes activation, credentials or transmission. Preserve originals;
plugin/importer boundaries remain separate and native usage stays noncanonical.

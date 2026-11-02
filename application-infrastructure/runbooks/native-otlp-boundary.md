# Native OTLP boundary prototype — synthetic, offline, untested

`native_otlp.py` implements the missing **whole-envelope serialization boundary**
for a future native diagnostic route. It is not a receiver, source integration,
exporter, live filter, or production-ready deployment. No sockets, credentials,
environment inspection, history discovery or background jobs are involved.
Docker is unavailable and hosted CI is paused; the new tests and golden fixture
comparison are **authored, not run**. The previous green revision does not cover
this code.

## Explicit fixture in, review envelope out

The input is one explicitly supplied JSON file or stdin, limited to 4 MiB of
UTF-8 bytes. Use newly made fixtures only. Its exact wrapper is:

```json
{
  "schema_version": 1,
  "synthetic": true,
  "producer": "native",
  "signal": "traces",
  "request": {"resourceSpans": []}
}
```

- [Canary-bearing input](../fixtures/native-otlp.synthetic.json): two linked spans,
  mixed-case trace IDs, resource/scope/schema URL canaries, names, status messages,
  a nested prompt attribute, token usage, an event and a link. All data is invented.
- [Expected output](../fixtures/native-otlp.expected.json): a review envelope whose
  `request` member is the rebuilt OTLP `ExportTraceServiceRequest`. The **whole
  review envelope is not an OTLP request body**. `transmitted: false` is literal.
- [Tests](../tests/test_native_otlp.py) are auto-discovered by the existing Docker
  validation workflow. They include golden output, lineage, malformed data,
  duplicate/cycle rejection, byte/count limits, collector routing and CLI redaction.

Inside the committed validation container only, the individual fixture command is:

```sh
python3 application-infrastructure/native_otlp.py \
  application-infrastructure/fixtures/native-otlp.synthetic.json
```

Success prints one complete review envelope to stdout. Failure exits 2 with one
fixed error on stderr and no partial output. There is no write/output-path mode,
no input overwrite and no upload flag. Shell redirection is not an archival or
delivery mechanism. The CLI rejects duplicate JSON keys and non-finite numbers;
all file/parse/contract errors suppress rejected content and paths.

## Exact preserved and discarded semantics

The implementation follows the [OTLP JSON encoding rules](https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding)
and [trace wire schema](https://github.com/open-telemetry/opentelemetry-proto/blob/main/opentelemetry/proto/trace/v1/trace.proto),
with a deliberately narrower synthetic-input profile:

| Field | Boundary behavior |
|---|---|
| `traceId` / `spanId` | Nonzero hex, exactly 32 / 16 characters; case normalized, no rehash/truncation |
| `parentSpanId` | Absent/empty for root; otherwise validated 16-character nonzero hex; retained unchanged except case |
| Start/end | Positive decimal strings in uint64 range; end must not precede start; no float conversion or millisecond rounding |
| Kind/status | Integer enums, not booleans or names; missing means unspecified/unset; message never copied |
| Resource/scope | Rebuilt, with empty resource and fixed synthetic scope; all original metadata and both schema URLs removed |
| Span content | Fixed operation name and diagnostic-role attribute only; attributes, usage, events, links, trace state, flags, dropped counters and unknown fields omitted |

The old `telemetry.py` opaque 32-character canonical IDs are **not OTLP span
IDs**. There is no implicit conversion between those contracts. This prototype
does not preserve source/session mapping, sampling flags or rich-content fidelity;
those gaps remain review gates, not capabilities silently inferred from lineage.
OTLP receivers can also accept JSON numbers for 64-bit values; this prototype
intentionally accepts decimal strings only and rejects zero/unset timestamps.

Limits apply across the request: 128 resource groups, 512 scope groups and 4096
input spans; event/link lists have a 4096-item per-span bound and are discarded.
Equivalent normalized duplicate span keys within a batch collapse with a count;
conflicting replays and same-trace cycles reject the **entire** batch. Keys are
`(traceId, spanId)`, not span ID alone. External parents are retained and counted
because a parent may be remote or in another batch. Zero unresolved parents is
not proof of complete delivery. No cross-batch dedup ledger exists here.

## Future connection contract, still blocked

1. Keep native logs and metrics off; no destinations are selected. Neither the
   plugin nor history importer is input to this adapter. They retain canonical
   ownership and separate content/source consent boundaries.
2. Before source activation, pin and test the installed Codex exporter format and
   implement a separately reviewed source-local receiver/transport. This CLI is
   not wired to Codex and cannot be configured as an endpoint. Never send raw
   native content straight to the cluster merely because gateway filtering exists.
3. After an approved source-local boundary, only the rebuilt `request` may follow
   a separately authorized transport: OTLP/HTTP JSON (`application/json`) to the
   private gateway `/v1/traces`, with verified mTLS. There is no endpoint/config
   generator or credential input in this prototype.
4. Keep the committed gateway's second-pass filter and its **diagnostic-project**
   exporter. Its destination is the explicit self-hosted Langfuse trace endpoint
   `/api/public/otel/v1/traces`, not the gateway's `/v1/traces`. The fixed attribute
   alone does not enforce project isolation; verify the resolved endpoint and
   project credential association without printing either secret.
5. Prove the exact pinned Collector accepts the rebuilt request and inspect the
   complete outbound payload with canaries. Exercise auth rejection, queue loss,
   partial success, retries, cancellation and cross-batch lineage. Current tests
   check offline structure only; they do not start Collector or prove ingestion.
6. Preserve original histories. Retain diagnostics as noncanonical; never fill
   plugin/importer usage gaps with native counts. A marker or syntactically valid
   ID does not establish that data is synthetic, anonymous or approved to export.

Deployment, source enrollment, credentials and content transmission remain
separately blocked; passing future tests will not authorize them.

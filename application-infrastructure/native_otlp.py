#!/usr/bin/env python3
"""Offline native OTLP/JSON boundary prototype. SYNTHETIC FIXTURES ONLY.

Reconstructs an ExportTraceServiceRequest inside a review envelope; never sends
it, reads source histories, discovers files, loads credentials or starts a server.
This is deliberately not wired to Codex. A synthetic marker is not a classifier
or permission to process real content. The CLI reads one explicit file or stdin
and writes only a complete sanitized review envelope after all checks succeed.
"""
import argparse
import json
import re
import sys

MAX_BYTES = 4 * 1024 * 1024
MAX_RESOURCES = 128
MAX_SCOPES = 512
MAX_SPANS = 4096
MAX_UINT64 = 2**64 - 1
ROLE = "diagnostic-noncanonical"


class ContractError(ValueError):
    """All error messages are fixed strings, never rejected input."""


def object_value(value):
    if type(value) is not dict:
        raise ContractError("expected object")
    return value


def list_value(value, limit):
    if type(value) is not list or len(value) > limit:
        raise ContractError("invalid bounded list")
    return value


def binary_id(value, width):
    if (type(value) is not str or not re.fullmatch(r"[0-9a-fA-F]{%d}" % width, value)
            or int(value, 16) == 0):
        raise ContractError("invalid OTLP identifier")
    return value.lower()


def nanoseconds(value):
    # Strict review profile: canonical decimal strings only. OTLP receivers may
    # accept numbers too, but this boundary avoids JSON numeric precision loss.
    if type(value) is not str or not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise ContractError("invalid nanosecond timestamp")
    if int(value) > MAX_UINT64:
        raise ContractError("nanosecond timestamp out of range")
    return value


def enum_value(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ContractError("invalid enum")
    return value


def sanitize_span(raw):
    raw = object_value(raw)
    trace = binary_id(raw.get("traceId"), 32)
    span = binary_id(raw.get("spanId"), 16)
    parent = raw.get("parentSpanId", "")
    if parent != "":
        parent = binary_id(parent, 16)
    if parent == span:
        raise ContractError("self-parent span")
    start = nanoseconds(raw.get("startTimeUnixNano"))
    end = nanoseconds(raw.get("endTimeUnixNano"))
    if int(end) < int(start):
        raise ContractError("invalid span interval")
    status = object_value(raw.get("status", {}))
    # Never copy raw resource/scope identity, names, schema URLs, attributes,
    # status messages, traceState, flags, events, links or dropped counters.
    return {"traceId": trace, "spanId": span, "parentSpanId": parent,
            "name": "diagnostic.operation", "kind": enum_value(raw.get("kind", 0), 5),
            "startTimeUnixNano": start, "endTimeUnixNano": end,
            "status": {"code": enum_value(status.get("code", 0), 2)},
            "attributes": [{"key": "dots.accounting.role", "value": {"stringValue": ROLE}}]}


def inspect_lineage(spans):
    """Reject cycles in this batch; report missing parents, never invent roots.

    Parents may legitimately be in another batch/host. No request-local check
    proves complete trace delivery or cross-batch deduplication.
    """
    checked = set()
    external = 0
    for key, span in spans.items():
        parent = span["parentSpanId"]
        if parent and (span["traceId"], parent) not in spans:
            external += 1
        path = set()
        cursor = key
        while cursor in spans and cursor not in checked:
            if cursor in path:
                raise ContractError("cyclic trace lineage")
            path.add(cursor)
            current = spans[cursor]
            cursor = (current["traceId"], current["parentSpanId"])
        checked.update(path)
    return external


def run(envelope):
    envelope = object_value(envelope)
    if (set(envelope) != {"schema_version", "synthetic", "producer", "signal", "request"}
            or type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1
            or envelope["synthetic"] is not True or envelope["producer"] != "native"
            or envelope["signal"] != "traces"):
        raise ContractError("synthetic native trace review envelope required")
    request = object_value(envelope["request"])
    if "resourceLogs" in request or "resourceMetrics" in request:
        raise ContractError("non-trace signals are disabled")
    resources = list_value(request.get("resourceSpans"), MAX_RESOURCES)
    spans = {}
    scope_count = input_count = duplicate_count = event_count = link_count = 0
    for resource in resources:
        resource = object_value(resource)
        # Unknown resource/scope fields are intentionally never traversed or
        # copied. Validate structural containers and bound the aggregate work.
        scopes = list_value(resource.get("scopeSpans"), MAX_SCOPES)
        scope_count += len(scopes)
        if scope_count > MAX_SCOPES:
            raise ContractError("scope limit exceeded")
        for scope in scopes:
            scope = object_value(scope)
            batch = list_value(scope.get("spans"), MAX_SPANS)
            input_count += len(batch)
            if input_count > MAX_SPANS:
                raise ContractError("span limit exceeded")
            for raw in batch:
                span = sanitize_span(raw)
                event_count += len(list_value(raw.get("events", []), MAX_SPANS))
                link_count += len(list_value(raw.get("links", []), MAX_SPANS))
                key = (span["traceId"], span["spanId"])
                if key in spans:
                    if spans[key] != span:
                        raise ContractError("conflicting span replay")
                    duplicate_count += 1
                else:
                    spans[key] = span
    external_count = inspect_lineage(spans)
    # Flatten resource/scope groups only after scrubbing their identities. Order
    # by binary identity so equivalent batches produce deterministic requests.
    ordered = [spans[key] for key in sorted(spans)]
    output = {"resourceSpans": []}
    if ordered:
        output["resourceSpans"] = [{"resource": {}, "scopeSpans": [
            {"scope": {"name": "dots.synthetic.diagnostics", "version": "1"}, "spans": ordered}]}]
    return {"schema_version": 1, "synthetic": True, "producer": "native", "signal": "traces",
            "project_role": "diagnostic", "canonical": False, "usage": None,
            "request": output,
            "report": {"input_span_count": input_count, "output_span_count": len(spans),
                       "batch_duplicate_count": duplicate_count,
                       "discarded_event_count": event_count, "discarded_link_count": link_count,
                       "external_parent_count": external_count,
                       "cross_batch_delivery_verified": False, "transmitted": False}}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_value):
    raise ContractError("non-finite JSON number")


def decode(content):
    if type(content) is not bytes or len(content) > MAX_BYTES:
        raise ContractError("fixture exceeds byte limit")
    return json.loads(content.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=reject_constant)


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        raise ContractError("invalid command arguments")


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("input", nargs="?", default="-", help="explicit synthetic JSON file, or stdin")
    try:
        args = parser.parse_args(argv)
        if args.input == "-":
            content = sys.stdin.buffer.read(MAX_BYTES + 1)
        else:
            with open(args.input, "rb") as stream:
                content = stream.read(MAX_BYTES + 1)
        result = run(decode(content))
        print(json.dumps(result, sort_keys=True))
    except (ContractError, ValueError, OSError, RecursionError):
        print("synthetic native OTLP contract rejected input", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

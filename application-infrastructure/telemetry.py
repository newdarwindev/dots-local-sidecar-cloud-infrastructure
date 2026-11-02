#!/usr/bin/env python3
"""Offline SYNTHETIC metadata contract harness; not a live exporter/importer.

Only consumes an explicitly supplied JSON envelope. No history discovery, HTTP,
watcher, secret access, durable delivery ledger or source enrollment is included.
Synthetic markers are a test contract, not a security classifier of real data.
"""
import argparse
import datetime as dt
import json
import re
import sys


class ContractError(ValueError):
    """A safe error: never include the rejected input in the message."""


def identifier(value):
    # Opaque canonical IDs, not paths, model names, native IDs or arbitrary labels.
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ContractError("invalid opaque identifier")
    return value


def timestamp(value):
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value):
        raise ContractError("invalid UTC timestamp")
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        raise ContractError("invalid UTC timestamp") from None


def integer(value):
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise ContractError("invalid nonnegative integer")
    return value


def choice(value, allowed):
    if type(value) is not str or value not in allowed:
        raise ContractError("invalid enumerated value")
    return value


def sanitize(event):
    """Rebuild the WHOLE envelope, never copy arbitrary resources/events/body.

    Deliberately omits model/job labels (not reviewed), raw source-native IDs,
    span names, status messages, links and nested event attributes. A real OTLP
    adapter must additionally preserve and verify its binary lineage schema.
    """
    if type(event) is not dict or event.get("synthetic") is not True:
        raise ContractError("synthetic fixture marker required")
    out = {"schema_version": 1, "synthetic": True}
    for key in ("source_id", "host_id", "session_id", "turn_id", "event_id", "trace_id", "span_id"):
        out[key] = identifier(event.get(key))
    out["parent_span_id"] = None if event.get("parent_span_id") is None else identifier(event["parent_span_id"])
    out["producer"] = choice(event.get("producer"), {"plugin", "importer", "native"})
    version = event.get("producer_version")
    if type(version) is not str or not re.fullmatch(r"\d{1,4}\.\d{1,4}\.\d{1,4}", version):
        raise ContractError("invalid producer version")
    out["producer_version"] = version
    out["surface"] = choice(event.get("surface"), {"cli", "exec", "desktop", "synthetic"})
    timestamp(event.get("time"))
    out["time"] = event["time"]
    out["status"] = choice(event.get("status"), {"ok", "error", "cancelled", "unknown"})
    out["duration_ms"] = integer(event.get("duration_ms"))
    usage = event.get("usage")
    if usage is None:
        out["usage"] = None  # unavailable is never silently zero
    else:
        if type(usage) is not dict:
            raise ContractError("invalid usage object")
        out["usage"] = {"kind": choice(usage.get("kind"), {"delta", "cumulative"}),
                        "provenance": choice(usage.get("provenance"), {"reported", "estimated"})}
        for key in ("input", "cached_input", "output"):
            out["usage"][key] = None if usage.get(key) is None else integer(usage[key])
        if (out["usage"]["cached_input"] is not None and out["usage"]["input"] is not None
                and out["usage"]["cached_input"] > out["usage"]["input"]):
            raise ContractError("cached input exceeds total input")
    return out


class SyntheticLedger:
    """In-memory contract simulation. Does NOT confirm delivery or persist state.

    Explicit enrollments establish immutable ownership before events. A replay
    needs the same ledger; restart durability remains a deployment acceptance gate.
    """
    def __init__(self, cutover, enrollments):
        self.cutover = timestamp(cutover)
        self.owners = {}
        self.canonical = {}
        self.diagnostics = {}
        if type(enrollments) is not list or len(enrollments) > 10000:
            raise ContractError("invalid enrollment list")
        for record in enrollments:
            if type(record) is not dict:
                raise ContractError("invalid enrollment")
            key = (identifier(record.get("source_id")), identifier(record.get("session_id")))
            if key in self.owners:
                raise ContractError("duplicate session enrollment")
            producer = choice(record.get("producer"), {"plugin", "importer"})
            start = timestamp(record.get("started"))
            end = None if record.get("ended") is None else timestamp(record["ended"])
            if end is not None and end < start:
                raise ContractError("invalid session interval")
            if producer == "importer" and (end is None or end >= self.cutover):
                raise ContractError("historical session must finish before cutover")
            if producer == "plugin" and start < self.cutover:
                raise ContractError("pre-cutover session requires explicit reconciliation")
            self.owners[key] = producer

    def ingest(self, raw):
        event = sanitize(raw)
        session = (event["source_id"], event["session_id"])
        # Canonical turn/event identity must be mapped before this harness. It
        # cannot infer copied histories or translate producer-native identifiers.
        key = (*session, event["turn_id"], event["event_id"])
        if event["producer"] == "native":
            event["canonical"] = False
            event["project_role"] = "diagnostic"
            event["usage"] = None  # never count native token snapshots
            target = self.diagnostics
        else:
            if self.owners.get(session) != event["producer"]:
                raise ContractError("session not owned by this producer")
            event["canonical"] = True
            event["project_role"] = "canonical"
            target = self.canonical
        if key in target:
            if target[key] != event:
                raise ContractError("conflicting replay requires reconciliation")
            return "duplicate"
        target[key] = event
        return "accepted"

    def report(self):
        # No aggregation of cumulative snapshots or unknown counters.
        return {"synthetic": True, "canonical": list(self.canonical.values()),
                "diagnostics": list(self.diagnostics.values()),
                "canonical_count": len(self.canonical),
                "diagnostic_count": len(self.diagnostics)}


def run(envelope):
    if type(envelope) is not dict or envelope.get("synthetic") is not True:
        raise ContractError("synthetic envelope required")
    events = envelope.get("events")
    if type(events) is not list or len(events) > 10000:
        raise ContractError("invalid bounded events list")
    ledger = SyntheticLedger(envelope.get("cutover"), envelope.get("enrollments"))
    outcomes = [ledger.ingest(event) for event in events]
    return {**ledger.report(), "outcomes": outcomes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default="-", help="explicit synthetic JSON file, or stdin")
    args = parser.parse_args()
    try:
        if args.input == "-":
            content = sys.stdin.read(4 * 1024 * 1024 + 1)
        else:
            with open(args.input, encoding="utf-8") as stream:
                content = stream.read(4 * 1024 * 1024 + 1)
        if len(content) > 4 * 1024 * 1024:
            raise ContractError("fixture exceeds size limit")
        result = run(json.loads(content))
        print(json.dumps(result, sort_keys=True))
    except (ContractError, ValueError, OSError, RecursionError):
        print("synthetic telemetry contract rejected input", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

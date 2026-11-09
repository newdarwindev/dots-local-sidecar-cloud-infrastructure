"""Synthetic only; run in the committed Docker validation workflow."""
import importlib.util
import json
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("telemetry", Path(__file__).parents[1] / "telemetry.py")
t = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(t)


def event(producer="plugin"):
    return dict(synthetic=True, source_id="a" * 32, host_id="b" * 32,
                session_id="c" * 32, turn_id="d" * 32, event_id="e" * 32,
                trace_id="f" * 32, span_id="1" * 32, parent_span_id=None,
                producer=producer, producer_version="1.2.3", surface="synthetic",
                time="2026-11-02T01:00:01Z", status="ok", duration_ms=12,
                usage=dict(kind="delta", provenance="reported", input=10, cached_input=2, output=3))


def enrollment(producer="plugin", **updates):
    out = dict(source_id="a" * 32, session_id="c" * 32, producer=producer,
               started="2026-11-02T01:00:00Z", ended=None)
    out.update(updates)
    return out


def ledger(records=None):
    return t.SyntheticLedger("2026-11-02T00:00:00Z", records if records is not None else [enrollment()])


class TelemetryTests(unittest.TestCase):
    def test_whole_envelope_allowlist(self):
        raw = event()
        canary = "SECRET-CANARY-DO-NOT-EXPORT"
        for key in ("body", "name", "events", "links", "resources", "model", "job_id", "prompt", "path", "error"):
            raw[key] = {"nested": canary}
        raw["usage"]["unknown"] = canary
        result = t.sanitize(raw)
        self.assertNotIn(canary, json.dumps(result))
        self.assertEqual(result["trace_id"], raw["trace_id"])

    def test_nested_smuggling_rejected(self):
        for field in ("status", "source_id", "producer_version", "duration_ms", "time", "surface"):
            raw = event()
            raw[field] = {"secret": "canary"}
            with self.subTest(field=field), self.assertRaises(t.ContractError):
                t.sanitize(raw)

    def test_unknown_usage_not_zero(self):
        raw = event()
        raw.pop("usage")
        self.assertIsNone(t.sanitize(raw)["usage"])
        raw["usage"] = dict(kind="delta", provenance="reported")
        self.assertIsNone(t.sanitize(raw)["usage"]["input"])

    def test_counter_types(self):
        for bad in (-1, True, 1.5, "10", {"secret": 1}, 2**53):
            raw = event()
            raw["usage"]["input"] = bad
            with self.subTest(value=bad), self.assertRaises(t.ContractError):
                t.sanitize(raw)

    def test_replay_and_overlap(self):
        state = ledger()
        self.assertEqual(state.ingest(event()), "accepted")
        self.assertEqual(state.ingest(event()), "duplicate")
        self.assertEqual(state.ingest(event("native")), "accepted")
        self.assertEqual(state.ingest(event("native")), "duplicate")
        with self.assertRaises(t.ContractError):
            state.ingest(event("importer"))
        result = state.report()
        self.assertEqual(result["canonical_count"], 1)
        self.assertEqual(result["diagnostic_count"], 1)
        self.assertIsNone(result["diagnostics"][0]["usage"])
        self.assertEqual(result["canonical"][0]["usage"]["input"], 10)

    def test_history_copied_native_path_is_ignored(self):
        state = ledger()
        raw = event()
        raw["path"] = "/synthetic/original"
        state.ingest(raw)
        raw["path"] = "/synthetic/copy"
        self.assertEqual(state.ingest(raw), "duplicate")

    def test_conflicting_replay_fails(self):
        state = ledger()
        state.ingest(event())
        changed = event()
        changed["usage"]["input"] = 20
        with self.assertRaises(t.ContractError):
            state.ingest(changed)
        self.assertEqual(state.report()["canonical_count"], 1)

    def test_spanning_cutover_held(self):
        for producer in ("plugin", "importer"):
            with self.subTest(producer=producer), self.assertRaises(t.ContractError):
                ledger([enrollment(producer, started="2026-11-01T23:00:00Z", ended="2026-11-02T01:00:00Z")])

    def test_historical_owner(self):
        state = ledger([enrollment("importer", started="2026-11-01T22:00:00Z", ended="2026-11-01T23:00:00Z")])
        raw = event("importer")
        raw["time"] = "2026-11-01T22:00:01Z"
        self.assertEqual(state.ingest(raw), "accepted")
        with self.assertRaises(t.ContractError):
            state.ingest(event("plugin"))

    def test_historical_event_must_be_inside_enrolled_interval(self):
        records = [enrollment("importer", started="2026-11-01T22:00:00Z", ended="2026-11-01T23:00:00Z")]
        for observed in ("2026-11-01T21:59:59Z", "2026-11-01T23:00:01Z", "2026-11-02T01:00:01Z"):
            state = ledger(records)
            raw = event("importer")
            raw["time"] = observed
            with self.subTest(observed=observed), self.assertRaises(t.ContractError):
                state.ingest(raw)
            self.assertEqual(state.report()["canonical_count"], 0)
        for observed in ("2026-11-01T22:00:00Z", "2026-11-01T23:00:00Z"):
            raw = event("importer")
            raw["time"] = observed
            self.assertEqual(ledger(records).ingest(raw), "accepted")

    def test_plugin_enrollment_start_and_close_are_enforced(self):
        state = ledger([enrollment(ended="2026-11-02T01:01:00Z")])
        for observed in ("2026-11-01T23:59:59Z", "2026-11-02T00:59:59Z", "2026-11-02T01:01:01Z"):
            raw = event()
            raw["time"] = observed
            with self.subTest(observed=observed), self.assertRaises(t.ContractError):
                state.ingest(raw)
            self.assertEqual(state.report()["canonical_count"], 0)
        raw = event()
        raw["time"] = "2026-11-02T01:00:00Z"
        self.assertEqual(state.ingest(raw), "accepted")
        raw = event()
        raw.update(time="2026-11-02T01:01:00Z", event_id="2" * 32, status="cancelled")
        self.assertEqual(state.ingest(raw), "accepted")
        # Resume after a closed interval cannot silently extend enrollment.
        raw.update(time="2026-11-02T01:01:01Z", event_id="3" * 32)
        with self.assertRaises(t.ContractError):
            state.ingest(raw)
        self.assertEqual(state.report()["canonical_count"], 2)

    def test_multiple_generations_in_turn_are_not_inferred_totals(self):
        state = ledger()
        state.ingest(event())
        second = event()
        second.update(event_id="2" * 32, span_id="3" * 32)
        state.ingest(second)
        self.assertEqual(state.report()["canonical_count"], 2)
        self.assertNotIn("total_tokens", state.report())

    def test_duplicate_enrollment_rejected(self):
        with self.assertRaises(t.ContractError):
            ledger([enrollment(), enrollment()])

    def test_unenrolled_native_diagnostic_only(self):
        state = ledger([])
        state.ingest(event("native"))
        self.assertEqual(state.report()["canonical_count"], 0)
        with self.assertRaises(t.ContractError):
            state.ingest(event())

    def test_cumulative_preserved_not_summed(self):
        state = ledger()
        for i in range(2):
            raw = event()
            raw["event_id"] = str(i + 2) * 32
            raw["usage"]["kind"] = "cumulative"
            state.ingest(raw)
        self.assertNotIn("total_tokens", state.report())
        self.assertEqual([e["usage"]["kind"] for e in state.report()["canonical"]], ["cumulative"] * 2)

    def test_two_turn_child_cancel(self):
        state = ledger()
        state.ingest(event())
        child = event()
        child.update(turn_id="2" * 32, event_id="3" * 32, parent_span_id="1" * 32, span_id="4" * 32, status="cancelled")
        state.ingest(child)
        self.assertEqual(state.report()["canonical_count"], 2)
        self.assertEqual(state.report()["canonical"][1]["parent_span_id"], "1" * 32)

    def test_real_content_disabled(self):
        raw = event()
        raw["synthetic"] = False
        with self.assertRaises(t.ContractError):
            t.sanitize(raw)
        with self.assertRaises(t.ContractError):
            t.run({"events": [event()]})

    def test_envelope_run(self):
        result = t.run(dict(synthetic=True, cutover="2026-11-02T00:00:00Z", enrollments=[enrollment()], events=[event(), event()]))
        self.assertEqual(result["outcomes"], ["accepted", "duplicate"])


if __name__ == "__main__":
    unittest.main()

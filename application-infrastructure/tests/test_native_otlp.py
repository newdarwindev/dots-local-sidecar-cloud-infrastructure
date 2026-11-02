"""Synthetic only. Authoring is not a pass; run via committed Docker validation."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("native_otlp", ROOT / "native_otlp.py")
n = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(n)
CANARY = "SYNTHETIC-OTLP-CANARY-NOT-A-SECRET"


def fixture():
    return json.loads((ROOT / "fixtures/native-otlp.synthetic.json").read_text())


def spans(envelope):
    return envelope["request"]["resourceSpans"][0]["scopeSpans"][0]["spans"]


class NativeOtlpTests(unittest.TestCase):
    def test_golden_fixture_whole_envelope_and_lineage(self):
        before = fixture()
        original = copy.deepcopy(before)
        result = n.run(before)
        expected = json.loads((ROOT / "fixtures/native-otlp.expected.json").read_text())
        self.assertEqual(result, expected)
        self.assertEqual(before, original)
        self.assertNotIn(CANARY, json.dumps(result))
        self.assertNotIn("gen_ai", json.dumps(result))
        self.assertFalse(result["canonical"])
        self.assertIsNone(result["usage"])
        self.assertEqual(spans(result)[1]["parentSpanId"], spans(result)[0]["spanId"])

    def test_minimal_emitted_shape(self):
        result = n.run(fixture())
        resource = result["request"]["resourceSpans"][0]
        self.assertEqual(set(resource), {"resource", "scopeSpans"})
        self.assertEqual(resource["resource"], {})
        scope = resource["scopeSpans"][0]
        self.assertEqual(set(scope), {"scope", "spans"})
        self.assertEqual(set(scope["scope"]), {"name", "version"})
        for span in scope["spans"]:
            self.assertEqual(set(span), {"traceId", "spanId", "parentSpanId", "name", "kind",
                                         "startTimeUnixNano", "endTimeUnixNano", "status", "attributes"})
            self.assertEqual(set(span["status"]), {"code"})
            self.assertEqual(span["attributes"], [{"key": "dots.accounting.role",
                                                  "value": {"stringValue": n.ROLE}}])

    def test_wrapper_fails_closed(self):
        for field, bad in (("schema_version", True), ("schema_version", 2), ("synthetic", False),
                           ("producer", "plugin"), ("producer", "importer"), ("signal", "logs"),
                           ("signal", "metrics"), ("request", [])):
            raw = fixture()
            raw[field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(n.ContractError):
                n.run(raw)
        raw = fixture()
        raw["endpoint"] = "https://example.invalid"
        with self.assertRaises(n.ContractError):
            n.run(raw)
        for field in ("resourceLogs", "resourceMetrics"):
            raw = fixture()
            raw["request"][field] = []
            with self.subTest(field=field), self.assertRaises(n.ContractError):
                n.run(raw)

    def test_identity_width_zero_type_and_nonhex_rejected(self):
        for field, width in (("traceId", 32), ("spanId", 16), ("parentSpanId", 16)):
            for value in ("0" * width, "f" * (width - 1), "f" * (width + 1), "z" * width,
                          True, 1, None, [], {}, "a/b", " YWJjZA== "):
                raw = fixture()
                spans(raw)[0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(n.ContractError):
                    n.run(raw)
        raw = fixture()
        spans(raw)[0]["spanId"] = "1" * 32  # synthetic ledger IDs are NOT OTLP span IDs
        with self.assertRaises(n.ContractError):
            n.run(raw)

    def test_empty_root_and_case_normalization(self):
        raw = fixture()
        spans(raw)[0]["spanId"] = "B" * 16
        spans(raw)[0]["parentSpanId"] = ""
        spans(raw)[1]["parentSpanId"] = "b" * 16
        result = n.run(raw)
        by_id = {s["spanId"]: s for s in spans(result)}
        self.assertEqual(by_id["b" * 16]["parentSpanId"], "")
        self.assertEqual(by_id["2" * 16]["parentSpanId"], "b" * 16)
        self.assertEqual(result["report"]["external_parent_count"], 0)

    def test_timestamp_integer_precision_bounds_and_order(self):
        for field in ("startTimeUnixNano", "endTimeUnixNano"):
            for bad in (True, 1, 1.5, "0", "-1", "01", "1.5", "1e9", " 1", "1 ",
                        str(2**64), "9" * 100, None, [], {}):
                raw = fixture()
                spans(raw)[0][field] = bad
                with self.subTest(field=field, bad=bad), self.assertRaises(n.ContractError):
                    n.run(raw)
        raw = fixture()
        spans(raw)[0].update(startTimeUnixNano=str(n.MAX_UINT64), endTimeUnixNano=str(n.MAX_UINT64))
        self.assertEqual(spans(n.run(raw))[0]["startTimeUnixNano"], str(n.MAX_UINT64))
        spans(raw)[0]["endTimeUnixNano"] = "1"
        with self.assertRaises(n.ContractError):
            n.run(raw)

    def test_typed_enums_and_status(self):
        for field, maximum in (("kind", 5), ("code", 2)):
            for bad in (True, False, -1, maximum + 1, "1", 1.0, None, {}, []):
                raw = fixture()
                target = spans(raw)[0] if field == "kind" else spans(raw)[0]["status"]
                target[field] = bad
                with self.subTest(field=field, bad=bad), self.assertRaises(n.ContractError):
                    n.run(raw)
        raw = fixture()
        spans(raw)[0]["status"] = CANARY
        with self.assertRaises(n.ContractError):
            n.run(raw)
        spans(raw)[0].pop("status")
        spans(raw)[0].pop("kind")
        self.assertEqual(spans(n.run(raw))[0]["status"], {"code": 0})
        self.assertEqual(spans(n.run(raw))[0]["kind"], 0)

    def test_duplicate_replay_after_normalization_and_conflict(self):
        raw = fixture()
        duplicate = copy.deepcopy(spans(raw)[0])
        duplicate["traceId"] = duplicate["traceId"].lower()
        duplicate["name"] = "different unexported name"
        spans(raw).append(duplicate)
        result = n.run(raw)
        self.assertEqual(result["report"]["batch_duplicate_count"], 1)
        self.assertEqual(result["report"]["output_span_count"], 2)
        duplicate["endTimeUnixNano"] = "1793577600300000000"
        with self.assertRaises(n.ContractError):
            n.run(raw)

    def test_self_parent_and_cycle_after_normalization(self):
        raw = fixture()
        spans(raw)[0].update(spanId="B" * 16, parentSpanId="b" * 16)
        with self.assertRaises(n.ContractError):
            n.run(raw)
        raw = fixture()
        spans(raw)[0]["parentSpanId"] = spans(raw)[1]["spanId"]
        with self.assertRaises(n.ContractError):
            n.run(raw)

    def test_external_parent_not_rewritten_as_root(self):
        raw = fixture()
        spans(raw)[0]["parentSpanId"] = "c" * 16
        result = n.run(raw)
        self.assertEqual(spans(result)[0]["parentSpanId"], "c" * 16)
        self.assertEqual(result["report"]["external_parent_count"], 1)
        self.assertFalse(result["report"]["cross_batch_delivery_verified"])

    def test_identity_is_scoped_by_trace_not_only_span(self):
        raw = fixture()
        second_trace = copy.deepcopy(spans(raw)[0])
        second_trace["traceId"] = "f" * 32
        spans(raw).append(second_trace)
        result = n.run(raw)
        self.assertEqual(result["report"]["output_span_count"], 3)
        self.assertEqual(result["report"]["batch_duplicate_count"], 0)

    def test_reordering_and_resource_scope_flattening(self):
        raw = fixture()
        first = n.run(raw)["request"]
        resource = raw["request"]["resourceSpans"][0]
        child = spans(raw).pop()
        resource["scopeSpans"].append({"scope": {"name": CANARY}, "spans": [child]})
        raw["request"]["resourceSpans"].append({"scopeSpans": []})
        resource["scopeSpans"].reverse()
        self.assertEqual(n.run(raw)["request"], first)

    def test_sanitized_request_is_stable_when_rewrapped(self):
        raw = fixture()
        result = n.run(raw)
        raw["request"] = result["request"]
        self.assertEqual(n.run(raw)["request"], result["request"])

    def test_collector_contract_keeps_diagnostics_isolated(self):
        import yaml
        values = yaml.safe_load((ROOT / "values/collector.yaml").read_text())
        config = values["alternateConfig"]
        self.assertEqual(set(config["service"]["pipelines"]), {"traces"})
        pipeline = config["service"]["pipelines"]["traces"]
        self.assertEqual(pipeline["exporters"], ["otlphttp/diagnostics"])
        self.assertEqual(set(config["exporters"]), {"otlphttp/diagnostics"})
        self.assertEqual(config["exporters"]["otlphttp/diagnostics"]["traces_endpoint"],
                         "${env:LANGFUSE_DIAGNOSTIC_TRACES_ENDPOINT}")
        self.assertEqual(pipeline["processors"], ["memory_limiter", "filter/envelope",
                                                 "transform/privacy", "batch"])
        self.assertTrue(config["receivers"]["otlp"]["protocols"]["http"]["tls"]["client_ca_file"])
        statements = config["processors"]["transform/privacy"]["trace_statements"][0]["statements"]
        self.assertIn('keep_keys(span.attributes, [])', statements)
        self.assertIn('set(span.attributes["dots.accounting.role"], "diagnostic-noncanonical")', statements)

    def test_missing_or_malformed_nested_containers(self):
        for field in ("resourceSpans", "scopeSpans", "spans", "events", "links"):
            for bad in (None, {}, CANARY, 1):
                raw = fixture()
                owners = {"resourceSpans": raw["request"],
                          "scopeSpans": raw["request"]["resourceSpans"][0],
                          "spans": raw["request"]["resourceSpans"][0]["scopeSpans"][0],
                          "events": spans(raw)[0], "links": spans(raw)[0]}
                owners[field][field] = bad
                with self.subTest(field=field, bad=bad), self.assertRaises(n.ContractError):
                    n.run(raw)
        for field in ("resourceSpans", "scopeSpans", "spans"):
            raw = fixture()
            owners = {"resourceSpans": raw["request"],
                      "scopeSpans": raw["request"]["resourceSpans"][0],
                      "spans": raw["request"]["resourceSpans"][0]["scopeSpans"][0]}
            owners[field][field] = [None]
            with self.subTest(field=field), self.assertRaises(n.ContractError):
                n.run(raw)

    def test_bounds_apply_across_containers(self):
        raw = fixture()
        raw["request"]["resourceSpans"] *= n.MAX_RESOURCES + 1
        with self.assertRaises(n.ContractError):
            n.run(raw)
        raw = fixture()
        raw["request"]["resourceSpans"] *= 2
        with patch.object(n, "MAX_SCOPES", 1), self.assertRaises(n.ContractError):
            n.run(raw)
        with patch.object(n, "MAX_SPANS", 3), self.assertRaises(n.ContractError):
            n.run(raw)

    def test_empty_request_is_not_claimed_delivered(self):
        raw = fixture()
        raw["request"] = {"resourceSpans": []}
        result = n.run(raw)
        self.assertEqual(result["request"], {"resourceSpans": []})
        self.assertEqual(result["report"]["output_span_count"], 0)
        self.assertFalse(result["report"]["transmitted"])

    def test_json_duplicate_keys_nonfinite_and_byte_limit(self):
        for raw in (b'{"synthetic":false,"synthetic":true}', b'{"a":{"b":1,"b":2}}',
                    b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}',
                    b'\xff', b'['):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                n.decode(raw)
        with patch.object(n, "MAX_BYTES", 4), self.assertRaises(n.ContractError):
            n.decode(b'"\xc3\xa9" ')

    def test_cli_golden_and_no_input_modification(self):
        path = ROOT / "fixtures/native-otlp.synthetic.json"
        before = path.read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "native_otlp.py"), str(path)],
                                capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout), n.run(fixture()))
        self.assertEqual(result.stderr, b"")
        self.assertEqual(before, path.read_bytes())

    def test_cli_rejections_are_atomic_and_redacted(self):
        for command, content in (([], b'{"secret":"' + CANARY.encode() + b'"}'),
                                 (["--" + CANARY], b""),
                                 (["/missing/" + CANARY], b"")):
            result = subprocess.run([sys.executable, str(ROOT / "native_otlp.py"), *command],
                                    input=content, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(result.stderr, b"synthetic native OTLP contract rejected input\n")


if __name__ == "__main__":
    unittest.main()

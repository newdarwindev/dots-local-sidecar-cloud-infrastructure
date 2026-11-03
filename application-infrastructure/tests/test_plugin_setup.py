"""Synthetic configuration tests; run only in the committed Docker workflow."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/plugin_setup.py"
SPEC = importlib.util.spec_from_file_location("plugin_setup", SCRIPT)
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)
CANARY = "SYNTHETIC-CONFIG-CANARY"


def fixture(command="check"):
    return json.loads((ROOT / f"fixtures/plugin-{command}.synthetic.json").read_text())


class PluginSetupTests(unittest.TestCase):
    def test_render_real_vendor_shape_never_enabled_and_no_keys(self):
        raw = fixture("render")
        before = copy.deepcopy(raw)
        result = p.render(raw)
        self.assertEqual(result, fixture()["layers"]["project"])
        self.assertEqual(raw, before)
        self.assertEqual(set(result), p.FIELDS)
        for key in p.BOOL_FIELDS:
            self.assertIs(result[key], False)
        self.assertNotIn("public_key", result)
        self.assertNotIn("secret_key", result)

    def test_check_matches_render_without_activation_claim(self):
        raw = fixture()
        before = copy.deepcopy(raw)
        result = p.check(raw)
        self.assertEqual(result["effective"], p.render(fixture("render")))
        self.assertEqual(result["sources"], dict.fromkeys(p.FIELDS, "project"))
        self.assertTrue(result["setup_valid"])
        for key in ("activation_allowed", "live_configuration_verified", "credentials_verified"):
            self.assertIs(result[key], False)
        self.assertEqual(raw, before)

    def test_source_contract_commit_is_explicit(self):
        lock = json.loads((ROOT / "contracts/codex-plugin.lock.json").read_text())
        self.assertEqual(p.UPSTREAM_COMMIT, lock["source"]["commit"])
        self.assertIn(p.UPSTREAM_COMMIT, lock["source"]["url"])
        self.assertFalse(lock["runtimeCompatibilityVerified"])

    def test_precedence_and_special_scoped_endpoint_alias(self):
        raw = fixture()
        expected = raw["target"]
        raw["layers"]["global"] = {"max_history_chars": 30000}
        raw["layers"]["env"] = {
            "LANGFUSE_CODEX_BASE_URL": "HTTPS://LANGFUSE.EXAMPLE.INVALID:443/",
            "LANGFUSE_BASE_URL": expected["base_url"],
            "LANGFUSE_CODEX_USER_ID": expected["user_id"],
            "LANGFUSE_CODEX_MAX_HISTORY_CHARS": "20000",
            "TRACE_TO_LANGFUSE": " OFF ",
        }
        result = p.check(raw)
        self.assertEqual(result["effective"]["base_url"], expected["base_url"])
        self.assertEqual(result["sources"]["base_url"], "env:LANGFUSE_CODEX_BASE_URL")
        self.assertEqual(result["sources"]["max_history_chars"], "env:LANGFUSE_CODEX_MAX_HISTORY_CHARS")
        self.assertEqual(result["sources"]["skill_tags"], "project")
        self.assertFalse(result["effective"]["enabled"])
        # Alias precedence must not depend on JSON object key order.
        raw["layers"]["env"] = dict(reversed(list(raw["layers"]["env"].items())))
        self.assertEqual(p.check(raw), result)

    def test_no_layers_cannot_inherit_hosted_url_or_auth_email(self):
        raw = fixture()
        raw["layers"]["project"] = {}
        with self.assertRaises(p.SetupError):
            p.check(raw)
        for field in ("base_url", "user_id", "skill_tags"):
            raw = fixture()
            del raw["layers"]["project"][field]
            with self.subTest(field=field), self.assertRaises(p.SetupError):
                p.check(raw)

    def test_activation_even_when_shadowed_is_rejected(self):
        for layer in ("global", "project", "env"):
            for field in p.BOOL_FIELDS:
                raw = fixture()
                key = field if layer != "env" else next(
                    name for name, candidate in p.ENV_FIELDS.items() if candidate == field)
                raw["layers"][layer][key] = "true" if layer == "env" else True
                with self.subTest(layer=layer, field=field), self.assertRaises(p.SetupError):
                    p.check(raw)
        raw = fixture()
        raw["layers"]["global"]["enabled"] = True
        raw["layers"]["env"]["TRACE_TO_LANGFUSE"] = "false"
        with self.assertRaises(p.SetupError):
            p.check(raw)

    def test_shadowed_url_and_identity_conflicts_are_rejected(self):
        for layer in ("global", "project", "env"):
            for field, value in (("base_url", "https://other.example.invalid"), ("user_id", "b" * 32)):
                raw = fixture()
                key = "LANGFUSE_CODEX_" + field.upper() if layer == "env" else field
                raw["layers"][layer][key] = value
                with self.subTest(layer=layer, field=field), self.assertRaises(p.SetupError):
                    p.check(raw)
        raw = fixture()
        raw["layers"]["env"] = {"LANGFUSE_BASE_URL": "https://cloud.langfuse.com",
                                "LANGFUSE_CODEX_BASE_URL": raw["target"]["base_url"]}
        with self.assertRaises(p.SetupError):
            p.check(raw)

    def test_url_canonicalization_and_explicit_nondefault_port(self):
        for raw, expected in (("HTTPS://LANGFUSE.EXAMPLE.INVALID:443/", "https://langfuse.example.invalid"),
                              ("https://lf.example.invalid:8443/", "https://lf.example.invalid:8443")):
            with self.subTest(raw=raw):
                self.assertEqual(p.origin(raw), expected)

    def test_unsafe_or_ambiguous_urls_fail_closed(self):
        bad = ["http://lf.example.invalid", "https://cloud.langfuse.com", "https://US.CLOUD.LANGFUSE.COM:443/",
               "https://jp.cloud.langfuse.com", "https://langfuse.com", "https://hipaa.cloud.langfuse.com",
               "https://cloud.langfuse.com.", "https://lf.example.invalid/path", "https://lf.example.invalid//",
               "https://lf.example.invalid?", "https://lf.example.invalid#", "https://lf.example.invalid?x=1",
               "https://user:pass@lf.example.invalid", "https://lf.example.invalid%2f.evil.invalid",
               "https://lf.example.invalid\\evil.invalid", " https://lf.example.invalid",
               "https://lf.example.invalid\n", "https://lf.examp\tle.invalid", "https://lf.example.invalid\x00",
               "https://lf.example.invalid\x7f", "https://lf.example.invalid:0443", "https://lf.example.invalid:",
               "https://lf.example.invalid:0", "https://lf.example.invalid:65536", "https://lf.example.invalid:-1",
               "https://127.0.0.1", "https://0x7f.0x1", "https://0x7f000001", "https://0177.0x1",
               "https://127.0.0.01", "https://lf.0x", "https://[::1]", "https://localhost", "https://lf.exämple.invalid",
               "https://xn--lf-9ia.example.invalid", "https://lf..invalid", "https://-lf.example.invalid",
               "https://lf.example-.invalid", "https://lf.123", "https://" + "a" * 64 + ".invalid",
               True, None, {}, []]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(p.SetupError):
                p.origin(value)

    def test_identity_is_required_opaque_and_nonempty_in_every_layer(self):
        for value in ("", "a@example.invalid", "0" * 32, "A" * 32, "a" * 31, "a" * 33,
                      "name", True, None, {}, []):
            raw = fixture()
            raw["layers"]["global"]["user_id"] = value
            with self.subTest(value=value), self.assertRaises(p.SetupError):
                p.check(raw)

    def test_history_limit_bounded_not_unlimited_and_effective_match(self):
        for value in (0, -1, True, 1.5, "20000", 200001, None):
            raw = fixture("render")
            raw["target"]["max_history_chars"] = value
            with self.subTest(value=value), self.assertRaises(p.SetupError):
                p.render(raw)
        for value in ("0", "200001", "2e4", "0x4e20", "020000", " 20000", "20000.0", "NaN", ""):
            raw = fixture()
            raw["layers"]["env"]["LANGFUSE_CODEX_MAX_HISTORY_CHARS"] = value
            with self.subTest(value=value), self.assertRaises(p.SetupError):
                p.check(raw)
        raw = fixture()
        raw["layers"]["env"]["LANGFUSE_CODEX_MAX_HISTORY_CHARS"] = "30000"
        with self.assertRaises(p.SetupError):
            p.check(raw)

    def test_unknown_credential_and_unsupported_aliases_rejected(self):
        for layer, keys in (("global", ("public_key", "secret_key", "environment", "trace_seed", "other")),
                            ("project", ("public_key", "secret_key", "environment", "trace_seed", "other")),
                            ("env", ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_CODEX_SECRET_KEY", "LANGFUSE_CODEX_ENABLED",
                                     "LANGFUSE_USER_ID", "LANGFUSE_SKILL_TAGS", "LANGFUSE_CODEX_ENVIRONMENT",
                                     "LANGFUSE_TRACING_ENVIRONMENT", "CODEX_HOME", "HOME", "OTHER"))):
            for key in keys:
                for value in ("", CANARY):
                    raw = fixture()
                    raw["layers"][layer][key] = value
                    with self.subTest(layer=layer, key=key), self.assertRaises(p.SetupError) as failure:
                        p.check(raw)
                    self.assertNotIn(CANARY, str(failure.exception))
                    self.assertNotIn(key, str(failure.exception))

    def test_empty_metadata_and_tags_only(self):
        raw = fixture()
        raw["layers"]["env"].update(LANGFUSE_CODEX_TAGS="[]", LANGFUSE_CODEX_METADATA="{}")
        result = p.check(raw)
        self.assertEqual(result["effective"]["tags"], [])
        self.assertEqual(result["effective"]["metadata"], {})
        for key, values in (("LANGFUSE_CODEX_TAGS", (CANARY, '["tag"]', "", "null", "{}")),
                            ("LANGFUSE_CODEX_METADATA", ('{"private":"' + CANARY + '"}', "", "null", "[]"))):
            for value in values:
                candidate = fixture()
                candidate["layers"]["env"][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(p.SetupError):
                    p.check(candidate)

    def test_strict_file_boolean_subset_and_env_aliases(self):
        for value in ("false", 0, None, [], {}):
            raw = fixture()
            raw["layers"]["global"]["enabled"] = value
            with self.subTest(value=value), self.assertRaises(p.SetupError):
                p.check(raw)
        for value in ("0", "false", "no", "off", " FALSE "):
            raw = fixture()
            raw["layers"]["env"]["TRACE_TO_LANGFUSE"] = value
            self.assertFalse(p.check(raw)["effective"]["enabled"])
        for value in ("1", "true", "yes", "on", "maybe", "", False, None):
            raw = fixture()
            raw["layers"]["env"]["TRACE_TO_LANGFUSE"] = value
            with self.subTest(value=value), self.assertRaises(p.SetupError):
                p.check(raw)

    def test_strict_plan_and_layers(self):
        for field, value in (("schema_version", True), ("schema_version", 2), ("target", []), ("layers", [])):
            raw = fixture()
            raw[field] = value
            with self.subTest(field=field), self.assertRaises(p.SetupError):
                p.check(raw)
        for layer in ("global", "project", "env"):
            raw = fixture()
            raw["layers"][layer] = None
            with self.subTest(layer=layer), self.assertRaises(p.SetupError):
                p.check(raw)
        raw = fixture()
        raw["layers"]["additional"] = {}
        with self.assertRaises(p.SetupError):
            p.check(raw)

    def test_no_ambient_environment_home_or_file_reads_in_pure_functions(self):
        raw = fixture()
        plan = fixture("render")
        with patch("os.getenv", side_effect=AssertionError("ambient env read")), \
             patch("os.environ", {}), patch("pathlib.Path.home", side_effect=AssertionError("home read")), \
             patch("builtins.open", side_effect=AssertionError("unrequested file read")):
            self.assertFalse(p.render(plan)["enabled"])
            self.assertFalse(p.check(raw)["effective"]["enabled"])

    def test_strict_json_and_byte_limit(self):
        for value in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'\xff', b'{'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                p.decode(value)
        with patch.object(p, "MAX_BYTES", 4), self.assertRaises(p.SetupError):
            p.decode(b'"\xc3\xa9" ')

    def test_cli_ignores_ambient_overrides_and_preserves_file(self):
        for command in ("render", "check"):
            path = ROOT / f"fixtures/plugin-{command}.synthetic.json"
            before = path.read_bytes()
            result = subprocess.run([sys.executable, str(SCRIPT), command, "--config", str(path)],
                                    env={"TRACE_TO_LANGFUSE": "true", "LANGFUSE_BASE_URL": "https://cloud.langfuse.com",
                                         "LANGFUSE_CODEX_SECRET_KEY": CANARY, "HOME": "/unreadable-synthetic-home"},
                                    check=True, capture_output=True)
            expected = p.render(fixture(command)) if command == "render" else p.check(fixture(command))
            self.assertEqual(json.loads(result.stdout), expected)
            self.assertEqual(result.stderr, b"")
            self.assertNotIn(CANARY.encode(), result.stdout)
            self.assertEqual(path.read_bytes(), before)

    def test_cli_invalid_args_and_paths_are_redacted(self):
        for args in (("activate",), ("render", "--config", "/missing/" + CANARY), ("--" + CANARY,)):
            result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(result.stderr, b"plugin setup rejected; no configuration applied\n")


if __name__ == "__main__":
    unittest.main()

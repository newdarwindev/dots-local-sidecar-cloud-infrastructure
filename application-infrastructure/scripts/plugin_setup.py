#!/usr/bin/env python3
"""Render/check a disabled, credential-free Langfuse Codex plugin configuration.

Reads one explicit non-secret JSON plan only. Never reads ambient environment,
Codex config/auth/history, installs a plugin, writes files or contacts a service.
The strict supported subset is matched to the commit in codex-plugin.lock.json;
it rejects ambiguous upstream coercions rather than silently falling back.
Use synthetic fixtures until separately approved source setup is available.
"""
import argparse
import json
import re
import sys
from urllib.parse import urlsplit

UPSTREAM_COMMIT = "e1d02be28e6bacbfe350a1bc1ccf861e54edee17"
MAX_BYTES = 64 * 1024
MAX_HISTORY = 200_000
FIELDS = {"enabled", "base_url", "user_id", "skill_tags", "max_history_chars",
          "debug", "fail_on_error", "tags", "metadata"}
BOOL_FIELDS = {"enabled", "skill_tags", "debug", "fail_on_error"}
ENV_FIELDS = {
    "TRACE_TO_LANGFUSE": "enabled",
    "LANGFUSE_BASE_URL": "base_url",
    "LANGFUSE_CODEX_BASE_URL": "base_url",
    "LANGFUSE_CODEX_USER_ID": "user_id",
    "LANGFUSE_CODEX_SKILL_TAGS": "skill_tags",
    "LANGFUSE_CODEX_MAX_HISTORY_CHARS": "max_history_chars",
    "LANGFUSE_CODEX_DEBUG": "debug",
    "LANGFUSE_CODEX_FAIL_ON_ERROR": "fail_on_error",
    "LANGFUSE_CODEX_TAGS": "tags",
    "LANGFUSE_CODEX_METADATA": "metadata",
}
DEFAULTS = {"enabled": False, "base_url": "https://cloud.langfuse.com",
            "skill_tags": True, "max_history_chars": MAX_HISTORY,
            "debug": False, "fail_on_error": False}


class SetupError(ValueError):
    """Fixed errors only; never interpolate input values, keys or paths."""


def exact_object(value, keys):
    if type(value) is not dict or set(value) != keys:
        raise SetupError("invalid setup object")
    return value


def origin(value):
    """Canonical HTTPS DNS origin; no DNS/private-network or TLS claim."""
    if (type(value) is not str or not value.isascii() or len(value) > 300
            or any(ord(c) <= 32 or ord(c) == 127 for c in value)
            or any(c in value for c in "@%\\?#")
            or not re.fullmatch(r"https://[^/]+/?", value, re.I)):
        raise SetupError("invalid self-hosted HTTPS origin")
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
    except ValueError:
        raise SetupError("invalid self-hosted HTTPS origin") from None
    if (not host or len(host) > 253 or host.endswith(".") or ":" in host
            or host == "langfuse.com" or host.endswith(".langfuse.com")):
        raise SetupError("invalid self-hosted HTTPS origin")
    labels = host.split(".")
    if len(labels) < 2 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in labels):
        raise SetupError("invalid DNS origin")
    # An ASCII alphabetic final label excludes decimal/octal/hex IPv4 spellings
    # that WHATWG/Node may reinterpret even when Python ipaddress would not.
    # IDNA and custom numeric final labels are outside this narrow profile.
    if not re.fullmatch(r"[a-z]{2,63}", labels[-1]) or any(x.startswith("xn--") for x in labels):
        raise SetupError("unsupported DNS origin")
    if ":" in parts.netloc:
        raw_port = parts.netloc.rsplit(":", 1)[1]
        if port is None or not 1 <= port <= 65535 or raw_port != str(port):
            raise SetupError("invalid origin port")
    return "https://" + host + (":" + str(port) if port not in (None, 443) else "")


def pseudonym(value):
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{32}", value) or value == "0" * 32:
        raise SetupError("explicit opaque user identity required")
    return value


def history_limit(value):
    if type(value) is not int or not 1 <= value <= MAX_HISTORY:
        raise SetupError("bounded history limit required")
    return value


def target(value):
    exact_object(value, {"base_url", "user_id", "max_history_chars"})
    return {"base_url": origin(value["base_url"]), "user_id": pseudonym(value["user_id"]),
            "max_history_chars": history_limit(value["max_history_chars"])}


def normalize(field, value, expected, environment=False):
    if environment:
        if type(value) is not str or len(value) > 1024:
            raise SetupError("invalid explicit environment value")
        if field in BOOL_FIELDS:
            lowered = value.strip().lower()
            if lowered not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
                raise SetupError("ambiguous boolean override")
            value = lowered in {"1", "true", "yes", "on"}
        elif field == "max_history_chars":
            if not re.fullmatch(r"[1-9][0-9]{0,5}", value):
                raise SetupError("ambiguous history override")
            value = int(value)
        elif field in {"tags", "metadata"}:
            # Only empty JSON containers are allowed; no CSV/coercion fallback.
            value = decode(value.encode("utf-8"))
    if field in BOOL_FIELDS:
        if type(value) is not bool or value is not False:
            raise SetupError("activation or unreviewed capture option prohibited")
        return False
    if field == "base_url":
        value = origin(value)
        if value != expected["base_url"]:
            raise SetupError("endpoint override differs from selected origin")
        return value
    if field == "user_id":
        value = pseudonym(value)
        if value != expected["user_id"]:
            raise SetupError("identity override differs from selected pseudonym")
        return value
    if field == "max_history_chars":
        return history_limit(value)
    if field == "tags" and type(value) is list and not value:
        return []
    if field == "metadata" and type(value) is dict and not value:
        return {}
    raise SetupError("unreviewed field or capture metadata")


def validate_plan(value, checking=False):
    keys = {"schema_version", "target", "layers"} if checking else {"schema_version", "target"}
    exact_object(value, keys)
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise SetupError("unsupported setup schema")
    return target(value["target"])


def render(value):
    expected = validate_plan(value)
    # This is a real vendor file shape, never an enabled config or placeholder key.
    return {"enabled": False, **expected, "skill_tags": False, "debug": False,
            "fail_on_error": False, "tags": [], "metadata": {}}


def check(value):
    expected = validate_plan(value, checking=True)
    layers = exact_object(value["layers"], {"global", "project", "env"})
    effective = dict(DEFAULTS)
    sources = {key: "defaults" for key in effective}
    for name in ("global", "project", "env"):
        layer = layers[name]
        allowed = ENV_FIELDS if name == "env" else FIELDS
        if type(layer) is not dict or set(layer) - set(allowed):
            raise SetupError("unsupported or credential-bearing configuration")
        # Validate every value before selecting winners, including shadowed
        # activation/cloud/identity values. This is stricter than the plugin.
        normalized = {}
        for key, item in layer.items():
            field = ENV_FIELDS[key] if name == "env" else key
            normalized[key] = normalize(field, item, expected, environment=name == "env")
        for key, item in normalized.items():
            field = ENV_FIELDS[key] if name == "env" else key
            if name == "env" and key == "LANGFUSE_BASE_URL" and "LANGFUSE_CODEX_BASE_URL" in layer:
                continue
            effective[field] = item
            sources[field] = "env:" + key if name == "env" else name
    # Explicit URL and identity prevent hosted/email defaults. Re-normalizing
    # final defaults also rejects inherited skill-tag capture. No auth file read.
    for field, item in effective.items():
        normalize(field, item, expected)
    if effective.get("user_id") != expected["user_id"]:
        raise SetupError("explicit user identity missing")
    if effective["max_history_chars"] != expected["max_history_chars"]:
        raise SetupError("effective history limit differs from selected limit")
    return {"schema_version": 1, "setup_valid": True, "activation_allowed": False,
            "live_configuration_verified": False, "credentials_verified": False,
            "upstream_commit": UPSTREAM_COMMIT, "effective": effective, "sources": sources}


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SetupError("duplicate JSON key")
        result[key] = value
    return result


def nonfinite(_value):
    raise SetupError("non-finite JSON number")


def decode(content):
    if type(content) is not bytes or len(content) > MAX_BYTES:
        raise SetupError("setup input exceeds byte limit")
    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=no_duplicates, parse_constant=nonfinite)
    except json.JSONDecodeError:
        raise SetupError("invalid JSON input") from None


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        raise SetupError("invalid command arguments")


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument("command", choices=("render", "check"))
    parser.add_argument("--config", required=True, help="explicit non-secret JSON plan; no discovery")
    try:
        args = parser.parse_args(argv)
        with open(args.config, "rb") as stream:
            value = decode(stream.read(MAX_BYTES + 1))
        result = render(value) if args.command == "render" else check(value)
        print(json.dumps(result, indent=2, sort_keys=True))
    except (SetupError, ValueError, OSError, RecursionError):
        print("plugin setup rejected; no configuration applied", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

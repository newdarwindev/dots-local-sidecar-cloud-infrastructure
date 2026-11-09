"""Nonsecret fixed native event processors; no live configuration or credentials."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('native_event_policy', Path(__file__).resolve().parents[1] / 'native_event_policy.py')
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


def render(config):
    if config != {} or not isinstance(config, dict):
        raise ValueError('Native event render accepts only an empty object')
    return {'edge_processors': POLICY.processors(), 'central_processors': POLICY.central_processors()}

"""Strict nonsecret upstream native-message renderer; no deployment or live reads."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('native_message_policy', Path(__file__).resolve().parents[1] / 'native_message_policy.py')
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


def render(config):
    if not isinstance(config, dict) or set(config) != {'enrolled', 'denied'}:
        raise ValueError('Exact native enrollment fields required')
    return POLICY.render(config['enrolled'], config['denied'])

"""Strict nonsecret render adapter; no filesystem inputs beyond committed policy code."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('conversation_policy', Path(__file__).resolve().parents[1] / 'conversation_policy.py')
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


def render(config):
    if not isinstance(config, dict) or set(config) != {'enrolled', 'denied', 'generations'}:
        raise ValueError('Exact conversation enrollment fields required')
    return POLICY.render(config['enrolled'], config['denied'], generations=config['generations'])

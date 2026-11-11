"""Strict nonsecret render adapter; no filesystem inputs beyond committed policy code."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('conversation_policy', Path(__file__).resolve().parents[1] / 'conversation_policy.py')
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


def render(config):
    required = {'enrolled', 'denied', 'generations'}
    if not isinstance(config, dict) or set(config) not in (required, required | {'future_after_ns'}):
        raise ValueError('Exact conversation enrollment fields required')
    return POLICY.render(config['enrolled'], config['denied'], generations=config['generations'],
                         future_after_ns=config.get('future_after_ns'))

#!/usr/bin/env python3
"""Bounded stdin-to-stdout setup review; fixed helpers only, no external actions."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 64 * 1024
ACTIONS = ('cluster-assess', 'cluster-packet', 'plugin-render', 'plugin-check')
ERROR = 'BLOCKED: invalid setup input; no configuration applied.\n'


def helper(name):
    # Names come only from the branches below, never input or CLI arguments.
    path = ROOT / 'application-infrastructure/scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location('setup_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reject_number(_value):
    raise ValueError('only bounded integer configuration fields are supported')


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def review(action, stream):
    if action not in ACTIONS:
        raise ValueError('unsupported setup action')
    content = stream.read(MAX_BYTES + 1)
    if not content or len(content) > MAX_BYTES:
        raise ValueError('input exceeds byte limit or is empty')
    config = json.loads(content.decode('utf-8'), object_pairs_hook=no_duplicates,
                        parse_constant=reject_number, parse_float=reject_number)
    if action.startswith('cluster-'):
        contract = helper('cluster_contract')
        if action == 'cluster-assess':
            return contract.assess(config)
        return {'schemaVersion': 1, 'mode': 'review-only', 'deploymentAllowed': False,
                'documents': contract.packet_documents(config)}
    plugin = helper('plugin_setup')
    return plugin.render(config) if action == 'plugin-render' else plugin.check(config)


def main(action, stdin=None, stdout=None, stderr=None):
    stdin = sys.stdin.buffer if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    try:
        result = review(action, stdin)
        # Finish serialization before printing; no partial input/error disclosures.
        output = json.dumps(result, indent=2, allow_nan=False) + '\n'
    except (ValueError, OSError, TypeError, KeyError, RecursionError):
        stderr.write(ERROR)
        return 2
    stdout.write(output)
    return 0

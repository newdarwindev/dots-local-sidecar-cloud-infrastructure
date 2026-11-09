"""Temporary LOCAL-ONLY admission projection; never widen a production gate.

Linked spans are rejected before projection. Consequently absence cannot distinguish
linked input from no input. Exact IDs are diagnostic correlation, not content.
No exporter, receiver, credentials or live activation is supplied by this module.
"""
import json

NAMES = ('codex_cli_rs', 'codex-app-server', 'codex_work_desktop', 'codex_exec')


def processors():
    a = 'span.attributes'
    statements = ['keep_keys(span.attributes, [])',
                  'set(span.name, "codex.admission.diagnostic")',
                  'set(span.trace_state, "")', 'set(span.status.message, "")',
                  'set(span.status.code, STATUS_CODE_UNSET)',
                  f'set({a}["diagnostic.service"], "unknown")',
                  f'set({a}["diagnostic.scope"], "unknown")',
                  f'set({a}["diagnostic.version_match"], false)',
                  f'set({a}["diagnostic.source_match"], false)',
                  f'set({a}["diagnostic.event_count"], Len(span.events))',
                  f'set({a}["diagnostic.link_count"], 0)']
    for name in NAMES:
        literal = json.dumps(name)
        statements += [f'set({a}["diagnostic.service"], {literal}) where resource.attributes["service.name"] == {literal}',
                       f'set({a}["diagnostic.scope"], {literal}) where scope.name == {literal}']
    statements += [f'set({a}["diagnostic.version_match"], true) where resource.attributes["service.version"] == "0.167.0"',
                   f'set({a}["diagnostic.source_match"], true) where {a}["diagnostic.version_match"] == true and {a}["diagnostic.service"] == {a}["diagnostic.scope"] and ContainsValue({json.dumps(NAMES[:3])}, {a}["diagnostic.service"])']
    return {
        'filter/admission-unlinked': {'error_mode': 'propagate', 'traces': {'span': ['Len(span.links) > 0']}},
        'transform/admission-classify': {'error_mode': 'propagate', 'trace_statements': [{'context': 'span', 'statements': statements}]},
        'filter/admission-events': {'error_mode': 'propagate', 'traces': {'spanevent': ['true']}},
        'transform/admission-envelope': {'error_mode': 'propagate', 'trace_statements': [
            {'context': 'resource', 'statements': ['keep_keys(resource.attributes, [])', 'set(resource.schema_url, "")']},
            {'context': 'scope', 'statements': ['keep_keys(scope.attributes, [])', 'set(scope.name, "codex.local.admission")', 'set(scope.version, "1")', 'set(scope.schema_url, "")']}]}}

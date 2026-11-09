"""Opt-in standard Collector diagnostic event policy prototype; no live I/O.

Pinned Codex 086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a event catalog.
Counts/usage are diagnostics, never canonical billing. Unknown events retain only
fixed names/timestamps. Spans with links remain excluded until link clearing is separately qualified.
"""
import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('native_source', Path(__file__).with_name('native_source_policy.py'))
SOURCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SOURCE)
EVENTS = ('codex.startup_phase', 'codex.turn_ttft', 'codex.turn_cost',
          'codex.plugin_install_elicitation_sent', 'codex.plugin_install_suggestion',
          'codex.conversation_starts', 'codex.api_request', 'codex.websocket_connect',
          'codex.websocket_request', 'codex.auth_recovery', 'codex.sse_event',
          'codex.user_prompt', 'codex.tool_decision', 'codex.sandbox_outcome',
          'codex.tool_result', 'codex.multi_agent.spawn.failure',
          'codex.agent_response', 'codex.guardian_assessment')
# Per-field event-kind applicability prevents a known numeric key on an arbitrary
# event from being interpreted as genuine usage. No floating point or text value
# is exported. Bound accommodates diagnostics, not arbitrary int64 identifiers.
FIELDS = {
    'duration_ms': ('codex.startup_phase', 'codex.turn_ttft', 'codex.api_request', 'codex.websocket_connect', 'codex.websocket_request', 'codex.sse_event', 'codex.tool_result'),
    'input_token_count': ('codex.sse_event',), 'output_token_count': ('codex.sse_event',),
    'cached_token_count': ('codex.sse_event',), 'cache_write_token_count': ('codex.sse_event',),
    'reasoning_token_count': ('codex.sse_event',), 'tool_token_count': ('codex.sse_event',),
    'ttft_ms': ('codex.sse_event',), 'arguments_length': ('codex.tool_result',),
    'output_length': ('codex.tool_result',), 'output_line_count': ('codex.tool_result',),
    'text_input_count': ('codex.user_prompt',), 'image_input_count': ('codex.user_prompt',),
    'local_image_input_count': ('codex.user_prompt',),
}
PREFIX = 'langfuse.observation.metadata.codex.native.diagnostic.'


def processors():
    a = 'span.attributes'
    init = ['keep_keys(span.attributes, [])', 'set(span.name, "codex.operation")',
            'set(span.trace_state, "")', 'set(span.status.message, "")',
            'set(span.attributes["dots.accounting.role"], "diagnostic-noncanonical")',
            f'set({a}["{PREFIX}event_count"], Len(span.events))',
            f'set({a}["{PREFIX}unclassified_event_count"], 0)',
            f'set({a}["{PREFIX}timeline_json"], "[]")',
            'set(span.attributes["native.temporary.fragments"], ParseJSON("[]"))',
            f'set({a}["{PREFIX}timeline_omitted_count"], 0)']
    for event in EVENTS:
        init.append(f'set({a}["{PREFIX}count.{event}"], 0)')
    for field in FIELDS:
        output = 'reported_total_token_count' if field == 'tool_token_count' else field
        init.append(f'set({a}["{PREFIX}sum.{output}"], 0)')
    ea = 'spanevent.attributes'
    statements = [f'set(spanevent.cache["raw"], {ea})',
                  'set(spanevent.name, "codex.event.unclassified")',
                  f'set(spanevent.name, {ea}["event.name"]) where ContainsValue({json.dumps(EVENTS)}, {ea}["event.name"])',
                  f'keep_keys({ea}, [])',
                  f'set({a}["{PREFIX}unclassified_event_count"], {a}["{PREFIX}unclassified_event_count"] + 1) where spanevent.name == "codex.event.unclassified"']
    for event in EVENTS:
        key = f'{PREFIX}count.{event}'
        statements.append(f'set({a}["{key}"], {a}["{key}"] + 1) where spanevent.name == {json.dumps(event)}')
    for field, events in FIELDS.items():
        raw = f'spanevent.cache["raw"]["{field}"]'
        condition = f'ContainsValue({json.dumps(events)}, spanevent.name)'
        if 'token_count' in field or field == 'ttft_ms':
            condition += ' and spanevent.cache["raw"]["event.kind"] == "response.completed"'
        valid = f'((IsInt({raw}) and {raw} >= 0 and {raw} <= 1000000000) or (IsString({raw}) and IsMatch({raw}, "^[0-9]{{1,9}}$")))'
        statements.append(f'set({ea}["{field}"], Int({raw})) where {condition} and {valid}')
        output = 'reported_total_token_count' if field == 'tool_token_count' else field
        key = f'{PREFIX}sum.{output}'
        statements.append(f'set({a}["{key}"], {a}["{key}"] + {ea}["{field}"]) where IsInt({ea}["{field}"]) and {a}["{key}"] <= 9000000000000000')
    timeline = f'{a}["{PREFIX}timeline_json"]'
    omitted = f'{a}["{PREFIX}timeline_omitted_count"]'
    statements += [
        f'set({ea}["reported_total_token_count"], {ea}["tool_token_count"]) where IsInt({ea}["tool_token_count"])',
        f'delete_key({ea}, "tool_token_count")',
        f'set(spanevent.cache["entry"], {ea})',
        'set(spanevent.cache["entry"]["name"], spanevent.name)',
        'set(spanevent.cache["entry"]["time_unix_nano"], String(UnixNano(spanevent.time))) where UnixNano(spanevent.time) > 0',
        'set(spanevent.cache["timeline"], span.attributes["native.temporary.fragments"])',
        'append(spanevent.cache["timeline"], String(spanevent.cache["entry"]))',
        'set(spanevent.cache["encoded"], Concat(["[", Concat(spanevent.cache["timeline"], ","), "]"], ""))',
        'set(span.attributes["native.temporary.fragments"], spanevent.cache["timeline"]) where Len(spanevent.cache["encoded"]) <= 4096 and Len(spanevent.cache["timeline"]) <= 32',
        f'set({timeline}, spanevent.cache["encoded"]) where Len(spanevent.cache["encoded"]) <= 4096 and Len(spanevent.cache["timeline"]) <= 32',
        f'set({omitted}, {omitted} + 1) where Len(spanevent.cache["encoded"]) > 4096 or Len(spanevent.cache["timeline"]) > 32',
    ]
    # Missing per-kind/sum/omission fields mean zero. Retain total count and
    # timeline shape even for spans without events; avoid zero-field amplification.
    zero_keys = [PREFIX + 'unclassified_event_count', PREFIX + 'timeline_omitted_count']
    zero_keys += [PREFIX + 'count.' + event for event in EVENTS]
    zero_keys += [PREFIX + 'sum.' + ('reported_total_token_count' if field == 'tool_token_count' else field) for field in FIELDS]
    finalize = ['delete_key(span.attributes, "native.temporary.fragments")']
    finalize += [f'delete_key({a}, {json.dumps(key)}) where {a}[{json.dumps(key)}] == 0' for key in zero_keys]
    return {'filter/source': SOURCE.source_gate(),
            'filter/event-envelope': {'error_mode': 'propagate', 'traces': {'span': ['Len(span.links) > 0', 'Len(span.events) > 10000']}},
            'transform/event-envelope': {'error_mode': 'propagate', 'trace_statements': [
                {'context': 'resource', 'statements': ['keep_keys(resource.attributes, [])', 'set(resource.schema_url, "")']},
                {'context': 'scope', 'statements': ['keep_keys(scope.attributes, [])', 'set(scope.name, "codex.native.diagnostics")', 'set(scope.version, "1")', 'set(scope.schema_url, "")']},
                {'context': 'span', 'statements': init}]},
            'transform/events': {'error_mode': 'propagate', 'trace_statements': [{'context': 'spanevent', 'statements': statements}]},
            'transform/event-finalize': {'error_mode': 'propagate', 'trace_statements': [{'context': 'span', 'statements': finalize}]},
            'filter/summarized-events': {'error_mode': 'propagate', 'traces': {'spanevent': ['true']}}}


def central_processors():
    """Revalidate the diagnostics subset centrally; never preserve arbitrary text.

    Timeline grammar accepts only serialized fixed names, numeric field values
    and decimal timestamps. It deliberately rejects any unrecognized string/key.
    This is a proposed replacement for diagnostics privacy only, not routing.
    """
    numeric_keys = [PREFIX + 'event_count', PREFIX + 'unclassified_event_count', PREFIX + 'timeline_omitted_count']
    numeric_keys += [PREFIX + 'count.' + name for name in EVENTS]
    numeric_keys += [PREFIX + 'sum.' + ('reported_total_token_count' if field == 'tool_token_count' else field) for field in FIELDS]
    import re
    name = '"name":"(?:' + '|'.join(re.escape(n) for n in (*EVENTS, 'codex.event.unclassified')) + ')"'
    number = '"(?:' + '|'.join(re.escape('reported_total_token_count' if n == 'tool_token_count' else n) for n in FIELDS) + ')":(?:[0-9]{1,9}|1000000000)'
    timestamp = '"time_unix_nano":"[0-9]{1,19}"'
    member = '(?:' + '|'.join((name, number, timestamp)) + ')'
    entry = r'\{' + member + '(?:,' + member + r')*\}'
    grammar = r'^\[(?:' + entry + '(?:,' + entry + r'){0,31})?\]$'
    a = 'span.attributes'
    statements = [f'set(span.cache["native"], {a})', f'keep_keys({a}, [])',
                  'set(span.attributes["dots.accounting.role"], "diagnostic-noncanonical")',
                  'set(span.name, "codex.operation")', 'set(span.status.message, "")', 'set(span.trace_state, "")']
    for key in numeric_keys:
        value = f'span.cache["native"][{json.dumps(key)}]'
        statements.append(f'set({a}[{json.dumps(key)}], {value}) where IsInt({value}) and {value} >= 0 and {value} <= 10000000000000')
    key = PREFIX + 'timeline_json'
    value = f'span.cache["native"][{json.dumps(key)}]'
    statements.append(f'set({a}[{json.dumps(key)}], {value}) where IsString({value}) and Len({value}) <= 4096 and IsMatch({value}, {json.dumps(grammar)})')
    return {'filter/native-event-central': {'error_mode': 'propagate', 'traces': {'span': [
                'instrumentation_scope.name != "codex.native.diagnostics" or instrumentation_scope.version != "1"', 'Len(span.links) > 0'], 'spanevent': ['true']}},
            'transform/native-event-central': {'error_mode': 'propagate', 'trace_statements': [
                {'context': 'resource', 'statements': ['keep_keys(resource.attributes, [])', 'set(resource.schema_url, "")']},
                {'context': 'scope', 'statements': ['keep_keys(scope.attributes, [])', 'set(scope.schema_url, "")']},
                {'context': 'span', 'statements': statements}]}}

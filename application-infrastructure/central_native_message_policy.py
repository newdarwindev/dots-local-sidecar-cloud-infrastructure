"""Pure standard Collector central EVENT gate; no I/O, endpoints or credentials."""
import copy
import json
import re

SESSION = re.compile(r'[A-Za-z0-9_-]{1,128}')
FILTER = 'filter/native-conversations'
TRANSFORM = 'transform/native-conversations'
PIPELINE = 'traces/native-conversations'
ROUTER = 'routing/conversations'
ROW = {'context': 'span', 'condition': 'instrumentation_scope.name == "codex.native.conversation" and instrumentation_scope.version == "1" and (span.name == "codex.native.user_message" or span.name == "codex.native.assistant_message")',
       'action': 'move', 'pipelines': [PIPELINE]}
NATIVE_PIPELINE = {'receivers': [ROUTER], 'processors': ['memory_limiter', FILTER, TRANSFORM, 'batch/conversations'], 'exporters': ['otlphttp/conversations']}

PLUGIN_ROW = {'context': 'span', 'condition': 'instrumentation_scope.name == "codex.conversation" and instrumentation_scope.version == "1" and span.name == "codex.conversation"',
              'action': 'move', 'pipelines': ['traces/conversations']}
BASE_PIPELINES = {
    'traces/ingress': {'receivers': ['otlp'], 'processors': ['memory_limiter'], 'exporters': [ROUTER]},
    'traces/diagnostics': {'receivers': [ROUTER], 'processors': ['memory_limiter', 'filter/privacy', 'transform/privacy', 'batch'], 'exporters': ['otlphttp/langfuse']},
    'traces/conversations': {'receivers': [ROUTER], 'processors': ['memory_limiter', 'filter/conversations', 'transform/conversations', 'batch/conversations'], 'exporters': ['otlphttp/conversations']},
}


def build_processors(enrolled, denied):
    if not isinstance(enrolled, dict) or not isinstance(denied, list):
        raise ValueError('Explicit enrollment map and denial list required')
    for sid, cutoff in enrolled.items():
        if not isinstance(sid, str) or not SESSION.fullmatch(sid) or type(cutoff) is not int or not 0 < cutoff < 2**63:
            raise ValueError('Invalid enrollment')
    if any(not isinstance(sid, str) or not SESSION.fullmatch(sid) for sid in denied):
        raise ValueError('Invalid denial')
    allowed = [f'(span.attributes["session.id"] == {json.dumps(sid)} and UnixNano(span.start_time) >= {cutoff})'
               for sid, cutoff in sorted(enrolled.items()) if sid not in denied]
    a = 'span.attributes'
    conditions = ['not (' + ' or '.join(allowed) + ')' if allowed else 'true',
                  'instrumentation_scope.name != "codex.native.conversation" or instrumentation_scope.version != "1"',
                  'span.name != "codex.native.user_message" and span.name != "codex.native.assistant_message"',
                  'Len(span.links) > 0', f'not IsString({a}["session.id"])',
                  f'{a}["langfuse.observation.type"] != "event"',
                  f'span.name == "codex.native.user_message" and (not IsString({a}["langfuse.observation.input"]) or {a}["langfuse.observation.output"] != nil)',
                  f'span.name == "codex.native.assistant_message" and (not IsString({a}["langfuse.observation.output"]) or {a}["langfuse.observation.input"] != nil)']
    return {FILTER: {'error_mode': 'propagate', 'traces': {'span': conditions, 'spanevent': ['true']}},
            TRANSFORM: {'error_mode': 'propagate', 'trace_statements': [{'context': 'span', 'statements': [
                'keep_keys(resource.attributes, [])', 'keep_keys(instrumentation_scope.attributes, [])',
                'keep_keys(span.attributes, ["session.id", "langfuse.observation.type", "langfuse.observation.input", "langfuse.observation.output"])',
                'set(span.status.message, "")', 'set(span.trace_state, "")']}]}}


def patch_config(config, enrolled, denied):
    """Insert native route only in recognized central shape, or return exact match.

    Existing differing native policy is not updated implicitly. The caller must
    separately review such changes. Private transport objects are deep-copied,
    never logged or read by this module.
    """
    generated = build_processors(enrolled, denied)
    if not isinstance(config, dict):
        raise ValueError('Unrecognized central configuration')
    try:
        router = config['connectors'][ROUTER]
        processors = config['processors']
        pipelines = config['service']['pipelines']
        if not isinstance(router, dict) or not isinstance(processors, dict) or not isinstance(pipelines, dict):
            raise ValueError('Unrecognized central component objects')
        table = router['table']
        if any(pipelines.get(key) != value for key, value in BASE_PIPELINES.items()):
            raise ValueError('Unrecognized existing pipelines')
        if set(pipelines) not in (set(BASE_PIPELINES), set(BASE_PIPELINES) | {PIPELINE}):
            raise ValueError('Unexpected pipeline')
        if 'otlp' not in config['receivers']:
            raise ValueError('Missing existing ingress receiver')
        for pipeline in BASE_PIPELINES.values():
            if any(key not in processors for key in pipeline['processors']):
                raise ValueError('Missing existing processor')
            if any(key not in config['exporters'] and key != ROUTER for key in pipeline['exporters']):
                raise ValueError('Missing existing exporter')
        if (set(router) != {'error_mode', 'default_pipelines', 'table'} or router['error_mode'] != 'propagate'
                or router['default_pipelines'] != ['traces/diagnostics'] or not isinstance(table, list)

                or 'memory_limiter' not in processors or 'batch/conversations' not in processors
                or 'otlphttp/conversations' not in config['exporters']):
            raise ValueError('Unrecognized central routing structure')
        plugin_rows = [row for row in table if row != ROW]
        if len(plugin_rows) != 1 or plugin_rows[0] != PLUGIN_ROW:
            raise ValueError('Unrecognized existing plugin route')
        present = [FILTER in processors, TRANSFORM in processors, PIPELINE in pipelines, ROW in table]
        if any(present):
            if (not all(present) or table != [ROW, PLUGIN_ROW] or pipelines[PIPELINE] != NATIVE_PIPELINE
                    or any(processors[key] != value for key, value in generated.items())):
                raise ValueError('Existing native policy differs; explicit review required')
            return copy.deepcopy(config)
        if len(table) != 1:
            raise ValueError('Unexpected routing rows')
    except (KeyError, TypeError) as error:
        raise ValueError('Unrecognized central configuration') from error
    result = copy.deepcopy(config)
    result['processors'].update(generated)
    result['connectors'][ROUTER]['table'].insert(0, copy.deepcopy(ROW))
    result['service']['pipelines'][PIPELINE] = copy.deepcopy(NATIVE_PIPELINE)
    return result

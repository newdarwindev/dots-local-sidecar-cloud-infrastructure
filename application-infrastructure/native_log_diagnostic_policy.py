"""Synthetic-only candidate standard Collector log projection; never enables producers.

Independent diagnostic observations, not reconstructed turns or billing usage.
No arbitrary text survives the first transform, including on parser errors.
"""
import json
import native_message_policy as messages
import native_event_policy as events
BASE_RENDER = messages.render


def render():
    config = BASE_RENDER({}, [])
    a = 'log.attributes'
    raw = lambda key: f'{a}[{json.dumps(key)}]'
    statements = ['set(log.cache["safe"], ParseJSON("{}"))']
    # Copy only validated finite enums/identifiers and syntax-limited clocks.
    for key, condition in {
        'event.name': f'ContainsValue({json.dumps(events.EVENTS)}, {raw("event.name")})',
        'event.kind': f'{raw("event.kind")} == "response.completed"',
        'conversation.id': f'IsString({raw("conversation.id")}) and IsMatch({raw("conversation.id")}, "^[a-f0-9]{{8}}-[a-f0-9]{{4}}-[a-f0-9]{{4}}-[a-f0-9]{{4}}-[a-f0-9]{{12}}$")',
        'event.timestamp': f'IsString({raw("event.timestamp")}) and IsMatch({raw("event.timestamp")}, "^20[0-9]{{2}}-[0-9]{{2}}-[0-9]{{2}}T[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}[.][0-9]{{3}}Z$")',
    }.items():
        statements.append(f'set(log.cache["safe"][{json.dumps(key)}], {raw(key)}) where {condition}')
    for key in events.FIELDS:
        value = raw(key)
        statements.append(f'set(log.cache["safe"][{json.dumps(key)}], Int({value})) where (IsInt({value}) and {value} >= 0 and {value} <= 1000000000) or (IsString({value}) and IsMatch({value}, "^[0-9]{{1,9}}$"))')
    statements += ['set(log.body, "")', 'set(log.severity_text, "")', 'set(log.event_name, "")',
                   'set(log.attributes, log.cache["safe"])', 'keep_keys(resource.attributes, [])',
                   'keep_keys(scope.attributes, [])', 'set(resource.schema_url, "")', 'set(scope.schema_url, "")',
                   'set(scope.name, "")', 'set(scope.version, "")']
    gate = ['resource.attributes["service.version"] != "0.167.0"',
            'not ContainsValue(["codex_cli_rs", "codex_exec", "codex-app-server", "codex_work_desktop"], resource.attributes["service.name"])',
            'scope.name != "codex_otel.log_only"', f'{a}["app.version"] != "0.167.0"']
    clock = 'UnixNano(Time(log.attributes["event.timestamp"], "%Y-%m-%dT%H:%M:%S.%LZ"))'
    template = {'resourceSpans': [{'resource': {}, 'scopeSpans': [{'scope': {'name': 'codex.native.diagnostics', 'version': '1'}, 'spans': [{'name': 'codex.operation', 'kind': 1, 'attributes': [
        {'key': 'dots.accounting.role', 'value': {'stringValue': 'diagnostic-noncanonical'}},
        {'key': events.PREFIX + 'event_count', 'value': {'intValue': '1'}},
        {'key': events.PREFIX + 'timeline_json', 'value': {'stringValue': ''}}]}]}]}]}
    span = 'log.cache["otlp"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]'
    output = ['set(log.cache["entry"], ParseJSON("{}"))', f'set(log.cache["entry"]["name"], {raw("event.name")})',
              f'set(log.cache["entry"]["time_unix_nano"], String({clock}))']
    for key, names in events.FIELDS.items():
        condition = f'ContainsValue({json.dumps(names)}, {raw("event.name")}) and IsInt({raw(key)})'
        if 'token_count' in key or key == 'ttft_ms':
            condition += f' and {raw("event.kind")} == "response.completed"'
        target = 'reported_total_token_count' if key == 'tool_token_count' else key
        output.append(f'set(log.cache["entry"][{json.dumps(target)}], {raw(key)}) where {condition}')
    output += [f'set(log.cache["otlp"], ParseJSON({json.dumps(json.dumps(template))}))',
               'set(log.cache["identity"], SHA256(Concat([log.attributes["conversation.id"], log.attributes["event.name"], log.attributes["event.timestamp"], String(UnixNano(log.observed_time))], ":")))',
               f'set({span}["traceId"], Substring(log.cache["identity"], 0, 32))',
               f'set({span}["spanId"], Substring(log.cache["identity"], 32, 16))',
               f'set({span}["startTimeUnixNano"], String({clock}))', f'set({span}["endTimeUnixNano"], String({clock}))',
               f'set({span}["attributes"][2]["value"]["stringValue"], Concat(["[", String(log.cache["entry"]), "]"], ""))',
               'set(log.body, String(log.cache["otlp"]))', 'keep_keys(log.attributes, [])']
    config['processors'] = {
        'filter/source': {'error_mode': 'propagate', 'logs': {'log_record': gate}},
        'transform/scrub': {'error_mode': 'propagate', 'log_statements': [{'context': 'log', 'statements': statements}]},
        'filter/shape': {'error_mode': 'propagate', 'logs': {'log_record': [f'{raw(k)} == nil' for k in ('event.name', 'event.timestamp', 'conversation.id')] + ['UnixNano(log.observed_time) <= 0']}},
        'transform/encode': {'error_mode': 'propagate', 'log_statements': [{'context': 'log', 'statements': output}]}}
    config['service']['pipelines']['logs/native_messages']['processors'] = list(config['processors'])
    # Default production informational diagnostics, not suppression to pass canaries.
    config['service']['telemetry']['logs']['level'] = 'info'
    return config

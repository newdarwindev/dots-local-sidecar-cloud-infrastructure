"""Bounded native log conversion using upstream Collector components only.

Not a provenance validator or automatic enrollment mechanism. Native user_prompt
can include unclassified input. Caller must qualify an isolated fresh session.
No runtime services, producer flags, credentials or historical readers here.
"""
import json
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('native_shared_policy', Path(__file__).with_name('conversation_policy.py'))
SHARED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARED)
ID, SECRET_PATTERN = SHARED.ID, SHARED.SECRET_PATTERN


def render(enrolled, denied, *, future_after_ns=None, tool_results=False):
    if type(tool_results) is not bool:
        raise ValueError('Explicit boolean tool_results required')
    if not isinstance(enrolled, dict) or not isinstance(denied, list):
        raise ValueError('Explicit enrollment and denials required')
    for session, cutoff in enrolled.items():
        if not isinstance(session, str) or not ID.fullmatch(session) or type(cutoff) is not int or not 0 < cutoff < 2**63:
            raise ValueError('Exact UUID and positive source-event timestamp required')
    if any(not isinstance(s, str) or not ID.fullmatch(s) for s in denied):
        raise ValueError('Exact denied UUID required')
    a = 'log.attributes'
    event = f'{a}["event.name"]'
    session = f'{a}["conversation.id"]'
    prompt = f'{event} == "codex.user_prompt"'
    response = f'{event} == "codex.agent_response"'
    clock = 'UnixNano(Time(log.attributes["event.timestamp"], "%Y-%m-%dT%H:%M:%S.%LZ"))'
    drop = SHARED.enrollment_predicates(enrolled, denied, session, clock, future_after_ns)
    drop += [
            f'{event} != "codex.user_prompt" and {event} != "codex.agent_response"',
            'resource.attributes["service.version"] != "0.167.0"',
            'resource.attributes["service.name"] != "codex_cli_rs" and resource.attributes["service.name"] != "codex-app-server" and resource.attributes["service.name"] != "codex_work_desktop" and resource.attributes["service.name"] != "codex_exec"',
            f'{a}["app.version"] != "0.167.0"',
            f'{prompt} and not IsString({a}["prompt"])',
            f'{prompt} and (Len({a}["prompt"]) == 0 or Len({a}["prompt"]) > 65536)',
            f'{response} and not IsString({a}["response"])',
            f'{response} and (Len({a}["response"]) == 0 or Len({a}["response"]) > 65536)',
            f'{response} and {a}["response_truncated"] != false',
            f'{response} and {a}["agent.type"] != "main"',
            f'{a}["parent.conversation.id"] != nil',
            'UnixNano(log.observed_time) <= 0',
            f'not IsString({a}["event.timestamp"])',
            'scope.name != "codex_otel.log_only"',
            f'{response} and not IsMatch({a}["item.id"], "^msg_[a-f0-9]{{16,128}}$")']
    clock = 'UnixNano(Time(log.attributes["event.timestamp"], "%Y-%m-%dT%H:%M:%S.%LZ"))'
    drop += [f'{session} == {json.dumps(s)} and {clock} < {t}' for s, t in sorted(enrolled.items())]
    # Static JSON shape only. Text enters typed maps after decoding this constant.
    template = {'resourceSpans': [{'resource': {}, 'scopeSpans': [{'scope': {'name': 'codex.native.conversation', 'version': '1'}, 'spans': [{
        'name': 'Codex native message', 'kind': 1, 'attributes': [
            {'key': 'session.id', 'value': {'stringValue': ''}},
            {'key': 'langfuse.observation.type', 'value': {'stringValue': 'event'}},
            {'key': 'langfuse.observation.input', 'value': {'stringValue': ''}}]}]}]}]}
    span = 'log.cache["otlp"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]'
    statements = [f'set(log.cache["text"], {a}["prompt"]) where {prompt}',
                  f'set(log.cache["text"], {a}["response"]) where {response}',
                  f'replace_pattern(log.cache["text"], {json.dumps(SECRET_PATTERN)}, "<secret excluded>")',
                  f'set(log.cache["otlp"], ParseJSON({json.dumps(json.dumps(template))}))',
                  f'set({span}["attributes"][0]["value"]["stringValue"], {session})',
                  f'set({span}["attributes"][2]["value"]["stringValue"], log.cache["text"])',
                  f'set({span}["attributes"][2]["key"], "langfuse.observation.output") where {response}',
                  f'set({span}["name"], "codex.native.user_message") where {prompt}',
                  f'set({span}["name"], "codex.native.assistant_message") where {response}',
                  'set(log.cache["item"], "")',
                  f'set(log.cache["item"], {a}["item.id"]) where {response}',
                  'set(log.cache["identity"], SHA256(Concat([log.attributes["conversation.id"], log.attributes["event.name"], log.attributes["event.timestamp"], String(UnixNano(log.observed_time)), log.cache["item"]], ":")))',
                  f'set({span}["traceId"], Substring(log.cache["identity"], 0, 32))',
                  f'set({span}["spanId"], Substring(log.cache["identity"], 32, 16))',
                  f'set({span}["startTimeUnixNano"], String({clock}))',
                  f'set({span}["endTimeUnixNano"], String({clock}))',
                  'set(log.body, String(log.cache["otlp"]))',
                  'keep_keys(log.attributes, [])']
    if tool_results:
        tool = f'{event} == "codex.tool_result"'
        drop[drop.index(f'{event} != "codex.user_prompt" and {event} != "codex.agent_response"')] += f' and not ({tool})'
        drop += [
            f'{tool} and (not IsString({a}["arguments"]) or not IsString({a}["output"]))',
            f'{tool} and (Len({a}["arguments"]) > 65536 or Len({a}["output"]) > 65600)',
            f'{tool} and (not IsString({a}["call_id"]) or not IsMatch({a}["call_id"], "^[A-Za-z0-9_-]{{1,128}}$"))',
            f'{tool} and (not IsInt({a}["tool_result_seq"]) or {a}["tool_result_seq"] <= 0)',
            f'{tool} and not IsBool({a}["output_truncated"])',
            f'{tool} and ({a}["success"] != "true" and {a}["success"] != "false")',
            f'{tool} and (not IsString({a}["duration_ms"]) or not IsMatch({a}["duration_ms"], "^[0-9]{{1,16}}$"))',
        ]
        for field in ('tool_name', 'tool_namespace', 'agent_name', 'mcp_server', 'mcp_server_origin'):
            drop.append(f'{tool} and (not IsString({a}["{field}"]) or Len({a}["{field}"]) > 1024)')
        # The original prompt/response projection is unchanged. Tool content uses
        # its own typed map and never serializes the ambient log envelope.
        statements[2] += f' where not ({tool})'
        tool_template = json.loads(json.dumps(template))
        tool_span = tool_template['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
        tool_span['name'] = 'codex.native.tool_result'
        tool_span['attributes'] += [
            {'key': 'langfuse.observation.output', 'value': {'stringValue': ''}},
            {'key': 'langfuse.observation.metadata', 'value': {'stringValue': ''}}]
        # Insert immediately before identity derivation, once the generic item is
        # initialized; IDs stay stable across Collector retries of this record.
        index = next(i for i, value in enumerate(statements) if value.startswith('set(log.cache["identity"]'))
        tool_statements = [
            f'set(log.cache["otlp"], ParseJSON({json.dumps(json.dumps(tool_template))}))',
            f'set({span}["attributes"][0]["value"]["stringValue"], {session})',
            f'set(log.cache["tool_input"], {a}["arguments"])',
            f'set(log.cache["tool_output"], {a}["output"])',
            f'replace_pattern(log.cache["tool_input"], {json.dumps(SECRET_PATTERN)}, "<secret excluded>")',
            f'replace_pattern(log.cache["tool_output"], {json.dumps(SECRET_PATTERN)}, "<secret excluded>")',
            f'set({span}["attributes"][2]["value"]["stringValue"], log.cache["tool_input"])',
            f'set({span}["attributes"][3]["value"]["stringValue"], log.cache["tool_output"])',
            'set(log.cache["tool_metadata"], ParseJSON("{}"))',
        ]
        for field in ('tool_name', 'tool_namespace', 'agent_name', 'mcp_server', 'mcp_server_origin', 'call_id', 'duration_ms', 'success', 'tool_result_seq', 'output_truncated'):
            tool_statements.append(f'set(log.cache["tool_metadata"]["{field}"], {a}["{field}"])')
            if field not in ('tool_result_seq', 'output_truncated'):
                tool_statements.append(f'replace_pattern(log.cache["tool_metadata"]["{field}"], {json.dumps(SECRET_PATTERN)}, "<secret excluded>")')
        tool_statements += [
            f'set({span}["attributes"][4]["value"]["stringValue"], String(log.cache["tool_metadata"]))',
            f'set(log.cache["item"], Concat([{a}["call_id"], String({a}["tool_result_seq"])], ":"))',
        ]
        statements[index:index] = [statement + f' where {tool}' for statement in tool_statements]
        # Redaction and JSON encoding can grow fields. Reject the final tool
        # projection locally using the same limits as the central gate. The
        # independent diagnostic fan-out still sees the original source event.
        statements[-1:-1] = [
            'set(log.cache["projection_valid"], true)',
            'set(log.cache["projection_valid"], false) where ' + tool + ' and ('
            'Len(log.cache["tool_input"]) > 65536 or Len(log.cache["tool_output"]) > 65600 or '
            f'Len({span}["attributes"][4]["value"]["stringValue"]) > 8192)',
        ]
        statements.append('set(log.attributes["projection.valid"], log.cache["projection_valid"])')
    config = {'extensions': {'basicauth/native_messages': {'htpasswd': {'file': '${env:CONVERSATION_HTPASSWD_FILE}'}}},
            'receivers': {'otlp/native_messages': {'protocols': {'http': {'endpoint': '127.0.0.1:17449', 'auth': {'authenticator': 'basicauth/native_messages'}}}}},
            'processors': {'filter/native_messages': {'error_mode': 'propagate', 'logs': {'log_record': drop}},
                           'transform/native_messages': {'error_mode': 'propagate', 'log_statements': [{'context': 'log', 'statements': statements}]}},
            'connectors': {'otlp_json/native_messages': {}},
            'exporters': {'otlphttp/rich': {'traces_endpoint': '${env:CONVERSATION_MTLS_TRACES_ENDPOINT}',
                'tls': {'ca_file': '${env:CONVERSATION_CA_FILE}', 'cert_file': '${env:CONVERSATION_CERT_FILE}',
                        'key_file': '${env:CONVERSATION_KEY_FILE}', 'min_version': '1.3'},
                'retry_on_failure': {'enabled': False}, 'sending_queue': {'enabled': False}}},
            'service': {'extensions': ['basicauth/native_messages'], 'telemetry': {'logs': {'level': 'error'}, 'metrics': {'level': 'none'}}, 'pipelines': {
                'logs/native_messages': {'receivers': ['otlp/native_messages'], 'processors': ['filter/native_messages', 'transform/native_messages'], 'exporters': ['otlp_json/native_messages']},
                'traces/native_messages': {'receivers': ['otlp_json/native_messages'], 'exporters': ['otlphttp/rich']}}}}
    if tool_results:
        config['processors']['filter/native_messages_projected'] = {
            'error_mode': 'propagate', 'logs': {'log_record': ['log.attributes["projection.valid"] != true']}}
        config['service']['pipelines']['logs/native_messages']['processors'].append('filter/native_messages_projected')
    if future_after_ns is not None or tool_results:
        # Parse per record without printing invalid source values or failing a
        # neighboring valid record. Overwrite any source-supplied marker first.
        config['processors']['transform/native_messages_clock'] = {
            'error_mode': 'silent', 'log_statements': [{'context': 'log', 'statements': [
                'set(log.attributes["source.clock.ns"], 0)',
                'set(log.attributes["source.clock.ns"], ' + clock + ')']} ]}
        config['processors']['filter/native_messages_clock'] = {
            'error_mode': 'propagate', 'logs': {'log_record': ['log.attributes["source.clock.ns"] <= 0']}}
        config['service']['pipelines']['logs/native_messages']['processors'][:0] = [
            'transform/native_messages_clock', 'filter/native_messages_clock']
    return config

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


def render(enrolled, denied):
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
    drop = [f'not ContainsValue({json.dumps(sorted(enrolled))}, {session})',
            f'ContainsValue({json.dumps(sorted(set(denied)))}, {session})',
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
    return {'extensions': {'basicauth/native_messages': {'htpasswd': {'file': '${env:CONVERSATION_HTPASSWD_FILE}'}}},
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

"""Render standard upstream Collector policy; never reads sessions or starts services."""
import json
import re

ID = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
PREFIX = 'langfuse.observation.'
SECRET_PATTERN = (r'SYNTHETIC_SECRET_[A-Z0-9_]+'
                  r'|(?i:Bearer\s+[A-Za-z0-9._~+/=-]+)'
                  r'|(?:sk|pk)-[A-Za-z0-9_-]{16,}'
                  r'|gh[pousr]_[A-Za-z0-9]{20,}'
                  r'|hvs\.[A-Za-z0-9_-]+'
                  r'|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----')


def enrollment_predicates(enrolled, denied, session, clock, future_after_ns=None):
    """Optional owner-approved future-event admission; permanent denials still win."""
    if future_after_ns is not None and (type(future_after_ns) is not int
                                        or not 0 < future_after_ns < 2**63):
        raise ValueError('Future enrollment requires a positive UTC nanosecond cutoff')
    known = f'ContainsValue({json.dumps(sorted(enrolled))}, {session})'
    if future_after_ns is None:
        drop = [f'not {known}']
    else:
        drop = [f'not IsString({session})',
                f'not IsMatch({session}, "^{ID.pattern}$")',
                f'not {known} and {clock} < {future_after_ns}']
    drop.append(f'ContainsValue({json.dumps(sorted(set(denied)))}, {session})')
    return drop


def render(enrolled, denied, *, generations=False, future_after_ns=None):
    """IDs map to original-start nanosecond cutoffs, verified fresh outside this renderer.

    Denials are permanent operational policy, even if an ID is also enrolled.
    Optional future_after_ns admits future events from additional UUID sessions.
    It does not prove their creation time or classify their contents. No discovery,
    historical readers, state, producer settings or service activation occurs.
    """
    if not isinstance(enrolled, dict) or not isinstance(denied, list):
        raise ValueError('Explicit enrollment map and permanent denial list required')
    for session, cutoff in enrolled.items():
        if not isinstance(session, str) or not ID.fullmatch(session):
            raise ValueError('Enrollment requires exact UUIDs')
        if type(cutoff) is not int or not 0 < cutoff < 2**63:
            raise ValueError('Enrollment requires positive original-start cutoff')
    if any(not isinstance(value, str) or not ID.fullmatch(value) for value in denied):
        raise ValueError('Denials require exact UUIDs')
    if type(generations) is not bool:
        raise ValueError('Explicit generation option required')
    a = 'span.attributes'
    kind = f'{a}["{PREFIX}type"]'
    session = f'{a}["session.id"]'
    root = f'{kind} == "agent"'
    generation = f'{kind} == "generation"'
    input_ = f'{a}["{PREFIX}input"]'
    output = f'{a}["{PREFIX}output"]'
    drop = enrollment_predicates(enrolled, denied, session, 'UnixNano(span.start_time)', future_after_ns)
    drop += [
            f'{kind} != "agent" and {kind} != "generation"',
            f'{root} and span.name != "Codex Turn"',
            f'{generation} and span.name != "LLM"',
            'Len(span.links) > 0',
            f'{root} and {a}["{PREFIX}metadata.codex.thread_id"] != {session}',
            f'{root} and not IsString({a}["{PREFIX}metadata.codex.turn_id"])',
            f'{root} and not IsString({input_})',
            f'{root} and not IsString({output})']
    for value, cutoff in sorted(enrolled.items()):
        drop.append(f'{session} == {json.dumps(value)} and UnixNano(span.start_time) < {cutoff}')
    if not generations:
        drop.append(generation)
    # Serialized media/object shapes are not a supported text representation.
    for attr in (input_, output):
        drop.append(f'{root} and IsMatch({attr}, "^[[:space:]]*[\\\\[{{]")')
    statements = [f'set(span.cache["kind"], {kind})',
                  f'set(span.cache["input"], {input_})',
                  f'set(span.cache["output"], {output})',
                  f'keep_keys({a}, ["session.id"])',
                  'set(span.name, "codex.conversation")',
                  'set(span.trace_state, "")',
                  'set(span.status.message, "")',
                  'set(span.status.code, 0)',
                  'set(span.kind, 1)',
                  f'set({kind}, span.cache["kind"])',
                  f'set({input_}, span.cache["input"]) where span.cache["kind"] == "agent"',
                  f'set({output}, span.cache["output"]) where span.cache["kind"] == "agent"']
    if generations:
        statements += [
            'set(span.cache["parsed"], ParseJSON(span.cache["output"])) where span.cache["kind"] == "generation"',
            f'set({output}, span.cache["parsed"]["content"]) where span.cache["kind"] == "generation" and IsString(span.cache["parsed"]["content"])']
    for attr in (input_, output):
        statements.append(f'replace_pattern({attr}, {json.dumps(SECRET_PATTERN)}, "<secret excluded>") where IsString({attr})')
    return {
        'extensions': {'basicauth/conversation': {'htpasswd': {'file': '${env:CONVERSATION_HTPASSWD_FILE}'}}},
        'receivers': {'otlp/conversation': {'protocols': {'http': {
            'endpoint': '127.0.0.1:17448', 'traces_url_path': '/api/public/otel/v1/traces',
            'auth': {'authenticator': 'basicauth/conversation'}}}}},
        'processors': {
            'filter/enrollment': {'error_mode': 'propagate', 'traces': {'span': drop, 'spanevent': ['true']}},
            'transform/conversation': {'error_mode': 'propagate', 'trace_statements': [
                {'context': 'resource', 'statements': ['keep_keys(resource.attributes, [])', 'set(resource.schema_url, "")']},
                {'context': 'scope', 'statements': ['keep_keys(scope.attributes, [])', 'set(scope.name, "codex.conversation")',
                                                    'set(scope.version, "1")', 'set(scope.schema_url, "")']},
                {'context': 'span', 'statements': statements}]},
            'filter/content': {'error_mode': 'propagate', 'traces': {'span': [
                f'not IsString({output})', f'IsMatch({output}, "^[[:space:]]*[\\\\[{{]")']}}},
        'exporters': {'otlphttp/rich': {
            'traces_endpoint': '${env:CONVERSATION_MTLS_TRACES_ENDPOINT}',
            'tls': {'ca_file': '${env:CONVERSATION_CA_FILE}', 'cert_file': '${env:CONVERSATION_CERT_FILE}',
                    'key_file': '${env:CONVERSATION_KEY_FILE}', 'min_version': '1.3'},
            'retry_on_failure': {'enabled': False}}},
        'service': {'extensions': ['basicauth/conversation'],
                    'telemetry': {'logs': {'level': 'error'}, 'metrics': {'level': 'none'}},
                    'pipelines': {'traces/conversation': {
                        'receivers': ['otlp/conversation'],
                        'processors': ['filter/enrollment', 'transform/conversation', 'filter/content'],
                        'exporters': ['otlphttp/rich']}}}}

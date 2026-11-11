"""Render a narrow upstream Collector attribution change; no runtime relay."""
import copy
import json
import re

ENVIRONMENT_KEY = 'langfuse.environment'
KEEP_NONE = 'keep_keys(span.attributes, [])'
KEEP_ENVIRONMENT = 'keep_keys(span.attributes, ["langfuse.environment"])'


def session_attribution_config(config):
    """Opt in to UUID-only session grouping through standard Collector OTTL.

    Existing source-side filtering can already have removed these fields; this
    cannot restore historical IDs or establish complete session coverage.
    """
    result = copy.deepcopy(config)
    blocks = result['processors']['transform/privacy']['trace_statements']
    candidates = [block['statements'] for block in blocks if block.get('context') == 'span'
                  and any(s in (KEEP_NONE, KEEP_ENVIRONMENT) for s in block['statements'])]
    if len(candidates) != 1:
        raise ValueError('Unexpected privacy processor; refuse broad regeneration')
    statements = candidates[0]
    capture = 'set(span.cache["native"], span.attributes)'
    clear_index = next(i for i, item in enumerate(statements) if item in (KEEP_NONE, KEEP_ENVIRONMENT))
    if capture not in statements:
        statements.insert(clear_index, capture)
    elif statements.index(capture) >= clear_index:
        raise ValueError('Session source must be captured before stripping attributes')
    pattern = '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    for key in ('thread_id', 'thread.id', 'conversation.id', 'session.id'):
        source = 'span.cache["native"][' + json.dumps(key) + ']'
        statement = ('set(span.attributes["session.id"], ' + source + ') where IsString('
                     + source + ') and IsMatch(' + source + ', ' + json.dumps(pattern) + ')')
        if statement not in statements:
            statements.append(statement)
    return result


def attribution_config(config, remote_environments, default_environment='local-codex'):
    """Preserve only reviewed fixed labels; all other metadata stays stripped.

    Labels describe the authenticated, already-enrolled producer configuration.
    They are not proof of machine identity and must not authorize access.
    A missing, invalid, arbitrary or unapproved label becomes the fixed default.
    """
    labels = list(remote_environments)
    for label in [*labels, default_environment]:
        if not isinstance(label, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', label):
            raise ValueError('Expected a bounded non-sensitive environment label')
    if not 1 <= len(labels) <= 8 or len(labels) != len(set(labels)):
        raise ValueError('Expected one to eight distinct reviewed remote labels')
    if default_environment in labels:
        raise ValueError('The default environment must not be a remote label')
    result = copy.deepcopy(config)
    processor = result['processors']['transform/privacy']
    blocks = processor['trace_statements']
    candidates = [block['statements'] for block in blocks if block.get('context') == 'span'
                  and any(s in (KEEP_NONE, KEEP_ENVIRONMENT) for s in block['statements'])]
    if len(candidates) != 1:
        raise ValueError('Unexpected privacy processor; refuse broad regeneration')
    statements = candidates[0]
    default = f'set(span.attributes["{ENVIRONMENT_KEY}"], {json.dumps(default_environment)})'
    replacement = (default + ' where not ContainsValue('
                   + json.dumps(labels) + f', span.attributes["{ENVIRONMENT_KEY}"])')
    if statements.count(KEEP_ENVIRONMENT) == 1 and statements.count(replacement) == 1:
        return result
    if statements.count(KEEP_NONE) != 1 or statements.count(default) != 1:
        raise ValueError('Unexpected or differently managed privacy rules; review required')
    if statements.index(KEEP_NONE) > statements.index(default):
        raise ValueError('Unexpected privacy statement order')
    statements[statements.index(KEEP_NONE)] = KEEP_ENVIRONMENT
    statements[statements.index(default)] = replacement
    return result


BATCH_ENV = {
    'OTEL_BSP_MAX_EXPORT_BATCH_SIZE': '1',
    'OTEL_BSP_SCHEDULE_DELAY': '100',
}


def batching_dotenv(existing):
    """Prepare Codex's native startup file, never a shell profile or wrapper.

    Refuse an existing general-purpose dotenv rather than parsing or rewriting
    credentials, interpolations or multiline values. Preserve comments verbatim.
    The caller must validate the installed Codex loader before activation.
    """
    if not isinstance(existing, str) or '\x00' in existing:
        raise ValueError('Expected UTF-8 dotenv text without NUL')
    seen = set()
    for line in existing.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        key, separator, value = stripped.partition('=')
        if not separator or key not in BATCH_ENV or value != BATCH_ENV[key] or key in seen:
            raise ValueError('Existing dotenv needs explicit review; no automatic overwrite')
        seen.add(key)
    missing = [key for key in BATCH_ENV if key not in seen]
    if not missing:
        return existing
    prefix = existing + ('\n' if existing and not existing.endswith('\n') else '')
    return prefix + ''.join(f'{key}={BATCH_ENV[key]}\n' for key in missing)

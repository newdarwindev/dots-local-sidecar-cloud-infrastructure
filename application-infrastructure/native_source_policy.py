"""Exact native-origin gate patch; no receiver, content capture or live I/O."""
import copy

VERSION = '0.167.0'
ORIGINS = ('codex_work_desktop', 'codex_cli_rs', 'codex-app-server')
VERSION_DROP = f'resource.attributes["service.version"] != "{VERSION}"'
OLD_GATE = {'error_mode': 'propagate', 'traces': {'span': [
    VERSION_DROP,
    'resource.attributes["service.name"] != "codex_work_desktop"',
    'instrumentation_scope.name != "codex_work_desktop"',
]}}


def source_gate():
    """Missing/unknown identities fail closed; only exact same-origin pairs pass."""
    pairs = ' or '.join(
        f'(resource.attributes["service.name"] == "{name}" and '
        f'instrumentation_scope.name == "{name}")' for name in ORIGINS)
    return {'error_mode': 'propagate', 'traces': {'span': [
        'resource.attributes["service.version"] == nil', VERSION_DROP,
        'resource.attributes["service.name"] == nil',
        f'not ({pairs})',
    ]}}


def patch_config(config):
    """Return a copy changing ONLY a recognized native filter/source gate.

    Caller owns private input/output handling. Never print the resulting config,
    credentials, or TLS material. This helper performs no filesystem/network I/O.
    """
    try:
        gate = config['processors']['filter/source']
        pipelines = config['service']['pipelines']
        processors = pipelines['traces']['processors']
    except (KeyError, TypeError) as error:
        raise ValueError('unrecognized native configuration structure') from error
    if (not isinstance(processors, list) or set(pipelines) != {'traces'}
            or processors.count('filter/source') != 1):
        raise ValueError('expected one native trace-only source gate')
    if gate != OLD_GATE and gate != source_gate():
        raise ValueError('unrecognized native source gate; manual review required')
    result = copy.deepcopy(config)
    result['processors']['filter/source'] = source_gate()
    return result

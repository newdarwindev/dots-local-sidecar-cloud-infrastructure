"""Fixed nonsecret merge components; never reads private configuration or applies it."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_log_diagnostic_policy as policy


def render(config):
    if not isinstance(config, dict) or config != {}:
        raise ValueError('Only an empty object is accepted')
    base = policy.BASE_RENDER({}, [])
    merged = policy.merge(base, {}, [])
    return {
        'processors': {key: value for key, value in merged['processors'].items() if key not in base['processors']},
        'connectors': {key: value for key, value in merged['connectors'].items() if key not in base['connectors']},
        'pipelines': {key: value for key, value in merged['service']['pipelines'].items() if key not in base['service']['pipelines']},
        'prepend_content_processor': 'filter/content_parser_guard',
        'existing_receiver': 'otlp/native_messages',
        'existing_exporter': 'otlphttp/rich',
    }

#!/usr/bin/env python3
"""Offline, non-executing repository lint with explicit coverage and fail-closed tools."""
import configparser
import hashlib
import json
import math
import plistlib
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from urllib.parse import unquote, urlsplit

import hcl2
from markdown_it import MarkdownIt
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {'.git', '.runtime', 'runtime', 'artifacts', 'rendered', '__pycache__', 'node_modules', '.venv'}
TOOLS = ('hadolint', 'shellcheck', 'ruff', 'yamllint', 'actionlint', 'biome', 'kubeconform', 'helm')
SHA256 = re.compile(r'[a-f0-9]{64}')
COMMIT = re.compile(r'[a-f0-9]{40}')
TLS_DIRECTORY = Path('application-infrastructure/tokscale/fixtures/tls-public')
TLS_FILES = {'ca1-cert.pem.fixture', 'ca2-cert.pem.fixture', 'agent1-cert.pem.fixture',
             'agent1-key.pem.fixture', 'LICENSE.node'}
# Bind the exception to the previously reviewed Node.js public-test provenance,
# not merely a mutable adjacent manifest that could relabel a new private key.
TLS_PROVENANCE_SHA256 = '05d42956dd27a759f51034d652e4bb1daeadeccb299c83f073f46c0862fd95f0'


class LintError(ValueError):
    """An actionable repository policy violation, not a skipped check."""


def require_tools(names=TOOLS):
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise LintError('Required tools missing: ' + ', '.join(missing) + '; rebuild validation/Dockerfile')


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LintError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def reject_constant(value):
    raise LintError('non-finite JSON number: ' + value)


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise LintError('overflowing/non-finite JSON number: ' + value)
    return number


def strict_json(text):
    return json.loads(text, object_pairs_hook=unique_pairs, parse_constant=reject_constant,
                      parse_float=finite_float)


class UniqueLoader(yaml.BaseLoader):
    """BaseLoader keeps GitHub `on` and YAML 1.2-style scalars unambiguous."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise LintError(f'duplicate/non-string YAML key at line {key_node.start_mark.line + 1}: {key}')
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def strict_yaml(text):
    return list(yaml.load_all(text, Loader=UniqueLoader))


def file_kind(path):
    if path.name == 'Dockerfile' or path.name.endswith('.Dockerfile') or path.name.startswith('Dockerfile.'):
        return 'docker'
    if path.name.endswith(('.yaml', '.yml', '.yaml.disabled', '.yml.disabled')):
        return 'yaml'
    if path.name in {'.gitignore', '.dockerignore'} or path.name.startswith('LICENSE'):
        return 'text'
    if path.name in {'local.dots.primary-start.plist.template',
                     'local.dots.primary-ui-homarr.plist.template',
                     'local.dots.primary-ui-argocd.plist.template',
                     'local.dots.primary-ui-openbao.plist.template'}:
        return 'plist'
    return {'.py': 'python', '.sh': 'shell', '.ts': 'typescript', '.tsx': 'typescript',
            '.json': 'json', '.md': 'markdown', '.hcl': 'hcl', '.service': 'systemd',
            '.toml': 'toml', '.txt': 'text', '.fixture': 'fixture'}.get(path.suffix)


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if path.is_symlink():
            raise LintError(f'{rel}: source symlinks require explicit review')
        if not path.is_file():
            continue
        kind = file_kind(path)
        if kind is None:
            raise LintError(f'{rel}: unclassified file; add intentional lint coverage, not a blanket exclusion')
        result.setdefault(kind, []).append(path)
    return result


def command(root, *args):
    print('+ ' + shlex.join(str(arg) for arg in args), flush=True)
    subprocess.run([str(arg) for arg in args], cwd=root, check=True)


def lint_commands(root, files):
    """Explicit filenames avoid tool-specific ignores silently hiding source files."""
    if files.get('docker'):
        yield ['hadolint', '--failure-threshold', 'warning', *files['docker']]
    if files.get('shell'):
        yield ['shellcheck', '--severity=style', '--norc', *files['shell']]
    if files.get('python'):
        yield ['ruff', 'check', '--no-cache', '--config', root / 'validation/ruff.toml', *files['python']]
    if files.get('yaml'):
        yield ['yamllint', '--strict', '--config-file', root / 'validation/yamllint.yml', *files['yaml']]
    workflows = [path for path in files.get('yaml', []) if
                 path.parent == root / '.github/workflows' or path.name.endswith('.yml.disabled')]
    if workflows:
        yield ['actionlint', '-shellcheck', shutil.which('shellcheck') or 'shellcheck', *workflows]
    if files.get('typescript'):
        yield ['biome', 'lint', '--config-path', root / 'validation/biome.json',
               '--error-on-warnings', *files['typescript']]


def check_docker_pins(root, paths, lock):
    for path in paths:
        stages = set()
        text = path.read_text()
        for number, line in enumerate(text.splitlines(), 1):
            if not re.match(r'^FROM\s', line, re.IGNORECASE):
                continue
            parts = shlex.split(line)
            source = parts[1]
            if source.startswith('--'):
                source = parts[2]
            if source.lower() not in stages and source != 'scratch':
                # Only this existing build contract supplies a lock-checked ARG.
                if source == '${BUN_IMAGE}' and path == root / 'application-infrastructure/tokscale/Dockerfile':
                    pass
                elif not re.fullmatch(r'[^\s@]+@sha256:[a-f0-9]{64}', source):
                    raise LintError(f'{path.relative_to(root)}:{number}: external FROM must use a full digest')
            if len(parts) >= 4 and parts[-2].upper() == 'AS':
                stages.add(parts[-1].lower())
        if '/validation/' in '/' + str(path.relative_to(root)) and lock['baseImage']['reference'] not in text:
            raise LintError(f'{path.relative_to(root)}: Python validation base differs from tools.lock.json')


def check_lock_values(value, location):
    if isinstance(value, list):
        for index, child in enumerate(value):
            check_lock_values(child, f'{location}[{index}]')
    if not isinstance(value, dict):
        return
    for key, child in value.items():
        label = f'{location}.{key}'
        if key in {'sha256', 'originalSha256', 'preparedTreeSha256'}:
            if not isinstance(child, str) or not SHA256.fullmatch(child):
                raise LintError(label + ': expected full lowercase SHA256')
        if key in {'digest', 'platformDigest'}:
            if not isinstance(child, str) or not re.fullmatch(r'sha256:[a-f0-9]{64}', child):
                raise LintError(label + ': expected immutable image digest')
        if key in {'commit', 'revision'}:
            if not isinstance(child, str) or not COMMIT.fullmatch(child):
                raise LintError(label + ': expected immutable Git commit')
        if key == 'url':
            if not isinstance(child, str) or not child.startswith('https://') or 'sha256' not in value:
                raise LintError(label + ': downloadable artifact requires HTTPS and SHA256')
        if key == 'files' and isinstance(child, dict):
            for filename, item in child.items():
                if isinstance(item, str) and not SHA256.fullmatch(item):
                    raise LintError(label + '.' + filename + ': expected file SHA256')
        check_lock_values(child, label)


def check_collector_pin(root):
    item = strict_json((root / 'application-infrastructure/images.lock.json').read_text())['images']['collector']
    def docker_hub_alias(reference):
        return reference.removeprefix('registry-1.docker.io/').removeprefix('docker.io/')
    expected = docker_hub_alias(item['tagReference'].rsplit(':', 1)[0] + '@' + item['digest'])
    for relative in ('validation/Dockerfile', 'application-infrastructure/validation/Dockerfile'):
        sources = re.findall(r'^FROM (\S+) AS collector$', (root / relative).read_text(), re.MULTILINE)
        if [docker_hub_alias(source) for source in sources] != [expected]:
            raise LintError(relative + ': Collector binary source differs from authoritative image lock')


def check_requirements(root, lock):
    for path in sorted(root.rglob('*requirements*.txt')):
        lines = path.read_text().replace('\\\n', '').splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)\s+--hash=sha256:([a-f0-9]{64})', line)
            if not match:
                raise LintError(f'{path.relative_to(root)}: require exact version and wheel hash, no URLs/options')
            name, version, digest = match.groups()
            item = lock['pythonPackages'].get(name)
            if item is None or (version, digest) != (item['version'], item['sha256']):
                raise LintError(f'{path.relative_to(root)}: package pin differs from tools.lock.json: {name}')


def check_workflow_pins(path):
    def visit(value):
        if isinstance(value, list):
            for child in value:
                visit(child)
        if not isinstance(value, dict):
            return
        if 'uses' in value:
            ref = value['uses']
            if not re.fullmatch(r'[^\s@]+@[a-f0-9]{40}', ref):
                raise LintError(f'{path}: action/reusable workflow must use a full commit SHA: {ref}')
        for child in value.values():
            visit(child)
    for document in strict_yaml(path.read_text()):
        visit(document)


def check_fixtures(root, paths):
    directory = root / TLS_DIRECTORY
    provenance_path = directory / 'provenance.json'
    if hashlib.sha256(provenance_path.read_bytes()).hexdigest() != TLS_PROVENANCE_SHA256:
        raise LintError('TLS public provenance changed; review exact upstream source and file hashes')
    provenance = strict_json(provenance_path.read_text())
    if set(provenance['files']) != TLS_FILES:
        raise LintError('TLS fixture exception inventory changed; exact public filenames need review')
    for name, digest in provenance['files'].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise LintError(f'{TLS_DIRECTORY / name}: public fixture checksum mismatch')
    approved = {TLS_DIRECTORY / name for name in TLS_FILES}
    for path in paths:
        rel = path.relative_to(root)
        if path.suffix == '.fixture' and rel not in approved:
            raise LintError(f'{rel}: fixture suffix is not a blanket secret exception')
        if re.search(r'^-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s*$', path.read_text(), re.MULTILINE):
            if rel not in approved:
                raise LintError(f'{rel}: private-key material outside exact verified public test fixture')


def headings(text):
    counts, anchors = {}, set()
    tokens = MarkdownIt().parse(text)
    for index, token in enumerate(tokens):
        if token.type != 'heading_open':
            continue
        inline = tokens[index + 1]
        title = ''.join(child.content for child in inline.children or [] if child.type in {'text', 'code_inline'})
        slug = re.sub(r'[^\w\- ]', '', title.lower()).replace(' ', '-')
        number = counts.get(slug, 0)
        counts[slug] = number + 1
        anchors.add(slug if number == 0 else f'{slug}-{number}')
    anchors.update(re.findall(r'<a\s+(?:name|id)=["\']([^"\']+)', text))
    return anchors


def check_markdown(root, path):
    for token in MarkdownIt().parse(path.read_text()):
        for child in token.children or []:
            target = child.attrGet('href') if child.type == 'link_open' else child.attrGet('src') if child.type == 'image' else None
            if target is None:
                continue
            parts = urlsplit(target)
            if parts.scheme or parts.netloc:
                continue  # Offline check: no HTTP requests and no reachability claim.
            destination = (path.parent / unquote(parts.path)).resolve() if parts.path else path
            if not destination.is_relative_to(root.resolve()) or not destination.exists():
                raise LintError(f'{path.relative_to(root)}: missing/out-of-tree local link: {target}')
            if parts.fragment and destination.suffix == '.md' and unquote(parts.fragment) not in headings(destination.read_text()):
                raise LintError(f'{path.relative_to(root)}: missing Markdown heading anchor: {target}')


def check_systemd(path):
    # Syntax and this repository's declared unit contract only. Does not run
    # systemd-analyze, load a unit, resolve an executable or start a service.
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_string(path.read_text())
    allowed = {
        'Unit': {'Description', 'After', 'Wants'},
        'Service': {'Type', 'ExecStart', 'Restart', 'RestartSec', 'KillMode', 'Delegate',
                    'LimitNOFILE', 'LimitNPROC', 'LimitCORE', 'TasksMax'},
        'Install': {'WantedBy'},
    }
    if set(parser.sections()) != set(allowed):
        raise LintError(f'{path}: expected Unit/Service/Install sections')
    for section, keys in allowed.items():
        if set(parser[section]) - keys:
            raise LintError(f'{path}: unknown directive in {section}; extend reviewed unit contract')
    if not parser['Service'].get('ExecStart', '').startswith('/'):
        raise LintError(f'{path}: ExecStart must be explicit and absolute')


def main():
    if not Path('/.dockerenv').exists():
        raise SystemExit('BLOCKED: run sh validation/run.sh lint; no host fallback.')
    require_tools()
    files = inventory(ROOT)
    print('Coverage: ' + ', '.join(f'{kind}={len(paths)}' for kind, paths in sorted(files.items())))
    for args in lint_commands(ROOT, files):
        command(ROOT, *args)
    lock = strict_json((ROOT / 'validation/tools.lock.json').read_text())
    for path in files.get('json', []):
        value = strict_json(path.read_text())
        if path.name.endswith('.lock.json'):
            check_lock_values(value, str(path.relative_to(ROOT)))
    for path in files.get('yaml', []):
        strict_yaml(path.read_text())
        if path.parent == ROOT / '.github/workflows' or path.name.endswith('.yml.disabled'):
            check_workflow_pins(path)
    for path in files.get('plist', []):
        plistlib.loads(path.read_bytes())
    for path in files.get('toml', []):
        tomllib.loads(path.read_text())
    for path in files.get('hcl', []):
        hcl2.loads(path.read_text())
    for path in files.get('systemd', []):
        check_systemd(path)
    for path in files.get('markdown', []):
        check_markdown(ROOT, path)
    check_docker_pins(ROOT, files.get('docker', []), lock)
    check_collector_pin(ROOT)
    check_requirements(ROOT, lock)
    check_fixtures(ROOT, [path for paths in files.values() for path in paths])
    print('PASS: source lint, strict structure, immutable pins, public fixture integrity and local docs links')


if __name__ == '__main__':
    try:
        main()
    except (LintError, ValueError, OSError, subprocess.CalledProcessError, yaml.YAMLError) as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        raise SystemExit(1) from error

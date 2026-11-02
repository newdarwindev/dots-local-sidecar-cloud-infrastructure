"""Exact repository/digest allowlist for all rendered container image fields."""
import re


def canonical_image(reference):
    if not isinstance(reference, str) or not re.fullmatch(r'[^\s@]+@sha256:[0-9a-f]{64}', reference):
        raise ValueError('image digest unresolved')
    repository, digest = reference.split('@')
    # Remove a tag only from the final path component (not a registry port).
    head, separator, tail = repository.rpartition('/')
    tail = tail.split(':', 1)[0]
    repository = head + separator + tail
    first = repository.split('/')[0]
    if '/' not in repository or not ('.' in first or ':' in first or first == 'localhost'):
        repository = 'docker.io/' + repository
    repository = re.sub(r'^registry-1\.docker\.io/', 'docker.io/', repository)
    if repository.startswith('docker.io/') and repository.count('/') == 1:
        repository = 'docker.io/library/' + repository.split('/', 1)[1]
    return repository + '@' + digest


def locked_image(item):
    if item.get('status') != 'resolved':
        raise ValueError('unresolved image lock')
    return canonical_image(item['tagReference'] + '@' + item['digest'])


def container_images(value):
    """Walk every nested pod template, including init/ephemeral and hook containers."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {'containers', 'initContainers', 'ephemeralContainers'}:
                if not isinstance(child, list):
                    raise ValueError('malformed container list')
                for container in child:
                    if not isinstance(container, dict):
                        raise ValueError('malformed container')
                    yield container.get('image')
            else:
                yield from container_images(child)
    elif isinstance(value, list):
        for child in value:
            yield from container_images(child)


def validate_images(documents, lock, collector_source=None):
    allowed = {locked_image(item) for item in lock['images'].values()}
    images = [canonical_image(image) for image in container_images(documents)]
    if not images:
        raise ValueError('no rendered container images')
    if any(image not in allowed for image in images):
        raise ValueError('rendered image outside reviewed repository/digest allowlist')
    if collector_source is not None:
        expected = locked_image(lock['images']['collector'])
        if canonical_image(collector_source) != expected:
            raise ValueError('copied Collector binary source differs from image lock')
        workloads = [obj for obj in documents if obj.get('kind') == 'Deployment'
                     and obj.get('metadata', {}).get('name') == 'otel-collector']
        if len(workloads) != 1:
            raise ValueError('expected exactly one Collector deployment')
        actual = [canonical_image(image) for image in container_images(workloads)]
        if actual != [expected]:
            raise ValueError('rendered Collector differs from copied binary source')
    return images

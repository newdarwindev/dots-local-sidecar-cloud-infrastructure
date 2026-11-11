FROM otel/opentelemetry-collector-contrib@sha256:7f22d2a6748110ffb6a59bc0df448bccbf501cdb667d610ede4c61d3863d5849 AS collector
FROM caddy@sha256:834468128c7696cec0ceea6172f7d692daf645ae51983ca76e39da54a97c570d AS caddy
FROM python:3.14.0-slim-bookworm@sha256:d13fa0424035d290decef3d575cea23d1b7d5952cdf429df8f5542c71e961576
WORKDIR /repo
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    RUFF_CACHE_DIR=/tmp/ruff
COPY validation/requirements.txt validation/tools.lock.json validation/install_tools.py /repo/validation/
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r validation/requirements.txt \
    && python validation/install_tools.py
COPY --from=collector /otelcol-contrib /usr/local/bin/otelcol-contrib
COPY --from=caddy /usr/bin/caddy /usr/local/bin/caddy
COPY . /repo
RUN python primary-infrastructure/validation/install_helm.py
USER 65532:65532
ENTRYPOINT ["python", "validation/check.py"]
CMD ["lint"]

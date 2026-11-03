FROM otel/opentelemetry-collector-contrib@sha256:7f22d2a6748110ffb6a59bc0df448bccbf501cdb667d610ede4c61d3863d5849 AS collector
FROM python:3.14.0-slim-bookworm@sha256:d13fa0424035d290decef3d575cea23d1b7d5952cdf429df8f5542c71e961576
COPY --from=collector /otelcol-contrib /usr/local/bin/otelcol-contrib
WORKDIR /work
COPY validation/runtime-requirements.txt /work/validation/runtime-requirements.txt
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r validation/runtime-requirements.txt
COPY primary-infrastructure /work/primary-infrastructure
RUN python primary-infrastructure/validation/install_helm.py
COPY application-infrastructure /work/application-infrastructure
ENTRYPOINT ["python", "application-infrastructure/validation/check.py"]

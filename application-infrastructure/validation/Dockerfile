FROM otel/opentelemetry-collector-contrib@sha256:7f22d2a6748110ffb6a59bc0df448bccbf501cdb667d610ede4c61d3863d5849 AS collector
FROM python:3.14.0-slim-bookworm
COPY --from=collector /otelcol-contrib /usr/local/bin/otelcol-contrib
WORKDIR /work
RUN pip install --no-cache-dir PyYAML==6.0.3
COPY primary-infrastructure /work/primary-infrastructure
RUN python primary-infrastructure/validation/install_helm.py
COPY application-infrastructure /work/application-infrastructure
ENTRYPOINT ["python", "application-infrastructure/validation/check.py"]

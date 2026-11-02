FROM python:3.14.0-slim-bookworm
WORKDIR /work
RUN pip install --no-cache-dir PyYAML==6.0.3
COPY primary-infrastructure /work/primary-infrastructure
RUN python primary-infrastructure/validation/install_helm.py
COPY application-infrastructure /work/application-infrastructure
ENTRYPOINT ["python", "application-infrastructure/validation/check.py"]

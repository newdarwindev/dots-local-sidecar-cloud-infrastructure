FROM python:3.14.0-slim-bookworm@sha256:d13fa0424035d290decef3d575cea23d1b7d5952cdf429df8f5542c71e961576
WORKDIR /work
COPY validation/runtime-requirements.txt /work/validation/runtime-requirements.txt
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r validation/runtime-requirements.txt
COPY primary-infrastructure /work/primary-infrastructure
RUN python primary-infrastructure/validation/install_helm.py
ENTRYPOINT ["python", "primary-infrastructure/validation/check.py"]

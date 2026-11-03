# Repository validation

Run linting, tests, schema checks and tool installation only through the committed
Docker entrypoint. Never start Docker/a daemon to bypass an unavailable runtime.
No host Python/Node/tool fallback, deployment, credentials, live target access,
CI enablement or persistent jobs. Public dependency downloads are allowed only
in the build and explicitly networked contract stages. Static lint is offline.

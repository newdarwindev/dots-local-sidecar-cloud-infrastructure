# Diagnostic attribution and CLI batching

## Collector labels

`formation_settings.py` changes two statements in a recognized standard Collector
privacy processor. It retains only privately reviewed fixed environment labels;
unknown, missing or non-string labels use the existing default. Labels are metadata,
not authenticated identity or access grants. Unexpected rules fail closed.

Apply to the current configuration, never replace a live multi-pipeline Collector
with the older example. Preserve TLS, endpoints, receiver/memory limits and queues.
Run the pinned Collector's Docker test before activation. With current approval,
restart only the affected Collector and report its ingestion gap. In-memory data
may be lost; this does not provide durable replay or complete delivery.

## Native CLI startup

`cli-batching.env.txt` contains the two upstream SDK settings for Codex's native
`$CODEX_HOME/.env` loader (default `~/.codex/.env`). `batching_dotenv` prepares them
idempotently and rejects conflicts, duplicate keys and other existing content.
It does not interpret arbitrary dotenv syntax or rewrite secrets.

- Test the installed binary with an isolated file; upstream main can change.
- Add only these keys to the user's private startup file. Do not overwrite a
  changed file, follow symlinks or weaken existing permissions.
- Verify a new launch with these variables removed from its parent environment.
  Do not restart active sessions or change inherited-variable precedence.
- No wrappers, managed-symlink replacement, signed-app edits or global shell
  exports. New Codex processes may pass the variables to their own children.

Batch size one avoids combining spans into oversized requests; a single oversized
span can still fail. Receiver limits, authentication, privacy rules and protocol
stay unchanged. Binary OTLP did not resolve the observed size error. No native
TOML batch-size key is documented; do not invent one.

Validate with `sh validation/run.sh application`. Offline tests are not live client
qualification: require exact backend record IDs, not timestamp-only correlation.
Keep credentials, host identities, configuration and live receipts outside Git.

Source: [Codex startup loader](https://github.com/openai/codex/blob/main/codex-rs/arg0/src/lib.rs).

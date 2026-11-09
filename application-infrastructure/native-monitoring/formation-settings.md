# Bounded diagnostic attribution and CLI batching

`formation_settings.py` renders two statement changes in an existing standard
Collector privacy processor. Supply only privately reviewed fixed environment
labels. It preserves no arbitrary names, paths, content, credentials or session
IDs. Unknown, missing and non-string labels map to the existing fixed default.
Source labels are metadata, not authenticated machine identity or access grants.
The helper rejects unexpected rules instead of rebuilding unrelated pipelines.
Apply it to current configuration rather than replacing a live multi-pipeline
Collector with the older single-pipeline example manifest.

The exact pinned Collector must pass the Docker-only runtime test before any
activation. Preserve TLS, endpoints, receiver limits, memory limits and queues.
Restart only the affected Collector after reporting the short ingestion gap.
In-memory queues may lose data; no complete-delivery or durable-replay claim.

`cli-batching.env.txt` uses upstream SDK variables verified with bounded
native CLI probes. Codex's upstream `arg0` startup loads `$CODEX_HOME/.env`
(default `~/.codex/.env`) before creating runtime threads. This is the selected
Codex-only launch mechanism. No executable, symlink, shell profile, signed app
bundle or global environment needs changing. New Codex processes can pass these
variables to their own children; unrelated applications are not modified.
They affect new processes, not existing sessions. Batch size one avoids combining
many spans into an oversized request; a single oversized span can still fail.
The existing receiver size cap remains in force. Do not widen it silently.

The current official Codex configuration reference documents exporter routing and
TLS but no native TOML batch-size key. Do not invent one. Do not replace managed
CLI symlinks with wrappers, modify signed app bundles, or export these variables
for all user applications. Use `batching_dotenv` to prepare the two exact settings. It is idempotent and
rejects conflicts, duplicate keys and other existing dotenv content instead of
rewriting secrets or interpreting arbitrary syntax. The example is not itself
a deployment. Activate only after the installed binary loads an isolated test
file successfully; then add the two keys to that user's Codex startup file,
without overwriting a changed file or following a symlink. Use a private new file
mode and preserve existing permissions. Keep configuration outside Git. Do not
restart active Codex sessions; verify new launches with batch variables removed
from the parent environment. Do not alter existing inherited variable precedence.

Source: [Codex native startup loader](https://github.com/openai/codex/blob/main/codex-rs/arg0/src/lib.rs).
Installed versions must still be tested because upstream main can change.
Native binary OTLP was also tested, but did not resolve the size error, so the
protocol remains unchanged. The receiver cap, authentication and privacy rules
are unchanged by batching. Exact backend IDs are proof only for records actually
read back; timestamps alone do not prove a session-to-trace mapping.

Validation: `sh validation/run.sh application`. No credentials or host identities
belong in this source tree. Runtime readback and native client coverage remain
separate from offline tests.

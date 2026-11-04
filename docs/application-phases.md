# Current application phase

The [operator setup guide](../application-infrastructure/README.md) is the current
source of truth: selected-cluster Langfuse/dependencies/S3, OTel, Tokscale with its
own PostgreSQL and independent `homarr-workload`. All are staged, not deployed.

Primary management, Authentik, OpenBao/ESO and shared domains remain
[later proposals](auth-domain-plan.md), not prerequisites. Exact host identity and
capacity stay private; hypothetical compatibility is not readiness or consent.

## AgentsView workstation archive — plan only (2026-11-04)

Add a separate local-first AgentsView workstream alongside, not inside or in place
of, the selected application cluster. The exact owner-selected workstation mapping
belongs in the private fleet placement record. **No installation, import, source
enrollment, credentials, scheduled jobs or deployment is performed by this plan.**
The existing workflow/budget pause and application readiness gates remain intact.

### Proposed architecture and source boundaries

Use a native macOS installation under the workstation owner's account, with a
version-pinned official release selected at activation. Verify architecture,
available storage/RAM, encrypted storage, OS compatibility and sleep/wake behavior.
Keep the UI loopback-only; a dashboard link must not expose the archive. Do not add
a public tunnel, shared ingress, remote database or fleet-wide mount.

Upstream offers a bundled macOS app/CLI, including ARM64 builds. Desktop and CLI
share a local SQLite archive and assets; foreground serving also discovers and
watches session sources. First launch of the macOS app requires a graphical login.
Review the pinned release's exact startup behavior before use: some CLI operations
start a detached daemon. See [official quick start](https://www.agentsview.io/docs/quickstart/).

Treat these as separate source classes, with an explicit allowlist before ingestion:

- Authorized local coding-agent histories: verify the installed version's parsers
  and only permitted source roots. Product support is not permission to read a
  protected directory. Never bypass an environment denial or ingest credentials.
- User-supplied ChatGPT ZIP exports: supported import using
  `agentsview import --type chatgpt <approved-export.zip>`; preserve the original.
- Claude.ai exports and Gemini Apps Takeout: optional, separately scoped inputs.
  Gemini import is CLI-only and does not reconstruct full multi-turn chats.
- ChatGPT dot/Codex web/cloud tasks: a distinct upstream `codex-cloud` source,
  **disabled in this baseline**. It uses existing Codex login material and private
  OpenAI endpoints, not a documented public export API. Enabling it requires a
  separate credential/access review. Do not change keychain storage to a plaintext
  credential file to make it work. Keep live-token capture off: upstream warns it
  can affect hosted chat state. The dot's main conversation is not imported by this
  source. See [configuration and limits](https://www.agentsview.io/docs/configuration/#codex-cloud).

### Export and import automation proposal

1. **Provider export remains a user step.** Request ChatGPT data through Settings
   or the Privacy Portal, then download from the notification while signed into
   the matching account. OpenAI says exports can take up to seven days and download
   links expire after 24 hours. Managed-workspace availability varies; unavailable
   exports need the workspace's approved data-access route. This plan assumes no
   supported unattended consumer-export API, does not scrape private endpoints,
   and does not promise a complete automatic export of every chat surface.
   [OpenAI export guidance](https://help.openai.com/en/articles/7260999-exporting-your-chatgpt-history-and-data).
2. **Proposed local intake, after separate execution approval:** the user places
   an approved completed export in a private inbox outside all repositories. A
   bounded importer checks file stability, provider/schema, archive size, safe ZIP
   paths and free space; records a checksum and provenance; imports through the
   supported CLI; then stores a result/checkpoint with imported, updated, unchanged,
   refused and failed counts. Serialize writes and retain originals, attachments
   and all receipts. A checksum prevents repeated processing of the same artifact;
   conversation IDs handle overlap between different exports.
3. **No silent replacement:** upstream ChatGPT re-import skips unchanged records
   and accepts compatible extensions, but divergent or shorter histories can be
   refused. Quarantine the receipt for review; never automatically use `--replace`.
   Retry transient failures with bounded backoff, not permanent schema/refusal
   errors. See [chat import semantics](https://www.agentsview.io/docs/chat-import/).
4. **Proposed scheduling:** after a successful manual trial and explicit approval,
   an owner-operated launchd job could scan only the approved inbox at a chosen
   cadence and catch up on wake. No scheduler definition is installed or enabled
   here. Sleep/offline periods must show stale status rather than success. Demo
   repository persistent jobs remain an owner-performed action.
5. **Archive export and recovery:** preserve the source export separately from the
   searchable archive. Plan consistent database-plus-assets snapshots, checksum
   manifests and an encrypted recovery destination selected by the owner. A live
   SQLite file copy alone is not a verified backup. Test restoration into an
   isolated archive without touching the original. Metadata reporting through
   `agentsview export sessions` is not a full conversation backup; its schema must
   be checked before a consumer accepts it.
   [Session export reference](https://www.agentsview.io/docs/session-export/).

### Privacy, acceptance and rollback gates

Keep raw chats, images, titles, identifiers, checkpoints, private paths and account
information out of Git, Slack receipts, cluster telemetry and public dashboards.
Allow only reviewed aggregate counts in operational reports. Do not enable Gist
publishing, hosted sync, remote embeddings or external insights for this archive.
Review telemetry/update-check behavior explicitly; local-first does not mean no
network traffic. Source histories, exports, archive assets and receipts are
always-preserve: no age/size cleanup or destructive retention policy.

Before activation: record the selected release/checksum, exact source scope,
local access boundary, private data location, capacity budget, backup custody and
approved execution mode. Validate with synthetic fixtures first: first import,
same-file repeat, overlapping export, divergence/shorter refusal, malformed and
unsafe ZIP, interrupted run, disk-full failure, sleep/wake and restore. Compare
counts and representative content/attachments privately; flag unsupported records
and unknown coverage. A searchable import is not proof of complete provider data.

Stop/rollback means stop the approved worker, disable only its approved schedule,
and retain originals plus the last good archive and failure receipts. Restore only
from a verified consistent snapshot after a reviewed decision. Do not remove source
chats, change account security or replace an archive automatically. Deployment and
runtime validation remain **NOT RUN**; documentation publication is not activation.

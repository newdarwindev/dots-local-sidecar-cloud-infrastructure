# Draft: OpenBao auto-unseal and seal migration

**Design review only. Not approved for activation, not a tested migration.**
This document changes no values, credentials, services or scheduled jobs. Keep
the current manual procedure until the decision record, rehearsal and execution
approvals below are complete. Do not automate submission of Shamir shares.

## Baseline and scope

The [reference values](../values/openbao.yaml) pin OpenBao 2.7.2 with one
TLS-protected Raft replica, persistent data/audit volumes and no `seal` stanza.
The [bootstrap plan](../README.md) specifies three Shamir shares, threshold two.
These are repository facts, not a claim about any host's current state. Before
execution, verify the running image/digest, storage identity and seal status
privately. Keep host inventory, account IDs and recovery locations out of Git.

Goal: after a separately approved migration, an ordinary OpenBao process restart
can unlock the same stored data through a trusted seal provider without an
operator submitting shares. This does not start a stopped Mac/VM, survive Mac
sleep, make a one-node cluster highly available, or establish application health.

## Proposed direction and alternatives

**First candidate: a dedicated Transit seal on an independently operated
OpenBao provider.** Transit is built into 2.7.2. This is a candidate, not evidence
that such a provider already exists. Do not create one as part of documentation.
Its host, storage, initial unlock, DNS, network, authentication and recovery must
not depend on this primary OpenBao instance or services that need its secrets.
Another pod in the same VM does not satisfy this design's independence goal.

- **External KMS/HSM:** evaluate if an already approved service and suitable
  machine identity exist. Several formerly built-in seals became external
  plugins in 2.7; select and checksum-pin the exact compatible ARM64 plugin and
  image before proposing installation. No cloud resource, paid service or new
  access grant is approved here. See [2.7 seal configuration][seal-config].
- **Static seal:** built in, but consider it only with an independently
  controlled secret source and an explicit threat-model review. A seal key next
  to the encrypted data is not equivalent to an independent KMS. Do not replace
  Shamir shares with a plaintext key in this repository, chart values, a local
  script or a launchd job. See [static seal guidance][static-seal].
- **Remain on Shamir:** the default if independent custody, bootstrap, recovery
  or recurring availability cannot be demonstrated. The
  [manual terminal procedure](manual-openbao-unseal-macos.md) remains valid for
  the existing Shamir state, not as a bypass for a failed auto-seal provider.

## Threat model and dependency review

Review both confidentiality and availability before choosing convenience:

1. A compromised workload must not gain access to the seal-provider credential.
   Kubernetes/node/host administrators and authorized pod-exec users can often
   access credentials available to the OpenBao process. Auto-unseal does not
   protect against those administrators or a compromised running server.
2. Theft of encrypted disks must not also yield everything needed to decrypt
   them. Examine the actual credential-delivery path and K3s encryption-key
   custody; merely storing a token in a Kubernetes Secret is not proof of this
   property. Distinguish offline disk theft from compromise of the live host.
3. Provider compromise plus access to the protected storage can undermine its
   encryption boundary. Use separate administration, least privilege and
   audited key lifecycle controls; provider access is a security boundary.
4. Provider outage, bad DNS, certificate expiry, token expiry, revoked access or
   missing old key versions can block the next start. An already-unsealed
   process is not evidence that its next restart will succeed. Avoid restarting
   it during a provider incident merely to test the hypothesis.
5. Reject dependency cycles: primary must not provide its own Transit key,
   authentication, provider credentials, TLS renewal or sole recovery access.
   ESO reading from primary cannot be the bootstrap source for its seal token.
   The same restriction applies to a provider requiring an IdP/DNS service that
   itself cannot start until primary is unsealed.

For an all-off cold start, prove this order privately: independent provider
storage/identity and network become available; provider unlocks through its own
approved mechanism; primary obtains its scoped provider credential; primary
starts and unseals; dependent applications start. A provider still using manual
Shamir moves the first human unlock elsewhere; it does not eliminate it.

## Transit design contract, not deployable configuration

Before preparing a deployable patch, record the chosen provider's verified TLS
origin and CA, dedicated mount/key, authorized administrators, machine-credential
delivery, renewal/expiry policy, availability target and recovery evidence in the
existing private operational records. Do not publish these details here.

The following is an **inert design sketch** with an invalid example hostname and
no credential or Secret manifest. It is not added to the active Helm values:

```hcl
seal "transit" {
  address         = "https://seal-provider.example.invalid:8200"
  key_name        = "primary-seal-example"
  mount_path      = "transit/"
  disable_renewal  = "false"
  tls_ca_cert     = "/openbao/seal-provider/ca.crt"
  tls_server_name = "seal-provider.example.invalid"
  tls_skip_verify = "false"
}
```

For the selected dedicated key, the client needs `update` on only its Transit
encrypt/decrypt paths, not key creation, deletion, configuration or arbitrary
secret access. Review a renewable orphan/periodic token and its self-renewal
permissions against the provider's policy. Periodic does not mean immortal:
long sleep/outage can exceed its renewal period. Define how an authorized owner
replaces an expired credential while primary remains sealed.

The 2.7.2 Transit interface accepts a token parameter or `BAO_TOKEN`; do not
invent a `token_file` option. A future implementation must choose a separately
approved secure injection route, never literal chart/Git values or shell
`export` commands. If runtime environment injection is selected, document its
exposure to pod/node administration. Do not inject Shamir/recovery shares.
No credential is generated, read or installed by this draft.

Keep inbound primary TLS and outbound provider TLS distinct. Review the image's
existing environment because it may override seal settings; do not dump it to
logs. Verify provider CA/hostname independently and keep TLS verification on.
The [version-pinned Transit documentation][transit] defines these parameters,
least-privilege paths, renewal considerations and old-key retention requirements.

## Approval gates before migration

Every item must have a named owner and current evidence. An approved document or
populated local approval file does not itself authorize its implementation.

- **Provider decision:** exact service/placement, key, plugin if any, costs,
  credential exposure and independence accepted. Any creation of identities,
  credentials, keys, access grants or security settings needs separate approval.
- **Recovery:** verify an existing encrypted, consistent pre-migration recovery
  point and restore path. If a new backup is needed, obtain explicit approval for
  that backup and its destination immediately before running it. Preparing this
  runbook does not authorize backup creation, transfer or scheduling.
- **Custody:** threshold holders have the existing shares for the correct
  cluster, independent of primary. Provider keys, their required versions and
  recovery access have independent custody and deletion protections.
- **Rehearsal:** demonstrate the exact 2.7.2 single-node Raft migration, restart
  and restore process in an approved isolated environment using synthetic data
  and synthetic credentials. Do not test failures against production first.
- **Change window:** owner approves the exact configuration diff, credential
  delivery, service interruption/restarts, bounded tests and recovery plan.
  Do not let GitOps revert the seal configuration; agree the controller plan
  without enabling sync or broadening controller permissions as a side effect.

## Proposed migration sequence after those gates

This adapts the upstream migration concept to the reference's **one replica**.
There is no standby to promote: schedule an outage. The exact stop/start and
manifest commands remain an implementation/rehearsal deliverable, not commands
to guess or execute from this design draft.

1. Recheck the intended storage/cluster, image, existing Shamir threshold,
   migration state and available key holders. Stop on a changed/uninitialized
   target or unexpected partial operation. If primary is sealed, any ordinary
   manual unlock needed for recovery preparation is a separate owner-run step.
2. Complete the approved recovery point and prove the independent provider is
   reachable and usable with the intended least-privilege identity. Verify the
   original seal material remains available. Do not create new primary storage.
3. In the approved outage, stop the sole OpenBao process safely, retain both
   PVCs, install only the reviewed seal configuration/credential references and
   restart the same deployment on the same Raft data. Do not run initialization,
   a key rotation, `operator migrate` storage migration, or a PVC replacement.
4. Confirm the expected migration state. The owner then uses a **separate private
   Terminal outside agent capture**, the manual runbook's TTY/TLS transport and
   the following keyless migration form, once per required distinct old share:

   ```sh
   primary_kubectl -n openbao exec -it openbao-0 -c openbao -- \
     env -i PATH=/bin:/usr/bin:/usr/local/bin HOME=/nonexistent \
     bao operator unseal -migrate -address=https://127.0.0.1:8200 \
     -ca-cert=/openbao/tls/ca.crt
   ```

   This is an owner-only step for an approved migration, not a command to run now.
   Enter shares only at the hidden prompt. Never put them in arguments,
   environment, pipes, files, screenshots, telemetry or chat. Do not mix ordinary
   and migration submissions or reset unexpected progress. The ordinary manual
   runbook's `migration: false` guard applies before migration; this step instead
   requires the specifically reviewed migration state.
5. Verify migration completion before any further change: initialized, unsealed,
   no migration in progress, expected new seal/recovery mode, same intended data
   and healthy Raft leadership/readiness. Review only necessary sanitized server
   evidence privately; do not paste complete logs into Git or chat.
6. Treat the original Shamir shares as recovery shares after successful
   migration; retain their protected custody and verify the resulting threshold.
   They are not a provider-independent fallback. Only after acceptance, perform
   the separately approved ordinary restart test without entering shares.

Upstream requires an outage, both seal mechanisms during migration and a
pre-migration backup; it converts old Shamir shares into recovery shares and
uses `operator unseal -migrate`. See [2.7.2 seal migration][seal-concepts].
The single-node adaptation above still needs the stated rehearsal.

## Acceptance evidence and failure tests

Record each check as **passed, failed, blocked or unrun**, with the tested
revision/version and a private evidence reference where needed. Publication,
successful rendering and a healthy current pod do not prove auto-unseal.

- **Normal restart:** the approved same-data process restart reaches
  `initialized: true`, `sealed: false`, `migration: false`, expected seal mode,
  healthy Raft leadership and pod readiness without share entry. Verify an
  approved synthetic canary and existing audit behavior, not private secrets.
- **Cold-start independence:** rehearsal starts from all intended components
  stopped and proves the dependency order, including provider bootstrap and
  credentials. A live primary must not be required to retrieve them.
- **Provider/TLS/authorization failures:** synthetic provider outage, invalid
  certificate, wrong key, expired/revoked token and insufficient policy must
  fail closed and produce actionable, sanitized diagnostics without fallback to
  Shamir automation, TLS bypass or broader privileges.
- **Renewal and long outage:** demonstrate renewal and credential replacement
  after a downtime exceeding the chosen token period. Test legitimate provider
  key rotation with old ciphertext/key-version availability preserved. Retain
  the default auto-seal health checks and review their sanitized failures as an
  early warning, not a reason to restart; see [2.7 seal settings][seal-config].
- **Recovery:** restore the approved recovery point in isolation with its
  matching seal dependencies; prove the planned reverse migration separately.
  Never delete the real key or revoke the only live credential as a test.
- **Telemetry boundary:** record only approved status, timings and error
  categories. Keep shares, tokens, headers, full environment, secret values and
  terminal input out of Langfuse, OpenTelemetry, audit exports and CI artifacts.
  This document does not configure any collector or expand capture.

## Stop, rollback and lockout handling

**Before changing storage seal state:** preserve evidence and use only the
rehearsed rollback plan. Do not assume a failed process made no state changes.

**After migration starts or completes:** a Git revert alone is not rollback.
The stored key wrapping may already have changed. Preserve data, both applicable
seal dependencies, recovery shares and logs; stop for an approved reverse
migration or isolated restore. Returning from auto-seal to Shamir requires the
old provider to work during migration, not simply deleting the seal stanza.

If the provider is unavailable, restore its approved access/availability first.
Recovery shares authorize recovery operations but cannot decrypt the root key
without the provider. Permanent loss of the required seal key can make the
cluster and its dependent backups unrecoverable. Do not destroy old versions,
reinitialize, rotate unrelated keys or repeatedly restart to try to escape this
dependency. See [seal lifecycle and migration requirements][seal-concepts].

## Draft validation and remaining decisions

- Reviewed reference values and version-pinned upstream 2.7.2 documentation.
- Read-only status was inspected privately; this public draft contains no host
  inventory, secret material, private endpoints or recovery locations.
- `sh validation/run.sh primary`: **blocked**, Docker daemon unavailable during
  draft preparation. No daemon was started and no host-tool fallback was used.
- No provider selected/provisioned, no credentials created, no deployment edits,
  no migration/share submission, no restart/failure test, and no restore performed.
  Runtime acceptance is **unrun**. Workflows remain unchanged.

Next decision: select an independently recoverable provider and credential
bootstrap design, or retain manual Shamir. Then commission the isolated rehearsal
and exact implementation patch. Do not treat this draft as deployment readiness.

[seal-concepts]: https://github.com/openbao/openbao/blob/v2.7.2/website/content/docs/concepts/seal.mdx
[transit]: https://github.com/openbao/openbao/blob/v2.7.2/website/content/docs/configuration/seal/transit.mdx
[seal-config]: https://openbao.org/docs/configuration/seal/
[static-seal]: https://openbao.org/docs/configuration/seal/static/

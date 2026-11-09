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

Read-only inspection on 2026-11-09 verified FileVault **On**, the dedicated
`primary` Lima guest **Running**, K3s **enabled/active**, and `openbao-0` on the
2.7.2 image (digest inspected privately). A token-free, CA-verified `bao status`
reported `initialized: true`, `sealed: true`, `type: shamir`, `t: 2`, `n: 3`,
`progress: 0`, `migration: false`, `recovery_seal: false`, and Raft. Sealed status
returned exit code 2. The installed `local.dots.primary-start` user LaunchAgent
starts the existing VM at login; K3s starts inside it. This is a
point-in-time observation, not a reboot test. Process names and launchd labels
showed no independent local seal provider, but absence is not conclusively
established by that inventory. The provider's binary, storage, identity, key,
credential, TLS and recovery path remain unverified.

Goal: after a separately approved migration, an ordinary OpenBao process restart
can unlock the same stored data through a trusted seal provider without an
operator submitting shares. This does not start a stopped Mac/VM, survive Mac
sleep, make a one-node cluster highly available, or establish application health.

## Proposed direction and alternatives

**Recommended future auto-unseal candidate: built-in Transit against a second,
dedicated OpenBao in a separate local Lima guest with its own persistent disk.**
Transit is built into 2.7.2. Give the provider its own Shamir seal and recovery
holders; an owner unlocks it privately before starting the primary guest after
each full host/guest restart. The provider must have no dependency on primary
OpenBao, its K3s, Argo CD, ESO, credentials, DNS, or application services. A
second pod in the primary VM would not meet this independence test. This design
uses supported OpenBao components and no cloud or second computer for normal
startup, but adds a service and moves the human unlock to that service. **It
does not offer unattended recovery after a Mac reboot.** If that is a firm
requirement, retain Shamir pending approval and proof of a genuinely independent
automatic key source. No such source has been verified on this Mac.

- **External KMS/HSM:** evaluate if an already approved service and suitable
  machine identity exist. Several formerly built-in seals became external
  plugins in 2.7; select and checksum-pin the exact compatible ARM64 plugin and
  image before proposing installation. No cloud resource, paid service or new
  access grant is approved here. See [2.7 seal configuration][seal-config].
- **Static seal fed by macOS Keychain:** built in and has no second server. It
  needs a separately designed and reviewed Keychain-to-guest delivery bridge,
  a reliable noninteractive access policy, memory-only guest/pod delivery, and
  ordering before K3s/OpenBao starts. None exists or is verified here. The
  current Lima guest has no host mounts. A key stored as a chart value,
  Kubernetes Secret or ordinary file alongside the Raft disk would collapse
  the offline theft boundary; K3s secrets encryption alone is insufficient if
  its key is recoverable from the same guest disk. FileVault helps while locked,
  but a logged-in host administrator or compromised host can access the bridge.
  Login Keychain availability before GUI login and unattended access after a
  reboot are **not assumed**. See [static seal guidance][static-seal].
- **Local PKCS#11 HSM:** may provide stronger key separation, but 2.7 requires
  an external KMS plugin, compatible ARM64 packaging, HSM and PIN custody,
  device availability through the guest, and tested cold-boot behavior. A
  software HSM on this same disk does not create an independent boundary. No
  suitable local device or plugin installation was verified.
- **Remain on Shamir:** the default if independent custody, bootstrap, recovery
  or recurring availability cannot be demonstrated. The
  [manual terminal procedure](manual-openbao-unseal-macos.md) remains valid for
  the existing Shamir state, not as a bypass for a failed auto-seal provider.

| Option | Cold boot after FileVault unlock | Custody and main failure | Other computer |
|---|---|---|---|
| Current Shamir | Owner logs in, primary VM starts, owner supplies two distinct shares | No provider dependency; share loss or unavailable holders blocks unlock | Not required for normal start; independent recovery copies are prudent |
| Separate local Transit provider (recommendation) | Owner logs in, starts provider guest, privately unseals it, then starts primary guest | Provider disk, key/version, TLS, token or availability failure blocks primary restart; Mac remains one physical failure domain | Not required for normal start; off-Mac recovery is prudent |
| Keychain-fed static | Could start after login if a new bridge and ordering pass tests | Static key exposure/lockout and custom delivery; no server outage | Not inherently required; independent key recovery still needed |
| Local PKCS#11 device | Only if device, plugin and PIN are ready before primary | Hardware loss, PIN lockout, plugin/device pass-through failure | Not inherently required; spare/recovery path needed |

Apple documents LaunchAgents as user-login jobs and LaunchDaemons as system
startup jobs; FileVault requires a human unlock at boot. The current primary
LaunchAgent therefore cannot establish pre-login service availability. A Mac
screen lock after a running login session is different from reboot or logout:
it should not itself restart the guests, but this must be tested. Sleep/power
loss still interrupts both guests. No option here makes this single Mac highly
available. See [Apple launchd][apple-launchd] and [FileVault][filevault].

## Concrete local Transit dependency and custody proposal

This is the **review target**, not an installed configuration:

1. Separately approve a pinned provider OpenBao release in a distinct Lima
   guest and storage directory. Size it against host memory and verify that its
   data and audit storage, TLS CA, and service identity remain recoverable if
   the primary guest/disk is lost. FileVault protects both guests at rest on
   this Mac; it does not separate them from a compromised logged-in host.
2. Keep the provider manually Shamir-sealed, with a dedicated Transit key and
   scoped encrypt/decrypt identity. Its shares, root administration and key
   version recovery must be held independently of primary. The primary's old
   shares must never unlock the provider or become its sole recovery path.
3. Choose a private guest-to-guest route and TLS name/CA that work before K3s,
   Argo CD, ESO and primary OpenBao. No primary-issued DNS, certificate, token,
   or secret may be needed. Verify route, host exposure and certificate renewal
   in an isolated rehearsal. Do not add public/listening host forwards by
   default.
4. Decide and review how the primary seal token is delivered. A namespace
   Secret is the simplest Kubernetes path but is readable by sufficiently
   privileged cluster/guest administrators and may be present in K3s storage;
   approve that exposure explicitly, including K3s encryption-key custody.
   A memory-only delivery design reduces persistence but adds startup machinery
   and must be proven before adoption. Neither route is selected yet. Token
   renewal and replacement must work while primary is sealed; the replacement
   authority must belong to the provider's independent administrators.
5. Replace the current login startup sequence only in a separately approved
   change: after FileVault unlock and GUI login, start/verify provider guest;
   authorized holder unlocks provider privately; prove Transit encrypt/decrypt
   with the scoped identity and trusted TLS; then start primary guest and let
   K3s/OpenBao start. The existing `local.dots.primary-start` auto-starts the
   primary guest at login, so it must be disabled or made dependent on a
   verified provider-ready gate **before** the production cutover. Merely
   launching the provider later fails the requested boot ordering. Use a bounded
   retry/stop policy, not an unverified race or a loop that hides lockout.

The exact provider image/digest, separate guest resources, route, certificate
authority, token delivery, startup change, recovery store and owner identities
are **open decisions** requiring a private implementation patch and rehearsal.
Do not infer that a login LaunchAgent alone solves unattended boot.

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
  and synthetic credentials. Include provider-first cold boot and reverse
  migration. Do not test failures against production first.
- **Change window:** owner approves the exact configuration diff, credential
  delivery, service interruption/restarts, bounded tests and recovery plan.
  Do not let GitOps revert the seal configuration; agree the controller plan
  without enabling sync or broadening controller permissions as a side effect.

Separate approvals are needed for installing/starting the provider guest,
initializing it, creating its shares and Transit key, issuing the scoped
credential, changing host/login startup and guest/network/security settings,
creating or testing a backup, changing the primary seal configuration, and the
production outage/share-entry/migration. The owner must review the exact patch,
target identities, custodians, timing and stop conditions before each action.

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
   original seal material remains available. Confirm the provider key version,
   provider's own recovery path, token expiry/renewal path and TLS origin without
   printing credentials. Do not create new primary storage.
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
   Confirm availability with the existing authorized holders out of band,
   without reading or copying shares into tooling. Keep their existing
   owner-controlled encrypted/offline custody, holder separation and access
   controls; do not put them into the provider, Kubernetes, the Mac startup
   path, Git, CI or agent logs. They are not a provider-independent fallback.
   Only after acceptance, perform the separately approved ordinary restart
   test without entering shares.

The pre-cutover record must identify the same Raft PVC/storage identity,
OpenBao image digest, chart revision, seal status/threshold, approved recovery
point and startup configuration. The implementation patch must show the exact
old/new seal stanzas, delivery reference and rollout diff. Reconcile GitOps
intent before stopping the sole pod. A successful CLI command or ready pod alone
does not establish that the intended data and audit trail survived.

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
  credentials. A live primary must not be required to retrieve them. On the
  actual Mac, use an owner-approved reboot test after FileVault unlock: before
  GUI login record that no user LaunchAgent/primary VM startup is expected;
  after login verify the provider guest is available first, holder unlocks it,
  scoped Transit access succeeds, and only then the primary guest starts.
  Record whether any step needed a second computer or interactive login.
- **Screen lock, logout and power behavior:** lock/unlock the Mac during an
  approved test and confirm neither process is unexpectedly resealed or
  restarted. Test logout and Mac sleep/wake separately; do not treat either as
  a cold boot. An owner-approved power-loss rehearsal must start from the
  FileVault prompt and repeat the provider-first sequence. Keep the screen-lock
  result separate from FileVault unlock.
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
- **Lockout:** in the synthetic rehearsal, withhold the provider guest, deny
  Transit, expire a test credential, and make a test key/version unavailable.
  Verify primary stays sealed after restart, no share-only bypass succeeds,
  diagnostics identify the failed dependency without leaking secrets, and
  restoring the dependency permits unseal. For production, simulate only a
  bounded, approved provider-unavailable condition with a proved recovery
  route; do not intentionally destroy or revoke live keys.
- **Telemetry boundary:** record only approved status, timings and error
  categories. Keep shares, tokens, headers, full environment, secret values and
  terminal input out of Langfuse, OpenTelemetry, audit exports and CI artifacts.
  This document does not configure any collector or expand capture.

## Stop, rollback and lockout handling

**Before changing storage seal state:** if preflight, provider, credential,
startup ordering, recovery point or TTY checks fail, do not submit `-migrate`
shares. Stop the rollout, restore the reviewed Shamir configuration and
login-startup arrangement if they were changed, and verify the same Raft data
remains sealed in Shamir mode. A clean config rollback is valid only when
evidence confirms migration never began. Preserve evidence and do not assume a
failed process made no storage changes.

**During partial migration:** stop further share submissions and rollout. Keep
the provider and its key/version/credential available, retain both PVCs and the
pre-migration recovery point, and record sanitized status. The owner follows
the rehearsed version-specific completion or restore branch; do not reset
progress, switch stanzas blindly, initialize or create a new Raft cluster.

**After migration completes:** a Git revert alone is not rollback. The stored
key wrapping has changed. For a planned reverse migration, retain the working
Transit provider and recovery shares, schedule another single-replica outage,
set the old Transit seal `disabled = "true"` in a reviewed config, restart the
same storage, and have authorized holders submit the required distinct recovery
shares with `bao operator unseal -migrate` in private terminals. Verify Shamir
seal type, threshold, data, audit and a separately approved restart/unseal
before retiring the provider. This path must first pass the synthetic rehearsal;
do not use these outline steps as production commands. If provider access is
permanently lost, reverse migration may be impossible. Use only a matching,
independently tested restore path; do not delete the provider or old key versions.

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
- `git diff --check`: passed for this revision.
- `sh validation/run.sh primary`: **blocked** on 2026-11-09 because the Docker
  daemon was unavailable. No daemon was started and no host-tool fallback was
  used.
- No provider selected/provisioned, no credentials created, no deployment edits,
  no migration/share submission, no restart/failure test, and no restore performed.
  Runtime acceptance is **unrun**. Workflows remain unchanged.

Nonsecret rechecks before implementation: `fdesetup status`, selected Lima
`list primary`, `launchctl list` for startup labels, K3s service enabled/active
state, `kubectl get` of the intended pod and StatefulSet (no Secret output),
and the manual runbook's isolated, CA-verified `bao status`. Record only seal
type, initialized/sealed, threshold, migration flag, version and exit code;
avoid full environment, manifests with Secret data, raw logs or credentials.
These read-only checks do not prove successful reboot ordering or migration.

Next decision: select an independently recoverable provider and credential
bootstrap design, or retain manual Shamir. Then commission the isolated rehearsal
and exact implementation patch. Do not treat this draft as deployment readiness.

[seal-concepts]: https://github.com/openbao/openbao/blob/v2.7.2/website/content/docs/concepts/seal.mdx
[transit]: https://github.com/openbao/openbao/blob/v2.7.2/website/content/docs/configuration/seal/transit.mdx
[seal-config]: https://openbao.org/docs/configuration/seal/
[static-seal]: https://openbao.org/docs/configuration/seal/static/
[apple-launchd]: https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html
[filevault]: https://support.apple.com/en-euro/guide/mac-help/mh11785/27/mac/27

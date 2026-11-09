# Primary infrastructure — staged reference implementation

**Current phase boundary:** see [application phases](../docs/application-phases.md). Shared
Authentik/OIDC, OpenBao/ESO and domain integration are later-stage proposals;
reference sequences below are not immediate rollout instructions. Secure local
bootstrap, private authenticated access and encrypted secret custody remain
mandatory before any separately approved deployment.

**Not deployed by publication.** This is generic ARM64 macOS/Linux-guest scaffolding, not a statement about any actual host. Activation, credentials, networking and synchronization require separate current owner approval. See [APPROVAL.md](APPROVAL.md).

Desired state is this public repository. Actual host inventory, host readiness, private operational decisions and recovery destinations belong outside this public repository. No private host record or usage dataset is included.

For cross-host eligibility use [fleet alignment](../docs/fleet-alignment.md).
Future shared identity and application naming are specified in the
[auth/domain plan](../docs/auth-domain-plan.md); neither changes these staged values.

## Pinned implementation

| Component | Pin | Purpose |
|---|---|---|
| Lima | 2.2.1, official Darwin ARM64 archive | Apple Virtualization (`vz`), no QEMU/Rosetta |
| Ubuntu | 24.04 ARM64 cloud image, 20260926 + SHA256 | Linux guest; no host directory mounts |
| K3s | v1.37.1+k3s1 + binary SHA256 | One embedded-etcd server, secrets encryption |
| Argo CD | chart 10.11.6 / app v3.5.6 | Scoped Homarr/OpenBao reconciliation |
| OpenBao | chart 0.30.6 / app 2.7.2 | Single Raft replica, TLS, persistent audit/data |
| Homarr | chart 8.40.1 / app v2.10.1 | Actual Homarr, SQLite PVC, existing encryption secret |
| ESO | chart 2.14.0 | Homarr namespace only, no cluster stores/push secrets |
| Helm | 3.22.1 + archive SHA256 | Bootstrap and Docker chart validation |

[artifacts.lock.json](artifacts.lock.json) records official release URLs and
checksums verified from release metadata on 2026-11-01. Lima's image URL/digest
comes from its tagged `v2.2.1/templates/_images/ubuntu-24.04.yaml`; no floating
image fallback is allowed. If removed upstream, stop and review a new pin.
Chart versions pin image tags; image manifests still require ARM64 verification
at activation. This is not a claim that images were pulled or workloads ran.

## Activation sequence after exact owner approval

Run from this directory. `python3 scripts/infra.py revision` prints a digest of
the reviewed inputs. An owner-reviewed, mode-0600 JSON file **outside this repo**
contains `revision`, ISO-8601 `expires`, and explicit `scopes` matching action names.
Set `DOTS_APPROVAL_FILE` to it. Never place credentials in that file. The file is
an accidental-execution guard; an agent may not manufacture approval.

1. `install-runtime`: checksum-verify official Lima and Helm archives into the
   dedicated user-local runtime directory; no global PATH/homebrew mutation.
2. `start`: create `primary`, 2 vCPU/4 GiB/40 GiB. Refuses while ffmpeg is present
   or process visibility is uncertain. Existing instances require inspection.
   Never quit or reprioritize another job to pass this check.
3. `bootstrap`: install checksum-pinned K3s in the guest; enable its systemd unit,
   embedded etcd and Secret encryption. This creates cluster keys/certificates.
   Existing binaries are refused instead of overwritten. No host kubeconfig export.
4. `argocd`: apply pinned chart/CRDs and namespaced target permissions. Initial
   Argo/Redis credentials are created by upstream services only after approval.
5. Owner creates TLS material using their approved secret-handling route and
   supplies `openbao/openbao-tls` with `tls.crt`, `tls.key`, `ca.crt`. Certificate
   SANs: `openbao.openbao.svc`, `openbao.openbao.svc.cluster.local`, `localhost`,
   `127.0.0.1`. Private CA/key remain outside Git and agent logs. Then `openbao`.
6. Owner initializes OpenBao with 3 Shamir shares / threshold 2, encrypting output
   directly to owner-controlled recovery storage. Owner unseals and enables audit
   at `/openbao/audit/audit.log`; never copy root/unseal values into chat or tools.
   Keep the bootstrap root credential offline and revoke it after scoped roles
   and recovery work. No real credentials until an off-host restore is proven.
7. `eso`: install namespaced ESO/CRDs. Owner configures KV-v2 mount `primary`,
   Kubernetes auth `primary-kubernetes`, role `homarr-db-read`, bound namespace
   `homarr`, SA `homarr-vault-reader`, audience `openbao`, max TTL 1h, and the
   exact [read policy](bootstrap/homarr-policy.hcl). Use OpenBao's projected SA
   for TokenReview; apply the explicitly approved auth-delegator binding.
   Put the public CA in `homarr/openbao-ca`. Apply `bootstrap/eso-openbao.yaml`
   only after these controls and synthetic rotation/denial tests succeed.
8. Owner creates a 32-byte Homarr encryption key through the approved secure
   route and stores it only at `primary/homarr/database` (`encryption-key`). ESO
   creates `homarr-db-encryption`. Do not rotate this key blindly: existing
   Homarr encrypted values require the corresponding migration/recovery process.
9. **Activation gate to resolve:** this repository is public, so private-repository deploy keys are not inherently required. The existing helper still checks for `argocd/primary-repo` before creating Applications. Review a credential-free repository registration compatible with that guard, or separately review and validate a helper change. Do not invent credentials, grant broader access, or bypass the guard during migration.
10. `gitops` creates the two Applications with auto-sync disabled. Review live
    diffs and manually synchronize OpenBao, then Homarr. Complete Homarr's owner
    account onboarding locally; no third-party integration tokens imported.
11. After manual sync, denial and rollback evidence, a fresh approval with
    `enable-sync` and `manualSyncAndRollbackVerified: true` permits `enable-sync`.
    This enables self-heal but never pruning. Argo/ESO controller upgrades remain
    explicit bootstrap actions; neither has authority to upgrade itself.

The dedicated Lima state uses `~/.local/share/dots-primary-lima` so generated SSH
socket paths stay within macOS's UNIX-domain socket limit. This is separate from
the runtime/tools directory under `~/Library/Application Support/dots-primary-infrastructure/`;
no existing Lima state is migrated automatically.

The launcher checks for both an existing `primary` instance and global overrides
inside that dedicated `LIMA_HOME` before starting. Bootstrap waits for node
registration before readiness, with one 180-second deadline covering both phases
and their subprocesses. A failed wait preserves the guest and installed K3s;
inspect service status/logs before further action and do not rerun installation.

The scripts implement installation and service scaffolding. Owner-held TLS,
unseal/root handling, policy setup and backup destination enrollment deliberately
remain explicit steps; none is silently executed by a bootstrap script.

## Access and persistence

Lima SSH uses host loopback 60022, without host SSH agent or public-key loading.
The K3s API stays inside the Linux guest; use `limactl shell primary -- sudo k3s
kubectl ...`. Guest networking uses Lima NAT, not bridged networking, VPN or host
firewall changes. Check CIDRs `10.72.0.0/16` and `10.73.0.0/16` against existing
routes before starting. Guest `net.ipv4.ip_forward=1` is a gated bootstrap change.

After separate `ui` approval, use a foreground guest port-forward bound to
127.0.0.1. Lima allows only these UI forwards (all other guest ports ignored):

| Guest command target | Guest and Mac port | Browser |
|---|---|---|
| `-n homarr port-forward svc/homarr 17575:7575 --address=127.0.0.1` | 17575 | HTTP loopback only |
| `-n argocd port-forward svc/argocd-server 18443:443 --address=127.0.0.1` | 18443 | HTTPS; verify service certificate |
| `-n openbao port-forward svc/openbao 18200:8200 --address=127.0.0.1` | 18200 | HTTPS; trust approved CA explicitly |

No forwards are started by repository publication. No LAN/public port, ingress,
Docker socket, cloud identity, agent fleet, browser session or demo service exists
in the baseline plan. For an existing primary with explicit owner approval, see
[optional login startup and existing UI recovery](startup/README.md). That opt-in
path resumes the existing guest after GUI login, preserves boot-scoped locks and
recovers only the three existing loopback routes. It does not run before login or
FileVault unlock, change Mac power settings, or unseal OpenBao. K3s resumes through
its existing guest unit; host uptime and live reboot acceptance remain separate. Sleep makes this host unavailable; until power/startup and
restore are validated, call it a local bootstrap, not a production primary.

## Validation and rollback

[Docker validation guide](../validation/README.md) owns `sh validation/run.sh`
and the pinned lint/schema toolchain. Checks remain UNRUN while Docker is absent
and workflows are owner-paused. [Committed workflow](../.github/workflows/primary-infrastructure.yml) builds and
runs validation in Docker on a hosted runner; it needs only read access to this
repo and public release downloads. No kubeconfig, SSH key or deployment credential
is passed to CI. Tests render and lint all four checksum-pinned charts and check
VM isolation, disabled sync, RBAC, TLS, services, persistence and credential scopes.
They do not establish live ARM64 compatibility, readiness, backup or GitOps health.

`rollback` disables both Application syncs then stops only the primary VM. If
cluster access fails, stop for inspection rather than delete anything. Keep VM
storage, PVCs, etcd token, recovery keys and audit/chat/Tether/decision logs.
Never invoke uninstall, prune, volume deletion, or destructive log rotation.
Snapshot/copy operations require a separately named encrypted off-host backup
location. No backup destination is supplied or scheduled by this reference implementation.

# Primary management recovery packet

**Prepared 2026-11-06. Procedure only; backup and restore acceptance are pending.**
The private operational record binds the selected destination, recipient reference,
custodian and target. Keep those details and every secret outside this public
checkout, build context, CI and chat. Configuration publication is not a data
backup. Further management services remain gated on independent recovery.

## Inventory and checkpoint contract

Before capture, record UTC time, source identity, exact source commit, deployed
revision, K3s version, datastore type, namespace/PV/PVC counts, storage backing and
an opaque checkpoint ID. Record observations separately from intended manifests.
The staged primary configuration selects embedded etcd and disables scheduled
snapshots; never substitute a SQLite file copy or enable a backup schedule.

| Component | Capture / independent recovery requirement |
| --- | --- |
| Reviewed configuration | Verified remote commit, artifact locks, Lima definition, K3s configuration and service unit; retain the deployed revision as well as newer source |
| Embedded etcd | One named, on-demand K3s snapshot, with timestamp and private integrity manifest; etcd includes Kubernetes Secrets and must be treated as credential material |
| Matching server token | Protect independently with the same checkpoint; it is needed to decrypt bootstrap data during restore; never print it or pass its value on a command line |
| Secret-encryption configuration | Preserve the matching server-side encryption configuration and required TLS/recovery files through an explicit private file allowlist; do not assume Git contains them |
| Persistent volumes | Record every claim, PV UID, reclaim policy and backing location; take engine-consistent application backups separately from etcd; an etcd snapshot contains no volume payload |
| OpenBao / Homarr / other management data | If absent, record absent at capture; if later present, inventory storage, engine/version, encryption key dependencies and a consistent checkpoint before claiming coverage |
| Operator access | Independently available GitHub login, encrypted backup access and owner-held decryption key; none may depend exclusively on this Mac, OpenBao, ESO or a future IdP |
| Histories | Preserve all original Tether/chat/decision histories, segments, attachments and metadata; no ingestion, copying, pruning or archive upload is implied by this packet |

Do not capture a running guest disk as the sole recovery method. Do not archive a
home directory or credential stores. Discovery of additional application data or
histories requires a separate explicit capture scope; omission must be visible.

## Capture and encrypted transfer

1. Complete the Docker-only source validation gate and bind the capture packet to
   the exact reviewed source/deployed versions. Recheck destination privacy and
   owner-controlled public recipient against the existing recovery record without
   downloading old credential archives or reading the private key.
2. Review an exact private file allowlist: the new etcd snapshot, matching server
   token, encryption configuration and any required TLS/recovery files. Record
   categories and byte counts privately, never their values. Reserve owner-only
   staging outside Git/build contexts (directory 0700, files 0600, encrypted
   backing storage). Disable command tracing and payload logging.
3. While preserving the running source, use the installed, matching K3s binary's
   `etcd-snapshot save --name <checkpoint-id>` once. Do not stop/reinstall K3s,
   repeat bootstrap, prune snapshots or modify existing disks/PVCs. Record failure
   and inspect before retrying; confirm no unexpected snapshot-side S3 transfer.
4. Encrypt the reviewed checkpoint and its private manifest using the established
   age recipient before transfer. Handle token/key bytes locally with the reviewed
   secret-handling procedure, outside tool output, shell arguments and chat.
   Neither a plaintext tarball nor a private key may enter Git.
5. Publish only the new ciphertext and its checksum to the selected private
   destination under a unique checkpoint name; retain existing artifacts and
   history. Do not add a watcher, schedule, new account or new credential. Verify
   the remote commit and independently downloaded ciphertext bytes. A successful
   push alone is insufficient evidence of recoverability.

These steps require the reviewed credential-category transmission scope. A
previous credential backup or a populated local approval guard does not prove
that a new checkpoint was captured, encrypted or uploaded.

## Isolated restore rehearsal

1. Use an independently accessible recovery workstation/session, with the
   original Mac/guest unavailable to the recovery process. Retrieve configuration
   and ciphertext through independent access. The owner uses the existing private
   key locally; the key must never be requested in chat or loaded into agent tools.
2. Verify ciphertext checksum, decrypt into new encrypted owner-only staging,
   check the private manifest, and reject absolute/traversing archive paths,
   escaping links or unexpected entries before extraction. Never extract over
   existing configuration or the sole copy of any backup.
3. Prepare a new disposable ARM64 Linux target with the exact K3s version. Use a
   separate instance name, `LIMA_HOME`, disk and network. No original disks, PVCs,
   shared folders, forwards, live cluster routes, GitOps sync or source endpoints
   may be attached. Enforce the network boundary before starting restored K3s.
4. Place the matching token and encryption configuration from staging in the new
   target via the reviewed private channel. With K3s stopped **only on the new
   target**, run the matching K3s `server --cluster-reset
   --cluster-reset-restore-path=<snapshot>` procedure. Read the matching upstream
   version's restore instructions first; never run cluster-reset on the original.
5. Start the isolated restored node. Verify registration, Ready, Secret decryption
   without printing values, namespace/object counts and expected identities. If
   PVCs exist, restore payloads onto newly provisioned volumes, preserving originals,
   then verify application IDs, authorization and consistency against the manifest.
   No service reconnects to production during rehearsal.
6. Record duration, checkpoint age/RPO, access independence, integrity results,
   versions, counts, failures and opaque target ID. Retain sanitized evidence and
   owner acceptance; preserve protected histories and original data. Retire only
   explicitly disposable rehearsal resources after evidence review. Do not claim
   cryptographic erasure from deleting files on APFS or SSDs.

**Acceptance:** verified off-host ciphertext, independently usable key and account
access, successful isolated restore and application checks for every captured
component. Any missing key, inaccessible account, wrong token, failed restore or
uncovered payload keeps management activation blocked. Report backup creation,
publication verification and restore acceptance as three separate outcomes.

## Authoritative procedure references

- [K3s backup and restore](https://docs.k3s.io/datastore/backup-restore): datastore selection and the matching server token.
- [K3s etcd snapshot and restore](https://docs.k3s.io/cli/etcd-snapshot): on-demand capture and isolated cluster reset.
- [Existing recovery boundaries](configuration-recovery.md) and [primary approval scopes](../primary-infrastructure/APPROVAL.md).

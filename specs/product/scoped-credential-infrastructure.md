# Epic dependency: scoped credential storage and browser-profile recovery

## Product goal and ownership

Provide the infrastructure needed for a selected browser workflow to obtain only its approved credential, while preserving independent control of encrypted profiles and recovery material. Browser account admission, origin verification, injection and control transfer are owned by [dots-browser-workflows](https://github.com/newdarwindev/dots-browser-workflows). This repository owns staged infrastructure contracts, not a parallel credential broker.

Use the [primary reference](../../primary-infrastructure/README.md), [activation approval](../../primary-infrastructure/APPROVAL.md) and [deferred platform boundaries](../../docs/auth-domain-plan.md). Management services are not prerequisites that may be silently activated by application setup.

## Stories and completion gates

| ID | Infrastructure story | Acceptance requirement |
| --- | --- | --- |
| SEC-01 | Separate management-plane identity and recovery from application and CI workloads. | Workload namespace/account cannot read management credentials or recovery material; pinned architecture-compatible artifacts and resource/network limits are evidenced. |
| SEC-02 | Deliver only scoped secret references using authorized workload identity and least privilege. | Wrong namespace, account or scope is denied before secret retrieval. Actual values never enter source, workflow history, telemetry or public receipts. |
| SEC-03 | Keep profile ciphertext separate from decryption authority and integrity metadata. | Storage access alone cannot restore a profile; corrupt or stale revisions fail; browser-owned identity verification is required after restore. |
| SEC-04 | Define credential rotation and refresh/restart boundaries. | New fetches use the authorized revision; existing cookies/process state are reported separately rather than assumed revoked. |
| SEC-05 | Record vault revocation, broker-lease closure, browser termination and external session invalidation independently. | Each operation has its own verified or unknown state; vault denial is never reported as website logout. |
| SEC-06 | Recover without destroying original histories, keys, PVCs or audits. | An independently authorized restore exercise identifies encrypted source, integrity check, owner custody, recovery point and actual restored behavior. Retained PVCs alone do not satisfy this gate. |
| SEC-07 | Activate only reviewed desired-state revisions after TLS, identity, denial and rollback checks. | Stale approval/configuration fails closed; source publication and green tests do not count as activation approval. |

## Evidence boundary and gaps

Staged management/application code and partial bootstrap evidence exist; neither a running pod nor an initialized vault establishes the complete credential lifecycle. Workload authentication, TLS/recovery custody, namespace isolation, rotation, browser checkpoint consistency and operational restore remain separately qualified. This specification does not claim that every service is absent or that a particular host is currently ready.

Keep deployment measurements and private target details outside this public tree. Preserve current runbooks instead of embedding live credentials, addresses or recovery commands here. No new backup, restore, security setting or persistent service is authorized by this document.

## Validation

Use the applicable [validation scope](../../validation/README.md) for source checks, plus separately authorized live identity and denial tests. Record source/install revisions and distinguish source checks, synthetic secret/profile fixtures, live access and independent recovery. Missing or failed stages remain visible.

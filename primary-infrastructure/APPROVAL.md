# Action-time approval template — not a grant

Publication and repository migration do not authorize activation. Obtain current owner approval of the reviewed revision digest, each action scope and expiry only after Docker validation succeeds. A populated local approval file is an accidental-execution guard, not proof of consent. Keep actual host identity, readiness, owner decisions and recovery destinations in private operational records.

Before approving, review the full [activation sequence](README.md#activation-sequence-after-exact-owner-approval), pinned artifacts, least-privilege manifests, resource budget and loopback-only exposure. Confirm the target ARM64 Mac, capacity, CIDR overlap, host availability and recovery arrangements privately. Do not terminate unrelated work or change host settings to pass a gate.

Separate scopes cover runtime installation, VM start, bootstrap/controller permissions, service setup, GitOps creation and synchronization. No installation, persistent startup, credentials, forwarding or controller grants follow from publishing this template. New terms, permission prompts, deployment destinations or scope changes require a fresh decision.

## Required gates

- Validate the exact final revision in the committed Docker workflow; verify image architecture separately before activation.
- Retain no host mounts, no shared SSH agent, no public ingress, no host API forward, no unapproved firewall/VPN/DNS/power changes. Review explicit loopback ports and guest NAT egress.
- Owner-held TLS, recovery shares/root credentials and backup material stay outside Git, CI, tools and chat. Use reviewed secret handling; no existing personal credentials are imported.
- Resolve credential-free access to this public desired-state repository without broad tokens or unnecessary deploy keys. The current helper retains a repository-registration guard; see README.
- Name an owner-controlled encrypted off-host backup destination privately and verify restore before storing real reusable credentials or claiming production readiness.
- Manual diff, synchronization and rollback come before separate enable-sync approval. Pruning stays disabled; privileged controller upgrades remain explicit.

## Rollback

Disable Application synchronization, end explicitly started UI forwards and stop only the new VM. Preserve disks, PVCs, keys, audit records and every Tether/chat/decision history. Do not uninstall, delete volumes or destructively rotate logs. Automatic startup and sleep prevention are separate operational decisions.

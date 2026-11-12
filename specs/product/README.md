# Product goals: private agent telemetry and credential infrastructure

This repository supports two concrete product capabilities. These specifications are goals and acceptance contracts, not activation instructions or a claim of deployed readiness.

| Epic | Owner boundary | Specification |
| --- | --- | --- |
| Native agent telemetry in Langfuse | Supported native producers, standard Collector projections, bounded transport and exact backend readback | [Telemetry stories](native-agent-telemetry.md) |
| Scoped credential infrastructure | Management-plane isolation, scoped secret delivery and recoverable profile dependencies | [Credential infrastructure stories](scoped-credential-infrastructure.md) |

## How to use this directory

Read the relevant story, then its linked canonical runbooks. Keep one source of truth for executable configuration. Record source revision, installed revision, test boundary, evidence timestamp and remaining gates separately. An accepted synthetic control is not production enrollment or independent restore.

The [native monitoring contract](../../docs/codex-native-monitoring.md), [application setup](../../application-infrastructure/README.md), [primary reference](../../primary-infrastructure/README.md) and [validation guide](../../validation/README.md) remain operational references. Browser identity, injection and human handoff belong to [dots-browser-workflows](https://github.com/newdarwindev/dots-browser-workflows); this repository must not create a competing browser broker.

## Evidence baseline

At the November 12, 2026 documentation review, main contains staged contracts. Separate [serial qualification source](https://github.com/newdarwindev/dots-local-sidecar-cloud-infrastructure/commit/b7d8c30f418c97dada23bc256cf681741c91c6f5) reports 324 tests and 79 schema resources; that integration-branch result does not merge or install its changes through this documentation. Live admission, session coverage and recovery remain separately qualified. Keep private target evidence outside this public repository.

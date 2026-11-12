# Agent entry points

Read the [product goals and specification map](specs/product/README.md) before changing telemetry or scoped credential infrastructure. Follow the applicable nested AGENTS.md and existing runbooks; this index does not replace them.

- [Native agent telemetry in Langfuse](specs/product/native-agent-telemetry.md) owns source identity, privacy, transport and backend acceptance.
- [Scoped credential infrastructure](specs/product/scoped-credential-infrastructure.md) defines this repository's dependency role for credential storage and browser profiles.
- Use [validation instructions](validation/README.md) for the required Docker scopes. Report unavailable checks explicitly; a documentation or source-test pass is not live acceptance.
- Keep this public repository generic: no host addresses, account identifiers, secret material, raw conversations or private receipts.
- Preserve existing queues, histories, data, authentication and unrelated pipelines. Specifications describe goals, not permission to deploy, enroll, widen capture, rotate credentials or run recovery.
- Update the relevant story's evidence and remaining gaps when implementing it. Do not duplicate operational instructions here.

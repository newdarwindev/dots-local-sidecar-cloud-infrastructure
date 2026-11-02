# Unified application identity and endpoint plan

**Later-stage proposal, 2026-11-02. No installation, identity enrollment, access
change, DNS change, certificate issuance or public exposure is performed by this
document.** Repository configuration and a running service are different facts.
The inventory owner must verify placement and application health before rollout.

The [current application phases](application-phases.md) defer shared identity,
central secrets and domain integration. Authentik remains the preferred proposal,
not an active rollout commitment. Mandatory secure local bootstrap/access remains
a gate before any application deployment.

## One policy, separate sources of truth

- This document owns reusable browser identity, endpoint naming and acceptance
  policy; application values remain the implementation source of truth.
- The private host inventory owns actual machines, observations and evidence.
  A private placement overlay maps stable role IDs to those records. Do not copy
  host specifications, addresses or security findings into public manifests.
- The existing private domain/endpoint catalog owns real zones, URLs, ownership,
  decision references and verification dates. Extend that catalog, not another
  parallel list of real domains. Its documentation shell is not deployed DNS.
- Application records should join these sources using `app_id`, `role_id`,
  `endpoint_id`, `auth_profile`, `access_group`, `machine_auth`, `data_class`,
  `lifecycle`, `observed_at` and `evidence_ref`. Lifecycle is explicitly
  `proposed`, `staged`, `observed-running`, `verified` or `retired`.
- Public examples contain generic roles and `example.invalid` names only. Real
  memberships, domain choices, recovery custody and secret-location references
  remain private. Secret values belong in neither repository.

## Preferred later-stage identity proposal: Authentik

Propose **one Authentik identity provider**, not one per host, for this mixed
native-OIDC and proxy-protected application estate. Its [OIDC and proxy provider
support](https://docs.goauthentik.io/add-secure-apps/providers) and
[per-application forward authentication](https://docs.goauthentik.io/add-secure-apps/providers/proxy/forward_auth/)
fit the two integration patterns below. This is the preferred future architecture, not a measured sizing result, pinned version,
installed service or access grant.

| Option | Documented fit | Decision consideration |
| --- | --- | --- |
| Authentik | OIDC plus proxy providers and configurable authentication flows | Preferred proposal: one administration surface for both patterns. Explicit MFA configuration and outpost operations still required. |
| [Authelia](https://www.authelia.com/integration/openid-connect/introduction/) | OpenID Connect provider and reverse-proxy integration | Valid alternative for a configuration-led proxy estate; do not describe it as lacking native OIDC. Prefer it if operational evaluation favors its configuration/user-directory model. |
| [Keycloak](https://www.keycloak.org/securing-apps/overview) | OAuth2/OIDC/SAML and application ecosystem integrations | Valid alternative where realm/federation requirements justify it; legacy apps still need a suitable authentication proxy/integration. Do not add custom login code merely to adopt it. |

Before activation, evaluate backup/restore, release provenance, supported
architecture, resource use and maintainability on the chosen management role.
Do not assume the existing small management guest has spare capacity. One IdP
means a shared availability dependency; a notebook that sleeps is not automatically
an acceptable identity host. Replicas sharing one host or disk are not HA.

### Why this choice fits OpenBao and the wider fleet

OpenBao supports standard OIDC; no IdP replaces its own policies or machine auth.
**Authentik is the preferred proposal for the whole estate**, combining native OIDC for Homarr,
Argo CD and Langfuse with proxy/outpost protection for other sites. Keycloak has
an [OpenBao-specific integration guide](https://openbao.org/docs/auth/jwt/oidc-providers/keycloak/)
and is a strong alternative for complex federation/realm requirements; do not
copy that guide's broad example roles or redirects as production policy. Authelia
remains attractive for a configuration-first proxy estate, but an HA deployment
has its own stateful dependencies, not just a tiny stateless config file. This
choice is not a claim that Authentik is intrinsically more compatible with Bao.

Authentik's [Vault recipe](https://integrations.goauthentik.io/security/hashicorp-vault/)
is useful protocol guidance, **not proof of tested OpenBao compatibility**. Require
a pinned-release integration test before migration. Current Authentik
[architecture](https://docs.goauthentik.io/core/architecture) uses server, worker and
PostgreSQL; Redis was removed from its architecture in 2025.10. Do not add a Redis
dependency from an old guide. Budget IdP resources separately; selecting the
observability target does not automatically assign IdP placement there.

#### OpenBao identity contract

- Validate exact issuer, client and HTTPS redirects for UI/CLI; no wildcard
  callback, disabled certificate checks or default administrator role. Use stable
  subject identifiers and a tested groups claim. Bind explicit external-group
  aliases to least-privilege Bao ACL policies; a group claim alone grants nothing.
  See the [JWT/OIDC API](https://openbao.org/docs/api/auth/jwt/).
- Limit group disclosure at the IdP. Authentik's default profile includes groups;
  adding a filtered mapping does not remove defaults because lists merge. Replace
  the default profile mapping when narrowing groups, then inspect actual claims.
  [Property mapping semantics](https://docs.goauthentik.io/add-secure-apps/providers/property-mappings/).
- Require MFA enrollment/authentication, including the never-enrolled test; choose
  denial or enrollment rather than skip and define freshness. Keep service
  Kubernetes/JWT identities independent of browser MFA.
- OIDC logout, group removal or IdP account disable is not immediate revocation of
  previously issued [OpenBao tokens](https://openbao.org/docs/concepts/tokens/).
  Use bounded human token TTL/max TTL, no unbounded periodic human tokens; test
  explicit Bao token revocation/identity disable during emergency offboarding.
- Verify cold-start recovery with IdP and OpenBao both unavailable. Bootstrap
  database/signing material, independent host access and Bao unseal custody cannot
  be recoverable only from the sealed service behind this same IdP.

Core OIDC/proxy fits the [free edition](https://goauthentik.io/pricing/); recheck
exact features before deployment and do not promise Enterprise-only controls.
Replicated app processes on one host do not provide database/host HA. Validate
matched server/worker/outpost versions, encrypted independent backups and restore.

### Browser policy

1. Prefer an application's native OIDC client. Use exact HTTPS redirect URIs,
   authorization-code flow and PKCE where the pinned client supports it; validate
   issuer, audience and certificate chain. Do not use wildcard redirects or disable
   TLS verification. Map stable subject identifiers and explicit groups to
   application roles; never turn every authenticated user into an administrator.
2. For apps without verified native OIDC, use per-application forward authentication
   at the approved ingress. Restrict the origin to that ingress; strip untrusted
   identity headers and recreate only verified headers. Guard HTML, JSON APIs,
   websocket/download routes and alternate origins, not only the landing page.
   Proxy authentication does not create application-level RBAC or user identities.
3. Require MFA enrollment and authentication for authorized users, with stronger
   administrator policy and tested recovery. Authentik's [hardening guide](https://docs.goauthentik.io/security/security-hardening)
   warns that the shipped flow skips MFA for users with no enrolled authenticator.
   Explicitly force enrollment or deny access; test an unenrolled account. Prefer
   WebAuthn/security keys with a separately approved recovery method. See its
   [authenticator validation stage](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/authenticator_validate/).
4. Define app-specific groups and deny-by-default authorization. An existing
   narrow viewer allowlist must remain equally narrow during migration. A fleet
   dashboard viewer is not necessarily a secrets or private-account-data viewer.
5. Test logout, session lifetime, disabled-user behavior and claim changes per
   application. A central logout is not proof that every app session is revoked.
   Keep current working gates until replacement denial and recovery tests pass.

## Application coverage and migration matrix

This is a **known-source coverage matrix**, not a claim of a complete live fleet
scan. Add subsequently discovered applications privately before routing them.

| App / component | Current source evidence, not asserted runtime | Proposed browser access | Non-browser boundary / transition gate |
| --- | --- | --- | --- |
| Homarr | Staged `values/homarr.yaml`: credentials provider, ClusterIP, ingress disabled | Native OIDC; explicit group mapping and reviewed account migration | Keep existing encryption key/data and integration secrets independent of login. Verify pinned version's account-linking behavior before removing credentials. |
| Target-specific Homarr | Planned separate `homarr-workload` instance under [current phases](application-phases.md), not deployed | Initially approved private authenticated local access; shared OIDC is later-stage | Independent database/PVC/encryption-key reference; do not run the ESO-dependent generic management sequence unchanged. |
| Argo CD | Staged `values/argocd.yaml`: local admin enabled, anonymous disabled, Dex disabled, TLS on | Native external OIDC plus explicit project/RBAC mappings; no Dex needed merely to use an existing OIDC provider | Dedicated least-privilege automation identity/token where required; do not reuse a human session or broaden cluster scopes. Retire routine admin use only after recovery is tested. |
| OpenBao | Staged `values/openbao.yaml`: TLS, one Raft replica, ClusterIP UI | Native OIDC for named humans mapped to narrow policies | ESO retains Kubernetes auth and scoped policies; no browser login gate in its machine path. Unseal and disaster recovery must work without IdP. |
| ESO | Staged namespace-scoped machine integration, no browser portal | No user-facing hostname or SSO portal | Separate Kubernetes service-account identity/audience/policy per approved scope. Keep existing narrow Homarr read policy. |
| Tokscale hub | Installation draft only; upstream frontend/database and authenticated upload | Proxy-protected browser/read surface; generalized native OIDC integration is not verified at reviewed revision | Preserve upstream hub login/token issuance. Exact authenticated submission route must work without an interactive redirect; do not exempt all `/api/*`. Review token scope/revocation before promising per-device isolation. |
| Langfuse | [Installation/coverage draft](langfuse-plan.md), no runtime or collector enabled | Native OIDC with Authentik: prefer its dedicated provider if supported by the pinned release, otherwise separately review custom OIDC; verify membership/enforcement and licensing | Project-key ingestion remains non-interactive, TLS-verified and private. Metadata-only default; rich transcript plugin requires explicit opt-in. No broad API bypass. |
| OpenTelemetry Collector | [Selected-cluster implementation design](opentelemetry-implementation-plan.md); not installed | No browser SSO portal; private health/admin probes only | Authenticated TLS machine ingestion; separate trace/log/metric pipelines. Logs/metrics destinations pending and disabled, not redirected to Langfuse. |
| Observability S3 storage | Same selected cluster; draft vendor-chart SeaweedFS choice, not deployed | No general public browser endpoint | Private scoped bucket credentials; off-cluster encrypted backup separately required. Same-cluster replicas/buckets are not independent recovery. |
| Fleet dashboard | Published synthetic read-only implementation; external authenticated ingress required, no live collector/deployment included | Proxy authentication, restricted viewers | Protect inventory/status APIs too; synthetic records do not establish host health. |
| Live-status dashboard | Published loopback implementation with narrow email-gated tunnel launcher; production gate not verified | Preserve current gate until an equally restrictive reviewed replacement exists | Account-sensitive reads remain constrained to approved viewers and matching source account. Do not generalize access to every fleet member. |
| Other applications | Privately assess current integration and record evidence before assigning a state | Choose native OIDC or proxy protection only after compatibility and authorization-equivalence tests | Keep contents and viewer identities private; documentation cleanup must not create a public route. |
| Identity provider | Authentik preferred later-stage proposal; not installed or version-pinned | Its own native authentication/MFA, private administration | Independent bootstrap/recovery path, not recursive authentication through itself. |

Native integration references: [Homarr SSO](https://homarr.dev/docs/advanced/single-sign-on/),
[Argo CD existing OIDC provider](https://argo-cd.readthedocs.io/en/stable/operator-manual/user-management/#existing-oidc-provider),
[OpenBao JWT/OIDC](https://openbao.org/docs/auth/jwt/).
Homarr callback configuration and group claims, Argo CLI/public-client handling,
and OpenBao UI versus CLI callbacks must be checked against pinned releases;
current online documentation is not automatically version-matched deployment YAML.

Source coverage: [fleet dashboard](https://github.com/newdarwindev/dots-fleet-dashboard),
[live-status dashboard](https://github.com/newdarwindev/dot-live-status), and
[Tokscale reviewed revision](https://github.com/junhoyeo/tokscale/tree/b26c433d03f23a2255ad9f212512ce83ede83da3).
Tokscale's [device/profile read helper](https://github.com/junhoyeo/tokscale/blob/b26c433d03f23a2255ad9f212512ce83ede83da3/packages/frontend/src/lib/publicProfileDevices.ts)
explicitly allows public reads: authenticated uploads alone do not protect usage.
Keep the native autosubmit default cadence; this plan introduces no six-hour job.

## Endpoint and certificate plan

Use service-oriented names independent of the current computer: for example
`auth.apps.example.invalid`, `homarr.apps.example.invalid`,
`argocd.apps.example.invalid`, `openbao.apps.example.invalid`,
`usage.apps.example.invalid`, `fleet.apps.example.invalid` and
`status.apps.example.invalid` and `langfuse.apps.example.invalid`. These are inert examples, not owned domains or
certificate requests. Give an app one canonical HTTPS origin; avoid path-prefix
hosting unless that specific app supports it. Keep Kubernetes internal service
DNS separate from browser-facing names and OIDC issuers.

Default to private connectivity and private DNS answers pointing at an approved
private ingress. No wildcard public ingress, public NodePort, database exposure
or Internet-forwarded management ports. Routing and DNS resolution are not access
control: enforce application authorization and network restrictions too. Preserve
loopback-only access until an approved private replacement is verified.

Choose one certificate strategy at activation:

- An owned domain with private/split-horizon address records plus ACME DNS-01 can
  provide browser-trusted TLS without opening HTTP ingress. [DNS-01](https://letsencrypt.org/docs/challenge-types/#dns-01-challenge)
  proves DNS control; delegate only the challenge zone and narrowly scope its API
  credential. Consider public certificate-transparency name disclosure before
  selecting names. Public certificate issuance does not make the app public.
- A private CA avoids public issuance but requires explicitly approved trust
  distribution and tested renewal on every client. Never tell clients to ignore
  certificate errors; do not make emergency recovery depend on a sealed secrets
  service that also supplies the only CA or DNS bootstrap credential.

Keep real DNS provider/zone, records, ownership evidence, trusted-client list,
renewal mechanism and ingress placement in the private catalog/overlay. Exact
public exposure, domain purchase, OAuth registrations, trust-store changes and
firewall/tunnel changes require separate scoped approval. Temporary tunnel URLs
are not stable OIDC issuer or callback identities.

## Machine identities and recovery

Browser SSO and machine authentication are separate. Give each integration the
smallest supported identity, audience, resource scope and expiry; rotate/revoke
and test it. Do not assume arbitrary client-credentials tokens work with every
application. Retain upstream supported mechanisms (including OpenBao Kubernetes
auth and Tokscale hub-issued reporting credentials). Never put session cookies,
OAuth secrets, root tokens, raw usage histories or private keys in Git.

OpenBao's [seal documentation](https://openbao.org/docs/concepts/seal/) establishes
that authentication is unavailable while sealed. Keep approved unseal custody,
encrypted backups, bootstrap credentials and recovery instructions accessible
independently of OpenBao and the IdP. Auto-unseal recovery keys do not replace a
lost underlying KMS/seal key. The IdP database and encryption/signing material
also need an independently recoverable backup. Break-glass access is audited,
limited, tested and not a permanent Internet-facing bypass.

## Bounded rollout after a separate activation decision

1. Reconcile private inventory and application records: identify actual host,
   app version, data class, current gate and last observed health. Installed CLI
   binaries, active services and healthy clusters are separate checks.
2. Select an always-available management placement and recovery destination;
   approve the actual domain/CA, viewer groups and exact change scope.
3. Validate IdP, private DNS/TLS and recovery using synthetic identities/data.
4. Pilot one low-sensitivity app. Test anonymous denial, wrong-group denial,
   unenrolled MFA denial, forged-header denial, direct-origin denial, revoked
   identity behavior, TLS renewal and IdP-down fail-closed behavior.
5. Add native OIDC apps individually, then proxy apps. Test UI/API/CLI behavior
   separately; authenticate reporters without widening browser access. Check
   scheduler context uses the private Tokscale URL, not its public fallback.
6. Verify recovery with the IdP unavailable and OpenBao sealed; rehearse rollback
   to the previous private route without removing its protection. Only then
   update each private record to `verified` with dated evidence.

Success means consistent policy and verified routes, not identical auth code in
every app. Keep unsupported apps private/unrouted rather than inventing custom SSO.

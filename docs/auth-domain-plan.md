# Deferred identity, secrets and domains

**Later proposals only.** Current [application setup](../application-infrastructure/README.md)
requires secure independent bootstrap, private authenticated access, secret custody
and recovery; it does not install shared identity, secrets or ingress.

- **Identity:** Authentik is the preferred proposal, not pinned/installed/tested.
  Native OIDC where the exact application version supports it; otherwise a reviewed
  per-app proxy. Do not revive competing IdPs or custom login work without a need.
- **Secrets:** OpenBao with narrowly scoped ESO is deferred. The
  [primary reference](../primary-infrastructure/README.md) preserves its exact
  bootstrap, policy and custody gates; do not use that sequence for workload Homarr.
- **Domains:** one approved private HTTPS origin per app; `*.example.invalid`
  names in examples are inert. Real zones, URLs, membership and recovery references
  belong in the existing private catalog, not a new public/parallel inventory.

## Preserve these gates before any future migration

1. Pin/evaluate actual release, architecture, capacity and independent restore.
   One IdP is an availability dependency; same-host replicas are not HA.
2. Use exact HTTPS callbacks, validated issuer/audience/CA and supported code/PKCE
   flows; no wildcard redirect or TLS bypass. Map stable subjects and explicit
   groups to least privilege, never every logged-in user to administrator.
3. Proxy protection covers UI, API, downloads, websockets and alternate origins;
   deny direct origins and strip/recreate identity headers. Proxy auth is not
   application-level RBAC. Retain narrow existing viewer gates until equivalence
   is proven, and keep unsupported apps private/unrouted.
4. Test MFA enrollment/denial (not just existing MFA), wrong group/user, forged
   headers, logout/revocation, disabled users, certificate renewal and IdP-down
   behavior. Do not remove local recovery authentication until its replacement works.
5. Keep native machine identities separate from browser cookies/redirects. Preserve
   supported Tokscale token auth and scoped OpenBao Kubernetes auth. Never exempt
   all `/api/*`; [Tokscale routes](../application-infrastructure/tokscale/contract-audit.md)
   and [telemetry project keys](../application-infrastructure/runbooks/telemetry.md)
   retain their own boundaries. Verify release/licensing before promising RBAC/SSO.
6. Keep OpenBao unseal material, IdP signing/encryption state, bootstrap access and
   encrypted backups independently recoverable while Bao is sealed/IdP is down.
   Root/unseal keys never enter tools/chat; recovery keys cannot replace a lost
   underlying seal/KMS key. Preserve application encryption keys and all histories.
7. Domain purchase, DNS/ingress/tunnel/firewall/trust-store changes, OAuth clients,
   certificate issuance, secret policy and access enrollment need exact approval.
   Private DNS is not authorization. DNS-01 still needs scoped credentials and
   review of certificate-transparency name disclosure; private CA needs approved
   trust distribution. Never tell clients to ignore certificate failures.

Private app records join `app_id`, `role_id`, `endpoint_id`, `auth_profile`,
`access_group`, `machine_auth`, `data_class`, `lifecycle`, `observed_at`, `evidence_ref`.
Use proposed/staged/observed-running/verified/retired honestly; actual health and
placement are dated evidence, not inferred from manifests.

Version-matched references: [Authentik providers](https://docs.goauthentik.io/add-secure-apps/providers),
[MFA hardening](https://docs.goauthentik.io/security/security-hardening),
[Homarr SSO](https://homarr.dev/docs/advanced/single-sign-on/),
[Argo OIDC](https://argo-cd.readthedocs.io/en/stable/operator-manual/user-management/#existing-oidc-provider),
[OpenBao OIDC](https://openbao.org/docs/auth/jwt/),
[OpenBao seal](https://openbao.org/docs/concepts/seal/),
[Langfuse auth](https://langfuse.com/self-hosting/security/authentication-and-sso),
[Langfuse feature/licensing](https://langfuse.com/pricing-self-host).

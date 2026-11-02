# Trust boundaries and cloud extension (draft)

## Boundaries

1. **Agent to gateway:** mutually authenticated requests; typed operations, policy, rate limits, expiry, audit. The agent never sees OpenBao root material, broad kubeconfigs, or cloud administrator credentials.
2. **Gateway to Git:** a narrow pull-request identity can propose changes to the approved desired-state repository. Protected branches, human review, and signed or attributable commits guard reconciliation. This public repository holds reviewed generic desired-state manifests; private host records, sensitive settings and recovery details remain separate and must never be included in public changes. Publication does not authorize reconciliation or deployment.
3. **Git to Argo CD:** project allowlists bind source repositories, destinations, and resource kinds. Separate cluster credentials and namespace scopes prevent a compromised workload target from gaining management access.
4. **OpenBao to ESO to workloads:** Each destination cluster runs its own ESO controller. Its Kubernetes service-account identity maps to a cluster-specific OpenBao policy. ESO materializes only required Secrets in its own cluster and namespace; Kubernetes encryption at rest and RBAC are required, and secret exposure through pods/logs remains a risk. Rotation is tested end to end.
5. **Crossplane to cloud:** dedicated provider identities per cloud and environment; least privileges, budgets, tags, and approved compositions. Crossplane claims cannot bypass owner review for spend or destructive operations.
6. **Local to cloud:** private connectivity and explicit egress controls. Classify data before replication; cloud resource creation is a reviewed operation, not an automatic response to local pressure.

## Extension pattern

For AWS, Google Cloud, and Azure, maintain independent cluster enrollment, provider configuration, identity federation where available, and composition implementations behind a small common claim vocabulary (for example `ComputeEnvironment` and `AppEndpoint`). A claim describes desired capability and a placement target; provider-specific compositions map it to resources. Keep storage and networking provider-specific. Argo CD targets each cluster explicitly and reports drift. Use quotas, budget alerts, and default deny policies. Test one disposable environment and teardown per provider before expanding.

Cloud capacity can absorb chosen workloads when artifacts, identity, network, data access, and architecture are compatible. Stateful migration and failover need application-specific procedures and recovery objectives; they are not provided by Crossplane or Argo CD alone.

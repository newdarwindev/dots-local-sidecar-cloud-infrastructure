# Primary sources reviewed 2026-10-31

- [K3s datastore choices](https://docs.k3s.io/datastore): default SQLite versus explicitly initialized embedded etcd.
- [K3s embedded etcd initialization](https://docs.k3s.io/datastore/ha-embedded): `--cluster-init` selects embedded etcd.
- [K3s backup and restore](https://docs.k3s.io/datastore/backup-restore): datastore-specific backup paths; retain the matching server token.
- [External Secrets Operator ClusterExternalSecret](https://external-secrets.io/latest/api/clusterexternalsecret/): ExternalSecret controllers create Secrets in their own cluster namespaces.
- [K3s requirements](https://docs.k3s.io/installation/requirements): Linux operating systems and supported CPU architectures.
- [Kubernetes Windows containers](https://kubernetes.io/docs/concepts/windows/intro/): Linux control plane and supported Windows Server worker requirements.
- [Argo CD declarative setup](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/): declarative bootstrap and App of Apps.
- [Crossplane with Argo CD](https://docs.crossplane.io/latest/guides/crossplane-with-argo-cd/): integration considerations.
- [OpenBao Kubernetes authentication](https://openbao.org/docs/auth/kubernetes/): service-account based authentication.
- [External Secrets Operator support](https://external-secrets.io/latest/introduction/stability-support/): provider stability varies; pin and validate.
- [NVIDIA GPU Operator platform support](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/platform-support.html): GPU/OS/runtime compatibility must be checked against actual hardware.

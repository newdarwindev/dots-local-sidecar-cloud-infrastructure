# Primary references to recheck at implementation

- [K3s requirements](https://docs.k3s.io/installation/requirements): Linux host and architecture prerequisites.
- [K3s datastore choices](https://docs.k3s.io/datastore): single-server SQLite versus explicitly initialized etcd.
- [K3s backup and restore](https://docs.k3s.io/datastore/backup-restore): datastore-specific backups and matching server token.
- [Argo CD declarative setup](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/): reviewed application sources and destinations.
- [OpenBao Kubernetes authentication](https://openbao.org/docs/auth/kubernetes/): workload identity boundary for a possible later feature.
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): base64 data needs separate encryption and access controls.

These sources explain possible mechanisms. They are not evidence of a deployment in this repository.

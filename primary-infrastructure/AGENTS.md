# Primary infrastructure

Never activate installation, credentials, network forwards, controller permissions,
GitOps synchronization or persistent startup without the owner's exact current
approval. A populated approval file is a local guard, not proof of consent.
Keep generated secrets and recovery material out of tools, logs, Git and CI.
Run validation only inside Docker through the committed workflow. Do not start
Docker, Lima or other services merely to work around validation being unavailable.
Keep all Tether/chat/decision histories, disks and PVCs during rollback. Do not
interrupt encoding jobs. No demo applications or cloud resources belong here.

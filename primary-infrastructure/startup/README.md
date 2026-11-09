# Existing primary: optional login startup

Requires explicit current owner approval to install a persistent startup item.
Publication alone activates nothing. This is an existing management guest, not
a demo service. Do not use this launcher for recovery guests or CI workloads.

Install `start-primary.sh` under the existing user's
`~/Library/Application Support/dots-primary-infrastructure/startup/` directory.
Create a user LaunchAgent named `local.dots.primary-start`, with `RunAtLoad=true`,
`ProgramArguments` of `/bin/sh` and the absolute installed script path,
`ProcessType=Background`, and explicit HOME and standard system PATH variables.
Set StandardOutPath and StandardErrorPath to separate files in that directory.
launchd appends these files; never truncate or rotate away operational history.
Do not set KeepAlive or a timer: this is a single login attempt, not a watchdog.
Load the plist in that user's GUI domain only after approval.

The script pins the dedicated Lima home and exact existing `primary` guest.
It refuses absent guest/runtime, unknown/broken/transitional status, and existing
locks. A running guest is a no-op; a stopped guest is resumed with unchanged
resources. It never creates, provisions, downloads, restores, unseals, changes
network/security, or touches recovery guests. Normal completion and handled
failures/signals release the acquired lock. A lock
left by an unhandled termination needs inspection before manual removal; do not
automatically clear stale locks. There are no retries or watchdog, and the launcher
does not impose a timeout on Lima; a hung operation requires owner inspection.

This runs **after GUI login**, not before login or FileVault unlock. K3s starts
inside the guest through its existing unit. OpenBao Shamir unseal remains an
owner action. No credentials or unseal shares belong in this launcher. Existing
foreground UI forwards do not automatically recover. Sleep and full host reboot
survival must be verified separately; a repeated kickstart is only an idempotence
check. Rollback: unload only this LaunchAgent and preserve guest/disks/logs.

Code tests must run through the repository's Docker validation entrypoint.
Runtime checks: load the installed item, verify exit 0, repeat kickstart against
Running primary, confirm boot identity unchanged and recovery guests still stopped.
A controlled guest stop/start or host reboot needs explicit coordinated scope.

`local.dots.primary-start.plist.template` is the exact generic plist shape.
Replace `__HOME__` with the XML-escaped absolute user home during an authorized
installation. Never load the unresolved template. Keep the plist user-owned;
no elevated daemon, new security permission, or global configuration is needed.

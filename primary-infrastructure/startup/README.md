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
same-boot locks. The lock name includes the validated macOS `kern.bootsessionuuid`;
missing or malformed boot identity refuses startup. Prior-boot locks are preserved
and do not block a new login after restart. A running guest is a no-op; a stopped guest is resumed with unchanged
resources. It never creates, provisions, downloads, restores, unseals, changes
network/security, or touches recovery guests. Normal completion and handled
failures/signals release the acquired lock. A lock
left by an unhandled termination needs inspection before manual removal; do not
automatically clear stale locks. There are no retries or watchdog. Start uses Lima's native `--timeout=180s`
readiness bound, supported by the installed Lima 2.2.1; it is not a whole-process
kill deadline. A hung status query or same-boot lock still needs owner inspection.

This runs **after GUI login**, not before login or FileVault unlock. K3s starts
inside the guest through its existing unit. OpenBao Shamir unseal remains an
owner action. No credentials or unseal shares belong in this launcher. The optional UI agents below recover the existing foreground UI routes. Sleep and full host reboot
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

## Existing UI route recovery

With the same explicit owner approval, install `forward-primary-ui.sh` and the
three `local.dots.primary-ui-*.plist.template` user LaunchAgents alongside the
guest launcher, replacing XML-escaped `__HOME__` as above. The route allowlist is
exactly the existing [access routes](../README.md#access-and-persistence): Homarr
17575:7575, Argo CD 18443:443, and OpenBao 18200:8200, all guest-loopback only.
No credential, service definition, Lima forwarding configuration or bind address
is changed. The script refuses absent/nonrunning primary and never starts it.

These UI agents alone use KeepAlive with a 30-second launchd throttle to recover
foreground port-forwards after guest restart or temporary service unavailability.
They do not watchdog/restart the guest or unseal OpenBao. Separate stdout/stderr
logs are append-only under the startup directory. Existing port conflicts fail
without killing any process. Install only one agent per route; unload these
three agents for rollback and preserve logs. A response from the forwarded UI
must be checked separately from LaunchAgent loaded/running status.

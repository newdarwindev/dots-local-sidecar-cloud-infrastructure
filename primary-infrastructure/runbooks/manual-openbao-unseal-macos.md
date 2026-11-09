# Manually unseal OpenBao from a MacBook Pro terminal

This is an **owner-run procedure for an existing, initialized deployment** of
the [primary reference configuration](../README.md). Publishing it does not
authorize or perform an unseal. Unsealing unlocks the existing secrets service
and can allow already-configured clients to resume accessing their secrets.

The reference uses the dedicated Lima `primary` VM, namespace `openbao`,
pod `openbao-0`, container `openbao`, OpenBao 2.7.2 and TLS-protected Raft storage.
Its initialization plan is three Shamir shares with a threshold of two.
**Check live status rather than assuming that initialization or deployment
has happened.** Actual host status and recovery locations stay outside this
public repository.

## Before starting

- Use your own local Terminal window, not a chat, agent-run command, shared
  terminal, screen recording, or session with input logging. Enable Terminal's
  Secure Keyboard Entry if appropriate for your local workflow; it is not a
  substitute for avoiding recorded/shared sessions.
- Have the required **distinct unseal shares for this exact cluster** available
  through your existing approved recovery process. Do not put them in this repo,
  shell history, command arguments, environment variables, temporary files, tool
  calls, screenshots, tickets, or chat. This procedure does not retrieve, decrypt,
  export, or back up recovery material.
- No root token, `bao login`, Mac OpenBao installation, kubeconfig export, UI
  port-forward, or TLS trust-store change is required. Use the CLI already in the
  running OpenBao container and its mounted CA certificate.
- The VM and pod must already be running. Do not start/restart services,
  initialize/reinitialize OpenBao, rekey, change the seal configuration, or
  enable GitOps as part of this procedure. Those are separate operations.

## 1. Select the existing primary VM on the Mac

Run in a separate private interactive macOS zsh or bash terminal, outside any
agent session. First require a local terminal:

```sh
test -t 0 && test -t 1 && printf "Local terminal is interactive.\n"
```

Stop unless the success message appears. Do not substitute an agent-allocated
TTY or share this terminal with an assistant. Then select the existing VM:

```sh
export LIMA_HOME="$HOME/.local/share/dots-primary-lima"
LIMA="$HOME/Library/Application Support/dots-primary-infrastructure/runtime/bin/limactl"
test -x "$LIMA" && "$LIMA" list primary
```

Stop if the runtime is missing or `primary` is not `Running`. Do not use a
different default Lima instance or add `--start` to work around the problem.

Define this terminal-only convenience function; it contains no credentials:

```sh
primary_kubectl() {
  "$LIMA" shell primary -- sudo /usr/local/bin/k3s kubectl "$@"
}
primary_kubectl -n openbao get pod/openbao-0
```

A sealed pod can be `Running` with `READY 0/1`; that alone is not a reason to
restart it. Stop if the pod is missing, pending, terminating, or crash-looping.
Do not change the target to an arbitrary pod or a load-balanced service.

## 2. Read seal status without a token

```sh
primary_kubectl -n openbao exec openbao-0 -c openbao -- \
  env -i PATH=/bin:/usr/bin:/usr/local/bin HOME=/nonexistent \
  bao status -address=https://127.0.0.1:8200 \
  -ca-cert=/openbao/tls/ca.crt -format=json
```

The isolated container environment avoids inherited token, proxy, address and
TLS-bypass settings. It does not change the pod environment. The CA is used
inside the container; no TLS private key or Kubernetes Secret is printed.

Interpret the response before proceeding:

- `initialized: true`, `sealed: true`, `type: "shamir"`, `t: 2`, `n: 3`,
  `progress: 0`: the reference's normal starting point for a two-share unseal.
- Exit code **2** (including `command terminated with exit code 2`) is expected
  when `bao status` successfully reports a sealed server. Exit code **0** means
  unsealed; other failures need investigation.
- `sealed: false`: skip share entry and go to verification. Do not reseal it
  just to exercise the procedure.
- `initialized: false`, a different seal type, `migration: true`, unexpected
  `t`/`n`, or a different cluster/storage arrangement: stop and review the
  matching recovery instructions. **Do not run `bao operator init`.**
- Nonzero starting `progress`: stop and coordinate with the other key holders. Do not
  automatically reset their work or assume which shares were submitted.
- A TLS, connection, or permissions error is not a sealed-status result. Stop;
  do not use `-tls-skip-verify`, replace certificates, or broaden access.

## 3. Confirm the terminal path without entering a share

```sh
primary_kubectl -n openbao exec -it openbao-0 -c openbao -- \
  sh -c 'test -t 0 && test -t 1 && printf "Container terminal is interactive.\n"'
```

Continue only if the success message appears. Keep stdin and stdout attached to
your terminal. Do not use a pipe, heredoc, `tee`, output redirection or an agent
tool for the following share entry. `-it` is required for the hidden prompt.

Immediately before the first share, repeat steps 1–2 in this private terminal.
Require the same intended running pod, `initialized: true`, `sealed: true`,
`type: "shamir"`, `t: 2`, `n: 3`, `progress: 0`, and no migration. Earlier
observations can become stale while coordinating. Stop on any unexpected state,
existing progress, TLS failure or unavailable TTY; do not reset progress. If
already unsealed, skip share entry and verify. Expected progress `1/2` after
your own first successful submission is handled in steps 4–5.

## 4. Enter the first share at the hidden OpenBao prompt

Run this command **without a share argument**:

```sh
primary_kubectl -n openbao exec -it openbao-0 -c openbao -- \
  env -i PATH=/bin:/usr/bin:/usr/local/bin HOME=/nonexistent \
  bao operator unseal -address=https://127.0.0.1:8200 \
  -ca-cert=/openbao/tls/ca.crt
```

Wait for `Unseal Key (will be hidden):` (wording can vary slightly), then enter
one share and press Return. Characters should not echo. If no hidden prompt
appears, cancel with Control-C. Never append the share to the command or paste it
at a shell prompt. Do not supply a root token or a recovery key from another
cluster.

For the checked two-share threshold, expect `Sealed true` and `Unseal Progress
1/2`. A share submission may exit successfully while the server is still sealed;
read the status fields, not only the exit code.

## 5. Enter a different share using the same command

Run the exact command from step 4 again against the same pod. At its hidden
prompt, enter a **different** share belonging to this cluster. With two valid
distinct shares, expect `Sealed false`. Do not enter a third share after success.

If progress does not advance, the share is rejected, or the pod restarts between
submissions, stop and re-read status. Repeating the same share does not satisfy
the threshold. Do not loop blindly, invoke `-reset`, reinitialize, or rotate keys
to force progress. A pod/server restart clears the in-memory unseal progress.

## 6. Verify and finish

Repeat the status command in step 2. Require `initialized: true`,
`sealed: false`, and exit code 0. Then check Kubernetes readiness:

```sh
primary_kubectl -n openbao wait --for=condition=Ready pod/openbao-0 --timeout=90s
primary_kubectl -n openbao get pod/openbao-0
```

If unsealed but not ready, report the nonsecret status and investigate separately.
Do not restart or redeploy to hide the failure. Unsealed/readiness success is not
proof of audit configuration, application health, access-policy correctness or
recoverable backups.

When done, close this dedicated terminal window. No port-forward or background
job was created. Keep recovery material in its existing approved custody.
When an assistant is coordinating, return only a plain completion confirmation
(e.g. "Finished entering the shares") or a nonsecret failure description. Do not
paste terminal transcripts or send screenshots. The assistant can then repeat
the read-only status and pod readiness checks; completion is not verified until
those checks succeed.

Only record a minimal result such as the time, intended target, sealed/unsealed
state and readiness outcome; never include shares, tokens or private recovery
locations. If you suspect a share was exposed, stop and use the owner's incident
and recovery process; do not erase existing logs or silently rotate credentials.

## Validation notes (2026-11-09)

- Rechecked the owner-run procedure against the official OpenBao 2.7 command
  documentation: no share argument selects the hidden prompt; status exit codes
  distinguish sealed (2), unsealed (0) and error (1).
- Read-only preflight exercised the existing in-pod status command with an
  isolated CLI environment and explicit CA verification. No share was supplied.
  This is preflight evidence only, not evidence of completed unsealing or health.
- `sh validation/run.sh primary`: blocked because the Docker daemon was
  unavailable. No daemon was started and no host validation fallback was used.
- Private-terminal transport and share submission remain owner-run checks.
  Recheck live state each time; these notes do not authorize skipping preflight.

## Limits and troubleshooting

- **Lost shares:** a root token cannot replace Shamir shares. If fewer than the
  threshold remain, stop and consult the approved recovery plan. Reinitializing
  does not unlock existing encrypted storage.
- **Later restarts:** a Shamir-sealed server normally needs manual unsealing
  again after restart. This document adds no automatic unseal or scheduled job.
- **Multiple replicas:** this runbook targets the reference's single replica.
  Each sealed server requires its own unseal operation; review a multi-node plan
  before extending this procedure.
- **TTY error:** use an actual local terminal and `-it`. Do not replace the
  hidden prompt with arguments, environment variables or piped input.
- **TLS error:** confirm the correct existing deployment, certificate validity,
  SAN for `127.0.0.1`, mounted CA and system time through an approved diagnostic
  route. Never bypass certificate verification.

References: [OpenBao operator unseal](https://openbao.org/docs/commands/operator/unseal/),
[status exit codes](https://openbao.org/docs/commands/status/),
[seal and unseal](https://openbao.org/docs/concepts/seal/),
[primary values](../values/openbao.yaml),
[validation boundary](../../validation/README.md).

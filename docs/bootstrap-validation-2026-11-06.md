# Bootstrap validation follow-up — 2026-11-06

**Final result: PASS, exit 0, verified by 2026-11-06T16:42:03Z.**

At this follow-up, source and remote `main` both identified
`fb104839ddb47f3fc8dc09111e535313b865753e` before documentation changes.
The prescribed `sh validation/run.sh primary` returned:

```text
BLOCKED: Docker daemon unavailable. Do not start it merely for validation.
```

No daemon was started, context switched, guest restarted or host test fallback
used. Both GitHub validation workflows were independently read through the API
and remained `disabled_manually`. Publication does not enable them.

Source review located the four intended Docker regression methods in
`primary-infrastructure/validation/check.py`: effective-home existing-instance
and override refusal; registration before readiness with one shared deadline;
hung registration bounded by that deadline; and readiness error/timeout without
installation retry. The launcher uses its dedicated effective `LIMA_HOME` and
one monotonic 180-second deadline, including subprocess timeouts and sleeps.
Those four primary regression methods passed in the later Docker run below.

## Docker runtime returned; build guard repaired

At 16:36 UTC the same command reached the already available Docker runtime;
no daemon was started by this task. The BuildKit image build then failed before
tests: its sandbox does not contain `/.dockerenv`, so the tool installer's guard
incorrectly refused Docker build execution.

The Dockerfile now bind-mounts the existing checksum lockfile read-only during
that build step. The installer accepts this exact read-only mount recorded in
Linux mountinfo, or the existing Docker runtime marker. There is no environment
override, fake marker creation, host install route, checksum bypass or skipped
check. This is an accidental-host-execution guard, not a claim that container
markers or mount metadata resist hostile impersonation. Four new regression
methods cover the read-only mount, wrong/writable/malformed/missing mounts,
symlinks, unavailable mountinfo and refusal before download or installation.

The same `sh validation/run.sh primary` completed successfully after the repair,
during **2026-11-06T16:38:48Z–16:42:03Z**. The tested tree consists of baseline
`fb104839ddb47f3fc8dc09111e535313b865753e` plus this tranche's BuildKit guard,
regression tests and recovery documentation; this result receipt was finalized
after execution. The source implementation and this dated receipt are committed
together; publication is independently verified in the private tranche receipt.

- Docker image build and checksum-verified public tool installation: passed.
- Offline source lint, immutable-pin/fixture/structure/local-link checks: passed.
- Validator suite: **83 tests passed**, including four new build-guard tests.
- Primary suite: **11 tests passed**, including effective `LIMA_HOME` refusal,
  registration-before-readiness, one combined 180-second deadline, hung-command
  bounds and readiness failure without reinstallation.
- Four primary Helm charts rendered/linted; strict schemas: **105 resources in
  10 files, 105 valid, 0 invalid, 0 errors, 0 skipped**.
- Final command exit: **0**. Application/Collector runtime tests were not selected.

The existing management guest was preserved; this is offline source validation,
not execution of the changed bootstrap against it. Both validation workflows
remain paused and are rechecked after publication. Independent encrypted recovery,
TLS/custody and runner execution retain their separate gates.

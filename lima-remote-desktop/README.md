# Lima remote desktop

An optional personal workstation for macOS on Apple silicon. The Ubuntu 24.04
guest starts Xfce with two RDP windows above two SSH panes. The guest uses a dark
theme, hides both panels until edge hover, and raises the selected window with a
2-pixel cyan focus outline. The window layout corrects client resizes.

This VM is independent of the [primary infrastructure VM](../primary-infrastructure/README.md).
Running infrastructure validation or cloning the repository does not start it.

## Create the VM and configure private targets

With Lima 2.2.1 or newer available on the Mac, run `./install.sh` from this
directory to create a **new** `remote-desktop` instance. The script refuses an
existing instance. Keep a working instance and its private keyring in place. To
migrate its settings, compare the files in [guest](guest/) with the installed
files under `~/.local/bin` in that guest and review any alias or keyring-item
name differences before replacing them.

Use a private directory outside the checkout. Copy
[`targets.example.sh`](targets.example.sh) there as `targets.env`, then set
the two RDP account names, the right-hand RDP DNS name or IPv4 address, and
both colon-separated SHA-256 certificate fingerprints. Treat the file as trusted
shell configuration. Obtain fingerprints from the servers over an independently
authenticated channel, such as authenticated SSH and
`openssl x509 -in /etc/xrdp/cert.pem -noout -fingerprint -sha256`.
Use the fingerprint value after the equals sign.

Prepare SSH `config` entries named `rdp-left` and `rdp-right` with the correct
remote usernames and a dedicated `IdentityFile ~/.ssh/rdp_ed25519`. Use
`IdentitiesOnly yes` and a `known_hosts` file with independently verified host
keys. The left profile tunnels xrdp from the target loopback through the SSH
alias. The right profile uses the existing TLS-protected RDP endpoint directly.
The left target's xrdp listener should be bound to `127.0.0.1:3389`
(`port=tcp://127.0.0.1:3389` in xrdp's configuration) and verified before use.

Run these commands with `PRIVATE` set to the private directory you prepared. The
files go directly into the guest user's home with restrictive permissions.

```sh
for file in config known_hosts rdp_ed25519; do
  limactl shell --workdir /tmp remote-desktop bash -se -c '
    umask 077
    install -d -m 700 "$HOME/.ssh"
    cat > "$HOME/.ssh/$1"
    chmod 600 "$HOME/.ssh/$1"
  ' install "$file" < "$PRIVATE/$file"
done

limactl shell --workdir /tmp remote-desktop bash -se -c '
  umask 077
  install -d -m 700 "$HOME/.config/lima-remote-desktop"
  cat > "$HOME/.config/lima-remote-desktop/targets.env"
  chmod 600 "$HOME/.config/lima-remote-desktop/targets.env"
' < "$PRIVATE/targets.env"
```

For xrdp servers that already run an Xfce desktop under the same account, a
new RDP session may exit immediately if it shares the existing session bus.
On a host configured to honor a per-user `startwm.sh`, use an isolated
`dbus-run-session -- xfce4-session` and a dedicated
`XDG_CACHE_HOME=$HOME/.cache/xrdp`. Review any existing startup script before
changing it.

## Enroll and start the dashboard

From a terminal in the Mac's graphical login session, run the following with
the VM running and its desktop signed in.

```sh
/usr/bin/python3 keyring.py enroll
/usr/bin/python3 keyring.py install-agent
limactl restart remote-desktop
```

Enrollment prompts without echo and saves the two items in the encrypted guest
Login collection. The Mac's login keychain keeps the independent unlock secret
under `Lima.remote-desktop.login`. The user LaunchAgent unlocks the collection
at most once per guest desktop session while the Mac keychain is available.
The guest signs in automatically, and FreeRDP reads the passwords via standard
input using the configured certificate pins. Lima ignores guest port forwards,
including the dashboard's loopback SSH tunnel. Keep local targets, SSH keys,
keyring files, and VM state outside Git.

## Confirm the result

After restart, confirm that both RDP desktops load and the two SSH panes reach
the intended hosts. Click each tile to test focus, then move the pointer to
the top center or bottom center to check panel reveal and hide. If a pane or
session fails, check the expected SSH alias, the configured certificate pin and
the guest's per-session client logs under
`$XDG_RUNTIME_DIR/rdp-login-dashboard/`. Keep runtime logs private.

To stop future automatic keyring unlocks, unload the user LaunchAgent with
`launchctl bootout "gui/$(id -u)/local.lima.remote-desktop.keyring"` and remove
its `local.lima.remote-desktop.keyring.plist` from `~/Library/LaunchAgents`.
This leaves the VM and its encrypted keyring available for recovery.

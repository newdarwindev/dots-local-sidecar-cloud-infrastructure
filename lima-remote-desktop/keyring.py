#!/usr/bin/env python3
"""Enroll local RDP passwords and install the Mac-to-guest keyring unlock agent."""
import ctypes
import getpass
import json
import os
import plistlib
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

INSTANCE = "remote-desktop"
SERVICE = f"Lima.{INSTANCE}.login".encode()
LABEL = f"local.lima.{INSTANCE}.keyring"
GUEST_TOOL = 'exec "$HOME/.local/bin/lima-rdp-secret-service" "$@"'
SESSION_STATE = """
set -eu
user=$(id -un)
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
desktop=$(loginctl show-seat seat0 -p ActiveSession --value)
[ -n "$desktop" ] || exit 0
[ "$(loginctl show-session "$desktop" -p Name --value)" = "$user" ] || exit 0
[ "$(loginctl show-session "$desktop" -p Type --value)" = x11 ] || exit 0
marker="$XDG_RUNTIME_DIR/rdp-dashboard-unlocked-$desktop"
[ ! -e "$marker" ] || exit 0
locked=$(busctl --user get-property org.freedesktop.secrets /org/freedesktop/secrets/collection/login org.freedesktop.Secret.Collection Locked)
if [ "$locked" = "b false" ]; then
    install -m 600 /dev/null "$marker"
else
    printf '%s' "$desktop"
fi
"""
UNLOCK = """
set -eu
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
[ "$(loginctl show-seat seat0 -p ActiveSession --value)" = "$1" ] || exit 1
"$HOME/.local/bin/lima-rdp-secret-service" unlock
locked=$(busctl --user get-property org.freedesktop.secrets /org/freedesktop/secrets/collection/login org.freedesktop.Secret.Collection Locked)
[ "$locked" = "b false" ]
install -m 600 /dev/null "$XDG_RUNTIME_DIR/rdp-dashboard-unlocked-$1"
"""


def keychain_password(create=False):
    security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    if not create:
        security.SecKeychainSetUserInteractionAllowed(False)

    # This is the macOS local user, which owns the Keychain entry.
    account = os.fsencode(Path.home().name)
    pointer, string, size = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32
    find = security.SecKeychainFindGenericPassword
    find.argtypes = [pointer, size, string, size, string, ctypes.POINTER(size),
                     ctypes.POINTER(pointer), pointer]
    find.restype = ctypes.c_int32
    length, data = size(), pointer()
    status = find(None, len(SERVICE), SERVICE, len(account), account,
                  ctypes.byref(length), ctypes.byref(data), None)
    if status == -25300 and create:  # errSecItemNotFound
        password = secrets.token_urlsafe(32).encode()
        add = security.SecKeychainAddGenericPassword
        add.argtypes = [pointer, size, string, size, string, size, pointer, pointer]
        add.restype = ctypes.c_int32
        if add(None, len(SERVICE), SERVICE, len(account), account, len(password), password, None):
            raise RuntimeError("Cannot create the macOS Keychain entry")
        return password
    if status:
        raise RuntimeError("Cannot read the macOS Keychain entry")
    release = security.SecKeychainItemFreeContent
    release.argtypes = [pointer, pointer]
    try:
        return ctypes.string_at(data, length.value)
    finally:
        release(None, data)


def guest_command(lima):
    return [lima, "shell", "--workdir", "/tmp", INSTANCE]


def enroll(lima):
    payload = {slot: getpass.getpass(f"RDP password for {slot}: ")
               for slot in ("rdp-left", "rdp-right")}
    if not all(payload.values()):
        raise ValueError("RDP passwords must be nonempty")
    payload["master"] = keychain_password(create=True).decode()
    subprocess.run(guest_command(lima) + ["bash", "-c", GUEST_TOOL, "keyring", "enroll"],
                   input=json.dumps(payload).encode(), check=True, timeout=15)


def unlock(lima):
    if not (Path.home() / ".lima" / INSTANCE / "ha.sock").is_socket():
        return
    guest = guest_command(lima)
    result = subprocess.run(guest + ["bash", "-c", SESSION_STATE],
                            capture_output=True, timeout=6, check=False)
    desktop = result.stdout.decode().strip()
    if result.returncode or not desktop:
        return
    if not desktop.isalnum():
        raise ValueError("Invalid guest session ID")
    subprocess.run(guest + ["bash", "-c", UNLOCK, "unlock", desktop],
                   input=keychain_password(), check=True, timeout=8)


def install_agent(lima):
    home = Path.home()
    folder = home / "Library/Application Support/Lima Remote Desktop"
    folder.mkdir(mode=0o700, exist_ok=True)
    executable = folder / "unlock-keyring.py"
    shutil.copyfile(Path(__file__).resolve(), executable)
    executable.chmod(0o700)
    agents = home / "Library/LaunchAgents"
    agents.mkdir(mode=0o700, exist_ok=True)
    plist = agents / (LABEL + ".plist")
    with plist.open("wb") as stream:
        plistlib.dump({
            "Label": LABEL,
            "ProgramArguments": ["/usr/bin/python3", str(executable), "unlock", lima],
            "StartInterval": 10,
            "RunAtLoad": True,
            "StandardErrorPath": str(home / "Library/Logs/lima-remote-desktop-keyring.log"),
        }, stream)
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)


def main():
    os.umask(0o077)
    if sys.argv[1:2] == ["unlock"] and len(sys.argv) == 3:
        unlock(sys.argv[2])
        return
    if len(sys.argv) != 2 or sys.argv[1] not in {"enroll", "install-agent"}:
        sys.exit("Usage: /usr/bin/python3 keyring.py enroll|install-agent")
    if os.environ.get("LIMA_HOME"):
        sys.exit("Use the default Lima home with this recipe")
    lima = shutil.which("limactl")
    if not lima:
        sys.exit("limactl must be on PATH")
    if sys.argv[1] == "enroll":
        enroll(lima)
    else:
        install_agent(lima)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        sys.exit("Lima RDP keyring operation deferred or failed.")

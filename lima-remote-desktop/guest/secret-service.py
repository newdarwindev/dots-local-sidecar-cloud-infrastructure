#!/usr/bin/env python3
"""Enroll or unlock the dedicated GNOME Login collection via the guest session bus."""
import json
import os
import sys

from gi.repository import Gio, GLib

SERVICE = "org.freedesktop.secrets"
ROOT = "/org/freedesktop/secrets"
COLLECTION = ROOT + "/collection/login"
SECRET = "org.freedesktop.Secret"
MASTER = "org.gnome.keyring.InternalUnsupportedGuiltRiddenInterface"


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"enroll", "unlock"}:
        raise ValueError("Expected enroll or unlock")
    enrollment = sys.argv[1] == "enroll"
    payload = json.load(sys.stdin) if enrollment else {"master": sys.stdin.read()}
    if not payload["master"]:
        raise ValueError("Missing login keyring unlock credential")

    runtime = f"/run/user/{os.getuid()}"
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime}/bus"
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def call(path, interface, method, parameters=None):
        return bus.call_sync(SERVICE, path, interface, method, parameters, None,
                             Gio.DBusCallFlags.NONE, 3500, None)

    _, session = call(ROOT, SECRET + ".Service", "OpenSession",
                      GLib.Variant("(sv)", ("plain", GLib.Variant("s", "")))).unpack()

    def secret(value):
        return (session, b"", value.encode(), "text/plain")

    try:
        if enrollment:
            collections, = call(ROOT, "org.freedesktop.DBus.Properties", "Get",
                                GLib.Variant("(ss)", (SECRET + ".Service", "Collections"))).unpack()
            if COLLECTION not in collections:
                props = {SECRET + ".Collection.Label": GLib.Variant("s", "login")}
                path, = call(ROOT, MASTER, "CreateWithMasterPassword", GLib.Variant(
                    "(a{sv}(oayays))", (props, secret(payload["master"])))).unpack()
                if path != COLLECTION:
                    raise RuntimeError("The Login collection could not be created")
        call(ROOT, MASTER, "UnlockWithMasterPassword", GLib.Variant(
            "(o(oayays))", (COLLECTION, secret(payload["master"]))))
        if enrollment:
            for slot in ("rdp-left", "rdp-right"):
                properties = {
                    SECRET + ".Item.Label": GLib.Variant("s", f"RDP dashboard ({slot})"),
                    SECRET + ".Item.Attributes": GLib.Variant(
                        "a{ss}", {"application": "rdp-dashboard", "host": slot}
                    ),
                }
                if not payload[slot]:
                    raise ValueError("Empty RDP password")
                item, prompt = call(COLLECTION, SECRET + ".Collection", "CreateItem", GLib.Variant(
                    "(a{sv}(oayays)b)", (properties, secret(payload[slot]), True))).unpack()
                if item == "/" or prompt != "/":
                    raise RuntimeError("The RDP item could not be stored in the unlocked keyring")
    finally:
        call(session, SECRET + ".Session", "Close")


if __name__ == "__main__":
    try:
        main()
    except (GLib.Error, OSError, ValueError, KeyError, RuntimeError):
        sys.exit("The guest login keyring operation failed.")

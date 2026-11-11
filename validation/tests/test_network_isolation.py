"""Fail-closed regression for Docker hosts with inert default tunnel devices."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('network_isolation',
    Path(__file__).resolve().parents[1] / 'network_isolation.py')
NETWORK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NETWORK)


class NetworkIsolationTests(unittest.TestCase):
    def test_loopback_and_inert_defaults_only(self):
        interfaces = {'lo': (9, 772)}
        self.assertTrue(NETWORK.isolated(interfaces, [], ['lo'], 0))
        interfaces.update({name: (0x80, kind) for name, kind in NETWORK.INERT_TUNNELS.items()})
        self.assertTrue(NETWORK.isolated(interfaces, [], ['lo'], 0))
        for name in NETWORK.INERT_TUNNELS:
            changed = dict(interfaces)
            changed[name] = (1, changed[name][1])
            self.assertFalse(NETWORK.isolated(changed, [], ['lo'], 0))

    def test_network_access_and_unknown_devices_rejected(self):
        local = {'lo': (9, 772)}
        for interfaces, routes, ipv6, caps in [
                ({}, [], [], 0), (local, ['route'], [], 0),
                (local, [], ['gre0'], 0), (local, [], [], 0x1000),
                ({**local, 'eth0': (0, 1)}, [], [], 0),
                ({**local, 'tunl0': (0, 1)}, [], [], 0)]:
            self.assertFalse(NETWORK.isolated(interfaces, routes, ipv6, caps))

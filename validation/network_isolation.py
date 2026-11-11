"""Require an isolated Docker network namespace, allowing inert kernel tunnels."""
from pathlib import Path
import socket

# Some Docker hosts create these DOWN fallback devices even for --network=none.
# Match both names and kernel ARPHRD types; never admit an arbitrary interface.
INERT_TUNNELS = {'tunl0': 768, 'gre0': 778, 'gretap0': 1, 'erspan0': 1,
                'ip_vti0': 768, 'ip6_vti0': 769, 'sit0': 776,
                'ip6tnl0': 769, 'ip6gre0': 823}


def isolated(interfaces, routes, ipv6_interfaces, effective_caps):
    if effective_caps != 0 or 'lo' not in interfaces:
        return False
    if routes or any(name != 'lo' for name in ipv6_interfaces):
        return False
    for name, (flags, kind) in interfaces.items():
        if name == 'lo':
            if kind != 772:
                return False
        elif name not in INERT_TUNNELS or kind != INERT_TUNNELS[name] or flags & 1:
            return False
    return True


def require_isolated_network():
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker-only runtime checks')
    base = Path('/sys/class/net')
    interfaces = {name: (int((base / name / 'flags').read_text(), 16),
                         int((base / name / 'type').read_text()))
                  for _, name in socket.if_nameindex()}
    routes = Path('/proc/net/route').read_text().splitlines()[1:]
    ipv6 = [line.split()[-1] for line in Path('/proc/net/if_inet6').read_text().splitlines()]
    caps = next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines()
                if line.startswith('CapEff:'))
    if not isolated(interfaces, routes, ipv6, int(caps, 16)):
        raise RuntimeError('Runtime checks require no routes, no active non-loopback interfaces, and no capabilities')

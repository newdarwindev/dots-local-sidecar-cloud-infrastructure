#!/usr/bin/env python3
"""Login-scoped surf desktop window and explicitly configured loopback forwards."""
import argparse
import ctypes
from datetime import datetime, timezone
import fcntl
import html
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener


def geometry(screen, conky=None):
    """Keep an icon column, panel clearance and gap before the actual Conky edge."""
    sx, sy, width, height = screen
    left = sx + (112 if width >= 1280 else 24)
    right = conky[0] - 42 if conky else sx + width - 24
    if right - left < 320:
        left = sx + 8
    if right - left < 160:
        raise ValueError('No usable dashboard space beside Conky')
    return left, sy + 56, right - left, max(160, height - 80)


def validate_config(config):
    forwards = config.get('forwards', [])
    ports, identifiers = set(), set()
    cluster = config.get('cluster', {})
    if forwards and not all(cluster.get(k) for k in ('context', 'system_namespace_uid', 'namespace_uids')):
        raise ValueError('Forwarding requires pinned cluster and namespace identities')
    for item in forwards:
        for key in ('id', 'namespace', 'service'):
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', item.get(key, '')):
                raise ValueError('Invalid forward identity')
        if item['id'] in identifiers:
            raise ValueError('Duplicate forward identity')
        identifiers.add(item['id'])
        for key in ('local_port', 'remote_port'):
            if type(item.get(key)) is not int or not 1024 <= item[key] <= 65535:
                raise ValueError('Use explicit unprivileged TCP ports')
        if item['local_port'] in ports:
            raise ValueError('Duplicate local port')
        ports.add(item['local_port'])
        if not cluster['namespace_uids'].get(item['namespace']):
            raise ValueError('Missing namespace identity pin')
    for item in config.get('links', []):
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', item.get('id', '')):
            raise ValueError('Invalid link identity')
        if item.get('forward') and item['forward'] not in identifiers:
            raise ValueError('Unknown forward')
        if not item.get('path', '/').startswith('/') or item.get('path', '/').startswith('//'):
            raise ValueError('Forward paths must be relative to their pinned origin')
        if item.get('url'):
            url = urlsplit(item['url'])
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ValueError('Bookmarks require credential-free HTTPS URLs')
    if config.get('start', 'home') not in {'home', *(item['id'] for item in config.get('links', []))}:
        raise ValueError('Unknown start page')
    return config


def child_lifetime():
    # Linux: children also stop if the supervisor is killed before cleanup runs.
    ctypes.CDLL(None).prctl(1, signal.SIGTERM)


def spawn(args, **kwargs):
    return subprocess.Popen(args, start_new_session=True, preexec_fn=child_lifetime, **kwargs)


def stop_child(child):
    if child is not None and child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=3)


def cluster_matches(cluster, namespace):
    """Read namespace UIDs only; never inspect or copy kubeconfig credentials."""
    for name, expected in [('kube-system', cluster['system_namespace_uid']),
                           (namespace, cluster['namespace_uids'][namespace])]:
        result = subprocess.run(
            ['kubectl', '--context', cluster['context'], '--request-timeout=4s',
             'get', 'namespace', name, '-o', 'jsonpath={.metadata.uid}'],
            capture_output=True, text=True, timeout=6, check=False)
        if result.returncode or result.stdout.strip() != expected:
            return False
    return True


class Forward:
    def __init__(self, spec, cluster, state):
        self.spec, self.cluster, self.state = spec, cluster, state
        self.child = None
        self.last_attempt = 0.0
        self.ready = False
        self.log = (state / (spec['id'] + '-forward.log')).open('a', buffering=1)

    @property
    def origin(self):
        return f'http://127.0.0.1:{self.spec["local_port"]}'

    def update(self):
        if self.child is None or self.child.poll() is not None:
            self.ready = False
            if time.monotonic() - self.last_attempt < 30:
                return
            self.last_attempt = time.monotonic()
            try:
                if not cluster_matches(self.cluster, self.spec['namespace']):
                    print(f'{self.spec["id"]}: cluster/namespace mismatch or unavailable', flush=True)
                    return
                # Refuse to adopt another process's listener, including an old forward.
                with socket.socket() as probe:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    probe.bind(('127.0.0.1', self.spec['local_port']))
                self.child = spawn(
                    ['kubectl', '--context', self.cluster['context'],
                     '-n', self.spec['namespace'], 'port-forward', '--address=127.0.0.1',
                     'service/' + self.spec['service'],
                     f'{self.spec["local_port"]}:{self.spec["remote_port"]}'],
                    stdout=self.log, stderr=subprocess.STDOUT)
            except (OSError, subprocess.TimeoutExpired):
                print(f'{self.spec["id"]}: forward unavailable; retry in 30s', flush=True)
                return
        try:
            # Loopback only, without an HTTP proxy or ambient proxy credentials.
            with build_opener(ProxyHandler({})).open(self.origin, timeout=2) as response:
                self.ready = response.status == 200 and self.child.poll() is None
        except OSError:
            self.ready = False

    def close(self):
        stop_child(self.child)
        self.log.close()


class DesktopWindow:
    def __init__(self, window_id):
        from Xlib import X, XK, Xatom, display
        from Xlib.protocol import event
        self.X, self.Xatom, self.event = X, Xatom, event
        self.display = display.Display()
        self.root = self.display.screen().root
        self.window = self.display.create_resource_object('window', window_id)
        self.window.set_wm_class('DesktopDashboards', 'DesktopDashboards')
        self.window.change_property(self.atom('_MOTIF_WM_HINTS'), self.atom('_MOTIF_WM_HINTS'),
                                    32, [2, 0, 0, 0, 0])
        self.window.change_property(self.atom('_NET_WM_WINDOW_TYPE'), Xatom.ATOM, 32,
                                    [self.atom('_NET_WM_WINDOW_TYPE_DESKTOP')])
        self.window.change_property(self.atom('_NET_WM_DESKTOP'), Xatom.CARDINAL, 32, [0xffffffff])
        states = ['_NET_WM_STATE_STICKY', '_NET_WM_STATE_SKIP_TASKBAR',
                  '_NET_WM_STATE_SKIP_PAGER', '_NET_WM_STATE_BELOW']
        for state in states:
            self.message('_NET_WM_STATE', [1, self.atom(state), 0, 2, 0])
        self.message('_NET_WM_DESKTOP', [0xffffffff, 2, 0, 0, 0])
        self.home_key = self.display.keysym_to_keycode(XK.string_to_keysym('Home'))
        for lock in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
            self.window.grab_key(self.home_key, X.ControlMask | X.Mod1Mask | X.ShiftMask | lock,
                                 False, X.GrabModeAsync, X.GrabModeAsync)
        self.display.sync()
        self.last_geometry = None

    def atom(self, name):
        return self.display.intern_atom(name)

    def message(self, name, values):
        self.root.send_event(self.event.ClientMessage(window=self.window, client_type=self.atom(name),
                                                      data=(32, values)),
                             event_mask=self.X.SubstructureRedirectMask | self.X.SubstructureNotifyMask)
        self.display.flush()

    def placement(self):
        screen = self.root.get_geometry()
        monitor = (0, 0, screen.width, screen.height)
        conky = None
        clients = self.root.get_full_property(self.atom('_NET_CLIENT_LIST'), self.Xatom.WINDOW)
        for identifier in clients.value if clients else []:
            candidate = self.display.create_resource_object('window', identifier)
            if 'ConkyDashboard' in (candidate.get_wm_class() or ()):
                pos = self.root.translate_coords(candidate, 0, 0)
                box = candidate.get_geometry()
                conky = (pos.x, pos.y, box.width, box.height)
                break
        try:
            output = subprocess.run(['xrandr', '--listmonitors'], capture_output=True,
                                    text=True, timeout=3, check=True).stdout
            boxes = re.findall(r'(\d+)/\d+x(\d+)/\d+\+(-?\d+)\+(-?\d+)', output)
            for width, height, x, y in boxes:
                candidate = tuple(map(int, (x, y, width, height)))
                if conky is None or candidate[0] <= conky[0] < candidate[0] + candidate[2]:
                    monitor = candidate
                    break
        except (OSError, subprocess.SubprocessError):
            pass
        box = geometry(monitor, conky)
        if box != self.last_geometry:
            self.message('_NET_MOVERESIZE_WINDOW', [0x2f00, *box])
            self.window.configure(stack_mode=self.X.Above)
            self.display.flush()
            self.last_geometry = box
        return box

    def navigate(self, url):
        encoded = url.encode('utf-8')
        self.window.change_property(self.atom('_SURF_GO'), self.atom('UTF8_STRING'), 8, encoded)
        self.display.flush()

    def restore_focus(self, previous):
        if previous:
            self.root.send_event(self.event.ClientMessage(window=previous,
                                 client_type=self.atom('_NET_ACTIVE_WINDOW'),
                                 data=(32, [2, self.X.CurrentTime, 0, 0, 0])),
                                 event_mask=self.X.SubstructureRedirectMask | self.X.SubstructureNotifyMask)
            self.display.flush()

    def home_pressed(self):
        result = False
        while self.display.pending_events():
            item = self.display.next_event()
            result |= item.type == self.X.KeyPress and item.detail == self.home_key
        return result


def write_hub(state, config, forwards, running=True, profile=None):
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    links = []
    records = []
    for item in config.get('links', []):
        forward = forwards.get(item.get('forward'))
        url = forward.origin + item.get('path', '/') if forward and forward.ready else item.get('url')
        status = ('Available locally' if forward.ready else 'Connection unavailable') if forward else item.get('status', 'Reference')
        label = html.escape(item['name'])
        body = f'<strong>{label}</strong><span>{html.escape(status)}</span><small>{html.escape(item.get("description", ""))}</small>'
        links.append(f'<a href="{html.escape(url, quote=True)}">{body}</a>' if url else f'<div class="inactive">{body}</div>')
        records.append({'id': item['id'], 'status': status, 'url': url})
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30"><title>Desktop dashboards</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;padding:32px;background:#111d29;color:#dce5ef;font:16px/1.5 system-ui,sans-serif}
h1{color:#66ddca;font-weight:500;margin:0}p{color:#a1b4c5}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(225px,1fr));gap:16px;margin:28px 0}
a,.inactive{display:flex;flex-direction:column;gap:9px;border:1px solid #304657;background:#182a38;border-radius:10px;padding:22px;color:inherit;text-decoration:none}
a:hover,a:focus{border-color:#66ddca}.inactive{opacity:.65}strong{font-weight:500;font-size:20px}span{color:#66ddca}small,footer{color:#a1b4c5;font-size:13px}
</style><h1>Desktop dashboards</h1><p>One page at a time · Ctrl + Alt + Shift + Home returns here</p><main>'''
    page += ''.join(links) + f'</main><footer>Local connection check: {now}<br>Unavailable and staged applications stay inactive.</footer></html>'
    ((profile or state) / 'home.html').write_text(page)
    report = {'observed_at': now, 'supervisor_running': running, 'links': records}
    temporary = state / 'status.tmp'
    temporary.write_text(json.dumps(report, indent=2) + '\n')
    temporary.replace(state / 'status.json')
    return records


def paths():
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'desktop-dashboard'
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', state)) / 'desktop-dashboard'
    return state, runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path.home() / '.config/desktop-dashboard/config.json')
    parser.add_argument('--autostart', action='store_true')
    parser.add_argument('--home', action='store_true')
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    state, runtime = paths()
    # Keep browser-facing files inside surf's distribution AppArmor allowlist.
    profile = Path.home() / '.surf/desktop-dashboard'
    for directory in (state, runtime, profile):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    address = str(runtime / 'control.sock')
    if args.status:
        report = json.loads((state / 'status.json').read_text()) if (state / 'status.json').exists() else {}
        with (runtime / 'instance.lock').open('a') as probe:
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                active = False
            except BlockingIOError:
                active = True
        report['supervisor_running'] = active
        if not active:
            for item in report.get('links', []):
                if item['status'] == 'Available locally':
                    item.update(status='Not running', url=None)
        print(json.dumps(report, indent=2))
        return
    lock = (runtime / 'instance.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
            control.sendto(b'stop' if args.stop else b'home', address)
        if args.stop:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except BlockingIOError:
                    time.sleep(0.1)
            raise RuntimeError('Desktop supervisor has not finished stopping')
        return
    if args.stop:
        return
    config = validate_config(json.loads(args.config.read_text()))
    log = (state / 'dashboard.log').open('a', buffering=1)
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)
    if args.autostart:
        time.sleep(12)
    print(datetime.now(timezone.utc).isoformat(), 'session starting', flush=True)
    if os.path.exists(address):
        os.unlink(address)
    control = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    control.bind(address)
    control.setblocking(False)
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    forwards = {item['id']: Forward(item, config.get('cluster', {}), state) for item in config.get('forwards', [])}
    browser = None
    home = (profile / 'home.html').as_uri()
    try:
        for _ in range(12):
            for forward in forwards.values():
                forward.update()
            if all(forward.ready for forward in forwards.values()) or not running:
                break
            time.sleep(1)
        records = write_hub(state, config, forwards, profile=profile)
        target = next((item['url'] for item in records if item['id'] == config.get('start') and item['url']), home)
        cookies = profile / 'cookies.txt'
        cookies.touch(exist_ok=True, mode=0o600)
        from Xlib import display, Xatom
        focus_display = display.Display()
        active = focus_display.screen().root.get_full_property(
            focus_display.intern_atom('_NET_ACTIVE_WINDOW'), Xatom.WINDOW)
        previous = int(active.value[0]) if active is not None and len(active.value) else 0
        focus_display.close()
        browser = spawn(['surf', '-w', '-f', '-T', '-x', '-g', '-n', '-B', '-d', '-a', '@',
                         '-c', str(cookies), target], stdout=subprocess.PIPE, stderr=log, text=True)
        readable, _, _ = select.select([browser.stdout], [], [], 20)
        if not readable:
            raise RuntimeError('Browser did not create a window')
        window = DesktopWindow(int(browser.stdout.readline().strip(), 0))
        window.restore_focus(previous)
        ticks = 0
        while running and browser.poll() is None:
            window.placement()
            if window.home_pressed():
                window.navigate(home)
            try:
                command = control.recv(32)
                if command == b'stop':
                    break
                window.navigate(home)
            except BlockingIOError:
                pass
            if ticks % 5 == 0:
                for forward in forwards.values():
                    forward.update()
                write_hub(state, config, forwards, profile=profile)
            ticks += 1
            time.sleep(1)
    finally:
        stop_child(browser)
        for forward in forwards.values():
            forward.close()
            forward.ready = False
        write_hub(state, config, forwards, running=False, profile=profile)
        control.close()
        if os.path.exists(address):
            os.unlink(address)
        print(datetime.now(timezone.utc).isoformat(), 'session stopped', flush=True)


if __name__ == '__main__':
    main()

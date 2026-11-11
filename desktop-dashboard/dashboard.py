#!/usr/bin/env python3
"""Login-scoped surf desktop window and explicitly configured loopback forwards."""
import argparse
import ctypes
from datetime import datetime, timezone
import fcntl
import html
import json
import math
import os
from pathlib import Path
import re
import select
import signal
import shutil
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


def pane_geometries(area, weights, gap=16):
    """Tile the available desktop without overlapping Conky or other panes."""
    x, y, width, height = area
    count = len(weights)
    vertical = width - gap * (count - 1) < 160 * count
    extent = (height if vertical else width) - gap * (count - 1)
    if extent < 160 * count:
        raise ValueError('Display is too small for the configured dashboard panes')
    sizes = [int(extent * weight / sum(weights)) for weight in weights]
    sizes[-1] += extent - sum(sizes)
    for index, size in enumerate(sizes):
        if size < 160:
            difference = 160 - size
            sizes[index] = 160
            largest = max(range(count), key=lambda candidate: sizes[candidate])
            sizes[largest] -= difference
    boxes, offset = [], 0
    for size in sizes:
        boxes.append((x, y + offset, width, size) if vertical else (x + offset, y, size, height))
        offset += size + gap
    return boxes


def langfuse_preferences(url, interval, all_history=False):
    """Native v4 preferences, scoped to this exact local project and origin."""
    parsed = urlsplit(url)
    project = re.match(r'/project/([^/]+)/', parsed.path)
    if parsed.scheme not in ('http', 'https') or project is None:
        raise ValueError('Langfuse refresh needs a project-specific HTTP URL')
    settings = json.dumps({'origin': parsed.scheme + '://' + parsed.netloc, 'project': project[1], 'interval': interval,
                           'allHistory': all_history, 'path': parsed.path})
    return '''(() => {
const preference = SETTINGS;
if (location.origin !== preference.origin || !location.pathname.startsWith('/project/' + preference.project + '/')) return;
try {
 if (preference.allHistory && location.pathname === preference.path) {
  // Advance the native custom-date filter without interrupting detail pages.
  const refreshHistory = () => {
   const next = new URL(location.href);
   next.searchParams.set('dateRange', '0-' + Date.now());
   location.replace(next.href);
  };
  const range = new URL(location.href).searchParams.get('dateRange') || '';
  const upper = /^0-[0-9]+$/.test(range) ? Number(range.slice(2)) : 0;
  if (!upper || Date.now() - upper > preference.interval * 2) {
   refreshHistory();
   return;
  }
  setTimeout(refreshHistory, preference.interval);
 }
 const marker = 'desktop-refresh-configured-' + preference.project;
 if (sessionStorage.getItem(marker)) return;
 const keys = ['tableRefreshInterval-events-' + preference.project, 'tableRefreshInterval-' + preference.project];
 let reload = false;
 for (const key of keys) {
  const value = JSON.stringify(preference.interval);
  if (sessionStorage.getItem(key) !== value) { sessionStorage.setItem(key, value); reload = true; }
 }
 if (localStorage.getItem('sidebar:state') !== 'false') { localStorage.setItem('sidebar:state', 'false'); reload = true; }
 sessionStorage.setItem(marker, 'true');
 if (reload) location.reload();
} catch (error) { console.warn('Desktop refresh preferences unavailable'); }
})();'''.replace('SETTINGS', settings)


def validate_config(config):
    workspace = config.get('workspace')
    if workspace is not None and (type(workspace) is not int or not 0 <= workspace <= 31):
        raise ValueError('Workspace must be a zero-based desktop index from 0 to 31')
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
        scheme = item.get('scheme', 'http')
        if not isinstance(scheme, str) or scheme not in {'http', 'https'}:
            raise ValueError('Forward scheme must be HTTP or HTTPS')
        health_path = item.get('health_path', '/')
        if (not isinstance(health_path, str) or not health_path.startswith('/') or health_path.startswith('//')
                or '?' in health_path or '#' in health_path or any(ord(char) < 32 for char in health_path)):
            raise ValueError('Forward health path must be a local path')
        if item['local_port'] in ports:
            raise ValueError('Duplicate local port')
        ports.add(item['local_port'])
        if not cluster['namespace_uids'].get(item['namespace']):
            raise ValueError('Missing namespace identity pin')
    link_ids = set()
    for item in config.get('links', []):
        if item.get('id') in link_ids or (item.get('id') == 'overview' and config.get('overview')):
            raise ValueError('Duplicate or reserved link identity')
        link_ids.add(item.get('id'))
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
    overview = config.get('overview')
    if overview:
        if not all(cluster.get(key) for key in ('context', 'system_namespace_uid', 'namespace_uids')):
            raise ValueError('Live overview requires pinned cluster identities')
        if not cluster['namespace_uids'].get(overview.get('namespace')):
            raise ValueError('Live overview requires a pinned namespace')
        if type(overview.get('port')) is not int or not 1024 <= overview['port'] <= 65535 or overview['port'] in ports:
            raise ValueError('Live overview requires its own unprivileged local port')
        if type(overview.get('refresh_seconds', 15)) is not int or not 5 <= overview.get('refresh_seconds', 15) <= 300:
            raise ValueError('Live overview refresh must be 5–300 seconds')
        live_path = overview.get('live_health_credentials')
        if live_path and (not isinstance(live_path, str) or not Path(live_path).is_absolute() or
                          not any(item['id'] == 'langfuse' for item in forwards)):
            raise ValueError('Live health export needs an absolute credential path and the owned Langfuse forward')
    if config.get('start', 'home') not in {'home', *(['overview'] if overview else []), *(item['id'] for item in config.get('links', []))}:
        raise ValueError('Unknown start page')
    panes = config.get('panes')
    if panes is not None:
        if not isinstance(panes, list) or not 1 <= len(panes) <= 3:
            raise ValueError('Configure one to three dashboard panes')
        available = {'home', *(['overview'] if overview else []), *(item['id'] for item in config.get('links', []))}
        selected = set()
        for pane in panes:
            if pane.get('link') not in available or pane['link'] in selected:
                raise ValueError('Dashboard panes require distinct known links')
            selected.add(pane['link'])
            weight, zoom = pane.get('weight', 1), pane.get('zoom', 1)
            if type(weight) not in (int, float) or not math.isfinite(weight) or weight <= 0:
                raise ValueError('Dashboard pane weights must be positive finite numbers')
            if type(zoom) not in (int, float) or not .5 <= zoom <= 2:
                raise ValueError('Dashboard zoom must be between 0.5 and 2')
            if 'langfuse_refresh_ms' in pane and pane['langfuse_refresh_ms'] not in (30000, 60000, 300000, 900000):
                raise ValueError('Use a native Langfuse refresh interval')
            if type(pane.get('langfuse_all_history', False)) is not bool:
                raise ValueError('Langfuse all-history must be a boolean')
            if pane.get('langfuse_all_history') and not pane.get('langfuse_refresh_ms'):
                raise ValueError('Langfuse all-history requires a refresh interval')
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


def orphaned_pane(args, parent, executable, profile):
    if parent != 1 or Path(executable).name != 'surf' or '-c' not in args:
        return False
    index = args.index('-c') + 1
    if index >= len(args):
        return False
    cookie = Path(args[index])
    return cookie.parent == profile and bool(re.fullmatch(r'cookies(?:-[a-z0-9-]+)?\.txt', cookie.name))


def retire_orphaned_panes(profile):
    for entry in Path('/proc').glob('[0-9]*'):
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            args = (entry / 'cmdline').read_bytes().decode().rstrip('\0').split('\0')
            parent = int((entry / 'stat').read_text().rsplit(')', 1)[1].split()[1])
            if orphaned_pane(args, parent, os.readlink(entry / 'exe'), profile):
                os.kill(int(entry.name), signal.SIGTERM)
                print('Retired orphaned dashboard pane', entry.name, flush=True)
        except (OSError, ValueError, UnicodeError):
            continue


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
        scheme = self.spec.get('scheme', 'http')
        host = 'localhost' if scheme == 'https' else '127.0.0.1'
        return f'{scheme}://{host}:{self.spec["local_port"]}'

    @property
    def health_url(self):
        return self.origin + self.spec.get('health_path', '/')

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
            with build_opener(ProxyHandler({})).open(self.health_url, timeout=2) as response:
                self.ready = response.status == 200 and self.child.poll() is None
        except OSError:
            self.ready = False

    def close(self):
        stop_child(self.child)
        self.log.close()


class DesktopWindow:
    def __init__(self, window_id, index=0, weights=None, workspace=None):
        from Xlib import X, XK, Xatom, display
        from Xlib.protocol import event
        self.X, self.Xatom, self.event = X, Xatom, event
        self.index, self.weights = index, weights or [1]
        self.display = display.Display()
        self.root = self.display.screen().root
        self.window = self.display.create_resource_object('window', window_id)
        self.window.set_wm_class('DesktopDashboards', 'DesktopDashboards')
        self.window.change_property(self.atom('_MOTIF_WM_HINTS'), self.atom('_MOTIF_WM_HINTS'),
                                    32, [2, 0, 0, 0, 0])
        self.window.change_property(self.atom('_NET_WM_WINDOW_TYPE'), Xatom.ATOM, 32,
                                    [self.atom('_NET_WM_WINDOW_TYPE_DESKTOP' if workspace is None else '_NET_WM_WINDOW_TYPE_NORMAL')])
        desktop = 0xffffffff if workspace is None else workspace
        self.window.change_property(self.atom('_NET_WM_DESKTOP'), Xatom.CARDINAL, 32, [desktop])
        states = ['_NET_WM_STATE_SKIP_TASKBAR', '_NET_WM_STATE_SKIP_PAGER', '_NET_WM_STATE_BELOW']
        if workspace is None:
            states.append('_NET_WM_STATE_STICKY')
        else:
            self.message('_NET_WM_STATE', [0, self.atom('_NET_WM_STATE_STICKY'), 0, 2, 0])
        for state in states:
            self.message('_NET_WM_STATE', [1, self.atom(state), 0, 2, 0])
        self.message('_NET_WM_DESKTOP', [desktop, 2, 0, 0, 0])
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
        box = pane_geometries(geometry(monitor, conky), self.weights)[self.index]
        if box != self.last_geometry:
            self.message('_NET_MOVERESIZE_WINDOW', [0x2f00, *box])
            self.window.configure(stack_mode=self.X.Above)
            self.display.flush()
            self.last_geometry = box
        return box

    def observed_state(self):
        box = self.window.get_geometry()
        position = self.root.translate_coords(self.window, 0, 0)
        workspace = self.window.get_full_property(self.atom('_NET_WM_DESKTOP'), self.Xatom.CARDINAL)
        title = self.window.get_wm_name()
        if isinstance(title, bytes):
            title = title.decode('utf-8', errors='replace')
        return {'actual_geometry': [position.x, position.y, box.width, box.height],
                'actual_workspace': int(workspace.value[0]) if workspace is not None else None,
                'title': title}

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


class BrowserPane:
    def __init__(self, spec, index, weights, profile, home, log):
        self.spec, self.index, self.weights = spec, index, weights
        self.profile, self.home, self.log = profile, home, log
        self.child, self.window, self.last_attempt = None, None, 0.0

    def start(self, records, prefer_home=False):
        self.last_attempt = time.monotonic()
        target = self.home if prefer_home else next(
            (item['url'] for item in records if item['id'] == self.spec['link'] and item['url']), self.home)
        self.waiting_for_link = target == self.home and not prefer_home and self.spec['link'] != 'home'
        base_cookies = self.profile / 'cookies.txt'
        cookies = base_cookies if self.index == 0 else self.profile / f'cookies-{self.spec["link"]}.txt'
        if not cookies.exists() and base_cookies.exists():
            shutil.copyfile(base_cookies, cookies)
        cookies.touch(exist_ok=True, mode=0o600)
        extra = []
        if self.spec.get('langfuse_refresh_ms') and target != self.home:
            script = self.profile / ('preferences-' + self.spec['link'] + '.js')
            script.write_text(langfuse_preferences(target, self.spec['langfuse_refresh_ms'],
                                                  self.spec.get('langfuse_all_history', False)))
            extra = ['-r', str(script)]
        from Xlib import display, Xatom
        focus_display = display.Display()
        active = focus_display.screen().root.get_full_property(
            focus_display.intern_atom('_NET_ACTIVE_WINDOW'), Xatom.WINDOW)
        previous = int(active.value[0]) if active is not None and len(active.value) else 0
        focus_display.close()
        cache = '-D' if self.spec.get('langfuse_refresh_ms') else '-d'
        self.child = spawn(['surf', '-w', '-f', '-T', '-x', '-g', '-n', '-B', cache, '-a', '@',
                            '-z', str(self.spec.get('zoom', 1)), '-c', str(cookies), *extra, target],
                           stdout=subprocess.PIPE, stderr=self.log, text=True)
        try:
            readable, _, _ = select.select([self.child.stdout], [], [], 20)
            if not readable:
                raise RuntimeError('Browser did not create a window')
            self.window = DesktopWindow(int(self.child.stdout.readline().strip(), 0), self.index, self.weights, self.spec.get('workspace'))
            self.window.placement()
            self.window.restore_focus(previous)
        except (ValueError, RuntimeError):
            stop_child(self.child)
            self.child, self.window = None, None
            raise

    def update(self, records):
        if self.child is None or self.child.poll() is not None:
            self.window = None
            if time.monotonic() - self.last_attempt >= 15:
                try:
                    self.start(records)
                except (OSError, ValueError, RuntimeError) as error:
                    print(f'{self.spec["link"]}: browser unavailable ({type(error).__name__})', flush=True)
            return
        self.window.placement()
        if self.waiting_for_link:
            target = next((item['url'] for item in records if item['id'] == self.spec['link']), None)
            if target:
                self.window.navigate(target)
                self.waiting_for_link = False
        if self.window.home_pressed():
            self.waiting_for_link = False
            self.window.navigate(self.home)

    def close(self):
        stop_child(self.child)


def overview_healthy(config):
    try:
        with build_opener(ProxyHandler({})).open(
                f'http://127.0.0.1:{config["overview"]["port"]}/api/status', timeout=2) as response:
            sample = json.load(response)
        age = time.time() - datetime.fromisoformat(sample['observed_at']).timestamp()
        return 0 <= age <= max(45, 3 * config['overview'].get('refresh_seconds', 15))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def navigation_targets(command, specs, records, home):
    """Resolve local link IDs to existing panes; never accept a supplied URL."""
    urls = {item['id']: item['url'] for item in records}
    if command == 'restore':
        return [(i, urls.get(spec['link']) or home) for i, spec in enumerate(specs)]
    if command == 'home':
        return [(0, home)]
    if command.startswith('open:'):
        selected = command[5:]
        if selected not in urls:
            return []
        index = next((i for i, spec in enumerate(specs) if spec['link'] == selected), len(specs) - 1)
        return [(index, urls[selected] or home)]
    return []


def write_hub(state, config, forwards, running=True, profile=None, overview_ready=False):
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
    if config.get('overview'):
        url = f'http://127.0.0.1:{config["overview"]["port"]}/' if overview_ready and running else None
        status = 'Available locally' if url else 'Connection unavailable'
        records.insert(2, {'id': 'overview', 'status': status, 'url': url})
        body = '<strong>Workloads &amp; OpenTelemetry</strong><span>' + status + '</span><small>Live workload readiness, storage, CPU history and telemetry delivery.</small>'
        links.insert(2, f'<a href="{url}">{body}</a>' if url else f'<div class="inactive">{body}</div>')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30"><title>Desktop dashboards</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;padding:24px;background:#111d29;color:#dce5ef;font:16px/1.5 system-ui,sans-serif}
h1{color:#66ddca;font-weight:500;margin:0}p{color:#a1b4c5}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,225px),1fr));gap:16px;margin:28px 0}
a,.inactive{display:flex;flex-direction:column;gap:9px;border:1px solid #304657;background:#182a38;border-radius:10px;padding:22px;color:inherit;text-decoration:none}
a:hover,a:focus{border-color:#66ddca}.inactive{opacity:.65}strong{font-weight:500;font-size:20px}span{color:#66ddca}small,footer{color:#a1b4c5;font-size:13px}
</style><h1>Desktop dashboards</h1><p>Open a dashboard below. Desktop shortcuts reuse the existing panes. Ctrl + Alt + Shift + Home returns here.</p><main>'''
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
    parser.add_argument('--open', metavar='LINK', help='Show a configured dashboard in an existing pane')
    parser.add_argument('--restore', action='store_true', help='Restore all configured dashboard destinations')
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
    config = validate_config(json.loads(args.config.read_text()))
    known = {item['id'] for item in config.get('links', [])}
    if config.get('overview'):
        known.add('overview')
    if args.open and args.open not in known:
        parser.error('Unknown configured dashboard')
    command = 'stop' if args.stop else 'open:' + args.open if args.open else 'restore' if args.restore else 'home'
    lock = (runtime / 'instance.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
            control.sendto(command.encode(), address)
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
    log = (state / 'dashboard.log').open('a', buffering=1)
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)
    if args.autostart:
        time.sleep(12)
    print(datetime.now(timezone.utc).isoformat(), 'session starting', flush=True)
    retire_orphaned_panes(profile)
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
    panes = []
    overview = None
    overview_log = None
    home = (profile / 'home.html').as_uri()
    try:
        for _ in range(12):
            for forward in forwards.values():
                forward.update()
            if all(forward.ready for forward in forwards.values()) or not running:
                break
            time.sleep(1)
        records = write_hub(state, config, forwards, profile=profile)
        if config.get('overview'):
            overview_log = (state / 'overview.log').open('a', buffering=1)
            overview = spawn(['/usr/bin/python3', str(Path(__file__).with_name('live_status.py')),
                              '--config', str(args.config)], stdout=overview_log, stderr=subprocess.STDOUT)
        specs = [dict(spec, workspace=config.get('workspace')) for spec in
                 (config.get('panes') or [{'link': config.get('start', 'home'), 'weight': 1}])]
        weights = [spec.get('weight', 1) for spec in specs]
        for index, spec in enumerate(specs):
            pane = BrowserPane(spec, index, weights, profile, home, log)
            panes.append(pane)
            try:
                pane.start(records, prefer_home=args.home and index == 0)
            except (OSError, ValueError, RuntimeError) as error:
                print(f'{spec["link"]}: browser unavailable ({type(error).__name__})', flush=True)
        def navigate(command):
            for index, target in navigation_targets(command, specs, records, home):
                if panes[index].window is not None:
                    panes[index].waiting_for_link = False
                    panes[index].window.navigate(target)

        pending_open = command if args.open else None
        ticks = 0
        while running:
            for pane in panes:
                pane.update(records)
            try:
                command = control.recv(128).decode('ascii', errors='replace')
                if command == 'stop':
                    break
                navigate(command)
            except BlockingIOError:
                pass
            if ticks % 5 == 0:
                if overview is not None and overview.poll() is not None:
                    overview = spawn(['/usr/bin/python3', str(Path(__file__).with_name('live_status.py')),
                                      '--config', str(args.config)], stdout=overview_log, stderr=subprocess.STDOUT)
                for forward in forwards.values():
                    forward.update()
                records = write_hub(state, config, forwards, profile=profile,
                                    overview_ready=overview is not None and overview.poll() is None and overview_healthy(config))
                layout = [{'link': pane.spec['link'], 'geometry': pane.window.last_geometry if pane.window else None,
                           'workspace': config.get('workspace'), 'pid': pane.child.pid if pane.child else None,
                           **(pane.window.observed_state() if pane.window else {})}
                          for pane in panes]
                (state / 'panes.json').write_text(json.dumps(layout, indent=2) + '\n')
            if pending_open and any(item['id'] == args.open and item['url'] for item in records):
                navigate(pending_open)
                pending_open = None
            ticks += 1
            time.sleep(1)
    finally:
        for pane in panes:
            pane.close()
        stop_child(overview)
        if overview_log is not None:
            overview_log.close()
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

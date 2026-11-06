#!/usr/bin/env python3
"""Read-only loopback status page for an explicitly selected local cluster."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import ProxyHandler, Request, build_opener


def kube_json(config, kind):
    result = subprocess.run(
        ['kubectl', '--context', config['cluster']['context'], '--request-timeout=4s',
         '-n', config['overview']['namespace'], 'get', kind, '-o', 'json'],
        capture_output=True, text=True, timeout=6, check=False)
    if result.returncode:
        raise RuntimeError('Kubernetes query unavailable')
    return json.loads(result.stdout)


def identities_match(config):
    from dashboard import cluster_matches
    return cluster_matches(config['cluster'], config['overview']['namespace'])


def pod_rows(document):
    rows = []
    for pod in document.get('items', []):
        status = pod.get('status', {})
        containers = status.get('containerStatuses', [])
        phase = status.get('phase', 'Unknown')
        desired = len(pod.get('spec', {}).get('containers', []))
        ready = sum(bool(item.get('ready')) for item in containers)
        restarting = sum(item.get('restartCount', 0) for item in containers)
        reasons = [state.get('waiting', {}).get('reason') for item in containers if (state := item.get('state', {})).get('waiting')]
        rows.append({'name': pod['metadata']['name'], 'phase': phase,
                     'ready': ready, 'desired': desired, 'restarts': restarting,
                     'healthy': phase == 'Succeeded' or (phase == 'Running' and desired > 0 and ready == desired),
                     'reason': next((reason for reason in reasons if reason), phase),
                     'created_at': pod['metadata'].get('creationTimestamp')})
    return sorted(rows, key=lambda row: (row['phase'] == 'Succeeded', row['name']))


def cpu_history(path, now):
    try:
        records = json.loads(path.read_text())
        valid = [row for row in records if isinstance(row.get('t'), (int, float))
                 and isinstance(row.get('cpu'), (int, float)) and 0 <= row['cpu'] <= 100
                 and now - 86400 <= row['t'] <= now]
        stride = max(1, len(valid) // 120)
        selected = valid[::stride]
        if valid and selected[-1]['t'] != valid[-1]['t']:
            selected.append(valid[-1])
        samples = [{'t': row['t'], 'cpu': round(row['cpu'], 1)} for row in selected][-121:]
        return {'samples': samples, 'stale': not valid or now - valid[-1]['t'] > 180}
    except (OSError, ValueError, TypeError, AttributeError):
        return {'samples': [], 'stale': True}


def storage_rows(entries):
    rows = []
    for entry in entries:
        try:
            stat = os.statvfs(entry['path'])
            used = (stat.f_blocks - stat.f_bfree) * stat.f_frsize
            available = stat.f_bavail * stat.f_frsize
            total = used + available
            rows.append({'name': entry['name'], 'available_bytes': available, 'total_bytes': total,
                         'used_percent': round(100 * used / total, 1) if total else None})
        except OSError:
            rows.append({'name': entry['name'], 'available_bytes': None, 'total_bytes': None, 'used_percent': None})
    return rows


def verification_summary(config):
    """Only numeric summaries leave the explicitly selected diagnostic project."""
    path = config['overview'].get('verification_credentials')
    forward = next((item for item in config.get('forwards', []) if item['id'] == 'langfuse'), None)
    if not path or forward is None:
        return None
    try:
        credential = json.loads(Path(path).read_text())
        token = base64.b64encode((credential['public_key'] + ':' + credential['secret_key']).encode()).decode()
        request = Request(f'http://127.0.0.1:{forward["local_port"]}/api/public/v2/observations?limit=100',
                          headers={'Authorization': 'Basic ' + token})
        with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
            observations = json.load(response).get('data', [])
        return {'available': True, 'observations': len(observations),
                'traces': len({item['traceId'] for item in observations if item.get('traceId')}),
                'synthetic': True, 'url': f'http://127.0.0.1:{forward["local_port"]}/project/{credential["project_id"]}'}
    except (OSError, ValueError, KeyError, TypeError):
        return {'available': False, 'synthetic': True}


def collect_snapshot(config, query=kube_json, identity_check=identities_match):
    now = time.time()
    snapshot = {'observed_at': datetime.fromtimestamp(now, timezone.utc).isoformat(timespec='seconds'),
                'host': config['overview'].get('title', 'Local workload status'),
                'namespace': config['overview']['namespace'], 'pods': [], 'nodes': [], 'volumes': [],
                'services': [], 'errors': [], 'cluster_verified': False,
                'available': {'pods': False, 'nodes': False, 'pvc': False}}
    try:
        if not identity_check(config):
            raise RuntimeError('Cluster identity mismatch or unavailable')
        snapshot['cluster_verified'] = True
        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs = {kind: pool.submit(query, config, kind) for kind in ('pods', 'nodes', 'pvc')}
            for kind, future in jobs.items():
                try:
                    data = future.result()
                    snapshot['available'][kind] = True
                    if kind == 'pods':
                        snapshot['pods'] = pod_rows(data)
                    elif kind == 'nodes':
                        snapshot['nodes'] = [
                            {'name': item['metadata']['name'],
                             'ready': any(c['type'] == 'Ready' and c['status'] == 'True' for c in item.get('status', {}).get('conditions', [])),
                             'version': item.get('status', {}).get('nodeInfo', {}).get('kubeletVersion', 'Unknown')}
                            for item in data.get('items', [])]
                    else:
                        snapshot['volumes'] = [{'name': item['metadata']['name'],
                                               'phase': item.get('status', {}).get('phase', 'Unknown'),
                                               'capacity': item.get('status', {}).get('capacity', {}).get('storage', 'Unknown')}
                                              for item in data.get('items', [])]
                except (OSError, ValueError, subprocess.SubprocessError, RuntimeError):
                    snapshot['errors'].append(kind + ' query unavailable')
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError):
        snapshot['errors'].append('Cluster identity unavailable or changed; workload data withheld')
    for spec in config.get('forwards', []):
        # A listener must also belong to the active desktop supervisor's sample.
        state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'desktop-dashboard/status.json'
        try:
            report = json.loads(state.read_text())
            stamp = datetime.fromisoformat(report['observed_at']).timestamp()
            owned = report.get('supervisor_running') and now - stamp < 45 and any(
                item['id'] == spec['id'] and item['status'] == 'Available locally' for item in report.get('links', []))
        except (OSError, ValueError, KeyError, TypeError):
            owned = False
        healthy = False
        if owned:
            try:
                endpoint = spec.get('health_path', '/')
                with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{spec["local_port"]}{endpoint}', timeout=2) as response:
                    healthy = response.status == 200
            except OSError:
                pass
        snapshot['services'].append({'name': spec['id'], 'healthy': healthy, 'owned': bool(owned)})
    snapshot['storage'] = storage_rows(config['overview'].get('storage', []))
    memory = {}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            parts = line.split()
            if parts[0] in ('MemTotal:', 'MemAvailable:'):
                memory[parts[0].rstrip(':')] = int(parts[1]) * 1024
    except (OSError, ValueError):
        pass
    snapshot['memory'] = memory
    snapshot['history'] = cpu_history(Path.home() / '.cache/conky/history.json', now)
    if any(service['name'] == 'langfuse' and service['owned'] and service['healthy'] for service in snapshot['services']):
        snapshot['verification'] = verification_summary(config)
    else:
        snapshot['verification'] = {'available': False, 'synthetic': True} if config['overview'].get('verification_credentials') else None
    active = [row for row in snapshot['pods'] if row['phase'] != 'Succeeded']
    snapshot['summary'] = {'running': sum(row['healthy'] for row in active), 'total': len(active),
                           'restarts': sum(row['restarts'] for row in active),
                           'volumes_bound': sum(row['phase'] == 'Bound' for row in snapshot['volumes'])}
    return snapshot


PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Live workload status</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;padding:18px 22px;background:#111d29;color:#dce5ef;font:14px/1.4 system-ui,sans-serif}
header{display:flex;align-items:center;justify-content:space-between;gap:12px}h1{margin:0;color:#66ddca;font-size:23px;font-weight:500}h2{font-size:12px;letter-spacing:.07em;color:#66ddca;font-weight:500;margin:18px 0 8px}.muted{color:#a1b4c5;font-size:12px}.good{color:#66ddca}.warn{color:#ffc078}
.summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}.metric{background:#182a38;border-radius:6px;padding:12px}.value{font-size:25px;display:block}.services{display:flex;gap:20px;flex-wrap:wrap;padding:10px 0;border-bottom:1px solid #304657}table{width:100%;border-collapse:collapse;font-size:12px}td,th{padding:6px 8px;text-align:left;border-bottom:1px solid #233b4a}th{font-weight:500;color:#a1b4c5}td:first-child{overflow-wrap:anywhere}th:nth-child(3),td:nth-child(3),th:nth-child(4),td:nth-child(4){text-align:right}.lower{display:grid;grid-template-columns:1fr 1fr;gap:24px}.volume{display:flex;justify-content:space-between;gap:12px;margin:5px 0}.track{height:5px;background:#233b4a;margin:8px 0}.fill{height:100%;background:#66ddca}svg{width:100%;height:74px;display:block}footer{font-size:11px;color:#a1b4c5;margin-top:14px}.error{color:#ffc078;padding:8px 0}a{color:#84b8ff;text-decoration:none}@media(max-width:650px){body{padding:12px}.summary{grid-template-columns:repeat(2,minmax(0,1fr))}.lower{grid-template-columns:1fr}.value{font-size:21px}}
</style><header><div><h1 id="host">Local workload status</h1><div class="muted" id="context">Loading live observations…</div></div><span class="good" id="fresh">LIVE</span></header>
<div class="services" id="services"></div><div class="muted" id="verification" style="margin-top:10px" hidden></div><div class="error" id="errors" hidden></div><div class="summary">
<div class="metric"><span class="muted">Workloads ready</span><span class="value" id="ready">—</span></div>
<div class="metric"><span class="muted">Cluster nodes ready</span><span class="value" id="nodes">—</span></div>
<div class="metric"><span class="muted">Persistent volumes bound</span><span class="value" id="volumes">—</span></div>
<div class="metric"><span class="muted">Host memory available</span><span class="value" id="memory">—</span></div></div>
<h2>APPLICATIONS &amp; DATA SERVICES</h2><table><thead><tr><th>Workload</th><th>State</th><th>Ready</th><th>Restarts</th></tr></thead><tbody id="pods"></tbody></table>
<div class="lower"><section><h2>STORAGE CAPACITY</h2><div id="storage"></div><div class="muted" id="claims"></div></section><section><h2>CPU HISTORY · LAST 24 HOURS</h2><svg id="history" role="img" aria-label="Observed host CPU history" viewBox="0 0 400 74"></svg><div class="muted" id="history-note"></div></section></div>
<footer id="observed"></footer><script>
const node=id=>document.getElementById(id),gib=n=>Number.isFinite(n)?(n/1073741824).toFixed(1)+' GiB':'Unavailable';
let last=null,connected=false;
function row(values){const tr=document.createElement('tr');for(const value of values){const td=document.createElement('td');td.textContent=value;tr.appendChild(td)}return tr}
function render(s){last=s;connected=true;node('host').textContent=s.host;node('context').textContent=s.namespace+' · '+(s.nodes.map(n=>n.version).join(', ')||'Cluster unavailable');
node('ready').textContent=s.available.pods?s.summary.running+' / '+s.summary.total:'Unknown';node('nodes').textContent=s.available.nodes?s.nodes.filter(n=>n.ready).length+' / '+s.nodes.length:'Unknown';node('volumes').textContent=s.available.pvc?s.summary.volumes_bound+' / '+s.volumes.length:'Unknown';node('memory').textContent=gib(s.memory.MemAvailable);
node('pods').replaceChildren(...s.pods.filter(p=>p.phase!=='Succeeded').map(p=>{const tr=row([p.name,p.healthy?'Running':p.reason,p.ready+' / '+p.desired,p.restarts]);tr.children[1].className=p.healthy?'good':'warn';return tr}));
node('services').replaceChildren(...s.services.map(v=>{const e=document.createElement('span');e.className=v.healthy?'good':'warn';e.textContent=v.name+' · '+(v.healthy?'HTTP healthy':'Unavailable');return e}));
const verification=node('verification');verification.hidden=!s.verification;if(s.verification){verification.textContent=s.verification.available?'Langfuse pipeline verified · '+s.verification.traces+' traces / '+s.verification.observations+' observations · SYNTHETIC TEST DATA':'Langfuse diagnostic project temporarily unavailable'}
node('storage').replaceChildren(...s.storage.map(v=>{const e=document.createElement('div'),line=document.createElement('div');line.className='volume';const label=document.createElement('span'),value=document.createElement('span');label.textContent=v.name;value.textContent=gib(v.available_bytes)+' free';line.append(label,value);const track=document.createElement('div'),fill=document.createElement('div');track.className='track';fill.className='fill';fill.style.width=(v.used_percent||0)+'%';if(v.used_percent>=90)fill.style.background='#ffc078';track.append(fill);e.append(line,track);return e}));
node('claims').textContent=s.volumes.map(v=>v.capacity+' '+v.phase).join(' · ');
const samples=s.history.samples,svg=node('history');svg.replaceChildren();if(samples.length>1){const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');line.setAttribute('points',samples.map((v,i)=>(i*400/(samples.length-1)).toFixed(1)+','+(70-v.cpu*.65).toFixed(1)).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','#66ddca');line.setAttribute('stroke-width','1.8');svg.append(line)}
node('history-note').textContent=samples.length?(s.history.stale?'History stale · ':'')+new Date(samples[0].t*1000).toLocaleTimeString()+' – '+new Date(samples.at(-1).t*1000).toLocaleTimeString()+' · '+samples.at(-1).cpu+'% latest':'No history observations';
node('observed').textContent='Observed '+new Date(s.observed_at).toLocaleString()+' · Updates every 15 seconds · Current local measurements';node('errors').hidden=!s.errors.length;node('errors').textContent=s.errors.join(' · ');age()}
function age(){const seconds=last?(Date.now()-Date.parse(last.observed_at))/1000:Infinity;node('fresh').textContent=!connected?'DISCONNECTED':seconds<45?'LIVE':'STALE';node('fresh').className=connected&&seconds<45?'good':'warn'}
async function refresh(){try{const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw Error();render(await r.json())}catch{connected=false;node('errors').hidden=false;node('errors').textContent='Local status connection unavailable';age()}}
refresh();setInterval(refresh,15000);setInterval(age,5000);
</script></html>'''


class StatusServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}:
            self.send_error(403)
            return
        if self.path == '/api/status':
            payload = json.dumps(self.server.snapshot).encode()
            mime = 'application/json'
        elif self.path in ('/', '/embed'):
            payload, mime = PAGE.encode(), 'text/html; charset=utf-8'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'self' http://127.0.0.1:17575")
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    server = StatusServer(('127.0.0.1', config['overview']['port']), Handler)
    server.snapshot = collect_snapshot(config)
    stop = threading.Event()

    def collect():
        while not stop.wait(config['overview'].get('refresh_seconds', 15)):
            server.snapshot = collect_snapshot(config)

    def shutdown(_signum, _frame):
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    threading.Thread(target=collect, daemon=True).start()
    server.serve_forever(poll_interval=.5)
    server.server_close()


if __name__ == '__main__':
    main()

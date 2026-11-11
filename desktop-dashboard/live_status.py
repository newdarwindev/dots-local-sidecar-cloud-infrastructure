#!/usr/bin/env python3
"""Read-only loopback status page for an explicitly selected local cluster."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
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


def stored_health_activity(config):
    """Read only the selected local-health project and expose bounded metadata."""
    path = config['overview'].get('live_health_credentials')
    forward = next((x for x in config.get('forwards', []) if x['id'] == 'langfuse'), None)
    if not path or forward is None:
        return {'available': False, 'rows': []}
    try:
        credential = json.loads(Path(path).read_text())
        token = base64.b64encode((credential['public_key'] + ':' + credential['secret_key']).encode()).decode()
        request = Request(f'http://127.0.0.1:{forward["local_port"]}/api/public/v2/observations?limit=100',
                          headers={'Authorization': 'Basic ' + token})
        with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
            data = json.load(response).get('data', [])
        rows = project_health_activity(data)
        latest = datetime.fromisoformat(rows[0]['startTime'].replace('Z', '+00:00')).timestamp() if rows else None
        return {'available': True, 'sample_count': len(rows), 'rows': rows[:6],
                'age_seconds': max(0, time.time() - latest) if latest is not None else None,
                'url': f'http://127.0.0.1:{forward["local_port"]}/project/{credential["project_id"]}/traces'}
    except (OSError, ValueError, KeyError, TypeError):
        return {'available': False, 'rows': []}


def project_health_activity(data):
    rows = []
    allowed = {'Desktop dashboard health', 'HTTP health: homarr', 'HTTP health: langfuse'}
    for item in data:
        if item.get('name') not in allowed or item.get('environment') != 'local-desktop':
            continue
        try:
            timestamp = datetime.fromisoformat(item['startTime'].replace('Z', '+00:00'))
            if timestamp.tzinfo is None:
                continue
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        latency = item.get('latency')
        rows.append({'name': item['name'], 'startTime': timestamp.isoformat(),
                     'latency': latency if type(latency) in (int, float) and math.isfinite(latency) and latency >= 0 else None,
                     'level': item.get('level') if item.get('level') in ('DEFAULT', 'DEBUG', 'WARNING', 'ERROR') else 'Unknown'})
    return sorted(rows, key=lambda row: row.get('startTime') or '', reverse=True)


def collect_snapshot(config, query=kube_json, identity_check=identities_match):
    now = time.time()
    start_ns = time.time_ns()
    snapshot = {'observed_at': datetime.fromtimestamp(now, timezone.utc).isoformat(timespec='seconds'),
                'host': config['overview'].get('title', 'Local workload status'),
                'namespace': config['overview']['namespace'],
                'refresh_seconds': config['overview'].get('refresh_seconds', 15), 'pods': [], 'nodes': [], 'volumes': [],
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
        healthy, started_ns, ended_ns, http_status = False, None, None, None
        if owned:
            started_ns = time.time_ns()
            try:
                endpoint = spec.get('health_path', '/')
                scheme = spec.get('scheme', 'http')
                host = 'localhost' if scheme == 'https' else '127.0.0.1'
                with build_opener(ProxyHandler({})).open(
                        f'{scheme}://{host}:{spec["local_port"]}{endpoint}', timeout=2) as response:
                    healthy = response.status == 200
                    http_status = response.status
            except HTTPError as error:
                http_status = error.code
            except OSError:
                pass
            ended_ns = time.time_ns()
        snapshot['services'].append({'name': spec['id'], 'healthy': healthy, 'owned': bool(owned),
                                     'started_ns': started_ns, 'ended_ns': ended_ns, 'http_status': http_status})
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
    snapshot['healthy'] = (snapshot['cluster_verified'] and not snapshot['errors']
                           and all(snapshot['available'].values())
                           and snapshot['summary']['running'] == snapshot['summary']['total']
                           and bool(snapshot['nodes']) and all(row['ready'] for row in snapshot['nodes'])
                           and all(row['phase'] == 'Bound' for row in snapshot['volumes'])
                           and all(row['healthy'] and row['owned'] for row in snapshot['services']))
    snapshot['catalog'] = [{'name': x['name'], 'status': x.get('status', 'Configured'),
                            'description': x.get('description', '')}
                           for x in config.get('links', []) if not x.get('url') and not x.get('forward')]
    snapshot['timing'] = {'start_ns': start_ns, 'end_ns': time.time_ns()}
    return snapshot


PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Desktop 4 · Operations overview</title><style>
:root{color-scheme:dark;--bg:#101923;--panel:#172431;--line:#2a4051;--muted:#a8bacb;--text:#eef4fa;--accent:#76e3ca}*{box-sizing:border-box}body{margin:0;padding:24px;background:var(--bg);color:var(--text);font:15px/1.4 system-ui,sans-serif}header{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:18px}.eyebrow{font-size:11px;letter-spacing:.16em;color:var(--accent);margin-bottom:5px}h1{font-size:28px;line-height:1.2;margin:0 0 6px;font-weight:600}h2{font-size:15px;margin:0;font-weight:600}p{margin:8px 0}.muted{color:var(--muted);font-size:12px}.good{color:var(--accent)}.warn,.error{color:#ffc078}#fresh{padding:7px 13px;border:1px solid currentColor;border-radius:30px;font-size:12px;font-weight:700;letter-spacing:.08em}.services{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}.services span{padding:6px 12px;background:var(--panel);border:1px solid var(--line);border-radius:6px}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.metric,.panel{border:1px solid var(--line);border-radius:12px;background:var(--panel)}.metric{padding:15px 18px}.value{display:block;font-size:30px;font-weight:600;margin-top:3px;font-variant-numeric:tabular-nums}.grid{display:grid;grid-template-columns:1.1fr 1fr;gap:16px}.panel{padding:18px;min-width:0}.panel-head{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:12px}a{color:#9bc8ff;text-decoration:none}a:hover{text-decoration:underline}a:focus-visible{outline:2px solid var(--accent);outline-offset:4px}.table-wrap{max-height:350px;overflow:auto}table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:12px}td,th{padding:9px 6px;text-align:left;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:500}td:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}th:first-child{width:49%}td:nth-child(n+3),th:nth-child(n+3){text-align:right}th:nth-child(2){width:20%}#activity th:first-child{width:48%}#verification{padding:12px;background:#101e2a;border-radius:7px;line-height:1.6;margin-bottom:13px;font-size:12px}.volume{display:flex;justify-content:space-between;gap:10px;margin-top:13px}.track{height:6px;background:#0d1822;border-radius:8px;margin:8px 0 13px;overflow:hidden}.fill{height:100%;background:var(--accent)}svg{width:100%;height:95px;display:block;margin-top:12px}#claims{line-height:1.7}#catalog{display:flex;flex-wrap:wrap;gap:16px;margin-top:18px;padding-top:14px;border-top:1px solid var(--line)}#catalog>div{flex:1;min-width:180px}.catalog-title{font-weight:500;font-size:13px}footer{display:flex;justify-content:space-between;gap:15px;color:var(--muted);font-size:11px;margin-top:16px}#errors{margin:0 0 12px;padding:10px 14px;border:1px solid #795f3b;border-radius:7px}#activity-note{margin-top:10px}@media(max-width:850px){body{padding:16px}.grid{grid-template-columns:1fr}.summary{grid-template-columns:repeat(2,1fr)}h1{font-size:24px}.table-wrap{max-height:none}}@media(max-height:950px) and (min-width:851px){body{padding:16px}.panel{padding:14px}td,th{padding:7px 5px}.table-wrap{max-height:285px}.value{font-size:26px}.metric{padding:10px 14px}svg{height:65px}}
@media(min-width:851px){body{height:100vh;display:flex;flex-direction:column;gap:12px;padding:20px}header,.services,.summary{margin:0;flex-shrink:0}.grid{flex:1;min-height:0;grid-template-rows:2fr 1fr}.panel{display:flex;flex-direction:column;min-height:0;overflow:auto}.panel-head{flex-shrink:0}.table-wrap{min-height:0;max-height:none;flex:1}#catalog{margin:0;padding-top:10px;flex-shrink:0}footer{margin:0;flex-shrink:0}.value{font-size:28px}.metric{padding:12px 16px}td,th{padding:7px 6px}}
</style><header><div><div class="eyebrow">DESKTOP 4 / LIVE OPERATIONS</div><h1 id="host">Operations overview</h1><div id="context" class="muted">Connecting to local services…</div></div><span id="fresh" class="warn">CONNECTING</span></header>
<div id="services" class="services"></div><div id="errors" class="error" hidden></div>
<div class="summary"><div class="metric"><span class="muted">Workloads ready</span><span class="value" id="ready">—</span></div><div class="metric"><span class="muted">Nodes ready</span><span class="value" id="nodes">—</span></div><div class="metric"><span class="muted">Volumes bound</span><span class="value" id="volumes">—</span></div><div class="metric"><span class="muted">Memory available</span><span class="value" id="memory">—</span></div></div>
<main class="grid"><section class="panel"><div class="panel-head"><h2>Applications &amp; data services</h2><a href="http://127.0.0.1:17575/boards/kali-6-status" class="muted">Open Homarr ↗</a></div><div class="table-wrap"><table><thead><tr><th>Workload</th><th>State</th><th>Ready</th><th>Restarts</th></tr></thead><tbody id="pods"></tbody></table></div><p class="muted">Restart counts are cumulative. Current readiness is shown separately.</p></section>
<section class="panel"><div class="panel-head"><h2>Langfuse &amp; OpenTelemetry</h2><a id="trace-link" hidden class="muted">Inspect traces ↗</a></div><div id="verification" class="muted" hidden></div><div class="table-wrap"><table id="activity"><thead><tr><th>Recent stored observation</th><th>Time</th><th>Duration</th></tr></thead><tbody id="activity-rows"></tbody></table></div><p id="activity-note" class="muted">Waiting for stored observation readback…</p><p class="muted">Source: live local health checks. Delivery counters reset when the dashboard restarts.</p></section>
<section class="panel"><h2>Storage capacity</h2><div id="storage"></div><div id="claims" class="muted"></div></section>
<section class="panel"><h2>CPU history · last 24 hours</h2><svg id="history" role="img" aria-label="Observed CPU history" viewBox="0 0 400 74"></svg><div id="history-note" class="muted"></div></section></main>
<div id="catalog"></div><footer><span id="observed"></span><span>Local dashboard · private loopback access</span></footer><script>
const node=id=>document.getElementById(id),gib=n=>Number.isFinite(n)?(n/1073741824).toFixed(1)+' GiB':'Unavailable';
let last=null,connected=false;
function row(values){const tr=document.createElement('tr');for(const value of values){const td=document.createElement('td');td.textContent=value;tr.appendChild(td)}return tr}
function render(s){last=s;connected=true;node('host').textContent=s.host;node('context').textContent=s.namespace+' · '+(s.nodes.map(n=>n.version).join(', ')||'Cluster unavailable');
node('ready').textContent=s.available.pods?s.summary.running+' / '+s.summary.total:'Unknown';node('nodes').textContent=s.available.nodes?s.nodes.filter(n=>n.ready).length+' / '+s.nodes.length:'Unknown';node('volumes').textContent=s.available.pvc?s.summary.volumes_bound+' / '+s.volumes.length:'Unknown';node('memory').textContent=gib(s.memory.MemAvailable);
const activity=s.stored_activity||{available:false,rows:[]};node('activity-rows').replaceChildren(...activity.rows.map(x=>row([x.name,new Date(x.startTime).toLocaleTimeString(),Number.isFinite(x.latency)?(x.latency*1000).toFixed(0)+' ms':'—'])));node('activity-note').textContent=activity.available?'Persisted readback · '+activity.sample_count+' health observations in the latest API sample (up to 100). '+(Number.isFinite(activity.age_seconds)?'Newest stored '+Math.round(activity.age_seconds)+' seconds ago.':'No stored local-health observations.'):'Stored observations unavailable — delivery acceptance alone does not prove storage.';node('activity-note').className=activity.available&&Number.isFinite(activity.age_seconds)&&activity.age_seconds<90?'muted':'warn';node('trace-link').hidden=!activity.url;if(activity.url)node('trace-link').href=activity.url;node('catalog').replaceChildren(...(s.catalog||[]).map(x=>{const e=document.createElement('div'),t=document.createElement('div'),d=document.createElement('div');t.className='catalog-title';t.textContent=x.name+' · '+x.status;d.className='muted';d.textContent=x.description;e.append(t,d);return e}));
node('pods').replaceChildren(...s.pods.filter(p=>p.phase!=='Succeeded').map(p=>{const tr=row([p.name,p.healthy?'Running':p.reason,p.ready+' / '+p.desired,p.restarts]);tr.children[0].title=p.name;tr.children[0].textContent=p.name.replace(/-[a-f0-9]{8,10}-[a-z0-9]{5}$/, '');tr.children[1].className=p.healthy?'good':'warn';return tr}));
node('services').replaceChildren(...s.services.map(v=>{const e=document.createElement('span');e.className=v.healthy?'good':'warn';e.textContent=v.name+' · '+(v.healthy?'HTTP healthy':'Unavailable');return e}));
const verification=node('verification');verification.hidden=!s.verification;if(s.verification){verification.textContent=s.verification.available?'Langfuse pipeline verified · '+s.verification.traces+' traces / '+s.verification.observations+' observations · SYNTHETIC TEST DATA':'Langfuse diagnostic project temporarily unavailable'}
if(s.live_feed){verification.hidden=false;verification.textContent='OpenTelemetry → Langfuse · '+s.live_feed.accepted_spans+' spans accepted · '+s.live_feed.failed_batches+' failed / '+s.live_feed.skipped_batches+' skipped batches · '+s.live_feed.status+(s.live_feed.last_success_at?' · Last accepted '+new Date(s.live_feed.last_success_at).toLocaleTimeString():'');verification.className=s.live_feed.failed_batches||s.live_feed.skipped_batches?'warn':'muted'}
node('storage').replaceChildren(...s.storage.map(v=>{const e=document.createElement('div'),line=document.createElement('div');line.className='volume';const label=document.createElement('span'),value=document.createElement('span');label.textContent=v.name;value.textContent=gib(v.available_bytes)+' free';line.append(label,value);const track=document.createElement('div'),fill=document.createElement('div');track.className='track';fill.className='fill';fill.style.width=(v.used_percent||0)+'%';if(v.used_percent>=90)fill.style.background='#ffc078';track.append(fill);e.append(line,track);return e}));
node('claims').textContent=s.volumes.map(v=>v.capacity+' '+v.phase).join(' · ');
const samples=s.history.samples,svg=node('history');svg.replaceChildren();if(samples.length>1){const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');line.setAttribute('points',samples.map((v,i)=>(i*400/(samples.length-1)).toFixed(1)+','+(70-v.cpu*.65).toFixed(1)).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','#66ddca');line.setAttribute('stroke-width','1.8');svg.append(line)}
node('history-note').textContent=samples.length?(s.history.stale?'History stale · ':'')+new Date(samples[0].t*1000).toLocaleTimeString()+' – '+new Date(samples.at(-1).t*1000).toLocaleTimeString()+' · '+samples.at(-1).cpu+'% latest':'No history observations';
node('observed').textContent='Observed '+new Date(s.observed_at).toLocaleString()+' · Updates every '+(s.refresh_seconds||15)+' seconds · Current local measurements';node('errors').hidden=!s.errors.length;node('errors').textContent=s.errors.join(' · ');age()}
function age(){const seconds=last?(Date.now()-Date.parse(last.observed_at))/1000:Infinity;const fresh=connected&&seconds<Math.max(45,3*(last?.refresh_seconds||15));const degraded=last&&(!last.healthy||(last.stored_activity&&(!last.stored_activity.available||last.stored_activity.age_seconds===null||last.stored_activity.age_seconds>90))||(last.live_feed&&last.live_feed.status!=='exporting live local health'));node('fresh').textContent=!connected?'DISCONNECTED':!fresh?'STALE':degraded?'DEGRADED':'LIVE';node('fresh').className=fresh&&!degraded?'good':'warn'}
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
    exporter = None
    if config['overview'].get('live_health_credentials'):
        from health_otel import HealthExporter
        forward = next(item for item in config['forwards'] if item['id'] == 'langfuse')
        exporter = HealthExporter(config['overview']['live_health_credentials'], forward['local_port'])

    def sample():
        snapshot = collect_snapshot(config)
        if exporter is not None:
            snapshot['live_feed'] = exporter.publish(snapshot)
            if any(x['name'] == 'langfuse' and x['owned'] and x['healthy'] for x in snapshot['services']):
                snapshot['stored_activity'] = stored_health_activity(config)
            else:
                snapshot['stored_activity'] = {'available': False, 'rows': []}
        return snapshot

    server.snapshot = sample()
    stop = threading.Event()

    def collect():
        while not stop.wait(config['overview'].get('refresh_seconds', 15)):
            server.snapshot = sample()

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

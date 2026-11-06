#!/usr/bin/env python3
"""Explicitly gated bootstrap. Never collects or generates service credentials."""
import argparse, datetime, hashlib, json, os, pathlib, platform, subprocess, sys, tarfile, urllib.request
ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = pathlib.Path.home() / 'Library/Application Support/dots-primary-infrastructure'
LOCK = json.loads((ROOT / 'artifacts.lock.json').read_text())
LIMA = STATE / 'runtime/bin/limactl'
LIMA_HOME = pathlib.Path.home() / '.local/share/dots-primary-lima'
ENV = dict(os.environ, LIMA_HOME=str(LIMA_HOME))

def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, env=ENV, **kwargs)

def revision():
    digest = hashlib.sha256()
    for p in sorted(ROOT.rglob('*')):
        rel = p.relative_to(ROOT)
        if p.is_file() and not any(x in {'runtime','artifacts','rendered','__pycache__'} for x in rel.parts):
            digest.update(str(rel).encode() + b'\0' + p.read_bytes())
    return digest.hexdigest()

def approve(scope):
    path = pathlib.Path(os.environ.get('DOTS_APPROVAL_FILE', '/nonexistent'))
    if not path.is_file() or path.stat().st_mode & 0o077:
        sys.exit('Stop: supply an owner-reviewed mode-0600 approval file outside Git.')
    data = json.loads(path.read_text())
    expiry = datetime.datetime.fromisoformat(data['expires'].replace('Z','+00:00'))
    if data.get('revision') != revision() or scope not in data.get('scopes',[]) or expiry <= datetime.datetime.now(datetime.timezone.utc):
        sys.exit('Stop: exact current revision/scope approval is missing or expired.')
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        sys.exit('This bootstrap targets the approved ARM64 Mac only.')
    return data

def artifact(name):
    item = LOCK['artifacts'][name]
    dest = ROOT / 'artifacts' / item['filename']; dest.parent.mkdir(exist_ok=True)
    if not dest.exists():
        with urllib.request.urlopen(item['url'], timeout=60) as response:
            payload = response.read()
        if hashlib.sha256(payload).hexdigest() != item['sha256']:
            sys.exit('Artifact checksum mismatch: ' + name)
        dest.write_bytes(payload)
    if hashlib.sha256(dest.read_bytes()).hexdigest() != item['sha256']:
        sys.exit('Cached artifact checksum mismatch: ' + name)
    return dest

def unpack(archive, dest):
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        members = []
        for member in tar.getmembers():
            # Lima includes one documentation-only relative symlink. Omit it.
            if member.issym() and member.name == './share/doc/lima/templates' and member.linkname == '../../lima/templates':
                continue
            if member.name.startswith('/') or '..' in pathlib.Path(member.name).parts or not (member.isfile() or member.isdir()):
                sys.exit('Unexpected unsafe archive member; inspect before installation.')
            members.append(member)
        tar.extractall(dest, members=members)

def guest(*args, **kwargs):
    return run([LIMA,'shell','primary','--',*args], **kwargs)

def put(source, destination):
    guest('sudo','tee',destination,input=pathlib.Path(source).read_bytes(),stdout=subprocess.DEVNULL)

def kubectl(*args, **kwargs):
    return guest('sudo','/usr/local/bin/k3s','kubectl',*args,**kwargs)

def apply(path):
    kubectl('apply','--server-side','-f','-',input=path.read_bytes())

def render(name, namespace):
    helm = STATE / 'tools/darwin-arm64/helm'
    return run([helm,'template',name,artifact(name),'--namespace',namespace,'--kube-version',LOCK['kubernetesVersion'],'--include-crds','--skip-tests','-f',ROOT/'values'/f'{name}.yaml'],capture_output=True).stdout

def no_encode():
    result = subprocess.run(['pgrep','-x','ffmpeg'],stdout=subprocess.DEVNULL)
    if result.returncode != 1:
        sys.exit('VM start deferred: ffmpeg exists or process visibility is uncertain. Recheck after encoding completes.')

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['revision','install-runtime','start','bootstrap','argocd','openbao','eso','gitops','enable-sync','rollback','status']); args=parser.parse_args()
    if args.action == 'revision': print(revision()); return
    if args.action == 'status':
        if not LIMA.exists(): print('Runtime not installed'); return
        run([LIMA,'list','primary']); return
    approval=approve(args.action)
    if args.action == 'install-runtime':
        if LIMA.exists(): sys.exit('Runtime already exists; inspect it rather than overwrite.')
        unpack(artifact('lima'),STATE/'runtime')
        unpack(artifact('helm-darwin'),STATE/'tools')
        return
    if args.action == 'start':
        no_encode()
        if not LIMA.exists(): sys.exit('Install the approved pinned runtime first.')
        # Dedicated LIMA_HOME prevents inherited mounts or global Lima overrides.
        if (STATE/'lima/_config').exists(): sys.exit('Inspect existing Lima global overrides before starting.')
        if (STATE/'lima/primary').exists():
            sys.exit('Instance already exists; use status and review before resuming.')
        run([LIMA,'start','--name=primary','--tty=false',ROOT/'lima/primary.yaml']); return
    if args.action == 'bootstrap':
        # Refuse upgrades and replacements. A failed partial bootstrap needs inspection.
        guest('test','!','-e','/usr/local/bin/k3s')
        binary=artifact('k3s')
        guest('sudo','mkdir','-p','/etc/rancher/k3s')
        put(binary,'/usr/local/bin/k3s'); guest('sudo','chmod','0755','/usr/local/bin/k3s')
        put(ROOT/'k3s/config.yaml','/etc/rancher/k3s/config.yaml')
        put(ROOT/'k3s/k3s.service','/etc/systemd/system/k3s.service')
        guest('sudo','modprobe','overlay'); guest('sudo','modprobe','br_netfilter')
        guest('sudo','sysctl','-w','net.ipv4.ip_forward=1')
        guest('sudo','systemctl','daemon-reload'); guest('sudo','systemctl','enable','--now','k3s')
        kubectl('wait','--for=condition=Ready','node/dots-primary','--timeout=180s'); return
    if args.action in {'argocd','openbao','eso'}:
        apply(ROOT/'bootstrap/namespaces.yaml')
        if args.action == 'openbao':
            # Values must already exist via the separate owner-controlled TLS procedure.
            kubectl('-n','openbao','get','secret','openbao-tls',stdout=subprocess.DEVNULL)
        name='external-secrets' if args.action=='eso' else args.action
        namespace='homarr' if args.action=='eso' else args.action
        kubectl('apply','--server-side','-f','-',input=render(name,namespace))
        if args.action=='argocd':
            kubectl('wait','--for=condition=Established','crd/applications.argoproj.io','crd/appprojects.argoproj.io','--timeout=120s')
            apply(ROOT/'bootstrap/argocd-rbac.yaml')
        return
    if args.action == 'gitops':
        kubectl('-n','argocd','get','secret','primary-repo',stdout=subprocess.DEVNULL)
        kubectl('-n','homarr','get','secret','homarr-db-encryption',stdout=subprocess.DEVNULL)
        for path in [ROOT/'gitops/project.yaml',ROOT/'gitops/openbao.yaml',ROOT/'gitops/homarr.yaml']: apply(path)
        print('Applications created with automatic synchronization DISABLED. Review diffs and synchronize manually.'); return
    if args.action == 'enable-sync':
        if not approval.get('manualSyncAndRollbackVerified'):
            sys.exit('Manual sync and rollback evidence is required before automatic synchronization.')
        for name in ['primary-homarr','primary-openbao']:
            kubectl('-n','argocd','patch','application',name,'--type=merge','-p',json.dumps({'spec':{'syncPolicy':{'automated':{'enabled':True,'prune':False,'selfHeal':True}}}}))
        return
    if args.action == 'rollback':
        # Disable admission first; on failure stop for inspection, never delete storage.
        for name in ['primary-homarr','primary-openbao']:
            kubectl('-n','argocd','patch','application',name,'--type=merge','-p','{"spec":{"syncPolicy":{"automated":{"enabled":false}}}}')
        run([LIMA,'stop','primary']); print('VM stopped; all disks, PVCs, keys and histories retained.')

if __name__=='__main__': main()
